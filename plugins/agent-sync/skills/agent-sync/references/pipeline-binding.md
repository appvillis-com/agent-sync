# Binding to task-pipeline

**Read this when** wiring `pipeline.json`, or adding a stage hook.

`agent-sync` supplies stages; it does not define them. The stage names below are
`task-pipeline`'s own — do not rename, renumber or fork them.

## Where it plugs in

| Stage | Calls | Why there and not elsewhere |
|---|---|---|
| **0 Intake grill** | `status`, then `acquire <KEY>` | The cloud KB and the board join the harvest's source ledger. The lease is taken **before the brief is committed**, or two agents write two briefs for one task |
| **1 Docs study** | — | External docs; nothing shared to coordinate |
| **2 Brainstorm + decompose** | `journal` | Also warns when a live run holds an overlapping key — cheapest moment to find the overlap |
| **3 Spec** | `reserve <REG>` per id | Ids must be reserved *before* they are written to git. Reading "next free id" is not reserving it |
| **4 Plan** | `journal` with the plan's file ownership | Parallel groups that write one file are a merge conflict scheduled for later |
| **5 Dev** | `renew` (automatic), `journal` | Also the owner of the submodule-commit → parent-gitlink bump. Nobody else has both repos in hand |
| **6 Tests** | `journal` | The suite result is evidence, and evidence belongs in the run |
| **7 Lint + deploy** | `journal` per gate | — |
| **8 Post-deploy** | `journal` | — |
| **9 Docs + wiki** | `signal` per dependency flip, then `board` | The main write point. The pipeline already updates docs here; the board is regenerated from what it wrote |
| **10 Acceptance** | `merge` when the work is on a branch — it records the merge and releases; otherwise `release` every lease and write the claim tag through | A run that ends without releasing looks alive until its TTL expires |

## pipeline.json

`task-pipeline`'s `pipeline.schema.json` already permits this; nothing is forked.
Add `agent-sync` to `skills[]` on the six stages that call it:

```json
{
  "stages": [
    { "id": "0",  "title": "Intake grill",  "skills": ["task-pipeline:grill", "agent-sync"],
      "gate": { "type": "manual", "check": "brief committed and lease held" } },
    { "id": "3",  "title": "Spec",          "skills": ["task-pipeline:spec", "agent-sync"],
      "gate": { "type": "auto",   "check": "every id in the spec was reserved" } },
    { "id": "4",  "title": "Plan",          "skills": ["task-pipeline:planning", "agent-sync"],
      "gate": { "type": "auto",   "check": "no two parallel tasks write one file" } },
    { "id": "5",  "title": "Dev",           "skills": ["task-pipeline:build", "agent-sync"],
      "gate": { "type": "auto",   "check": "lease live and submodule pointers current" } },
    { "id": "9",  "title": "Docs + wiki",   "skills": ["task-pipeline:artifacts", "agent-sync"],
      "gate": { "type": "auto",   "check": "board regenerated and no mirror drift" } },
    { "id": "10", "title": "Acceptance",    "skills": ["task-pipeline:acceptance", "agent-sync"],
      "gate": { "type": "auto",   "check": "every lease released and every claim tag written through" } }
  ]
}
```

Stages 1, 2, 6, 7 and 8 keep their own `skills[]`; `agent-sync` only journals there,
which needs no wiring.

## Preflight

`task-pipeline` is required. When it is absent, print the install line and **stop** —
do not improvise a substitute flow, because without those stages there is nothing to
bind to and the result is ad-hoc work wearing a pipeline's vocabulary.

```bash
npx sshlg-skills install
```

That installer also brings `super-ux` (its stage-3 UX track is required for
user-facing work) and `make-skill`, and it prunes the duplicate plain-copy shadow in
`~/.claude/skills/` that otherwise serves a stale skill over the installed plugin.

## Gate expressions

Each `check` above is verified by the coordinator, not by prose — and since 1.3.0 the repository
half of that verification is a command rather than a promise: **`agent_sync.py finish`** runs the
pointer, cleanliness, pushed-ness and lease checks, and `finish --gates` adds the project's own
declared gates. Until then this table described work nothing performed.

| Check | How it is decided |
|---|---|
| lease held | replay the log; holder == this run |
| every id reserved | every `DEC-`/`OQ-`/`DEP-`-shaped token new in the diff has a `reserve` line in this run |
| no two parallel tasks write one file | intersect the file lists journaled at stage 4 |
| submodule pointers current | `git submodule status` reports no `+` prefix — `finish` |
| every repository pushed | no commits ahead of upstream anywhere, parent included — `finish` |
| board regenerated, no drift | each mirror stamp equals `git rev-parse HEAD` for its source |
| every lease released | replay the log; this run holds nothing |
