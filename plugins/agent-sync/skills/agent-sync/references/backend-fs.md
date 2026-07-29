# Filesystem backend — the degraded mode

**Read this when** running without a cloud backend, or explaining to an operator
what they do and do not get.

## What it is

Plain files under `.agent-sync/` in the repository, committed and pushed:

```
.agent-sync/
├── claims.log          # the append log
├── reservations.log
├── signals.log
├── runs/<runId>.log
└── board.md            # generated
```

## Capabilities — declared honestly

```json
{ "atomicAppend": false, "totalOrderRead": false, "search": false }
```

`atomicAppend` is false. A local `>>` is atomic for small writes on one machine, but
agents here are separated by **git**, not by a filesystem: two agents append on two
clones, and the merge decides the order after the fact. There is no total order at
the moment of the decision, which is exactly when the protocol needs one.

## What follows from that

**This backend is never the lease authority.** With it configured, the coordinator:

1. says so at session start, in one plain sentence;
2. uses git-file leases — a lease is a committed, pushed file, and the push either
   wins the race or is rejected as non-fast-forward, which is the only real mutual
   exclusion available here;
3. marks every run `ungated` on the board.

## Git-file lease

```
1. write   .agent-sync/leases/<KEY>.lock  containing run id, ts, ttl
2. commit  and push
3. push rejected  -> someone else took it; fetch, read the holder, back off
   push accepted  -> you hold it
```

The remote's fast-forward rule is the arbiter. This is slower than an append log and
it fails whenever the network does — both are honest limits, and neither is hidden.

## When this is the right choice

- A project with one agent at a time, which wants the journal and the board without
  standing up a service.
- An air-gapped or offline repository.
- A first run, before the operator has chosen a knowledge backend.

## When it is the wrong choice

- Several agents working at once with a shared remote and frequent pushes: the
  rejection rate makes progress slow and the retries noisy.
- Anything where the operator has been told the project is protected. It is not; it
  is `ungated`, and the board must keep saying so.
