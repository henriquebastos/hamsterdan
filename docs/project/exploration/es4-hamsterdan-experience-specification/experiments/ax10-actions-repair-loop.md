# AX10 — The rerun → repair loop is a bounded escalation ladder

## Question

AX5's last MISSED items: the actions rerun → repair loop, and repair
lineage through confirmed resumes. Production spreads this across two
state places, a basis place, three guard-joined transitions with
seven read arcs, and eight flags (`topology.py:877-950, 1484-1499`).
Question: is this the one place where the cycle is real domain
structure — and if so, can a tree-authored, phase-explicit machine
with attempt/fingerprint fences express it without the flags, the
basis place, or the read arcs?

Spike: [ax10-actions-repair-loop/](ax10-actions-repair-loop/) — 16
tests, all passing; no production code touched.

## Production today: one ladder, eight flags

```text
authorize_rerun    reads authority, mutation_state      (2 read arcs)
                   consumes actions_state, actions_basis
authorize_repair   reads authority, actions_state       (2 read arcs)
                   consumes mutation_state, actions_basis
basis_retire       reads authority, actions_state,
                   mutation_state                       (3 read arcs)
                   consumes actions_basis
```

```python
# topology.py:877-900 — the two authorization predicates
def _first_failure(a, s, m, value):
    return (_current(a, value) and s.actions == "failed"
        and not s.rerun_requested                    # flag
        and s.actions_observation == value.observation
        and value.conclusion == "failure"
        and not any((m.provisional, m.change_in_flight, m.repair_in_flight)))

def _repairable(a, s, m, value):
    return (_current(a, value) and value.conclusion == "failure"
        and s.rerun_requested                        # flag
        and value.attempt > s.rerun_attempt          # flag re-deriving the event
        and not m.repair_used                        # lineage
        and not m.provisional and not m.change_in_flight
        and not m.repair_in_flight                   # in-flight
        and s.actions == "reproduced"
        and s.actions_observation == value.observation
        and value.fingerprint != m.repair_fingerprint)  # lineage
```

The domain loop underneath is a **bounded escalation ladder** — and
unlike AX8/AX9's joins, the ladder itself is genuine requirement:

```text
failure ──▶ rerun (once) ──▶ reproduced ──▶ repair (once per
fingerprint, once per PR lineage) ──▶ new head ──▶ next generation,
lineage carried (topology.py:524-530) ──▶ … ──▶ human
```

## The model: phases and fences instead of flags and reads

```python
# ax10_repair.py (abridged) — one folded value, phase-explicit
@dataclass(frozen=True)
class Actions:
    epoch: int; head: str
    phase: str = "observing"   # failed | reproduced | green | flaky_green |
                               # awaiting_confirm | discarded | repair_faulted | …
    run_id: str = ""; attempt: int = 0; fingerprint: str = ""
    repair_used: bool = False; repair_fingerprint: str = ""   # lineage

def decide(actions):
    if actions.phase == "failed":
        return (RerunWork(f"actions-rerun:{epoch}:{head}:{run_id}:{attempt}"),)
    if (actions.phase == "reproduced" and actions.fingerprint
            and not actions.repair_used                        # once per lineage
            and actions.fingerprint != actions.repair_fingerprint):  # never twice
        return (RepairWork(f"repair:{epoch}:{head}:{fingerprint}", ...),)
    return ()

def resume(prior, epoch, head):    # _start_generation:524-530 — lineage carried
    return Actions(epoch, head, repair_used=prior.repair_used,
                   repair_fingerprint=prior.repair_fingerprint)
```

Event flow for the worst case:

```text
ActionsObserved(1, failure, fp-A)   → phase=failed        → RerunWork(…run-9:1)
ActionsObserved(1, failure, fp-A)   → inert (duplicate — the fence)
ActionsObserved(2, failure, fp-A)   → phase=reproduced    → RepairWork(repair:…:fp-A)
RepairSettled(ok=True, head=h3)     → awaiting_confirm    → Quiesce(expected=h3)
   … webhook h3 → resume(epoch+1) carries repair_used, fp-A …
ActionsObserved'(2, failure, fp-A)  → reproduced, SAME fingerprint → needs_human
```

## Findings

1. **GitHub's attempt counter is the loop variable.**
   `rerun_requested`/`rerun_attempt` re-derive what the next
   observation already says: `failure@attempt=1` is a first failure,
   `failure@attempt>1` is a reproduction, `success@attempt>1` is
   flaky-green. Two flags and their maintenance vanish because the
   provider numbers the loop for us.
2. **The monotonic fence replaces the basis machinery.** A stale or
   duplicate `ActionsObserved` is inert by comparison with the folded
   `(run_id, attempt, conclusion)` — replacing the `actions_basis`
   place, the `basis_retire` transition, its `_basis_done` predicate,
   and three read arcs (tested).
3. **The in-flight guards vanish again** (AX8 finding 1): a repair in
   flight is an unfolded `RepairSettled`; the phase IS the machine.
   `change_in_flight` mutual exclusion belongs to the control layer
   (one mutation authority at a time), not to a flag in the actions
   concern.
4. **The cycle is real — but it is a ladder, not a loop.** The
   authoring stays tree-shaped: each rung emits at most one
   identity-deduped operation; the "iteration" is the *next
   generation* after the repair's own push, with lineage
   (`repair_used`, `repair_fingerprint`) carried through `resume` —
   exactly production's `_start_generation:524-530`. Boundedness is
   structural: one rerun and at most one repair per generation, the
   same fingerprint never repaired twice, the last rung always the
   human (tested: worst case emits exactly two operations).
5. **Repair outcomes route the control layer, not the net.** ok →
   `Quiesce(expected=provisional_head)` (AX6 confirm); CAS moved →
   discard and `Quiesce(expected=None)` (doctrine: preconditions
   changed, never force); agent failure → the human rung with the
   generation still running (dashboard escalation,
   `contracts/readiness.py:635`).

## Deliberate divergences, named

- **Reproduction is about the failure, not the requester.** Any
  second failure of the same run counts as reproduced; production
  only counts its own rerun, so a human-triggered rerun failing at
  attempt 2 would get one more machine rerun first. Same class:
  post-human-rerun success folds flaky_green here, green there.
- **Authorization state folds from results only** (AX9's divergence):
  `decide` re-emits the same operation until a newer observation
  folds; the AX3 gate absorbs replays.
- **CAS-moved burns the repair budget** (production parity:
  `fold_effect` sets `repair_used` on any settled repair). Marked
  OPEN: doctrine reads CAS loss as "preconditions changed", so a
  refund is arguable — a product choice, not mechanism.

## Failure modes

| Mode | Behavior |
| --- | --- |
| duplicate observation | inert at the fence (tested) |
| stale attempt / stale generation | inert (tested) |
| foreign or mistimed `RepairSettled` | inert: operation/phase mismatch (tested) |
| observation after the generation settled | inert: control owns the next move (tested) |
| rerun success | flaky_green, loop exits (tested) |
| repair on already-repaired fingerprint | no work; human rung (tested, incl. across resume) |
| repair CAS moved | discard + `Quiesce(expected=None)` (tested) |
| agent failure | `repair_faulted`, `needs_human`, generation running (tested) |
| infinite loop | structurally impossible: the ladder has three rungs and ends at the human (tested) |
| replay | refold; values only, no clock, no coroutine (tested) |

## Divergence classification

```text
rerun_requested / rerun_attempt     ACCIDENTAL — re-derive the event's attempt counter
actions_basis + basis_retire + 3    ACCIDENTAL — the fold's monotonic fence
  read arcs
repair_in_flight / provisional      ACCIDENTAL — unfolded exit + control state (AX8/AX6)
  guards in this cluster
escalation ladder itself            REQUIREMENT — kept: rerun once, repair once per
                                      fingerprint, once per lineage, human last
repair lineage across resumes       REQUIREMENT — kept as resume() carrying two fields
CAS-moved burns repair budget       OPEN (product) — model mirrors production
reproduction regardless of          OPEN (minor) — model diverges deliberately
  rerun requester
```

## Verdict

**Promising; continue.** The one real cycle in the cluster is a
bounded escalation ladder whose loop variable (attempt) and fences
(fingerprint, lineage) are domain facts, not topology. Eight flags,
one place, one transition, and seven read arcs reduce to a
phase-explicit fold plus two pure decisions — with the ladder's
boundedness now structural instead of emergent. AX5's MISSED list is
closed: AX8 (projection + announcement), AX9 (timers/reminders), AX10
(rerun → repair with lineage through resumes).
