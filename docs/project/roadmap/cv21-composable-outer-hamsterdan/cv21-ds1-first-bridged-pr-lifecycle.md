---
code: CV21.DS1
level: Delivery Story
status: Completed
status_reason: The first bridged lifecycle and its isolated deterministic, process-recovery, concurrency, architecture, and feedback evidence are locally complete
updated: 2026-08-29
related:
  - index.md
  - architecture.md
  - workflow-bridge.md
  - delivery-sequence.md
---

# CV21.DS1 — Establish the first bridged PR lifecycle

## Outcome

Deliver the smallest real pulse of the new outer system: a strict deterministic
command registers one immutable PR subject, new host composition opens its new
readiness lifecycle, the sole bridge mounts and seeds the current Net, one named
bounded action advances, and host receives detached new posture. The operation
survives fresh-process reconstruction and exactly replays.

## Vertical path

```text
register/step command -> new host composition -> new readiness runtime
  -> sole bridge -> current Net/seed -> detached new posture -> host record
```

## Owns

- isolated `src/hamsterdan2`/`tests2` quality and architecture gate;
- minimum workflow-boundary values, bridge construction, immutable subject/root
  binding, readiness runtime, host composition, and detached posture;
- core Timeline, logical clock, action identity, artifact, replay, local/root
  simulation, independent checkers, and resource gauges; and
- public bounded Petrus construction/replay qualification needed by this pulse.

## Excludes

No provider observation, Motus Worker construction, Activity execution,
workflow replacement code, current outer application reuse, runtime selector,
current state access, or deployment.

## Acceptance

- only `readiness/workflow_bridge.py` imports the exact legacy allowlist;
- the bridge mounts the production current Net and seed without old outer code;
- the one-PR Engine receives its engine-facing Dispatch without constructing or
  driving a Worker or concrete Worker implementation registry;
- host cannot inspect markings, old types, or Petrus runtime objects;
- one call returns after one named cut with finite measured resources;
- process death before and after that cut reconstructs deterministically;
- exact replay from a fresh object graph reproduces actions and posture; and
- a checker-sensitive mutation of subject, action, or bridge identity fails.

## Delivered contract

The strict command binds installation `44`, repository `31`, and pull request
`7` to Instance `github:44:31:pr:7` and root `instances/44/31/7`. The composed
default registers that subject, opens one readiness runtime, mounts the retained
Net only through the bridge, and records detached `awaiting_observation` posture
at the `host_recorded` cut. Registration and step remain public phases.

Readiness opens History only through Petrus's fenced SQLite `create_engine` and
`load_engine` construction doors. Their nonblocking database-and-Instance
writer fence refuses a second Engine before it loads the same canonical
History. The host catalog additionally holds one SQLite immediate-write
transaction across the readiness callback, serializing the normal composed
action path. Engine close or process loss releases the Petrus fence; process
loss rolls back the host transaction. Canonical readiness History survives
before `host_recorded`, while the host record makes a later turn idempotent
after the cut.

The independent root checker admits only four retained phases for this tracer:
empty, subject registered, readiness durable without a host record, and host
recorded. It derives the expected subject, action, Instance, and bridge identity
outside production construction. Subject, action, and bridge mutations each
fail it.

## Evidence

- `scripts/check hamsterdan2` is the isolated strict gate over only
  `src/hamsterdan2` and `tests2`; default `scripts/check quick` includes it.
- Owner-local and root Petrus version-4 artifacts carry finite resource samples
  and exactly replay from fresh roots.
- Actual child `SIGKILL` before and after `host_recorded` preserves the public
  Petrus runner's exact acknowledged prefix. Fresh child processes reconstruct
  as `applied` before the cut and `idempotent` after it.
- The real current Net and seed run through the sole bridge. No Worker,
  concrete Activity execution, provider observation, external effect, current
  state, selector, or deployment was added.
- Architecture checks pin acyclic imports, empty package facades, runtime and
  simulation custody, use of Petrus's fenced Engine constructors, sole concrete
  host construction, the exact legacy allowlist, and absence of Worker
  construction or legacy artifact leakage.
