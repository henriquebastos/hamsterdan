# DS1 concept extraction

## Source

- Delivery Story: [`../cv20-ds1-first-bounded-pr-lifecycle.md`](../cv20-ds1-first-bounded-pr-lifecycle.md)
- First-use register: [`../api-contracts.md`](../api-contracts.md), "First-use
  ownership" and "DS API-strengthening register"
- Fixed vocabulary: [`../architecture.md`](../architecture.md), "Naming and
  vocabulary"

Reviewed source revision: 2026-08-28 working tree.

## Extracted behavior

DS1 registers one repository/PR subject, binds it to one readiness root, opens
one real readiness lifecycle, advances the real workflow once, and returns a
detached bounded posture. Reconstruction discards process-local objects and
rebuilds from retained owner state. Exact replay creates a fresh object graph.

The story also introduces the deterministic simulation and evidence needed to
prove that behavior: Timeline, artifact/replay mechanics, owner-local checkers,
one cross checker and finite resource limits.

## Evidence ledger

| Source location | Observed claim | Candidate consequence |
|---|---|---|
| Outcome, lines 19–26 | One subject enters a real lifecycle and returns detached posture through reconstruction/replay | subject, lifecycle, posture, reconstruction, exact replay |
| Vertical path, lines 31–37 | Host composition joins subject/root binding, workflow seed/fold and detached result | readiness root, step result |
| Component Technical Stories, lines 51–59 | The tracer adds bounded Petrus replay, subject/root binding, Timeline, artifacts and local simulation | Timeline, artifact, local checker |
| Fixed design, lines 85–100 | Binding is immutable; one call ends at one cut; runtime objects are detached; replay is fresh; all resources are finite | PR subject, cut, posture, reconstruction, exact replay |
| Acceptance, lines 147–162 | Fresh-process recovery and a substitution-sensitive cross checker are required | local checker, cross checker |
| API contracts / PR subject, lines 71–79 | Subject semantics are fixed but concrete representation and fields remain DS review | keep concept; defer code name |
| API contracts / Shared step result, lines 440–493 | StepResult and WorkPosture are fixed detached result names but concrete first-use fields remain DS review | evaluate concept versus API vocabulary after later trace |
| API contracts / Timeline, lines 901–936 | Timeline and Artifact names and behavior are fixed; core result/error fields remain DS review | enduring technical candidates |

## Construction-only exclusions

- `hamsterdan2` and `tests2` are temporary namespaces.
- The isolated replacement gate controls construction and does not describe the
  completed product domain.
- Non-selectability describes DS1–DS12 rollout posture and ends at DS13.
- Existing V5 source, state and terminology are not definition sources.

## Unresolved DS-review items

- concrete subject and root representations;
- lifecycle factory and method names;
- StepResult and WorkPosture fields and private-value treatment;
- Petrus replay cursor shape;
- simulation module mechanics/type names; and
- artifact result, error and diagnostic fields.

These open API decisions do not erase the fixed behavior of the candidate
concepts. They prevent the analysis from silently promoting a provisional code
name into canonical language.

## Trace handoff

The DS2–DS13 trace is complete in the
[candidate register](candidate-register.md). Navigator review is paused before
the first concept decision.
