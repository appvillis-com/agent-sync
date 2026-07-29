---
name: agent-sync
description: "Use when several coding agents work one repository at the same time and must not collide - claiming a task, reserving the next decision/question/ticket id, journaling a run, filing or answering a cross-repo dependency, or regenerating the shared board. Triggers - 'claim this task' / 'возьми задачу', 'who is working on X' / 'кто сейчас делает X', 'reserve an id' / 'зарезервируй id', 'sync the board' / 'обнови доску', 'set up agent coordination' / 'настрой координацию агентов', /agent-sync. Use it BEFORE editing any shared registry file (decisions, open questions, roadmap, workstreams, dependencies) in a project that has .claude/agent-sync.json, even when the user never mentions coordination - an unclaimed edit to those files is how two agents overwrite each other."
compatibility: "Requires the task-pipeline skill for its stages (npx sshlg-skills install). Needs python3 3.9+ and curl. The knowledge backend is configured per project; with none configured it degrades to git-file leases. Enforcement hooks are Claude Code only - on other agents the same checks run as a self-check."
license: MIT
metadata:
  version: "0.1.0"
  author: appvillis-com
---

# agent-sync — one project, many agents, no collisions

Two planes, and one rule between them:

> **Git is the record plane. The cloud is the coordination plane.**
> A fact that must survive is written to git first and referenced from the cloud.
> A fact about *who is doing what right now* lives in the cloud and expires.

No cloud object is ever the only home of a durable fact. Everything below exists to
keep that true while several agents write at once.

## Three traps — read these before anything else

**1. No backend offers compare-and-swap.** Outline's `documents.update` has
`editMode: append|replace|prepend|patch` and **no `lastRevision`**. So a mutable
table of claims is a race: two agents read it, both write, the second wins and the
first believes it holds a lease it lost. Never model coordination state as a
document you rewrite. Append, then read back, and let document order decide.

**2. `atomicAppend: false` means you are NOT the lease authority.** If the
configured adapter cannot append server-side, say so out loud, fall back to
git-file leases, and mark the run `ungated`. A pretended lease is worse than no
lease, because the other agent trusts it.

**3. Hooks exist only in Claude Code.** On Cursor, Codex and every other agent the
skills CLI serves, there is no `PreToolUse` and nothing blocks a guarded edit. Run
`guard` yourself before touching a guarded file and record the run as `ungated`.
Do not describe the project as protected when it is not.

## First command in any project: `init`

**Never run anything else against an uninitialised project.** `init` is where the
storage question gets asked and answered, once, and written down.

**Ask the operator these two things in chat — do not guess, do not pick a default:**

1. **Where should coordination state live?**
   - a knowledge cloud (`outline`) — real leases, shared across machines;
   - or local files (`fs`) — no credentials, but **degraded**: not the lease
     authority, every run recorded `ungated`.
2. **If cloud: the instance URL.** The URL is configuration, not a secret, so you
   may write it. The **token is not** — you never ask for it in chat, never read it
   back, and never place it yourself.

Then run it with their answers:

```bash
python3 "$SKILL_DIR/scripts/agent_sync.py" init --backend outline --url https://<their-instance>
python3 "$SKILL_DIR/scripts/agent_sync.py" init --backend fs
```

`init` writes `.claude/agent-sync.json` (shape, committed), writes
`.env.agent-sync` with the keys and an **empty** token line (identity, mode 600),
adds `.env.agent-sync` and `.agent-sync/` to `.gitignore`, and then prints exactly
what the operator must do themselves — create the token in their own instance and
paste it into that one line. It never overwrites an existing config or env file
without `--force`.

Relay those closing instructions to the operator verbatim. Getting the token into
the file is their step, and the design depends on it staying theirs.

## Then, before every session

```bash
python3 "$SKILL_DIR/scripts/agent_sync.py" status
```

Idempotent. Inspects, repairs what is missing, prints a status block, names exactly
ONE next action.

- No credentials in the environment → degraded mode, reported, and it continues.
  Missing credentials are not an error, they are a smaller mode.
- `task-pipeline` absent → it prints the install line and stops. Do not improvise a
  substitute flow; without those stages there is nothing to bind to.

```bash
npx sshlg-skills install
```

## The commands

| Command | Does |
|---|---|
| `init` | **Run first.** Ask where state lives, write config + gitignored env file, print the operator's step |
| `status` | Inspect, repair, report, name one next action |
| `bootstrap` | Create the cloud container and print the id to paste into the env file |
| `acquire <KEY>` | Take the lease on a task id. Prints `won` or `lost <holder>` |
| `renew <KEY>` | Extend the lease. The `PostToolUse` hook does this for you |
| `release <KEY>` | Give the lease back. Always do this, including on failure |
| `reserve <REG>` | Reserve the next id in a register (`DEC`, `OQ`, `DEP`, …). Prints the id |
| `release-id <REG> <ID>` | Return an id you did not end up writing to git |
| `journal <text>` | Append one line to this run's journal |
| `signal <DEP-ID> <state>` | Move a cross-repo dependency: `filed`/`accepted`/`delivered`/`closed`/`refused` |
| `guard <path>` | Answer whether this run may write that path. Exit 0 = yes, 2 = no |
| `board` | Regenerate the read-only board and the mirror from git |
| `whoami` | Print this run's id and its held leases |

`$SKILL_DIR` is this skill's own directory. Every command reads
`.claude/agent-sync.json` from the project root and needs no arguments beyond those
listed.

## Claiming — the shape that matters

```
acquire → do the work → release
```

Never skip `release`, including when the work failed: an abandoned lease blocks the
task until its TTL expires, and the next agent cannot tell "in progress" from
"crashed an hour ago". A lease is a promise to come back.

**The lease is not the claim.** The lease says who holds the task *now* and
expires; the durable claim is the tag in git — `[name]` in the directions board,
`todo (claimed: <role>)` in a service roadmap. `acquire` writes that tag through in
the same run and `release` clears it, so one fact keeps one home. Do not invent a
third place to record who owns a task.

**Read `references/lease-protocol.md` before changing anything about acquisition,
expiry, stealing or id allocation** — it carries the exact line grammar and the
replay rules that make two agents reach the same answer.

## Guarded files

The project config lists registry files that several agents write. Before editing
one:

```bash
python3 "$SKILL_DIR/scripts/agent_sync.py" guard docs/DECISIONS.md
```

Exit 2 means another run holds it. Do not edit anyway and do not "just fix one
line" — those files are exactly where a lost write costs the most, because a
clobbered decision looks like a decision.

In Claude Code the `PreToolUse` hook runs this for you and denies the edit. On
other agents nothing does; run it yourself.

## Reserving an id

Reading "Next free ID" from a file is not reserving it. Two agents read `DEC-0216`
and both write `DEC-0216`.

```bash
python3 "$SKILL_DIR/scripts/agent_sync.py" reserve DEC   # → DEC-0216
```

Allocation is positional over the append log, so every agent computes the same
answer without trusting anyone's arithmetic. If you reserve an id and do not write
it to git, `release-id` it — otherwise the number is a hole that the board reports
as a leak, and nobody can tell a hole from work in a branch.

## Binding to task-pipeline

This skill supplies stages; it does not define them. Stage names are
`task-pipeline`'s own.

| Stage | What to do here |
|---|---|
| 0 Intake grill | Add the cloud KB and the board to the harvest's source ledger; `acquire` **before** the brief is committed |
| 2 Brainstorm | `journal`; warn if a live run holds an overlapping key |
| 3 Spec | `reserve` every id before writing it to git |
| 4 Plan | Register file ownership for the plan's parallel groups |
| 5 Dev | Lease renews itself; own the submodule-commit → parent-gitlink bump |
| 6 Tests · 7 Lint · 8 Post-deploy | `journal` each gate result |
| 9 Docs + wiki | The main write point — `signal` the dependency flips, then `board` |
| 10 Acceptance | `release` every lease, write the durable claim tag through to done |

**Read `references/pipeline-binding.md` when wiring `pipeline.json`** — it holds the
`skills[]` entries and the gate expressions.

## Configuration

Two files, and the split between them is the whole security model.

**`.claude/agent-sync.json`** — *shape*, committed: which backend, TTLs, which files
are guarded, which registers exist, which gates to run.

**`.env.agent-sync`** — *identity*, created by `init`, mode 600, gitignored:

```
AGENT_SYNC_BACKEND=outline
AGENT_SYNC_OUTLINE_URL=https://<instance>
AGENT_SYNC_OUTLINE_TOKEN=          # the operator fills this line, nobody else
AGENT_SYNC_OUTLINE_COLLECTION=     # printed by `bootstrap`
```

Load it before running agents:

```bash
set -a && . ./.env.agent-sync && set +a
```

Never write a host name or a token into the config, a test, an example or a commit.
Do not handle a token value, echo it, or pass it as a command-line argument. If the
operator offers one in chat, tell them to put it in that file instead.

**A submodule's config declares only its own registers.** Cross-repository facts
belong to the parent repository. A service repo that lists the parent's decision
register in its config is a configuration defect.

## Backends

| Backend | `atomicAppend` | Read when |
|---|---|---|
| `outline` | yes | `references/backend-outline.md` — before touching any Outline call |
| `fs` | no (degraded) | `references/backend-fs.md` — the git-file fallback and its limits |

**Read `references/adapter-contract.md` before adding a backend.** Six primitives,
three capability flags, and a degradation path that must be honest.

## Generated objects

The board and the mirror are machine-written. Their first line is

```
<!-- agent-sync:generated source=<repo>@<sha> at=<iso8601> — edit in git, not here -->
```

A write to an object missing that marker is refused, not forced. If a human took
over a generated page, report it and stop; do not restore your version over theirs.

The mirror is a **rendering** of git, stamped with the source commit. It has no
authority. When its stamp and `HEAD` disagree, the board gate fails — that is
drift, not a formatting problem.

## Non-negotiables

- Append, read back, then act. Never rewrite a coordination document.
- `release` what you `acquire`, on every path including failure.
- Credentials never reach `argv`, a log line, or the repository.
- Degrade out loud. `ungated` is an acceptable state; a false claim of enforcement is not.
- Everything the cloud holds about a durable fact is a link to git, never a substitute.

## References

Each file is loaded on its own trigger, not by default.

| File | Read it when |
|---|---|
| `references/adapter-contract.md` | adding or auditing a knowledge backend |
| `references/lease-protocol.md` | changing acquisition, expiry, stealing or id allocation |
| `references/backend-outline.md` | making any Outline API call, or debugging one |
| `references/backend-fs.md` | running without a cloud backend, or explaining degraded mode |
| `references/pipeline-binding.md` | wiring `pipeline.json`, or adding a stage hook |
| `references/hooks.md` | installing, debugging or removing the Claude Code hooks |

If this copy arrived without `references/`, fetch them from
`https://raw.githubusercontent.com/appvillis-com/agent-sync/main/plugins/agent-sync/skills/agent-sync/references/<file>`.
