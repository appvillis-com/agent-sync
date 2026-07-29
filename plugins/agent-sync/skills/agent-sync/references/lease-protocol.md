# Lease and id-reservation protocol

**Read this when** changing acquisition, expiry, stealing, or id allocation — or
when two agents disagree about who holds something.

No planned backend offers compare-and-swap. So the protocol never asks one: both
leases and id reservations are decided by **replaying one append-only log**, and

> **the order of lines in the document is authoritative. Timestamps are used only
> to expire leases, never to order them.**

Clocks differ between agents. Document order does not.

## Line grammar

One event per line, appended, never edited. Exactly this shape:

```
- `2026-07-29T10:42:13Z` `op=acquire` `key=ASC-072` `run=r-7f3a91` `ttl=2700` `repo=account-session-connect` `sha=9bba6d2`
```

Parsed by:

```
^[-*+] `(?P<ts>[^`]+)`(?P<pairs>(?: `[a-z_]+=[^`]*`)+)$
```

**Emit `- `; accept `-`, `*` or `+`.** The bullet is deliberately liberal because a
knowledge base normalises markdown on the way in — Outline rewrites `- ` to `* ` —
so a parser anchored to the character you wrote rejects every line the server hands
back. Observed live, and it presented as a lost race rather than a parse failure.

Required on every line: `op`, `key`, `run`. `op` is one of
`acquire` · `release` · `renew` · `base` · `reserve` · `release_id` · `signal` · `journal`.

Unparseable lines are **counted and reported**, never guessed at. Anything
entry-shaped (`^[-*+] \``) that fails the full pattern counts as unparseable; blank
lines, prose and the generated marker are skipped without counting.

**Do not put a narrower pre-filter in front of the pattern.** A `continue` that
tests for the exact bullet you emitted skips malformed lines *before* they can be
counted, so the ratio reads 0% while nothing parses — the guard and the counter both
go quiet at once. This is not hypothetical; it is how the bug above stayed invisible.

**An unreadable log is not a lost race.** When more than 2% of a log fails to parse,
`acquire` **raises** instead of reporting `lost`, and the board gate fails. Reporting
a lost race would name a holder who does not exist and send the caller looking for
them.

## Acquiring — the third design, and the first that is true

```
1. reap     if .agent-sync/leases/<K>.lock exists and is expired, remove it
2. create   os.open(lock, O_CREAT | O_EXCL) — this is the decision, and it is atomic
3. lost     FileExistsError -> read the holder out of the file and report it
4. won      write {run, ts, ttl, repo}; publish op=acquire to the plane for visibility
```

**Publishing is not the decision.** A failure to reach the knowledge base costs
visibility, never correctness: the lock is already held. So the append is wrapped and
its failure reported, not raised.

### Why not the knowledge base

Two earlier designs failed, and the measurements are worth keeping:

- **One shared append-only document.** Twelve concurrent appends returned twelve
  successes and left three lines. `editMode: append` reads, appends and writes back, so
  simultaneous writers clobber each other — and each is told it succeeded. A lease
  decided on that can be held by two runs, each with proof.
- **One document per writer.** Loss goes to zero (12/12 land). But the decision needs
  to know whether a contender is *still writing*, and without compare-and-swap nothing
  answers that. Eight parallel processes each read only their own shard: **eight winners
  for one key.** A longer settle window took it to five. It cannot reach one.

`O_EXCL` answers the question the store cannot: twelve processes, one winner, eleven
losers naming the same holder.

### The limit, stated

A lock file is exclusive between processes on **one filesystem**. Two machines have two
filesystems and therefore two locks, and the plane's record is then advisory. The tool
reports which it is; it never implies the stronger one.

## Expiry and stealing

A lock is expired when `now > ts + ttl` for the timestamp inside it, refreshed by
`renew`.

Default `ttl` is 2700 s (45 minutes). `renew` is emitted at most once per
`renewIntervalSeconds` (default 300 s) — by the `PostToolUse` hook in Claude Code,
and by the agent itself everywhere else.

**Stealing an expired lease is the ordinary `acquire` path.** There is no force flag:
the reap step removes an expired lock and the create proceeds. The steal is visible on
the plane with both run ids, so an operator can see that it happened and when.

## Releasing

`release` on every path, including failure. An abandoned lease is indistinguishable
from active work until its TTL runs out, and during that window the task looks
taken. Report the failure and release; do not hold the lease "in case".

## Id reservation

Reading a "next free id" line from a file is not reserving it. Allocation is
**positional over the log**, so no agent has to trust another's arithmetic.

A register is opened once:

```
- `…` `op=base` `key=DEC` `value=0216` `run=r-bootstrap`
```

Then, replaying in order and maintaining a free list:

- `op=release_id key=DEC value=NNNN` pushes `NNNN` onto the free list.
- `op=reserve key=DEC` takes the free-list head if it is non-empty; otherwise it
  takes `base + (count of prior reserves not served from the free list)`.

Every reader computes the same assignment for every reserve line, including its own.

**An id you reserved and did not write to git must be released** with
`release_id`. An id that is reserved, unreleased and absent from git after its run
closes is reported by the board as a **leak** — never reclaimed automatically,
because a half-written decision on a branch is not the same thing as an unused
number, and silently handing it out again would produce two documents with one id.

## The lease is not the claim

| Fact | Home | Lifetime |
|---|---|---|
| Who holds this task **right now** | the lease log | ephemeral, TTL |
| Who **owns** this task | the git claim tag (`[name]`, `todo (claimed: <role>)`) | durable |

The **run** writes the git tag through — the agent, not the tool. A process that
rewrites a shared registry on its own is the exact mechanism that clobbers another
agent's work, and it would do it from a hook, unattended. So the tool **verifies**:
`status` reports where a held lease and the git tag disagree, and says plainly when the
configured mapping cannot be checked at all rather than passing silently. Do not add a
third place that records ownership — a project with two claim vocabularies has, in
practice, none.
