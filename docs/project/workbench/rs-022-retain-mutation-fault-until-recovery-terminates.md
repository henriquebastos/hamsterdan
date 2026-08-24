---
status: Candidate
captured: 2026-08-24
navigator: Henrique
source: ../exploration/es9-human-codebase-ownership/candidate-review.md
---

# RS-022 — Retain mutation ambiguity until recovery terminates

## Existing field to refine

A durable `FaultM` terminates one `git_gate` Activity occurrence while retaining
the logical mutation, stable publication identity, and agent route for explicit
recovery. Its readiness fault is global so it survives lifecycle admission of a
newer provider head.

`mutation._recover` currently clears that global fault as soon as an authorized
human reopens the operation. It also emits a pending mutation fact under the
original incarnation. If the pushed head has already entered lifecycle as a
newer incarnation, readiness ignores the stale pending fact but applies the
global fault clear.

Concrete failure shape:

1. Git publication moves H0 to H1 but enters canonical History as `FaultM`.
2. Provider observation admits H1 as incarnation 2.
3. Incarnation-2 CI, review, collaboration, and authority are ready.
4. A human authorizes recovery of the original incarnation-1 operation.
5. The replacement `git_gate` remains pending without a terminal.
6. Readiness has no current pending mutation and no global fault, so it can
   authorize incarnation 2 before recovery proves an outcome.

## Evidence

- `src/hamsterdan/readiness/net_v5/mutation.py`: `_fold_fault` and `_recover`;
- `src/hamsterdan/readiness/net_v5/readiness.py`: `_current`,
  `_apply_mutation_pending`, `_apply_fault_cleared`, and authorization mailbox
  inhibitors;
- `tests/unit/readiness/net_v5/test_mutation_loop.py`:
  `TestFaultAndRecovery`;
- `tests/integration/testing/test_readiness_world.py`:
  `test_real_v5_recovers_one_ambiguous_authorized_git_publication_after_crash`;
  and
- the ES-009 Git-ambiguity journey and candidate review.

A held-Activity reproduction left a replacement `git_gate` pending while the
incarnation-2 readiness snapshot had no pending operation, no fault, and
`announced == [1, 2]`.

The topology ordering gap is proven under the repository's supported held
scheduler. Production currently uses `InlineDispatch` for `git_gate`, so this
exploration did not prove that today's single-owner production composition can
pause at the exact unsafe cut.

## Candidate boundary

Keep the operation-keyed mutation fault until the replacement recovery Activity
records a known terminal. `Pushed`, `MovedM`, or `DeclinedM` may clear the fault
through an explicitly ordered terminal settlement. A repeated `FaultM` must
retain or replace it.

Human recovery authorizes one new proof attempt. It does not itself establish
that provider ambiguity is resolved.

Preserve:

- the same logical publication operation and payload digest;
- lookup-before-authority ordering;
- one fresh Activity occurrence per authorized recovery;
- incarnation-safe late `ProvisionalHead` settlement; and
- global fault visibility across head admission.

## Correctness obligations for the future plan

- **Authoritative state and authority.** Canonical History owns Activity request
  and terminal state. `MutState` owns the unresolved logical operation.
  Readiness owns the global operation-keyed fault projection.
- **Safety.** No readiness advisory may be authorized while an explicitly
  recovered mutation lacks a known terminal, even if its original incarnation
  is stale and the current head is otherwise green.
- **Fair-environment liveness.** A proven `Pushed`, `MovedM`, or `DeclinedM`
  terminal must clear the blocker exactly once. Another `FaultM` remains
  recoverable and fail-closed.
- **Bounds.** Recovery remains one human-authorized occurrence at a time under
  the mutation baton. No automatic retry loop is added.
- **Nondeterminism.** Head admission, fact folding, Activity request, provider
  lookup, terminal delivery, process crash, and readiness authorization may
  interleave.
- **Crash and ambiguity cuts.** Test after recovery admission, after
  `ActivityRequested`, after provider lookup, after provider effect acceptance,
  before terminal append, after terminal append, and before fault settlement
  reaches readiness.
- **Independent evidence.** Hold the Activity and inspect both canonical pending
  occurrence state and the readiness snapshot. The final converged journey is
  insufficient evidence by itself.

## Change Request

### CR-001 — Clear the mutation fault only from known recovery settlement

Status: Parked

A future plan must select the typed fact and ordering through which known
mutation terminals clear the global fault. It must prove that stale-incarnation
settlement cannot erase or strand another operation's fault.

Likely files:

- `src/hamsterdan/readiness/net_v5/mutation.py`
- `src/hamsterdan/readiness/net_v5/readiness.py`
- `src/hamsterdan/contracts/readiness_v5.py`, only if a new typed settlement fact
  is required
- `tests/unit/readiness/net_v5/test_mutation_loop.py`
- `tests/unit/readiness/net_v5/test_readiness_loop.py`
- `tests/integration/testing/test_readiness_world.py`
- generated Git recovery campaign coverage if the observable schedule changes

Validation seeds:

- hold recovery `git_gate` after incarnation-2 admission and assert no readiness
  request exists;
- release `Pushed`, `MovedM`, and `DeclinedM` terminals and assert exact fault
  settlement;
- release another `FaultM` and assert the operation remains blocked;
- exercise crash cuts before and after terminal projection;
- replay any generated counterexample exactly;
- run focused mutation/readiness tests, semantic recovery, generated campaign,
  `scripts/check quick`, and `scripts/check full`.

## Pull state

This candidate is captured but not pulled. No topology, fault semantics, test,
runtime, launch prerequisite, commit, or release action is authorized by this
record. ES-009 remains a learning session.
