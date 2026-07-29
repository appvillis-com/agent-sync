# Changelog

All notable changes to this project are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## 0.2.0 — 2026-07-29

Coordination is not only mutual exclusion. An audit against the stated purpose — *agents
see what each other are doing and pick up important changes in time* — found the tool
enforced exclusion and delivered neither half of the awareness.

### Fixed
- **`status` shows what other runs are doing.** It reported only the caller's own leases,
  so an agent learned a task was taken and nothing about who held it or what they were
  touching. A lease you cannot see makes you blocked; a lease you can see makes you
  coordinated.
- **Cross-repo signals were write-only.** `signal` appended and nothing ever read the log,
  so a producer was still never told a dependency had been filed against them — the exact
  failure the feature exists to prevent. `status` now surfaces what landed since this run
  last looked, watermarked per run so it stays quiet until something actually changes.
- **The board renders recent signals** alongside live leases.

### Notes
- Verified with three concurrent runs across two repositories: an agent working inside a
  submodule alone sees the leases and signals of agents in the parent repository, because
  both read one coordination plane.

## 0.1.0 — 2026-07-29

First release.

### Added
- **Lease authority with TTL** — `acquire` / `renew` / `release`, decided by replaying
  one append-only log. Document order is authoritative; timestamps only expire a lease,
  because agents' clocks differ and the protocol must not depend on them.
- **Race-free id reservation** — positional allocation over the same log, so two agents
  cannot be handed one number. An id reserved and never written to git is reported as a
  leak rather than silently reclaimed.
- **Pluggable adapter contract** — six primitives, three declared capabilities
  (`atomicAppend`, `totalOrderRead`, `search`), and a mandatory honest-degradation path:
  a backend that cannot arbitrate exclusively must refuse lease authority and say so.
- **Backends** — `outline` (hosted or self-hosted; server-side append gives a total order
  without compare-and-swap) and `fs` (local, degraded, `ungated`).
- **Run journal and cross-repo signal feed** — `filed → accepted → delivered → closed`,
  so a producer learns a dependency was filed against them.
- **Generated board** — commit-stamped, and it refuses to overwrite a page that lacks the
  generated marker, so a page a human took over is reported instead of clobbered.
- **Claude Code hooks** — `SessionStart`, `PreToolUse` (deny a guarded edit or a commit
  staging one without a live lease), throttled `PostToolUse` renew, `SessionEnd` release.
  The guard exits 2 on its own internal failures, because any other code fails open.
- **`init` as the first command** — it asks where coordination state lives instead of
  guessing, writes committed shape and a gitignored mode-600 env file, and leaves the
  token line empty for the operator to fill.
- **Validator with a negative self-test**, plus CI.

### Verified against a live instance
Built and then exercised end to end against a real Outline deployment, which surfaced three
defects the unit-level work had not:
- **Markdown normalisation.** The store rewrites a `- ` bullet to `* `, so the log parser now
  emits `- ` and accepts `-`/`*`/`+`. Anchoring to the character written rejected every line
  the server returned.
- **A silent pre-filter hid malformed lines from the counter meant to expose them**, so the
  unparseable ratio read 0% while nothing parsed. Anything entry-shaped now reaches the pattern
  and is counted.
- **An unreadable log reported as a lost race.** `acquire` now raises above a 2% unparseable
  ratio rather than naming a holder who does not exist.
- HTTP error bodies are surfaced instead of dropped — a bare `400` cost a debugging round when
  the response said `collectionId: Invalid UUID`.
- The collection may be given as a UUID, a `urlId`, or the whole `name-urlId` slug from the
  address bar, because that is what a person actually copies.

### Notes
- Hooks exist only in Claude Code. Elsewhere the same checks run as a self-check and the
  run is recorded `ungated` — a documented limit, surfaced rather than hidden.
- Requires [task-pipeline](https://github.com/ssheleg/task-pipeline) for its stages.
