---
code: CV18.DS2
level: Delivery Story
status: Completed
status_reason: The Navigator accepted the debugger-like real-host World, independent continuous checker, ambiguity/restart vertical, and exact replay
updated: 2026-08-18
related:
  - index.md
  - cv18-ds1-readiness-correctness-model-and-simulation-contract.md
  - ../../debt/items/readiness-dst-composition-must-split-before-campaign-expansion.md
  - https://github.com/henriquebastos/petrus
---

# CV18.DS2 — Deterministic host and provider fault world

> **Current topology note:** DS2 was accepted while the former production Net
> was the default. The Navigator subsequently made non-sharded V5 the sole
> production composition. DS3's current World preserves this contract and
> authoring experience over the real V5 host; sharded V5 remains excluded.

## Intent

Run the real supported Hamsterdan host composition under deterministic logical
time and event order while external systems remain explicit, bounded models of
truth and failure rather than ad hoc mocks.

## Delivered experience

The author-facing shape follows the Instant Offer precedent: one World owns the
real application and modeled external systems; one Timeline exposes business
verbs and debugger-like `run_until` checkpoints.

```python
world = ReadinessWorld(path)
timeline = world.timeline()

timeline.set_pull_request(...)
timeline.set_ci(...)
timeline.set_review(...)
delivery = timeline.emit_webhook("pull_request", action="synchronize")
timeline.lose_effect_response("readiness")
timeline.deliver_webhook(delivery)

timeline.run_until(
    "provider accepted readiness",
    lambda state: state["provider"]["response_losses"] == ["readiness"],
)
timeline.crash("after_readiness_terminal_before_projection")
timeline = world.restart()
final = timeline.converge()

artifact = world.artifact("ambiguity-restart")
replay_readiness(artifact, replay_path)
```

Every Timeline verb lowers through Petrus's one command interpreter. The
expanded artifact replays those commands, automatic host follow-ups,
observations, fault activation, crash, restart, fair-phase entry, and finish;
it does not serialize the Python predicate.

## Delivered scope

- Consume Petrus only through its accepted public deterministic event,
  logical-time, fault, crash/reload, checker, and replay surface. DS2 was
  accepted against commit `1936ae8` / `petrus.testing.dst/v1`; DS3 first
  advanced to `5ded726` / v3 and now pins `44cac5f` / v4 for deterministic
  profile resources.
- At acceptance, compose the real production-default `HostService`, production readiness Net,
  signed ASGI webhook route, durable custody, canonical Petrus History, Motus
  Activity worker, runnable index, and reconciliation path. V5 receives only
  compatibility-preserving clock propagation; it is not selected by this World.
- Expose strict commands for PR authority/lifecycle, CI attempts, agent review
  evidence, human review/thread facts, agent terminals, webhook emission and
  delivery, provider-effect visibility, and explicit logical-time advance.
- Keep provider truth mutation, webhook creation, and delivery separate so
  omission, reordering, and exact redelivery are first-class authored actions.
- Model comment-backed provider effects with definite rejection,
  accepted-visible, accepted-but-response-lost, delayed visibility, and
  operation-identity collision cuts. The accepted vertical executes the
  response-lost readiness cut and lookup-first recovery.
- Keep provider truth independent of Hamsterdan's desired state. Stable markers,
  operation IDs, comments, and agent-operation ledgers record what the modeled
  provider accepted; lookup-first recovery queries that truth.
- Crash by discarding all host/process objects and reopening through production
  custody, History, runnable, operation, and reconciliation paths. Revoked
  Timeline handles fail, and weak-reference evidence proves the dropped
  generation graph is collectable before restart.
- Make every external call fail on an undeclared operation; silent permissive
  mocks are prohibited.
- Enforce generic Petrus budgets plus profile bounds for facts, effects, calls,
  queues, durable state, payload/observation bytes, and a diagnostic wall-clock
  watchdog.
- Serialize and exactly replay the expanded schedule without using a PRNG.

## Independent checker

The checker is a separate answer key, not a workflow step. It derives expected
readiness from DS1's authored external facts and compares that answer with a
detached host view after every accepted atomic command, fault activation, and
fresh load. It also rejects:

- modeled custody actions whose detached host disposition differs;
- duplicate provider operation acceptance or identity/content collisions;
- duplicate Motus terminal projection or more terminals than requests;
- DS1 safety violations; and
- test credentials or webhook authority in retained observations/artifacts.

The expected admission is never copied from Host History or custody status. A
focused sensitivity regression deliberately makes custody retain one modeled
delivery and proves the checker ends the run as `invariant_failure`. A second
regression proves a terminally disposed non-actionable delivery cannot be
reported as completed or normalized as semantic admission.

## Host compatibility seam

The production host gained only application-owned public doors required by the
opaque Petrus profile:

- construction-time clock and GitHub transport injection with unchanged
  production defaults;
- one shared clock through webhook custody, runnable work, application timers,
  and both supported topology constructors;
- bounded `process_one`, `run_one_activity`, `run_due(limit=1)`, and
  `reconcile_one` operations;
- detached subject/work observations and earliest runnable due time; and
- abrupt non-settling `abort`, distinct from graceful `close`.

No Coordinator, mutable Engine, Instance, History, Dispatch, provider client,
or runtime handle crosses the profile boundary.

## Acceptance / Done condition

1. One vertical scenario crosses signed delivery custody → readiness work →
   external effect accepted → terminal/acknowledgement crash → full host rebuild
   → lookup-first settlement without duplicate effect.
2. Replaying an expanded scenario produces the same normalized provider truth,
   accepted Histories/custody, expected-model/checker observations, and terminal disposition at
   the same commits.
3. The host is genuinely reconstructed; no runtime, provider client, mutable
   fake-world alias, timer object, or Engine survives a simulated process crash.
4. Accepted-but-response-lost differs from definite rejection and drives the
   production recovery path rather than an invented exactly-once shortcut.
5. Every scenario is bounded by events, logical time, provider calls, retained
   state, pending work, and wall-clock test budget, and reports the ending bound.
6. No credential, private payload, real provider authority, wall sleep, or
   private Petrus runtime import is needed.
7. Existing focused host, V5, CV17 parity, and full gates remain green.

## Driver QA and evidence

- The vertical scenario crosses signed delivery custody, production readiness
  work, accepted external effect, lost response, frozen terminal, crash before
  projection, fresh reconstruction, and lookup-first convergence with one
  provider acceptance.
- The old Timeline is stale after crash, no dropped generation remains alive,
  and replay produces the same operations, journal digest, checks, and terminal
  disposition.
- Exact duplicate delivery remains one independent semantic admission and one
  provider effect.
- Unknown commands, malformed bounded payloads, unsupported faults, undeclared
  provider requests, stale generation use, custody mismatch, and retained
  credentials fail visibly.
- Focused host/World verification and the full project gate pass; the accepted
  worklog records the exact final counts.

## Out of scope

- Stateful random workload generation and shrinking; DS3 owns it.
- Real GitHub API, Git object, model-provider, or network fidelity claims.
- Reimplementing readiness, authority, retry, settlement, or Petrus logic in
  the fault world.
- Reopening or replacing completed CV17, or selecting the default topology.

## Accepted DS3 carry-forward

This story proves the reusable substrate and one elaborate vertical scenario;
it is not semantic coverage of mutually exclusive states. The Navigator
accepted these explicit carry-forwards:

- DS1 fault families not needed by the vertical—stale/rate-limited reads,
  History/Dispatch/timer cuts, agent-terminal delivery cuts, and Git publication
  cuts—become executable in DS3 beside the generated schedules and checker
  properties that exercise them. DS2 does not claim those cuts ran.
- `readiness_world.py` was accepted as one coherent vertical composition for
  this story. DS3 has since split provider truth/adapters from
  profile/checker/Timeline ownership and exercised that boundary with its first
  generated dimension, resolving the linked debt item.
- The version-1 Hamsterdan profile is one fixed safe subject and deterministic
  fixture family; that profile identity is separate from Petrus API/artifact
  versions.
  Subject/profile expansion belongs to generated campaigns, not this proof.
- Same-process generation revocation/collection is simulation evidence. Actual
  process-kill and real-provider correspondence remain separate DS4 evidence.

## Resolved dependency limit

DS2 was accepted while Petrus artifact v1 could retain only authored normal
endings. Petrus commit `5ded726` resolves that DS3 blocker: v2/v3 artifacts
retain exact World-owned budget/checker failures, and v3 adds seeded provenance,
while strict v1/v2 replay remains supported. Hamsterdan's first generated slice
now promotes and replays a checker counterexample through the same interpreter;
profile/runtime exceptions deliberately remain harness failures. Current commit
`44cac5f` adds v4 resource-bound failures and exact v1-v3 compatibility without
changing that distinction.
