---
status: Decided
raised: 2026-08-01
decided: 2026-08-01
deciders:
  - Henrique (Navigator)
related:
  - CV1
  - CV1.DS1
---

# Hamsterdan is a standalone Petrus application

## Decision

Hamsterdan is developed in a private repository owned by `henriquebastos` and
consumes Petrus as an exact pinned dependency. It does not live under Petrus
`examples/` and does not import qualified PR-readiness example code.

The host is the sole runtime composition root. `github_app`, `agents`, and
`readiness` are sibling subsystems that may share neutral `contracts` but do not
import one another. The readiness Net lives within the readiness bounded
context. GitHub and agent work execute as typed Motus Activities; no GitHub
credential enters agent territory.

Source ownership is independent from provider instances. HBNetwork owns the
first private GitHub App registration and installation for sandbox validation.
That instance uses Hamsterdan code without making HBNetwork the source-project
owner.

## Rationale

The separate repository makes packaging, dependencies, tests, secrets,
deployment, product decisions, and future public distribution independently
reviewable. Host-only composition prevents provider concerns from contaminating
workflow semantics while matching Petrus's Engine and Activity ownership.

## Consequences

- Hamsterdan owns its Ariad history and application roadmap.
- Petrus remains authoritative for runtime behavior and historical CV9 evidence.
- Qualified behavior is transferred under characterization and parity tests.
- The first deployment supports one App registration and installation account;
  generalized multi-registration tenancy waits for evidence.
- A future common `@hamsterdan` identity across organizations requires one
  canonical public App or a deliberate transfer of the validation registration.
