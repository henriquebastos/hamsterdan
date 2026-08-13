"""ES-004 AX8 — the readiness projection as a fold over subnet exits.

AX5's one honest OPEN: production computes readiness by joining nine
cohort places through 25 read arcs at three transitions
(request_dashboard 8, authorize_readiness 8, reminder_due 9). The
requirement — derive readiness from all concern states — is the
product core and untouchable. This spike tests the alternative
mechanism: concern subnets emit typed exits; the control layer FOLDS
them into a snapshot value; the derived decisions (dashboard,
announce) are pure functions of the fold.

Production rules mirrored, with the omissions classified (not hidden):

- gates: the core of `workflow_gates_ready`
  (contracts/readiness.py:763-800) — actions green/flaky_green,
  review clear with no blocking findings, findings published, human
  approved, no changes requested, no unresolved conversations,
  mergeable, no conflict;
- `ready`: gates AND dashboard_current AND not requested AND not
  announced (topology.py:1104-1110);
- `_request_dashboard`: projection drift or format bump, AND not
  already requested (topology.py:1113-1116).

Deliberately omitted from the model, each with its fold-shape:

- `distinct_reviewer_required/approved`, `base_current or not
  strict_base`: same shape as the modeled gates — settled facts a
  concern exit would fold; omitted as repetitive, not different.
- nine `*_capability_blocking` / `*_publication_fault` flags:
  provider-degradation facts. In the fold model these are exits of
  the provider gates themselves (a gate that exhausts its budget
  emits a typed fault exit) — same fold shape — OR they escalate to
  the AX6 control state (Quiescent/Terminal) when the whole
  generation cannot proceed. Either way they are facts, not reads.
- `provisional` / `change_in_flight` / `repair_in_flight`: NOT
  omitted — eliminated. See finding 1 below.

Two structural findings this spike is designed to surface:

1. Production's in-flight guards (`provisional`, `change_in_flight`,
   `repair_in_flight` inside workflow_gates_ready) exist because its
   snapshot mixes settled state with in-flight flags. The fold sees
   only SETTLED exits — work in flight is simply "not yet folded",
   and the AX6 control state already refuses decisions while
   Quiescent. The flags have nothing left to guard.

2. Production's `dashboard_requested` / `readiness_requested` /
   `announced` dedup flags are request-identity bookkeeping. In the
   fold model, decision identity IS the operation identity —
   (epoch, projection digest) — so idempotency needs no flags: the
   same folded state can only ever emit the same operation, and the
   gate's lookup-first (AX3) absorbs the replay.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# -- the folded snapshot (settled facts only — no in-flight flags) ----------------------


@dataclass(frozen=True)
class Snapshot:
    """One value per generation, folded from subnet exits. Fresh at
    every AX6 resume (epoch+1), so `announced` needs no reset logic."""

    epoch: int
    head: str
    actions: str = "unknown"  # unknown | green | flaky_green | failed | …
    review: str = "unknown"  # unknown | clear | blocking
    blocking_findings: int = 0
    findings_published: bool = False
    human_approved: bool = False
    changes_requested: bool = False
    unresolved_conversations: int = 0
    mergeable: bool = True
    conflict: bool = False
    published_projection: str = ""  # digest the dashboard currently shows
    announced: bool = False
    reminder_snoozed: bool = False  # AX7 durable note (used by AX9)


# -- subnet exit events (each is a typed port payload, not a place read) -----------------


@dataclass(frozen=True)
class ActionsSettled:
    actions: str  # fold_actions vocabulary: green | flaky_green | failed | …


@dataclass(frozen=True)
class ReviewSettled:
    review: str
    blocking_findings: int


@dataclass(frozen=True)
class FindingsPublished:
    pass


@dataclass(frozen=True)
class HumanSettled:
    approved: bool
    changes_requested: bool
    unresolved_conversations: int


@dataclass(frozen=True)
class DashboardAcknowledged:
    projection: str  # the digest the gate confirmed is now visible


@dataclass(frozen=True)
class AnnouncementAcknowledged:
    pass


@dataclass(frozen=True)
class ReminderSnoozed:  # AX7 durable note landing in the snapshot
    snoozed: bool


type Exit = (
    ActionsSettled
    | ReviewSettled
    | FindingsPublished
    | HumanSettled
    | DashboardAcknowledged
    | AnnouncementAcknowledged
    | ReminderSnoozed
)


def fold(snapshot: Snapshot, exit_value: Exit) -> Snapshot:
    """Pure, and commutative across INDEPENDENT concerns: two exits
    touching different fields can arrive in either order. Exits of the
    same concern are naturally ordered by that concern's subnet."""

    match exit_value:
        case ActionsSettled(actions):
            return replace(snapshot, actions=actions)
        case ReviewSettled(review, blocking):
            return replace(snapshot, review=review, blocking_findings=blocking)
        case FindingsPublished():
            return replace(snapshot, findings_published=True)
        case HumanSettled(approved, changes, unresolved):
            return replace(
                snapshot, human_approved=approved, changes_requested=changes, unresolved_conversations=unresolved
            )
        case DashboardAcknowledged(projection):
            return replace(snapshot, published_projection=projection)
        case AnnouncementAcknowledged():
            return replace(snapshot, announced=True)
        case ReminderSnoozed(snoozed):
            return replace(snapshot, reminder_snoozed=snoozed)


# -- the derived decisions (pure functions of the fold) -----------------------------------


def projection(snapshot: Snapshot) -> str:
    """The dashboard content digest — what production computes as
    dashboard_projection_digest over nine places, here a function of
    one value."""
    facts = (
        snapshot.actions,
        snapshot.review,
        snapshot.blocking_findings,
        snapshot.findings_published,
        snapshot.human_approved,
        snapshot.changes_requested,
        snapshot.unresolved_conversations,
    )
    return f"proj-{hash(facts) & 0xFFFFFF:06x}"


def gates_ready(snapshot: Snapshot) -> bool:
    """`workflow_gates_ready`, minus the in-flight flags (finding 1:
    the fold sees only settled exits, and Quiescent already stops all
    decisions — there is no in-flight to guard against here)."""
    return all(
        (
            snapshot.actions in {"green", "flaky_green"},
            snapshot.review == "clear" and snapshot.blocking_findings == 0,
            snapshot.findings_published,
            snapshot.human_approved,
            not snapshot.changes_requested,
            snapshot.unresolved_conversations == 0,
            snapshot.mergeable,
            not snapshot.conflict,
        )
    )


def wants_dashboard(snapshot: Snapshot) -> bool:
    """Projection drift — production's `_request_dashboard`, without
    the `dashboard_requested` flag (finding 2: operation identity
    dedups instead)."""
    return snapshot.published_projection != projection(snapshot)


def is_ready(snapshot: Snapshot) -> bool:
    """Production's `ready`: gates AND the published dashboard is
    current AND not yet announced this generation."""
    return gates_ready(snapshot) and not wants_dashboard(snapshot) and not snapshot.announced


# -- decision → work, with identity instead of flags ----------------------------------------


@dataclass(frozen=True)
class DashboardWork:
    operation: str
    projection: str


@dataclass(frozen=True)
class AnnounceWork:
    operation: str


def decide(snapshot: Snapshot) -> tuple[DashboardWork | AnnounceWork, ...]:
    """Everything the control layer may emit for this snapshot. The
    operation string IS the dedup: the same folded state can only
    produce the same operations, and the attempt-first gates (AX3)
    absorb replays lookup-first."""
    work: list[DashboardWork | AnnounceWork] = []
    if wants_dashboard(snapshot):
        digest = projection(snapshot)
        work.append(DashboardWork(f"dashboard:{snapshot.epoch}:{snapshot.head}:{digest}", digest))
    if is_ready(snapshot):
        work.append(AnnounceWork(f"readiness:{snapshot.epoch}:{snapshot.head}:{projection(snapshot)}"))
    return tuple(work)
