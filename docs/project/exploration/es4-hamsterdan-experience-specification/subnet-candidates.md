# Subnet candidates — resolved by AX1

The seed inventory here was promoted by
[AX1](experiments/ax1-subnet-contracts.md), which owns the full contracts.
This file keeps the resolved shape for quick reference.

## Final decomposition

| Unit | Kind | Gate | Discard-safe until |
| --- | --- | --- | --- |
| Control layer (authority, generations, quarantine, routing) | not a subnet | — | — |
| Review production | subnet | none (feeds P) | always |
| CI observation | subnet | none (read-only) | always |
| CI rerun | subnet | comment gate | the marker post |
| Conversation classify | subnet | none (feeds fan-out) | always |
| Agent mutation — shape M ×4 (`repair`, `change`, `update_base`, `resolve_conflict`) | fractal shape | **git gate** (CAS) | the CAS advance |
| Publication — shape P ×5 (reply, findings, readiness, reminder; dashboard as mutable singleton) | fractal shape | **comment gate** | the post/update |
| Dashboard projection (render) | subnet | none (feeds P) | always |
| Timer/reminder scheduling | control-layer state + timer | — | — |

Two fractal shapes cover 9 of the 11 activities. The system has exactly
two world-mutation gate types; every secure exit passes through one.

## Workbench questions — resolved

| # | Question | Resolution |
| --- | --- | --- |
| 1 | Is admission/generation lifecycle a subnet or the control layer? | **The control layer itself** — no provider effects of its own; owns all DERIVED decisions (AX1 Finding 5) |
| 2 | Dashboard: subscribe to exits or derive from snapshot? | **Derive from snapshot** — relational digest currency decides it (`contracts/readiness.py:675-714`) |
| 3 | Where do the two idempotency kinds appear? | Kind 1 (skip) = lookup-first at both gates; Kind 2 (classify) = CAS failure → `discarded`, marker collision → `fault` (AX1 Finding 4) |
| 4 | Shared vs concern-specific exits? | Universal: `completed`, `discarded`, `blocked`, `fault` (+ `retryable` strictly subnet-internal); the rest is payload |

## Shared exit vocabulary

```text
completed(T)               domain result; control routes onward
discarded(StaleAuthority)  authority moved; control MAY restart (D2)
blocked(RecoverableFault)  retries exhausted; waits for explicit recovery
fault(NonrecoverableFault) classified terminal; projected, not retried
retryable                  never crosses a subnet boundary
```
