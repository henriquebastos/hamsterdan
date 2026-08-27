---
code: CV20.DS8
level: Delivery Story
status: Planned
status_reason: Waits for CV20.DS6 and CV20.DS7 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds6-reconstructible-agent-execution.md
  - cv20-ds7-one-pr-readiness-execution.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS8 — Deliver trusted host custody and fair supervision

## Outcome

Implement the sole concrete composition root, provider/agent resource custody,
instance catalog, lifecycle evidence, fair runnable sequence/lease, one-PR
turns, detached inspection, bounded startup/shutdown, qualification faults,
API, process CLI, and operator package.

## CV20 contract

This story implements the sole concrete composition root and multi-PR
supervisor from [the architecture](architecture.md). Its lifecycle, catalog,
runnable, fairness, inspection and process contracts are in
[the API contract](api-contracts.md). It consumes DS6/DS7 public APIs rather
than decoding workflow or Petrus state.

## Owned paths

```text
src/hamsterdan2/host/__main__.py
src/hamsterdan2/host/api.py
src/hamsterdan2/host/clock.py
src/hamsterdan2/host/composition.py
src/hamsterdan2/host/service.py
src/hamsterdan2/host/instances.py
src/hamsterdan2/host/inspection.py
src/hamsterdan2/host/runnable.py
src/hamsterdan2/host/qualification.py
src/hamsterdan2/host/agents/**
src/hamsterdan2/operator/__main__.py
src/hamsterdan2/operator/qualification.py
tests2/behavioral/host/**
tests2/behavioral/operator/**
tests2/integration/test_host_lifecycle.py
```

`host/simulation` remains a placeholder until DS9. Packaging/service selection
remains current-only through DS11.

## Fixed design

- `host/composition.py` is the only module that constructs readiness with
  concrete GitHub and agent implementations and process resources.
- Host owns configuration, credentials, webhook custody, provider/agent
  resource lifetime, store factories, routes, instance catalog and
  supervision.
- Host never imports workflow loop names/terminals, decodes History, or holds
  Petrus Engine/Dispatch/Worker objects.
- Instance discovery is catalog-based. Filesystem/History scans are forbidden.
- Runnable order is a durable monotonic sequence with one subject lease per
  claim. Expired leases repair to the queue; an always-due subject cannot starve
  another.
- One host turn calls one PR lifecycle for bounded work, persists fresh
  lifecycle evidence, then acknowledges/requeues according to detached result.
- Route and lifecycle generations advance on owned changes and fence stale
  readiness effects.
- Agent delivery acknowledgement follows readiness custody; host does not
  acknowledge on transport/runtime success alone.
- Startup and shutdown are bounded, idempotent and failure-isolated per
  resource/instance. A bad subject does not prevent unrelated subjects.
- Inspection returns detached bounded posture and operation identities, never
  canonical workflow state.
- FastAPI and command rims delegate to service/application APIs. Business
  semantics do not live in HTTP handlers or command functions.
- The replacement remains non-selectable and absent from current service
  configuration in this story.

## Position and predecessors

Requires CV20.DS6 and DS7; DS7 defines effect adapters over the DS5 GitHub
capabilities. The target host remains disabled and non-selectable.

## Implementation sequence

1. Rule construction, catalog, lifecycle, runnable, inspection and operator
   APIs below.
2. Implement config/secret validation and bounded process-resource factories.
3. Implement instance catalog, route/lifecycle evidence and reconstructible
   instance factory.
4. Implement durable runnable sequence/lease and one-PR turn supervision.
5. Compose concrete GitHub, agent and readiness capabilities in the sole root.
6. Implement bounded inspection, service/API lifespan and operator commands.
7. Prove two-PR fairness, lease/route/lifecycle recovery, acknowledgement
   ordering, partial startup/close containment and credential boundaries.
8. Prove no target selector, entry point or deployment path exists.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- composition and one-PR instance factory signatures;
- subject/root/provider-route registration and lookup contracts;
- route/lifecycle evidence values and generation update rules;
- runnable enqueue/claim/renew/complete/requeue API and lease identity;
- host-turn input/result and `StepResult` acknowledgement mapping;
- detached inspection/posture schema and operation-identity fields;
- startup/close error aggregation, timeout and partial-failure contracts;
- FastAPI application/service lifecycle boundary; and
- operator command names, arguments, dry-run behavior and exit/error payloads.

Names may be strengthened, especially operator and inspection vocabulary. Sole
composition ownership, catalog discovery, durable fairness, bounded lifecycle,
detached inspection and non-selectability are fixed.

## Done condition

Host contains no workflow names or Petrus runtime objects; one already-due PR
cannot starve another; route and lifecycle generations fence work; delivery
acknowledgement follows readiness custody; startup/shutdown are finite and
failure-isolated; and credentials remain inside trusted process custody.

## Rollback

Remove target host/operator and their fresh stores. The current service entry
point and current state remain unchanged.

## Validation

Run two-PR fairness, route generation, delivery ordering, catalog/hint loss,
lifecycle response loss, lease repair, startup/close containment, credential
and inspection bounds, FastAPI lifespan, and CLI integration.

## Expansion boundary

Expand composition/custody, fair supervision, inspection/API, and operator
surfaces into independently green User or Technical Stories. Record final
host/operator contracts in CV20 before DS9 and DS11 rely on them.
