# Changelog

All notable changes to this project are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## 1.3.1 — 2026-07-29

### The git lease was invisible to everything that reads a lease — fixed

Found in production, blocking real work three times in one session. In `git` lease mode `acquire`
won the lease by pushing `refs/agent-sync/leases/<key>` and stopped there, while `held()` — the one
function behind `whoami`, `status` and the **PreToolUse guard** — read `.agent-sync/leases/*.lock`,
which nothing in that path ever wrote. The result was the exact inversion of the tool's purpose:
`acquire` printed *won*, `whoami` printed *holds: nothing*, and the guard **denied the run that held
the lease**. Every guarded register was unwritable under the mode this tool recommends, and the only
way past it was to bypass the guard — which is the behaviour the guard exists to prevent.

The git ref remains the authority; it is what makes exclusion hold across machines. What was missing
is that the winner now leaves a local note, so the local question — *does this run hold that key?* —
is answered locally instead of putting a network round-trip in front of every Edit. `release`
already removed that note, which is why only one half of the loop was ever written.

**Why it shipped:** the lease-visibility assertion existed only for the local mode. `test/validate.py`
now runs acquire → `whoami` → `guard` → release against **both** modes; against 1.3.0 it fails with
the two symptoms above, which is the point of adding it.

## 1.3.1 — 2026-07-29

### Ignoring the state directory does nothing once git is tracking it

Found in the project this plugin was built for: `.agent-sync/` was gitignored **and committed**,
because the files went in before the rule existed. Consequences, all of them silent:

- every tool call rewrites `last-renew`, so all three repositories were permanently dirty and no
  run could ever report itself finished
- `run-id` is the checkout's **agent identity**. Committed, it reaches every clone — two machines
  would then coordinate as one run, which is the failure 1.3.0 fixed at the other end

`init` now untracks the directory when it finds it tracked, and `check` reports it as a problem
rather than passing a project whose state is versioned. Probed: a repository with a committed
`.agent-sync/run-id` fails `check` with the exact removal command, and passes once it is untracked.

## 1.3.0 — 2026-07-29

### Two agents in one checkout were one identity — fixed

Found in production, in the case this plugin exists for: **two Claude sessions working the same
checkout shared a single run id**, so the lease could not separate them. A hook runs with
`CLAUDE_SESSION_ID` in its environment and a plain shell command does not, and the marker file held
one id per checkout — so the second session adopted whatever the first had stamped. Both acquired
as one run, both were guarded as one run, and `release` would take a lease the caller never
acquired. The failure is silent: `whoami` reports a lease, and it is somebody else's.

- the marker is now a **map** keyed by session, and migrates the old single-value file into it
- a plain shell has no session id, so the `SessionStart` hook stamps
  `.agent-sync/sessions/<CLI pid>` with the session it *does* know, and later commands find
  themselves by walking their own ancestry. Exact, and no command-line parsing: the throwaway
  shell every tool call runs in carries claude paths in its argv and defeated every heuristic
  aimed at the CLI binary
- stale stamps are removed when their process is gone, so the directory cannot grow
- where identity still cannot be established, the run says so rather than presenting a shared
  entry as separation

### `scaffold --full` — the architecture that keeps documentation linked, not merely present

`scaffold` seeded a decision register and an agent protocol. That is enough to be coordinated and
not enough to stay coherent: the things that rot are the links between documents, and nothing was
seeding the pieces that hold them — a question register that resolves into decisions, an index
nobody has to scan the register to use, one place for facts about two repositories, one definition
per entity with a checkable address, **and a gate**, because each of those decays silently.

`--full` adds `OPEN_QUESTIONS.md`, `INDEX.md`, `DEPENDENCIES.md`, `DATA_MODEL.md` (with the entity
register and the one-definition rule) and `scripts/check-docs.sh`, which fails on: an id cited and
never defined, a next-free-ID line that is not next, a relative link to a file that does not exist,
a `#anchor` that does not exist in the file it points at, and a decision with no index row. All
five probed against planted defects.

**A fresh scaffold passes its own gate.** The first version did not — it counted the template block
and the allocation line as real ids — and a project that starts red teaches everyone that the gate
is noise.

### `finish` — the gate expressions this plugin declares, executed

`references/pipeline-binding.md` has always listed *submodule pointers current* and *every lease
released* as gate expressions "verified by the coordinator, not by prose". Nothing ran them:
`check` validates the **setup** — config, registers, credentials, snapshot — and never looks at the
state of the repositories.

`finish` answers the other question, *is the work finished*:

- every submodule's recorded gitlink equals its HEAD. This is the failure it exists for and it is
  invisible from either side alone: the submodule is pushed, its CI is green, its roadmap says
  done, and a clone of the parent has the commit before the work
- every repository — parent included — is clean and pushed, with a detached submodule accepted
  only when its commit exists on some remote branch
- no lease left held, because a run that ends holding one blocks the next agent for the whole TTL
- `--gates` also runs the project's own declared gate commands

## 1.2.4 — 2026-07-29

### Fixed — the tool misreported its own version, and disagreed with itself about the lease
- **`VERSION` drifted a release behind.** The constant said `1.2.2` while every manifest
  said `1.2.3`, so each `status` and `adopt` header named the wrong version — the exact
  number the README tells an operator to compare when hunting a stale install channel.
  `check_version_sync()` read five manifests and not the script; `check_scripts_run()` ran
  `--version` only to prove the process starts, and threw the answer away. The constant is
  now part of the sync check, so this cannot drift silently again.
- **`gated` was decided by the record backend, which has not decided a lease since 1.0.0.**
  It read the adapter's `atomicAppend`/`totalOrderRead` capabilities, and both directions
  lied: `outline` with a local lock reported `gated` while exclusion was machine-local —
  the pretended lease the skill's own trap 2 warns about — and `fs` with git refs reported
  `ungated` while every lease was a genuine cross-machine compare-and-swap. It now derives
  from `leaseBackend`.
- **Six surfaces phrased the guarantee independently, and two called the knowledge base
  the "lease authority".** `status` said `lease authority: NO — degraded` for the same
  project where `check` said `exclusive on this machine` and `acquire` said something else
  again. One guarantee described three ways reads as three guarantees, and an operator acts
  on the weakest. The wording now lives in one table (`lease_guarantee()`), used by
  `status`, `acquire`, `check`, the board, the setup snapshot and `init`. `status` reports
  the record plane and the lease as the separate facts they are.

### Added
- **`test/validate.py` exercises the agreement**: for `leaseBackend` `local` and `git` it
  runs `status`, `acquire` and `check` against a throwaway repository (a real bare remote
  for `git`) and fails if any of them omits the guarantee, or if `status` still calls the
  record backend the lease authority. Verified red against 1.2.3, green after.

## 1.2.3 — 2026-07-29

### Fixed — the guard blocked commits in projects that never installed agent-sync
`_lib.sh` states the contract: *"Every hook is a no-op in a project that does not use
agent-sync, so installing the plugin globally changes nothing elsewhere."* `guard.sh` was
the one hook that never sourced `_lib.sh`, and it honored that contract on only one of its
two branches.

- **The `git commit` branch had no configuration check.** It ran `agent_sync.py guard` on
  every staged path; in an uninitialized project that command exits 2 with *"no
  `.claude/agent-sync.json` in this project"*, which the loop read as "this run holds no
  lease" — so every commit in every repo without agent-sync was blocked, with a message
  naming a lease the project could not possibly need. The single-file branch had the check
  all along, which is why the failure only ever surfaced on commits.
- `guard.sh` now sources `_lib.sh` and gates on `agent_sync_configured` like the other three
  hooks, so the check cannot drift apart from them again. The hand-rolled `AGENT_SYNC_PY`
  path and the duplicated `[ -f … ]` test are gone.
- The staged-path listing now runs against `${CLAUDE_PROJECT_DIR:-$PWD}`, the same directory
  the configuration check reads. Before, the two could point at different repositories.

### Added
- **`test/validate.py` exercises the no-op contract** instead of only checking syntax: every
  hook runs against a throwaway git repository that has a staged file and no
  `.claude/agent-sync.json`, and must exit 0. Verified red against the pre-fix `guard.sh` and
  green after — a `bash -n` pass could never have caught this.

## 1.2.2 — 2026-07-29

### Changed
- **The npm package is `@ssheleg/agent-sync`.** Unscoped `agent-sync` was rejected on publish
  with a 403: npm's name-similarity policy fires only on `PUT`, so `npm view` reporting E404
  ("free") predicts nothing — the collision was with an existing `agentsync`. Scoped names are
  exempt from that policy, which is the documented fix.
- **The command is still `agent-sync`.** A package's `bin` name is independent of its package
  name, so nothing about daily use changes; only the install line grows a scope.
- GitHub install (`npx github:appvillis-com/agent-sync`) and the Claude Code plugin are
  unaffected — the registry only ever bought the short name.

## 1.2.1 — 2026-07-29

### Fixed — documentation that contradicted the code
Compressing the skill surfaced three statements that measurement had already disproved and
that nobody had gone back to correct. This is the drift the tool exists to catch, in the
tool's own documentation.

- `lease-protocol.md` opened by declaring that *no backend offers compare-and-swap, so both
  leases and id reservations are decided by replaying one append-only log*. Half of that is
  still true — id allocation is positional over the log — and half has been false since
  1.0.0. It now separates the two mechanisms, because confusing them is how this went wrong
  twice.
- The same file still said the **run** writes the claim tag and the tool only verifies. As
  of 1.2.0 the tool writes it through.
- `backend-fs.md` described a "git-file lease" — commit the lock, push it, read the
  rejection — a design that was never built. Leases have never depended on which knowledge
  backend is configured, and the file now says so.

### Changed
- `SKILL.md` trimmed from 4779 to 4325 tokens (13% headroom under the 5000 cap), with the
  full measurement history left in `CHANGELOG.md` and `lease-protocol.md` where it belongs.
- `lease-protocol.md` gains the cross-machine section it was missing.

## 1.2.0 — 2026-07-29

### Added — the claim is written through to the roadmap again
Demoted to a check in 1.0.0 because an unattended process rewriting a shared registry is
the collision a lease exists to prevent. It is back, with that objection engineered out:

- **One row.** The single table row containing the task id as a whole word. Zero rows →
  nothing happens. Two or more → **refused**, with the reason. It never guesses.
- **One cell.** Only the configured cell changes; links, notes and every other column are
  untouched byte for byte. `cell` is 0-based, negative counts from the end.
- **Reversible.** The previous text is stored in `.agent-sync/claims.json` and restored
  verbatim on release — not a default, what was actually there. After acquire→release,
  `git diff` on the roadmap is **empty**.
- **Atomic.** Written to a temp file and moved into place, so a crash cannot leave the
  register half-edited.

Closing a task is still yours: the tool refuses to write `done` on your behalf, because a
status a machine sets is a status nobody checked. `references/roadmap.md` documents the
whole cycle — claiming, closing, re-planning, and what to do when the claim cannot be
written.

### Added — cross-machine leases
`leaseBackend: "git"` pushes a commit to `refs/agent-sync/leases/<key>`, and the remote's
non-fast-forward rejection **is** a compare-and-swap. Verified against a hosted remote
before being written: A created the ref, B pushed a different commit without force and was
rejected, the ref still held A. Then eight parallel processes against the real remote —
**one winner, seven losers all naming it**.

Expired leases are stolen with `--force-with-lease` against the exact object seen, so a
steal cannot clobber a holder who renewed in between. `local` remains the default and is
still exclusive between processes on one filesystem; `acquire` and `check` now say which
guarantee you actually have instead of implying the stronger one.

## 1.1.0 — 2026-07-29

The skill can now take **any** project from nothing to a validated setup on its own.

### Added
- **`check`** — validates the whole setup and refuses to call a broken one healthy. It fails
  on a register whose allocation pattern matches nothing, a guard glob that matches no file
  (a rule protecting nothing), a gate whose script is missing, a mirror source that is not
  there, empty credentials, a `.gitignore` that misses the env file — or that file being
  **tracked by git**, the one unrecoverable mistake here — a hand-edited or stale snapshot,
  **a snapshot no agent instruction file links**, and a register with no baseline. Every one
  of those failed for real during this tool's own adoption.
- **`scaffold`** — creates the documentation architecture where it is absent: a decision
  register with an allocation line and an `AGENTS.md` pointing at the generated snapshot. It
  never touches an existing file. A tool that rewrites a project's conventions on adoption is
  worse than one that does nothing.
- The snapshot is stamped with a **hash of the configuration** it describes, so staleness
  means the configuration moved on — not that a commit happened. Comparing commits was wrong
  at both boundaries: a snapshot is generated before the commit that carries it, and the
  config is usually added in that same commit, so the very first adoption always looked stale.

## 1.0.1 — 2026-07-29

### Fixed
- **A rate-limited knowledge base stopped the work, not just the record.** `journal`, `record`
  and `signal` raised when the store was unreachable or throttling, so a burst of shard creation
  could fail a run outright. The plane carries visibility, not correctness: publishing now
  reports the gap loudly and lets the caller continue. Swallowing it would hide a hole in the
  record; raising made an availability dependency out of a notebook.
- Retries widened to seven attempts for `429` and transient `5xx`, which is what a burst of
  document creation actually needs.
- Run journals moved to the shard naming scheme (`20 Runs — <run>`) so they are enumerated like
  every other log.

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
