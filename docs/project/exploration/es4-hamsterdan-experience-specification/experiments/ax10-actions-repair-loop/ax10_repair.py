"""ES-004 AX10 — the actions rerun → repair loop as a bounded escalation ladder.

Production spreads this loop across two state places (ActionsState,
MutationState), a basis place (actions_basis), three guard-joined
transitions with seven read arcs (authorize_rerun 2, authorize_repair
2, basis_retire 3), and eight flags (rerun_requested, rerun_attempt,
repair_used, repair_fingerprint, repair_in_flight,
repair_recovery_required, provisional, change_in_flight) —
topology.py:877-950, 1484-1499.

The domain loop underneath is a BOUNDED ESCALATION LADDER, and this
is the one place where the cycle is real requirement, not accidental
topology:

    failure ──▶ rerun (once) ──▶ reproduced ──▶ repair (once per
    fingerprint, once per PR lineage) ──▶ new head ──▶ next
    generation, lineage carried ──▶ … or human.

Production rules mirrored:

- `fold_actions` (topology.py:295-319): conclusion → phase mapping,
  fingerprint capture, flaky-green on post-rerun success;
- `_first_failure` (877-885) / `_repairable` (888-900): the ladder's
  two authorization predicates;
- `_accept_repair` (835-841) + `fold_effect` (381-402): repair result
  folding, fingerprint defaulting, repair_used burned on ANY settled
  repair;
- `_start_generation` (524-530): repair_used / repair_fingerprint
  carried into every new generation — the AX5 MISSED "repair lineage
  through confirmed resumes";
- dashboard escalation (`contracts/readiness.py:635`): reproduced +
  repair_used ⇒ "human repair authorization".

Structural findings this spike is designed to surface:

1. `rerun_requested` / `rerun_attempt` are RE-DERIVATIONS of the
   observation's own attempt counter. GitHub numbers the attempts;
   `failure@attempt=1` is a first failure, `failure@attempt>1` is a
   reproduction, `success@attempt>1` is flaky. The flags exist to
   remember what the next event already says.
2. `repair_in_flight` / `provisional` guards vanish for the AX8
   reason: in-flight work is an unfolded exit; the phase IS the
   machine. `change_in_flight` mutual exclusion is the control
   layer's job (one mutation authority), not a flag in the actions
   concern.
3. `actions_basis` + `basis_retire` (a place, a transition, three
   read arcs) are replaced by the fold's monotonic fence: a stale or
   duplicate observation is inert by comparison with the folded
   (run_id, attempt, conclusion).

Deliberate divergences, named:

- Any second failure of the same run counts as reproduced, whoever
  triggered the rerun. Production only counts its own
  (`rerun_requested`): a human-triggered rerun failing at attempt 2
  would get OUR rerun at attempt 3 before repair. The failure
  reproduced either way; the requester is not part of the domain
  question. Same class: success@attempt>1 is flaky_green even for a
  human-triggered rerun.
- Re-arm/authorization state folds only from results (AX9's
  divergence): decide re-emits the same operation until a newer
  observation folds; the AX3 gate dedups lookup-first.
- CAS-moved repair keeps production's repair_used=True (the budget is
  burned). Marked OPEN below: doctrine says CAS loss is
  "preconditions changed", so a refund is arguable — but that is a
  product choice, not a mechanism choice.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# -- the folded concern state: phase-explicit, flag-free ------------------------------------

RUNNING = {"queued", "requested", "waiting", "in_progress"}
CONTROL_SETTLED = {"awaiting_confirm", "discarded"}  # control layer owns the next move


@dataclass(frozen=True)
class Actions:
    epoch: int
    head: str
    phase: str = "observing"
    # observing | running | failed | reproduced | green | flaky_green
    # | halted:<conclusion> | awaiting_confirm | discarded | repair_faulted
    run_id: str = ""
    attempt: int = 0
    conclusion: str = ""
    fingerprint: str = ""
    provisional_head: str = ""
    # lineage — survives generations (topology.py:524-530)
    repair_used: bool = False
    repair_fingerprint: str = ""


def resume(prior: Actions, epoch: int, head: str) -> Actions:
    """`_start_generation`: fresh concern state, lineage carried."""
    return Actions(epoch=epoch, head=head, repair_used=prior.repair_used, repair_fingerprint=prior.repair_fingerprint)


# -- typed exits ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionsObserved:
    """GitHub's fact. The attempt counter is GitHub's own loop
    variable — production's rerun_requested/rerun_attempt re-derive it."""

    epoch: int
    head: str
    run_id: str
    attempt: int
    conclusion: str  # success | failure | canceled | unavailable | queued | …
    fingerprint: str = ""


@dataclass(frozen=True)
class RepairSettled:
    """AX3 gate completion for RepairWork. `category` mirrors the
    provider outcome: '' (agent failure), 'cas_moved' (push lost the
    race — preconditions changed)."""

    epoch: int
    head: str
    operation: str
    ok: bool
    provisional_head: str = ""
    fingerprint: str = ""
    category: str = ""


type Exit = ActionsObserved | RepairSettled


def _observe(actions: Actions, value: ActionsObserved) -> Actions:
    known = (
        value.run_id == actions.run_id
        and (
            value.attempt < actions.attempt
            or (value.attempt == actions.attempt and value.conclusion == actions.conclusion)
        )
    )
    if known:  # the monotonic fence — production's actions_basis + basis_retire
        return actions
    facts = dict(run_id=value.run_id, attempt=value.attempt, conclusion=value.conclusion)
    if value.conclusion in RUNNING:
        return replace(actions, phase="running", **facts)
    if value.conclusion == "success":  # fold_actions: flaky iff a rerun succeeded
        return replace(actions, phase="flaky_green" if value.attempt > 1 else "green", **facts)
    if value.conclusion == "failure":  # fold_actions: reproduced iff a rerun failed
        phase = "reproduced" if value.attempt > 1 else "failed"
        return replace(actions, phase=phase, fingerprint=value.fingerprint, **facts)
    return replace(actions, phase=f"halted:{value.conclusion}", **facts)  # canceled, unavailable…


def fold(actions: Actions, exit_value: Exit) -> Actions:
    if exit_value.epoch != actions.epoch or exit_value.head != actions.head:
        return actions  # stale generation — inert
    if actions.phase in CONTROL_SETTLED:
        return actions  # the generation is over; control owns the next move
    match exit_value:
        case ActionsObserved() as value:
            return _observe(actions, value)
        case RepairSettled() as value:
            if actions.phase != "reproduced" or value.operation != _repair_operation(actions):
                return actions  # not ours — inert
            burned = dict(  # production burns the budget on ANY settled repair
                repair_used=True,
                repair_fingerprint=value.fingerprint or actions.fingerprint,  # _accept_repair default
            )
            if value.ok:
                return replace(actions, phase="awaiting_confirm", provisional_head=value.provisional_head, **burned)
            if value.category == "cas_moved":  # preconditions changed: discard, never force
                return replace(actions, phase="discarded", **burned)
            return replace(actions, phase="repair_faulted", **burned)


# -- pure decisions ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RerunWork:
    operation: str


@dataclass(frozen=True)
class RepairWork:
    operation: str
    fingerprint: str


def _repair_operation(actions: Actions) -> str:
    return f"repair:{actions.epoch}:{actions.head}:{actions.fingerprint}"


def decide(actions: Actions) -> tuple[RerunWork | RepairWork, ...]:
    """The ladder: each rung emits at most one operation, identity-
    deduped. `_first_failure` and `_repairable` reduce to phase
    checks plus the two lineage fences."""
    if actions.phase == "failed":
        return (RerunWork(f"actions-rerun:{actions.epoch}:{actions.head}:{actions.run_id}:{actions.attempt}"),)
    repairable = (
        actions.phase == "reproduced"
        and bool(actions.fingerprint)
        and not actions.repair_used  # one auto-repair per PR lineage
        and actions.fingerprint != actions.repair_fingerprint  # never the same failure twice
    )
    if repairable:
        return (RepairWork(_repair_operation(actions), actions.fingerprint),)
    return ()


def needs_human(actions: Actions) -> bool:
    """The ladder's last rung — dashboard's 'human repair
    authorization' (contracts/readiness.py:635)."""
    exhausted = actions.repair_used or actions.fingerprint == actions.repair_fingerprint
    return (actions.phase == "reproduced" and exhausted) or actions.phase == "repair_faulted"


@dataclass(frozen=True)
class Quiesce:
    """The control layer's move (AX6): expected head or plain wait."""

    expected: str | None


def control_move(actions: Actions) -> Quiesce | None:
    if actions.phase == "awaiting_confirm":
        return Quiesce(expected=actions.provisional_head)  # our push; confirm on webhook
    if actions.phase == "discarded":
        return Quiesce(expected=None)  # someone else's head is coming
    return None
