# AX8 — The readiness projection as a fold, not a join

## Question

AX5's one honest OPEN (C4): production derives the dashboard and the
readiness announcement by *joining* nine cohort places through 25 read
arcs at three transitions (`request_dashboard` 8, `authorize_readiness`
8, `reminder_due` 9 — `readiness/net/topology.py:1104-1220`). The
requirement is the product core — readiness IS a function of every
concern's state — so the joins cannot be classified accidental the way
C1/C2/C3 were. Question: is the *join* the requirement, or only the
*mechanism*? Hypothesis: concern subnets emit typed exits; the control
layer **folds** them into one snapshot value; dashboard and
announcement decisions become pure functions of the folded value; the
25 read arcs disappear without losing a single production rule.

Spike: [ax8-projection-fold/](ax8-projection-fold/) — 8 tests, all
passing; no production code touched. Production rules mirrored from
`workflow_gates_ready` (`contracts/readiness.py:763-800`), `ready`
(`topology.py:1104-1110`), `_request_dashboard`
(`topology.py:1113-1116`).

## Production today: the marking is the snapshot

The three projection transitions each read most of the cohort:

```python
# topology.py — _dashboard reads NINE places to assemble one value
def _dashboard(binding, outputs):
    a, ac, r, h, m, fp, cp, p, rp = _values(
        binding, Authority, ActionsState, ReviewState, HumanState, ...
    )
```

The joined value feeds guards that mix three different kinds of fact:

```python
# contracts/readiness.py:763-800 (abridged)
def workflow_gates_ready(control):
    return all((
        control.actions in {"green", "flaky_green"},        # settled fact
        findings_clear, control.findings_published,          # settled fact
        control.human_approved, ...                          # settled fact
        not any((control.provisional,                        # in-flight flag
                 control.change_in_flight,
                 control.repair_in_flight)),
        not control.dashboard_capability_blocking, ...       # provider fault
    ))

# topology.py:1104-1116
def ready(s):
    return workflow_gates_ready(s) and s.dashboard_current \
        and not s.readiness_requested and not s.announced    # dedup flags

def _request_dashboard(s):
    return (not s.dashboard_current or s.dashboard_format < DASHBOARD_FORMAT) \
        and not s.dashboard_requested                        # dedup flag
```

Because the snapshot is assembled *from the live marking*, it must
carry in-flight flags (don't announce while a repair runs) and dedup
flags (`dashboard_requested`, `readiness_requested`, `announced`) —
and every flag is a place, every place read is an arc, and `Authority`
alone accumulates degree 46.

## The model: exits fold, decisions derive

```text
production                              proposed
──────────────────────────────          ──────────────────────────────
9 concern places                        typed concern exits (ports)
   │ 25 read arcs                          │ ordinary token flow
   ▼                                       ▼
3 join transitions                      fold(snapshot, exit) → snapshot
   │ guards over marking + flags           │ one immutable value/generation
   ▼                                       ▼
dashboard / announce / remind           decide(snapshot) → work items
```

```python
# ax8_projection.py (abridged)
@dataclass(frozen=True)
class Snapshot:            # one value per generation, fresh at AX6 resume
    epoch: int; head: str
    actions: str = "unknown"; review: str = "unknown"; ...
    published_projection: str = ""; announced: bool = False

def fold(snapshot: Snapshot, exit_value: Exit) -> Snapshot:
    match exit_value:
        case ActionsSettled(a):        return replace(snapshot, actions=a)
        case ReviewSettled(r, b):      return replace(snapshot, review=r, blocking_findings=b)
        case DashboardAcknowledged(p): return replace(snapshot, published_projection=p)
        case AnnouncementAcknowledged(): return replace(snapshot, announced=True)
        ...

def decide(snapshot) -> tuple[DashboardWork | AnnounceWork, ...]:
    work = []
    if wants_dashboard(snapshot):      # projection drift, no flag
        work.append(DashboardWork(f"dashboard:{epoch}:{head}:{digest}", digest))
    if is_ready(snapshot):             # gates AND dashboard current AND not announced
        work.append(AnnounceWork(f"readiness:{epoch}:{head}:{digest}"))
    return tuple(work)
```

Event flow for the green path:

```text
ActionsSettled(green) ─┐
ReviewSettled(clear)  ─┤ fold (any order — commutative      decide →
FindingsPublished     ─┤ across independent concerns)       DashboardWork
HumanSettled(ok)      ─┘                                        │ AX3 gate publishes
DashboardAcknowledged(digest) → fold                         decide → AnnounceWork
AnnouncementAcknowledged      → fold                         decide → () settled
```

## Finding 1: the in-flight flags have nothing left to guard

Production guards readiness with `provisional` / `change_in_flight` /
`repair_in_flight` because its snapshot is assembled from a marking
that mixes settled state with work-in-progress. The fold sees only
**settled exits**: while a repair runs, the actions exit it will
eventually produce simply *has not folded* — actions is still
`failed`, readiness is already false, there is nothing to suppress.
And while `Quiescent` (AX6), the control layer runs no decisions at
all. Tested: `test_in_flight_work_is_simply_an_unfolded_exit`.

This upgrades AX5's C2 verdict: the in-flight flags are not merely
*mechanically* accidental (flag-as-place); in the fold model the
guards themselves are residue of deriving decisions from a live
marking instead of from settled facts.

## Finding 2: operation identity replaces the dedup flags

`dashboard_requested`, `readiness_requested`, `announced`-reset are
request-identity bookkeeping. In the fold model the decision identity
IS the operation identity — `dashboard:{epoch}:{head}:{digest}` — so
the same folded state can only ever emit the same operation, and the
AX3 attempt-first gate absorbs replays lookup-first. Idempotency
needs no flags. Tested:
`test_same_state_emits_the_same_operation_not_a_flag`,
`test_dashboard_requested_on_drift_and_settled_on_ack`.

`announced` survives as a folded fact (it is a settled outcome, not a
dedup flag), and it needs no reset machinery: an AX6 resume starts a
fresh `Snapshot(epoch+1)`, so "announce once per generation" is a
consequence of the snapshot's lifetime, not a rule. Tested:
`test_fresh_generation_announces_again_without_reset_logic`,
`test_regression_after_announce_flips_ready_off_and_updates_dashboard`.

## Order, replay, durability

- **Commutativity.** Exits touching different concerns fold to the
  same snapshot in any arrival order (tested over all 24 permutations
  of the four green exits). Exits of the *same* concern are ordered by
  that concern's own subnet — the fold does not reintroduce
  arrival-order coupling.
- **Replay.** The fold is event-sourced by construction: the snapshot
  is a left fold over the generation's exit events, rebuildable from
  the existing event log. The snapshot is a projection/cache, never
  authoritative state — losing it costs a refold, not correctness.
  No live builder or runtime object becomes durable state.
- **Serialization.** Exits are frozen dataclasses (typed port
  payloads per AX4); the snapshot is a frozen dataclass of scalars.
  Both serialize trivially.
- **Debugging.** "Why isn't this PR announced?" becomes: print one
  snapshot, see which gate is false — instead of inspecting nine
  places and three flag places across the marking.

## Failure modes

| Mode | Behavior |
| --- | --- |
| duplicate exit delivery | fold is idempotent per fact (`replace` with same value); decide emits the same operation; AX3 gate dedups |
| stale-generation exit | fold boundary is per-generation: a `Snapshot(epoch=n)` never folds an epoch-m exit; AX6 epoch increment makes stale completions inert |
| dashboard publish fails mid-flight | no ack folds → `published_projection` stays stale → decide re-emits the same operation; the gate retries or faults |
| concern regresses after announce | new exit folds, `is_ready` flips false, red dashboard still publishes, no announce (tested) |
| provider capability exhausted | classified, not modeled: a fault exit folding as a fact, or AX6 escalation — same shape either way |

## What the model deliberately omits

`distinct_reviewer_*` and `strict_base`/`base_current` gates: same
fold-shape as the modeled gates, omitted as repetitive. The nine
`*_capability_blocking`/`*_publication_fault` flags: provider-
degradation facts that fold like any other exit or escalate to AX6 —
facts, not reads. `reminder_due`'s 9 reads are deferred to AX9: the
reminder decision is another pure function of this same snapshot plus
a timer ingress.

## Divergence classification

```text
25 projection read arcs        ACCIDENTAL — the join is mechanism; the fold
                                preserves every production rule without reads
in-flight guard flags          ACCIDENTAL — residue of deciding from a live
                                marking (upgrades AX5 C2)
dedup/request flags            ACCIDENTAL — operation identity + AX3 dedup
announce-once-per-generation   REQUIREMENT — kept, as snapshot lifetime
readiness gate predicate       REQUIREMENT — kept verbatim
dashboard drift → republish    REQUIREMENT — kept, as digest inequality
```

## Verdict

**Promising; continue.** AX5's last OPEN closes: the projection
requirement survives intact as a pure `decide` over a folded snapshot;
the 25 read arcs, three in-flight guards, and three dedup flags are
all mechanism, all accidental. The fold also gives AX9 its natural
home — `reminder_due`'s 9 reads should become `decide_reminder(snapshot,
TimerDue)` — which is the next experiment.
