---
name: agent-sync
description: "Use when several coding agents work one repository at the same time and must not collide - claiming a task, reserving the next decision/question/ticket id, journaling a run, filing or answering a cross-repo dependency, or regenerating the shared board. Triggers - 'claim this task' / 'возьми задачу', 'who is working on X' / 'кто сейчас делает X', 'reserve an id' / 'зарезервируй id', 'sync the board' / 'обнови доску', 'set up agent coordination' / 'настрой координацию агентов', /agent-sync. Use it BEFORE editing any shared registry file (decisions, open questions, roadmap, workstreams, dependencies) in a project that has .claude/agent-sync.json, even when the user never mentions coordination - an unclaimed edit to those files is how two agents overwrite each other."
compatibility: "Requires the task-pipeline skill for its stages (npx sshlg-skills install). Needs python3 3.9+ (stdlib only, HTTP included - nothing to pip install) and bash for the hooks. The knowledge backend is configured per project; with none configured it degrades to git-file leases. Enforcement hooks are Claude Code only - on other agents the same checks run as a self-check."
license: MIT
metadata:
  version: "1.0.0"
  author: appvillis-com
---

# agent-sync — one project, many agents, no collisions

Two planes, and one rule between them:

> **Git is the record plane. The cloud is the coordination plane.**
> A fact that must survive is written to git first and referenced from the cloud.
> A fact about *who is doing what right now* lives in the cloud and expires.

No cloud object is ever the only home of a durable fact. Everything below exists to
keep that true while several agents write at once.

## Four traps — read these before anything else

**1. The knowledge base cannot arbitrate. Exclusion comes from an atomic file
create.** Measured, not assumed: twelve concurrent appends to one Outline document
returned twelve successes and left **three** lines — `editMode: append` reads, appends
and writes back, so simultaneous writers clobber each other and every one is told it
succeeded. Sharding per writer stops the loss, and then breaks the *decision*: with no
compare-and-swap there is no way to know a contender is still writing, so eight
processes each read only their own shard and **eight of them won one key**. No settle
window closes that. `O_EXCL` does: one winner out of twelve, every loser naming the
same holder. The plane still carries the record — it just never decides.

**2. A lease is exclusive on one machine and advisory across machines.** The lock file
is a real mutex between processes sharing a filesystem, which is how these agents
actually run. Two machines have two filesystems and therefore two locks. Say
`ungated`/advisory out loud where it applies — a pretended lease is worse than no
lease, because the other agent stops checking.

**3. Hooks exist only in Claude Code.** On Cursor, Codex and every other agent the
skills CLI serves, there is no `PreToolUse` and nothing blocks a guarded edit. Run
`guard` yourself before touching a guarded file and record the run as `ungated`.
Do not describe the project as protected when it is not.

**4. The store rewrites what you wrote — parse liberally, and never call an
unreadable log a lost race.** Outline normalises markdown on the way in: a `- `
bullet comes back as `* `. A parser anchored to the character you emitted then
rejects every line the server returns, and the caller is told **`lost`** when the
truth is *the log could not be read*. That is a lie pointing at a holder who does
not exist. Emit `- `, accept `-`/`*`/`+`, count anything entry-shaped that fails to
parse, and **fail loudly** once more than 2% is unparseable. Beware the silent
pre-filter especially: a `continue` before the regex hides bad lines from the very
counter meant to expose them.

## Bringing this into an existing project

Run `adopt` before `init`. It reads the repository and prints what it found — id
registers, registry files, gates — plus the decisions it **refuses to make for you**,
then proposes a config. It writes nothing.

```bash
python3 "$SKILL_DIR/scripts/agent_sync.py" adopt
```

Confirm the registers and guarded files with the operator before writing them. A
register pointed at the wrong file makes every later check confidently wrong, and a
guarded list that misses a shared file leaves the one place collisions actually happen
unprotected. In a submodule it declares no registers at all: decisions belong to the
parent repository.

Then: `init` → paste the approved config → `reconcile --set-baseline` → `setup` →
commit the snapshot and link it from the project's agent instructions.

## First command in a project: `init`

**Never run anything else against an uninitialised project.** `init` is where the
storage question gets asked and answered, once, and written down.

**Ask the operator these two things in chat — do not guess, do not pick a default:**

1. **Where should coordination state live?**
   - a knowledge cloud (`outline`) — the shared record, awareness and board across
     machines. **It does not decide leases**; nothing in it can (trap 1);
   - or local files (`fs`) — no credentials, no shared awareness, every run `ungated`.

   Either way the lease itself is an atomic local lock, exclusive between processes on
   one filesystem and advisory beyond it.
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

**Read the two awareness sections it prints — they are the point, not decoration.**

- **Other runs working this project right now.** Who holds what, this minute. Do not
  take those on, and do not "just look at" the files they cover. A lease you cannot
  see makes you blocked; a lease you can see makes you coordinated.
- **New since you last looked.** Cross-repo dependency moves that landed while you
  were away. A dependency that moved may unblock what you planned — or invalidate it.
  This list is watermarked per run, so it stays quiet until something actually
  changes; when it speaks, it matters.

An agent that skips this block will re-derive work someone else is doing and act on a
dependency state that changed an hour ago.

What else `status` decides for you:

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
| `record <text>` | Append what you **actually built** — `--decision DEC-…`, `--files a,b` |
| `reconcile` | Intent (git) vs as-built (cloud). `--set-baseline` once per project |
| `signal <DEP-ID> <state>` | Move a cross-repo dependency: `filed`/`accepted`/`delivered`/`closed`/`refused` |
| `guard <path>` | Answer whether this run may write that path. Exit 0 = yes, 2 = no |
| `board` | Regenerate the shared board and this repo's page. `--mirror` also renders the configured git docs into the plane |
| `whoami` | Print this run's id and its held leases |
| `setup` | Write the generated snapshot of how **this** project is wired, for agents to read |
| `adopt` | Inspect an existing project and **propose** a config — writes nothing |

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

## Nothing in a log is ever edited or deleted

The logs are **replayed in order**, so an edit silently rewrites a decision every other
agent has already acted on. Correction is by **appending** the correcting entry:

- a lease is **released**, never removed;
- a reserved id you did not use is returned with `release-id`, which appends;
- a wrong as-built entry is superseded by a later, correct one — both stay visible,
  and that history is the point.

Generated pages are the only exception: they are rewritten wholesale, and a page whose
first line lost its `agent-sync:generated` marker is **refused**, not overwritten.

## Two documentation sources, and the duty to reconcile them

Git docs answer **how it should be** — written before the code, often without it.
The as-built record answers **how it actually is** — derived from what agents really
wrote. Neither is a copy of the other, and neither outranks the other, because they
answer different questions. **The gap between them is the finding**, not a defect.

The duty runs at both ends of every task:

- **Before starting** (docs-study stage) — `reconcile`, then read both sides for the
  area you are about to touch. Resolve each divergence: the git doc is stale, or the
  as-built record is wrong, or they genuinely disagree and that is a decision to make.
  Building on an unresolved divergence means writing code against a system that does
  not exist.
- **After finishing** (docs stage) — `record` what you actually built, update the git
  documents that state intent, then `reconcile` again. A task that updated one side
  has left the next agent a divergence to find the hard way.

`reconcile` is mechanical and says so: it compares ids, commits and presence, and
refuses to judge whether the built thing matches what the document describes. That is
a reading, and it is yours.

Every project also carries a **generated snapshot** of its own wiring — registers,
guarded files, gates, what is written where and what is never deleted. Write it with
`setup`, commit it, and link it from the project's agent instructions, so every agent
reads the same description of the pipeline instead of inferring it from behaviour.

**Read `references/two-sources.md` before the first reconcile in a project**, and
whenever deciding which side a piece of documentation belongs on.

## Binding to task-pipeline

This skill supplies stages; it does not define them. Stage names are
`task-pipeline`'s own.

| Stage | What to do here |
|---|---|
| 0 Intake grill | Add the cloud KB and the board to the harvest's source ledger; `acquire` **before** the brief is committed |
| 1 Docs study | `reconcile` — study git docs **and** the as-built record, resolve every divergence before writing code |
| 2 Brainstorm | `journal`; warn if a live run holds an overlapping key |
| 3 Spec | `reserve` every id before writing it to git |
| 4 Plan | Register file ownership for the plan's parallel groups |
| 5 Dev | Lease renews itself; own the submodule-commit → parent-gitlink bump |
| 6 Tests · 7 Lint · 8 Post-deploy | `journal` each gate result |
| 9 Docs + wiki | The main write point — `record` what was built, update the git docs, `signal` the dependency flips, `reconcile` again, then `board` |
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
| `references/two-sources.md` | before the first reconcile, or when deciding where a document belongs |

If this copy arrived without `references/`, fetch them from
`https://raw.githubusercontent.com/appvillis-com/agent-sync/main/plugins/agent-sync/skills/agent-sync/references/<file>`.
