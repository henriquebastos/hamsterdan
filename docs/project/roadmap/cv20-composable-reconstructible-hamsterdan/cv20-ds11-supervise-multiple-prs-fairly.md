---
code: CV20.DS11
level: Delivery Story
status: Dropped
status_reason: Parent CV20 was superseded before implementation by CV21 and CV22; this audited story is retained as design evidence
updated: 2026-08-28
related:
  - index.md
  - cv20-ds10-discover-unregistered-open-prs-boundedly.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS11 — Supervise multiple PRs fairly

## Outcome

Deepen the proven one-PR spine into bounded multi-PR process supervision. An
operator/service command starts the non-selectable replacement host, bounded
startup reconstructs registered subjects, a durable runnable sequence leases
one due subject at a time, each turn invokes readiness once, and already-due
subjects progress fairly despite one failing or repeatedly waking PR.

## Vertical paths

```text
operator/service start or webhook wake
  -> host bounded catalog page and provider/agent resource construction
  -> durable enqueue sequence plus selection lease
  -> open one subject's real readiness lifecycle
  -> exactly one established readiness cut
  -> persist delivery/route/posture consequences
  -> tail requeue or terminal close
  -> bounded detached portfolio inspection and shutdown

completed repository discovery pass
  -> idempotent unknown-subject registration/enqueue
  -> durable fair selection among known-subject and discovery turns
  -> one bounded readiness or discovery cut
  -> tail requeue without starving either work class
```

This tracer introduces one concurrency dimension—multiple independent PRs—and
fairly schedules the known-subject and discovery turns established by DS10,
while preserving all DS1–DS10 owner, authority, effect and recovery contracts.

## Component Technical Stories

1. Implement durable catalog and bounded instance reconstruction pages.
2. Implement coalesced runnable reasons, monotonic enqueue sequence, leases,
   expiry repair and tail requeue across known-subject and discovery turns.
3. Implement one-readiness-call host turns and consequence persistence.
4. Implement failure-isolated startup/shutdown, FastAPI lifespan and process CLI.
5. Implement operator registration/inspection/qualification surfaces.
6. Extend host/root simulation, fairness checker, generated schedules and real
   process/lease/concurrency correspondence.

## Initial owned paths

```text
src/hamsterdan2/host/{service,runnable,instances,inspection,api,__main__,qualification}.py
src/hamsterdan2/operator/{__main__,qualification}.py
src/hamsterdan2/host/composition.py and host/agents/**
implemented host/root simulation and tests
```

## Fixed design

- Host catalog maps subject to relative readiness root and provider route. It
  never copies workflow state or discovers instances by scanning History/files.
- Runnable state owns monotonic enqueue sequence, eligibility instant, lease,
  coalesced reasons and tail requeue. A repeatedly failing/re-woken subject is
  ordered behind already-due unclaimed subjects.
- Discovery turns and known-subject turns share durable fair scheduling without
  making repository traversal part of a readiness lifecycle. Neither class can
  starve the other under the accepted finite bounds.
- One service turn selects one subject, opens/reconstructs it, calls readiness
  at most once, persists consequences and requeues/closes it.
- Host preserves the nested readiness cut unchanged and never interprets
  workflow names, Activities or typed terminals.
- Expired lease, lost/corrupt wake hint and process death reconstruct from
  catalog plus readiness inspection; hints are not authority.
- Startup reads bounded catalog pages. Shutdown stops claims then closes each
  instance/resource independently under explicit limits; one failure does not
  prevent unrelated progress/cleanup.
- Inspection is detached and bounded. Operator/API rims contain no business
  semantics and expose no credentials or live runtime objects.
- Replacement service remains disabled/non-selectable through DS12.

## API-strengthening checkpoint

Review startup, one turn, inspection and shutdown call trees and settle:

- catalog register/page/lookup and reconstructible instance factory signatures;
- runnable enqueue/claim/renew/complete/requeue identities and transactions;
- known-subject/discovery-turn fairness and bounded selection representation;
- host-turn input/result plus readiness `StepResult` consequence mapping;
- startup/close result aggregation, cancellation, timeout and partial-failure
  taxonomy;
- detached portfolio inspection JSON and stable operation fields;
- FastAPI lifespan, service and operator command/dry-run/error APIs;
- lease/process/route/readiness response-loss cuts; and
- catalog/runnable/lease/loaded-instance/call/time/byte/artifact limits.

Write ruled signatures into [the API contract](api-contracts.md). Catalog
discovery, durable fairness, one-call turns, failure isolation, bounded lifecycle
and non-selectability are fixed.

## Tracer acceptance

Given at least two already-due PRs—one repeatedly failing or waking—and a due
repository discovery turn, when bounded service turns run, then each
non-terminal subject and the discovery pass progress in durable fair order, no
turn invokes readiness twice, failures remain isolated, and inspection reports
bounded detached posture. Lease loss and process death reconstruct and continue
without duplicate external effects or registration.

Acceptance covers partial startup, lease expiry at every turn cut, lost wake
hints, concurrent enqueues, route/lifecycle generation movement, terminal close
and bounded shutdown. Fairness-sequence/subject substitution leaves locals green
and fails exactly host/root checks. Exact replay, lowered portfolio bounds,
physical effect counts, real SQLite/filesystem/process-kill/lease/concurrency
correspondence and secret scans are required.

## Done condition

The real multi-PR service vertical is fair, reconstructible, observable and
bounded. Standalone catalog/runnable/service tests cannot close the DS without
two-PR composed evidence.

## Stop conditions

Stop if host parses workflow/Petrus state, fairness depends on an in-memory
queue, one turn drains readiness, one subject blocks startup/shutdown/progress of
another, wake hints become authority, or the replacement becomes selectable.

## Rollback

Remove multi-PR service/operator/runnable growth and fresh host stores. DS9's
one-PR tracer portfolio remains accepted; current production remains sole runtime.

## Validation

Run two-plus-PR fairness, lease/crash/requeue, lost hints, one-call turns,
startup/shutdown containment, inspection/operator/API behavior, local/cross
sensitivities, generated schedules/shrinking, exact replay, lowered bounds,
process/storage/concurrency correspondence, distribution/secret scans and gates.

## Expansion boundary

Catalog, runnable, turn, lifecycle and operator work may be separate Technical
or User Stories. Keep DS11 open until the same production host demonstrably
supervises multiple real readiness lifecycles fairly.
