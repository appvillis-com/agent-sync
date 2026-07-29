# Changelog

All notable changes to this project are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## 1.0.0 — 2026-07-29

A full audit of the running system against its own promises. Three surfaces were
configured and unimplemented, and the central safety claim was false. All measured, none
inferred.

### Fixed — the lease was not exclusive
- **A shared append-only document loses writes.** Twelve concurrent appends to one Outline
  document returned twelve successes and left **three** lines: `editMode: append` reads,
  appends and writes back, so simultaneous writers clobber each other and each is told it
  succeeded. A lease decided on that can be held by two runs, each with proof.
- **Sharding per writer fixes the loss and breaks the decision.** 12/12 land, but without
  compare-and-swap nothing can answer "is a contender still writing?", so eight parallel
  processes each read only their own shard and **eight won one key**. A three-second settle
  window took it to five. It cannot reach one.
- **Exclusion now comes from `os.open(O_EXCL)`** — an atomic create is the decision, and the
  plane carries the record. Twelve parallel processes, **one winner, eleven losers all naming
  the same holder**. Publishing to the plane can fail without affecting correctness, so it is
  reported rather than raised.
- The limit is stated instead of implied: a lock file is exclusive between processes on one
  filesystem, advisory across machines. `exclusiveLease` joins the capability set and defaults
  to false, because declaring it without compare-and-swap is the most damaging lie an adapter
  can tell.

### Fixed — configured but not implemented
- **`claimTags`** appeared in the schema, in every config and in DEC-0216, and was read
  nowhere. `status` now reports where a held lease and the git claim tag disagree — and says
  plainly when the configured mapping *cannot be verified at all*, which is the case in the
  project that shipped it. The tool verifies; the run writes. A process that rewrites a shared
  registry unattended from a hook is the mechanism that clobbers other agents' work.
- **Mirror drift detection** was asserted in a docstring beside code that never checked it.
  `status` now reports pages whose stamped commit is not HEAD.
- Transient `5xx` from the knowledge base are retried like `429`; twelve concurrent document
  creations had been failing outright.

## 0.6.0 — 2026-07-29

### Fixed
- **The mirror was configured, documented and not implemented.** `mirror.enabled` and
  `mirror.sources` existed in the schema, the config and the generated setup snapshot, and
  nothing read them — a surface with nothing behind it, which is the failure mode that reads as
  finished. `board --mirror` now renders each configured document into the plane, stamped with
  the commit it was made from, refusing any page whose generated marker a human removed. A cap
  on the number of files is reported rather than applied silently: a quiet truncation reads as
  "everything is mirrored" when it is not.

## 0.5.0 — 2026-07-29

### Added
- **`adopt`** — inspect an existing project and *propose* a configuration. Adoption is where a
  coordination tool most easily starts lying: guess a register wrong and every later check is
  confidently about the wrong file. So it reads the repository, prints what it found, prints the
  decisions it **refuses to make for you** (a registry file carrying ids with no "next free id"
  line cannot have allocation reserved safely), and writes nothing. In a submodule it proposes no
  registers at all, because decisions belong to the parent repository.

## 0.4.0 — 2026-07-29

Found by simulating three agents working three repositories at once, entered from one
umbrella — the arrangement this tool is for. Every defect below was invisible from inside
a single checkout.

### Fixed
- **Every submodule agent ran isolated, in degraded mode, seeing nobody.** A submodule is
  its own git repository, so the project root is the submodule and `.env.agent-sync` — which
  lives in the superproject — was never found. Three agents entered from one umbrella and
  coordinated with nothing, each reporting `ungated` while believing it was configured. The
  env file is now located from the superproject and parent directories, so one credential
  file serves the whole tree.
- **A submodule's `reconcile` reported every umbrella decision as an orphan.** The as-built
  log is shared by all repositories; id registers are per-repository, and a service repo
  declares none because decisions live in the parent. Comparing the shared log against a
  local register produced a wall of false findings — the loudest possible way to teach
  people to ignore a check. Register checks are now scoped to what the checkout can judge,
  and say plainly when they are not evaluated here.
- **Regenerating the board from a submodule replaced the shared view with a narrower one.**
  Four repositories wrote one page; last writer won. The board now carries only facts true
  from every checkout, and repo-local findings moved to their own generated page.

### Added
- **`setup`** writes a generated snapshot of how *this* project is wired — registers,
  guarded files, gates, the two documentation sources, what is written where, and what is
  never deleted. Commit it and link it from the project's agent instructions so every agent
  reads the same description of the pipeline instead of inferring it from behaviour. It is
  generated rather than hand-written, because a hand-written description of a configuration
  drifts from it, which is the exact failure this tool exists to surface.
- **The lifetime and deletion protocol is now stated.** Nothing in a log is edited or
  deleted: the logs are replayed in order, so removing a line silently rewrites a
  conclusion other agents already acted on. Correct by appending. Generated pages are the
  narrow exception, and one that has lost its marker is refused, not overwritten.

## 0.3.3 — 2026-07-29

### Fixed
- **The enforcement hook ran in a different mode from the agent it was guarding.** A hook is
  spawned with a bare environment and never inherits the operator's
  `set -a && . ./.env.agent-sync`, so every hook silently fell back to the `fs` backend while
  the agent's own commands used the cloud. Consequences, both invisible: the guard **denied
  edits whose lease was properly held**, and it recorded runs as `ungated` while the agent had
  been told `gated`. The gate was structurally broken in exactly the scenario it exists for.
  The tool now loads `.env.agent-sync` itself — the path is deterministic, so correctness must
  not depend on how the process was invoked. An already-set variable still wins.

## 0.3.2 — 2026-07-29

### Fixed
- **`reconcile` demanded an as-built record for an id nobody had taken.** The id scraper
  matched every `DEC-\d+` token in a register, including the "Next free ID" pointer — the one
  number that by definition is *not* allocated. Two symptoms, one cause: a permanent false
  finding on the unallocated id, and a baseline stamped one higher than reality, which quietly
  excused the newest real decision from ever being checked. The register's own
  `nextFreeIdPattern` now identifies that pointer and subtracts it.
  Found by running the new duty against this project rather than by reading the code.

## 0.3.1 — 2026-07-29

### Fixed
- **The guard blocked the lease holder.** A hook runs with `CLAUDE_SESSION_ID` in its
  environment and a plain shell command usually does not, so the run id was derived two
  different ways for one session: the agent acquired a lease as `r-f49d900b9` and was then
  denied by its own `PreToolUse` guard as `r-5ef2554fe611`. The primary flow — acquire,
  then edit a guarded register — could not complete. Found when the gate refused the very
  commit that was writing its decision record.
  The marker file is now authoritative for the checkout, with the session name recorded
  beside it: a different session rotates the id, while a run that merely *learns* its
  session name adopts it instead of rotating.

## 0.3.0 — 2026-07-29

### Fixed
- **Three of the four hooks were dead on macOS.** They called `timeout`, which is GNU
  coreutils and absent from a stock macOS, so `session-start`, `renew` and `session-end`
  all died with "command not found" — leases were never renewed and never released
  there, the exact abandoned-lease failure this tool exists to prevent. A portable
  `run_limited` helper now uses `timeout`, then `gtimeout`, then a plain-bash watchdog.
  `guard` was unaffected, so enforcement itself never lapsed.

### Added
- **The as-built record, and the duty to reconcile it against git.** Git documents say
  how it *should* be — written before the code, often without it. `70 As-built` says how
  it *actually is*, derived from what agents really wrote. Two source-of-truths answering
  two different questions; the gap between them is the finding, not a defect. New
  `record` and `reconcile` commands, wired into the pipeline's docs-study stage (resolve
  divergence before writing code) and docs stage (update both sides, then re-check).
- **`reconcile` is a ratchet, not a flood.** `--set-baseline` stamps today's ids as a
  counted backlog that may only shrink; ids written after it must carry an as-built
  record. A check that fails on all of history is a check that gets switched off.
- **Awareness names the repository.** Work spans several repos entered from one umbrella,
  and "r-alpha holds ASC-072" is only actionable once you know which checkout it is in.
- **`npx agent-sync update`** — updates every channel and prunes the shadow copy in the
  same step, because `npx skills update --global` recreates it on its own even when
  claude-code was never targeted.
- **`install.sh`** POSIX fallback and a **Cursor rule** (`cursor/rules/agent-sync.mdc`,
  no relative links, since the file gets copied into foreign projects).

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
