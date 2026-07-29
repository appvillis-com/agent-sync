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
^- `(?P<ts>[^`]+)`(?P<pairs>(?: `[a-z_]+=[^`]*`)+)$
```

Required on every line: `op`, `key`, `run`. `op` is one of
`acquire` · `release` · `renew` · `base` · `reserve` · `release_id` · `signal` · `journal`.

Unparseable lines are **skipped and reported**, never guessed at. When more than 2%
of a log is unparseable the board gate fails — a log nobody can replay is not a
coordination system, and a quiet skip would hide that.

## Acquiring

```
1. append   op=acquire key=<K> run=<R> ttl=<seconds>
2. wait     250 ms + jitter 0-150 ms
3. read     log.read, replay from the top
4. resolve  K's holder is the earliest acquire for K that is at that point
            neither released nor expired
5. if holder == R  -> won
   else            -> lost; append op=release key=<K> run=<R>; back off;
                      retry at most 3 times, then report and stop
```

Step 5's release on a loss matters: without it the log accumulates acquires that
replay as contenders forever, and the third agent sees a queue that does not exist.

Replay is a pure function of the log text. Two agents replaying the same text reach
the same holder, which is what makes this safe without a lock server.

## Expiry and stealing

An `acquire` is expired when `now > ts + ttl` **and** no `renew` for the same
`(key, run)` appears later in the log.

Default `ttl` is 2700 s (45 minutes). `renew` is emitted at most once per
`renewIntervalSeconds` (default 300 s) — by the `PostToolUse` hook in Claude Code,
and by the agent itself everywhere else.

**Stealing an expired lease is the ordinary `acquire` path.** There is no separate
force flag: the replay simply finds the previous holder expired. The steal is
visible in the log with both run ids, so an operator can always see that it
happened and when.

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

`acquire` writes the git tag through in the same run; `release` clears it. One fact,
one durable home, one stated derivation. Do not add a third place that records
ownership — a project with two claim vocabularies has, in practice, none.
