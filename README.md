# agent-sync

[![CI](https://github.com/appvillis-com/agent-sync/actions/workflows/validate.yml/badge.svg)](https://github.com/appvillis-com/agent-sync/actions/workflows/validate.yml)
[![npm](https://img.shields.io/npm/v/agent-sync)](https://www.npmjs.com/package/agent-sync)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Several coding agents, one repository, no collisions.**

When more than one agent works a project at the same time, the coordination
substrate most teams already have — a decisions log, a roadmap, a board, per-repo
task files — stops being enough. Every one of those is a file edited by hand. That
works for people taking turns and fails for agents working at once:

| What goes wrong | Why |
|---|---|
| Two agents mint the same decision id | "Next free id" is a line in a file; reading it is not reserving it |
| A claim blocks a task forever | A role name is not a holder, and it has no expiry |
| Two agents start the same task | Git shows what was committed, never what is in flight |
| Merge conflicts on every shared register | Everyone writes the same three files |
| A cross-repo dependency is never noticed | Filing one notifies nobody |

`agent-sync` closes exactly those, and nothing else.

## The idea

> **Git is the record plane. The cloud is the coordination plane.**

A fact that must survive is written to git first and referenced from the cloud. A
fact about *who is doing what right now* lives in the cloud and expires. No cloud
object is ever the only home of a durable fact, so your single-source-of-truth rules
stay intact.

Leases and id reservations are decided by **replaying one append-only log**. No
supported knowledge base offers compare-and-swap, so the protocol never asks for
one: append, read back, and let document order decide. Every agent replaying the
same log reaches the same answer.

## What you get

- **Leases with a TTL** — claim a task, renew automatically, steal an expired one.
  Stealing is visible in the log, never silent.
- **Race-free id reservation** — positional allocation over the log, so two agents
  cannot be handed one number.
- **A run journal** — what each run did, with commits, gate results and evidence.
- **A cross-repo signal feed** — `filed → accepted → delivered → closed`, so a
  producer learns a dependency was filed against them.
- **A generated board** — machine-written, commit-stamped, and it refuses to
  overwrite a page a human took over.
- **Enforcement hooks** for Claude Code that deny an edit to a guarded register file
  without a live lease.

## Install

```bash
npx agent-sync install
```

Claude Code gets the plugin; every other agent gets the skill through the
[skills CLI](https://github.com/vercel-labs/skills); the duplicate plain copy in
`~/.claude/skills/` is pruned, because that shadow silently serves a stale skill.

Or from GitHub, tracking `main`:

```bash
npx github:appvillis-com/agent-sync install
```

Claude Code only:

```bash
claude plugin marketplace add appvillis-com/agent-sync && claude plugin install agent-sync@agent-sync
```

## First run

**Initialisation is the first command, and it asks a question rather than guessing.**

```
/agent-sync init
```

The agent asks where coordination state should live — a knowledge cloud, or local
files — and, for the cloud, the instance URL. Then it writes:

- `.claude/agent-sync.json` — **shape**, committed: TTLs, guarded files, registers, gates;
- `.env.agent-sync` — **identity**, mode 600, added to `.gitignore`, with the token
  line left **empty**.

Creating the API token and pasting it into that line is your step, and it stays
yours: the tool never asks for a token in chat, never echoes one, and never passes
one as a command-line argument.

```bash
set -a && . ./.env.agent-sync && set +a
```

## Backends

The knowledge store is a **pluggable adapter** — six primitives, three declared
capabilities. Nothing about a specific vendor is baked in, and no instance address
ships in this repository.

| Backend | Lease authority | Notes |
|---|---|---|
| `outline` | yes | [Outline](https://www.getoutline.com), hosted or self-hosted. Server-side append gives a total order without compare-and-swap |
| `fs` | no — **degraded** | Local files. Real mutual exclusion between agents on one machine, none across machines. Every run is recorded `ungated` |

**A backend that cannot arbitrate says so.** When the adapter is not the lease
authority, `agent-sync` announces it, falls back to git-file leases, and marks runs
`ungated` — because a lease that is not actually exclusive is worse than none, and
the other agent has stopped checking.

## Requires task-pipeline

`agent-sync` supplies stages; it does not define them. It binds to
[task-pipeline](https://github.com/ssheleg/task-pipeline)'s stages 0, 3, 4, 5, 9
and 10. If task-pipeline is absent it prints one line and stops rather than
improvising a substitute flow:

```bash
npx sshlg-skills install
```

## What ships

One skill, `agent-sync`, with its contracts beside it:

| File | Read it when |
|---|---|
| `references/adapter-contract.md` | adding or auditing a knowledge backend |
| `references/lease-protocol.md` | changing acquisition, expiry, stealing or id allocation |
| `references/backend-outline.md` | making any Outline API call, or debugging one |
| `references/backend-fs.md` | running without a cloud backend, or explaining degraded mode |
| `references/pipeline-binding.md` | wiring `pipeline.json`, or adding a stage hook |
| `references/hooks.md` | installing, debugging or removing the Claude Code hooks |

Plus `scripts/agent_sync.py` (stdlib only), the four hook scripts, and
`agent-sync.schema.json` for the project config.

## Limits, stated plainly

- **Hooks are Claude Code only.** On Cursor, Codex and the rest there is no
  `PreToolUse`, so nothing blocks a guarded edit; the same checks run as a
  self-check and the run is recorded `ungated`. Read the board's column rather than
  assuming.
- **Ordering, not clocks.** Document order decides who holds a lease; timestamps
  only expire one. Agents' clocks differ and the protocol does not depend on them.
- **A reserved id that never reaches git is reported, not reclaimed.** A
  half-written decision on a branch is not an unused number.

## Verify a change offline

```bash
python3 test/validate.py
python3 test/validate.py --self-test
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Security reports: [SECURITY.md](SECURITY.md).

## License

MIT © Appvillis
