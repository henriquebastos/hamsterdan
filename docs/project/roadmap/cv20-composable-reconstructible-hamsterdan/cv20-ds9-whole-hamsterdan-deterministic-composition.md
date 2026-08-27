---
code: CV20.DS9
level: Delivery Story
status: Planned
status_reason: Waits for CV20.DS3–DS8 and is not pulled
updated: 2026-08-27
related:
  - index.md
  - cv20-ds3-pure-readiness-workflow.md
  - cv20-ds4-hamsterdan-simulation-runtime.md
  - cv20-ds5-strict-github-provider-operations.md
  - cv20-ds6-reconstructible-agent-execution.md
  - cv20-ds7-one-pr-readiness-execution.md
  - cv20-ds8-trusted-host-custody-fair-supervision.md
  - architecture.md
  - api-contracts.md
  - delivery-sequence.md
  - replacement-ledger.md
---

# CV20.DS9 — Compose whole Hamsterdan deterministically

## Outcome

Implement workflow, readiness, GitHub, agents, and host owner-local simulation
packages, then mount those unchanged modules through `simulation.hamsterdan`.
Keep local checkers with their owners and put only cross-module properties in
the root composition.

## CV20 contract

This story implements the simulation ownership graph in
[the architecture](architecture.md) on the DS4 mechanics API. The local module
protocol, composed causal checker, artifact and replay contracts are in
[the API contract](api-contracts.md). All commands, observations and eligibility
remain with their production owner.

## Owned paths

```text
src/hamsterdan2/workflow/simulation/**
src/hamsterdan2/readiness/simulation/**
src/hamsterdan2/github_app/simulation/**
src/hamsterdan2/agents/simulation/**
src/hamsterdan2/host/simulation/**
src/hamsterdan2/simulation/hamsterdan.py
tests2/simulation/test_workflow.py
tests2/simulation/test_readiness.py
tests2/simulation/test_github_app.py
tests2/simulation/test_agents.py
tests2/simulation/test_host.py
tests2/simulation/test_composition.py
```

Production owner modules and root simulation mechanics are already complete and
must not be changed merely to make a simulation convenient.

## Fixed design

- Each owner-local simulation imports its real production owner and generic
  DS4 mechanics; it owns local commands, observations, fault meanings,
  resources and checker.
- Local simulations do not import one another. Root composition constructs and
  mounts all five unchanged modules.
- Root composition owns only explicit adapters and cross-module properties. It
  cannot reimplement workflow folds, provider behavior or agent lifecycle.
- The workflow module mounts the real `build_net` path and exposes durable
  ActivityRequested/History evidence, including exact decoded `MutWork`,
  occurrence, correlation and idempotency.
- The agents module exposes exact accepted delivered request/result values with
  copy isolation. The readiness module accepts a coding capability supplied by
  root composition.
- The causal vertical is a data dependency: real workflow `MutWork` → canonical
  `CodingRequest` → exact accepted delivered `CodingResult` → publication →
  `Pushed` into the original Activity occurrence.
- A/B result sensitivity changes publication evidence/head while work and
  request stay equal. Workflow-work substitution leaves all local checkers
  green and produces exactly one workflow→composition cross violation.
- Crash after accepted publication reconstructs generation 2, looks up first,
  and neither invokes the agent nor publishes again.
- Composed resource keys are exactly the union of mounted local budgets plus
  root artifact/interleaving costs. There is no hidden drain or queue.
- Artifacts replay by rebuilding the same object graph and comparing exact
  local/cross reports, causal evidence, operations, generation, resource peaks
  and digest.

## Position and predecessors

Requires CV20.DS3–DS8 so every local simulation mounts a real production owner
and the shared semantic-free runtime.

## Implementation sequence

1. Rule the shared local-module protocol and owner-specific vocabularies below.
2. Implement one local simulation/checker at a time against its production
   owner, with a local red/green counterexample and finite budget.
3. Add root composition with only wiring/adapters and unioned resources.
4. Prove canonical whole-system readiness, response-loss generation-2 recovery
   and exact replay.
5. Prove authority substitution creates only the intended cross violation.
6. Prove result A/B sensitivity and workflow-work substitution across a full
   publication/recovery/fold flow.
7. Freeze artifact schema/bounds and expose the evidence command consumed by
   DS10/DS11 qualification.

## API-strengthening checkpoint

The Plan Checkpoint must settle:

- concrete local-module types and closed results around the fixed
  open/drop/close/resource/command/observe/eligible/step operations;
- each owner's command, observation, named cut and fault vocabulary;
- local checker report and cross-checker report schemas;
- composition adapter protocols and explicit value validation;
- artifact scenario/evidence field names and causal-evidence projection;
- resource-union keys and per-owner inspection fields; and
- evidence runner/CLI name, arguments and deterministic output contract.

The API may remove experiment-era names and ceremony. Owner-local semantics,
unchanged-module mounting, causal data dependency, local/cross checker boundary,
bounded resources and exact replay are fixed.

## Done condition

Every local checker proves a meaningful local counterexample; composition-only
authority/work substitutions leave locals green and fail only the cross
checker; the real `MutWork`→delivered result→publication→original occurrence
vertical is causal; resource unions are bounded; and artifacts replay exactly.

## Rollback

Remove local simulation packages and root composition. Production owners remain
independently green and import no simulation code.

## Validation

Run local checker red/green cases, composition-only counterexamples,
response-lost generation-2 recovery, result A/B and workflow-work sensitivity,
resource-union failures, strict artifact encode/decode, and exact replay.

## Expansion boundary

Expand local modules by owner, then root composition. Do not implement a second
whole-application model or let local simulations import one another. Final
simulation vocabulary lives in CV20 and is the only input to DS10/DS11.
