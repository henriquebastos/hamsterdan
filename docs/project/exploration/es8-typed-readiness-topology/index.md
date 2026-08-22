---
status: Promoted
opened: 2026-08-21
promoted: 2026-08-22
navigator: Henrique
---

# ES-008 — Typed readiness decisions as production V5 topology

## Inquiry

Does production V5 hide durable semantic alternatives inside pure Python
folds that the Petri net should express as specialized token colors, places,
and transitions? The bounded experiment targets readiness's open
`GateFact(kind, body)` mailbox and leaves V5's actor-loop ownership and
dashboard projection contract unchanged.

The test is deliberately direct: change production V5 without committing or
promoting it, use the existing behavior and replay tests as the oracle, then
compare the resulting net. If the result does not earn promotion, remove the
experimental production changes and retain this record only.

## Boundary

- Replace only the readiness decision mailbox and its `kind` dispatcher.
- Keep `GateFact` as the dashboard's open projection envelope; dashboard-only
  events do not become readiness types.
- Preserve the existing JSON projection shape (`kind`, `incarnation`, `body`).
- Preserve actor-loop ownership, announcement races, replay, close drains,
  recovery, and dashboard behavior.
- Do not use filters for current readiness facts: these are modeled outcomes,
  not same-type value predicates. Filters are reserved for the input-only
  legacy envelope migration described below.

## Result

Readiness now receives nine strict colors through nine places and nine named
fold transitions: state, checks, review, findings, human, mutation pending,
mutation settled, fault raised, and fault cleared. The `_apply` kind/body
dispatcher no longer exists. Each producer emits the specialized fact to
readiness and the same wire-compatible value to the existing dashboard
envelope.

The former `ready.facts` path remains input-only because a process interrupted
before promotion may retain a token there. Nine filtered migration transitions
convert those envelopes into specialized colors; no current production
transition can emit to the legacy place. Both a quiescent pre-promotion history
and a history cut with a retained legacy checks fact were opened against the
promoted net; the latter migrated and drained to the correct snapshot.

Splitting the mailbox exposed a previously hidden invariant. The old shared
FIFO happened to fold state authority before CI/review evidence emitted by
that admission. Independent typed places removed that ordering, and the
durable host test observed checks for incarnation 1 fold inertly against the
incarnation-0 snapshot. The repaired topology states the rule directly:
`ready.state_facts` inhibits every incarnation-scoped fact fold. Authorization
and deferred wake remain inhibited until every typed mailbox is quiet.
Two further producer-causality rules are now explicit: mutation pending folds
before mutation settled, and a recovery's fault-clear folds before a same-drive
re-fault.

## Comparison

| Measure | Before | Experiment | Delta |
| --- | ---: | ---: | ---: |
| Places | 99 | 108 | +9 |
| Transitions | 112 | 137 | +25 |
| Arcs | 453 | 570 | +117 |
| Arcs / node | 2.147 | 2.327 | +0.180 |
| Inhibitor arcs | 4 | 38 | +34 |
| Guards | 0 | 0 | 0 |
| Filtered arcs | 0 | 17 | +17 |

The production source changes by +777/-200 lines; 153 added lines are
the strict fact/body contracts, while the rest is explicit producer routing,
folds, drains, migration, and ordering/authorization arcs. The cost is real:
topology and code are larger, especially because post-close drain behavior,
mailbox quiescence, and cross-version recovery must be complete for every
specialized place.

## Evidence

- Focused production-loop oracle: 163 tests pass.
- Complete V5 loop plus host oracle: 484 tests pass.
- Repository checkpoint: `scripts/check full` passes, including 1,250 Python
  tests and 53 Bun tests (9 relay plus 44 demo-video tests).
- Strict fact JSON was checked to hydrate both as its exact specialized type
  and as the unchanged dashboard `GateFact` projection.
- Structural tests pin every mailbox's exact color and fold, all authorization
  and causal-ordering inhibitors, zero guards, and filters exclusively on the
  legacy migration boundary.
- A cross-version crash-cut check created History with `origin/main`, retaining
  one token at `ready.facts`, then opened and drained it with the promoted net.

## Navigator verdict — promoted 2026-08-22

**Promote this bounded readiness refactor and the design rule it demonstrates.**
The experiment does more than move an `if` statement: it makes the admitted
semantic alternatives, their type contracts, quiescence requirement, and a
previously accidental FIFO authority rule inspectable in the net. Full
behavioral parity supports keeping the production change despite the measured
topology cost.

The rule is not “turn every Python branch into a place.” Promote a decision
when its alternatives are durable domain meanings or when ordering between
those meanings affects enabledness. Keep local computations inside a typed
fold, and use filters only for total routing among predicates over one honest
type. Apply the rule to another V5 loop only through a separately measured
slice; conversation classification and lifecycle admission remain candidates,
not scope silently included here.

The Navigator accepted the bounded production refactor, its design rule, and
the input-only compatibility lane after the implementation, experience, and
promotion review checkpoints. The durable ruling lives in the linked decision
record; this exploration retains the experiment and comparison evidence.
