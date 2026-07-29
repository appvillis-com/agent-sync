# Two documentation sources, and the duty to reconcile them

**Read this when** starting a task, finishing one, or deciding where a piece of
documentation belongs.

## They answer different questions

| Source | Answers | Written | Authority over |
|---|---|---|---|
| **Git docs** (`docs/`, ADRs, specs, contracts) | *How it should be* | before the code, often without it | intent, design, scope, decisions |
| **The coordination plane** (`70 As-built`) | *How it actually is* | from what agents really wrote | the record of what was built, by whom, at which commit |

Neither is a copy of the other and neither outranks the other, because neither is
answering the other's question. A spec that describes an unbuilt thing is not wrong —
it is intent. An as-built record that contradicts the spec is not wrong either — it is
what happened.

**The gap between them is the finding.** It is drift between plan and reality, and
surfacing it is the whole point. A system where the two can never disagree has simply
hidden the disagreement.

This is why the as-built record does **not** violate a single-source-of-truth rule:
there is no second home for one fact, there are two facts. What would violate it is
copying a decision's *body* into the cloud and editing it there.

## The duty, both ends of a task

**Before starting** — during the pipeline's docs-study stage:

```bash
python3 "$SKILL_DIR/scripts/agent_sync.py" reconcile
```

Read the git documents for the area you are about to touch **and** the as-built
record for it. Then resolve every divergence one of three ways:

1. the git document is stale → fix it, or record why it stands;
2. the as-built record is wrong or incomplete → correct it with `record`;
3. they genuinely disagree and the disagreement is real → that is a decision to make,
   not a discrepancy to paper over. Raise it before you write code against either.

Starting work on top of an unresolved divergence means building against a document
that describes a system that does not exist.

**After finishing** — during the pipeline's docs stage:

```bash
python3 "$SKILL_DIR/scripts/agent_sync.py" record "what you actually built" --decision DEC-0216 --files a.py,b.ts
python3 "$SKILL_DIR/scripts/agent_sync.py" reconcile
```

Update **both** sides in the same change: the git documents that state intent, and the
as-built record of what landed. Then run the check again. A task that updated only one
side has left the next agent a divergence to discover the hard way.

## What `reconcile` decides, and what it refuses to

It is mechanical, and it says so in its own output. It finds:

- an as-built entry whose commit is **not in this repository's history** — recorded
  from a branch that never landed, or from another repo;
- an id written in a register **after the baseline** with no as-built record — decided
  since adoption, and nothing reports it was built;
- an as-built entry citing an id that **exists in no register** — built against
  something never written down.

It does **not** judge whether the built thing matches what the document describes.
That is a reading, not a diff. The tool points at where to look and refuses to imply
it checked the substance.

## The baseline — why the check is a ratchet

A project adopting this on day one has every prior decision unrecorded. A check that
reports all of them reports nothing: it is noise, and noise is what gets a gate
switched off.

```bash
python3 "$SKILL_DIR/scripts/agent_sync.py" reconcile --set-baseline
```

Run once per project. Ids at or below the baseline become a **backlog** — counted,
visible, allowed only to shrink. Ids after it must carry an as-built record or the
check fails. This is the same shape as a well-behaved lint ratchet, and for the same
reason: a gate that fails on history is a gate nobody keeps.

## Where a piece of documentation belongs

| It is… | Home |
|---|---|
| a decision about what to build | git — the decision register |
| a contract, schema, spec | git |
| user-facing behaviour | git |
| "this is what I implemented, here is the commit" | the as-built record |
| "the implementation diverged from the spec, here is why" | **both** — as-built for the fact, git for the decision |
| who is doing what right now | the claims log — ephemeral, never git |

When in doubt: if it must survive the tool being uninstalled, it goes in git.
