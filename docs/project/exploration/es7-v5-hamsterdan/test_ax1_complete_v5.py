"""AX1 — the complete cohabited V5 Hamsterdan: nine actor loops, ONE instance.

Greenfield from the ES-005 chapter-17 boundary contract as translated
by AX0 (oracle-amended). Every loop = mailbox(es) + private baton +
round pipeline + pure folds; cross-loop communication is declared
arcs only (AX7 anti-braid invariant). No guards, no read arcs, no
filters, no epochs — the only epoch survivor is the **incarnation**
counter living as data in the lifecycle baton (AX0 amendment A1).

The nine loops:

- **lifecycle** — the admission hub: all external observations enter
  here; its pure folds decide what work facts to emit. Dormancy is
  the baton saying Quiescent; nothing is drained or seeded.
- **review** — AX6's loop plus A2 publication state
  (Idle/Pending/Blocked/Faulted), recovery with the SAME effect
  identity, and dismissals.
- **ci** — pure observation folds: newest exact-head run wins;
  payload status is never trusted.
- **escalation** — the ladder: rerun once, then repair once per
  fingerprint, then human. `moved` never burns budget.
- **conversation** — never ends: read-only replies in ANY state
  including Terminal; committing intents only from Running.
- **mutation** — the baton IS the one-at-a-time serialization;
  server-side CAS; a fault fails closed but the baton always returns.
- **dashboard** — mutable singleton; republish on digest drift only.
- **reminder** — maturity is a durable fact; snooze suppresses the
  decision, never the fact.
- **readiness** — the projection: folds seven fact kinds into one
  snapshot; incarnation-mismatched facts are inert; announce-once per
  incarnation recorded on acknowledgment (A1.6).

A1.5 authority classification (oracle-demanded, explicit):

- **Authority-sensitive** — request carries the full claim
  `(incarnation, head, base, policy, operation)` and its gate fences
  every field: findings publication, readiness announcement, git
  mutation (head via server-side CAS, base/policy via fresh read),
  CI rerun (moved burns no budget).
- **Authority-orthogonal by design** — read-only or projection
  effects whose content derives from current durable state; landing
  late is at worst cosmetically outdated (Navigator-accepted):
  conversation replies (answer in ANY state), reminder comments
  (about the PR's clock, not the head's content), dashboard upsert
  (idempotent overwrite, self-healing on the next fact).

A2 custody styles (both durable, each loop uses exactly one):

- **held baton** — the memory travels inside the round token and the
  place stays empty until a terminal fold returns it: review,
  escalation rerun, mutation, dashboard (incl. recovery).
- **recorded pending** — the baton returns immediately but carries an
  explicit pending record so single-flight is data, not luck:
  readiness (`announcing`), reminder (`pending` per timer),
  conversation (`pending` per reply id — deliberately concurrent).

The tests execute AX0's A4 acceptance timelines on the frozen engine
with a fake GitHub world, then replay the chronicle.
"""

from dataclasses import dataclass, field

from ax5_compiler import VariantPayloadConverter, VariantRoutingActivityHandler
from petrus.engine import Engine, choose_throughput
from petrus.impetus.binding import DerivedActivityHandler
from petrus.impetus.dsl import BuiltNet, NetSpec, petri_handler
from petrus.impetus.history import ActivityRequested
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch, InMemoryDispatch

# ---------------------------------------------------------------------------
# Ingress colors (host-normalized observations)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeadSeen:
    head: str
    base: str
    mergeable: bool
    policy: str  # the host's current policy version (A1.5 authority field)


@dataclass(frozen=True)
class DraftSeen:
    pass


@dataclass(frozen=True)
class ReadySeen:
    pass


@dataclass(frozen=True)
class CloseSeen:
    reason: str


@dataclass(frozen=True)
class CommentSeen:
    id: str
    kind: str
    arg: str
    authorized: bool


@dataclass(frozen=True)
class HumanSeen:
    approval: bool
    changes_requested: bool
    unresolved: int


@dataclass(frozen=True)
class RunSeen:
    head: str
    run_id: int
    attempt: int
    conclusion: str
    fingerprint: str


@dataclass(frozen=True)
class TimerDue:
    timer_id: str


# ---------------------------------------------------------------------------
# Batons (one per loop; the mem dict travels through round tokens)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LifeState:
    phase: str  # running | quiescent | terminal
    incarnation: int
    head: str
    base: str
    mergeable: bool
    policy: str
    expected: str
    expected_op: str
    lineage: str


@dataclass(frozen=True)
class ReviewMemory:
    reviewed: list[str] = field(default_factory=list)
    provisional: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    dismissed: list[str] = field(default_factory=list)
    pub: dict = field(default_factory=lambda: {"phase": "idle"})


@dataclass(frozen=True)
class CiMemory:
    head: str = ""
    base: str = ""  # current authority for escalation requests (A1.5)
    policy: str = ""
    lineage: str = ""  # budget lineage: fresh on new/superseded, kept on confirmed/resumed
    incarnation: int = 0
    best: list = field(default_factory=list)  # [run_id, attempt] or []
    status: str = "pending"
    fingerprint: str = ""  # the best run's failure fingerprint ("" if none)
    parked: list = field(default_factory=list)  # fps whose escalation MOVED
    # under my current authority; a fresh admission reissues them


@dataclass(frozen=True)
class Ladder:
    reruns: dict = field(default_factory=dict)  # "{lineage}:{fp}" -> done|fault
    repairs: dict = field(default_factory=dict)  # "{lineage}:{fp}" -> pending|done|fault
    rerun_faults: dict = field(default_factory=dict)  # key -> {op, reason} (A2 retention)


@dataclass(frozen=True)
class ConvMemory:
    served: list[str] = field(default_factory=list)
    pending: dict = field(default_factory=dict)  # id -> reply text in flight (A2)
    blocked: dict = field(default_factory=dict)  # id -> retained reply text
    faulted: dict = field(default_factory=dict)  # id -> reason


@dataclass(frozen=True)
class MutState:
    state: str = "idle"  # idle | faulted
    op_key: str = ""  # faulted retention: the exact operation identity
    op: str = ""
    head: str = ""
    base: str = ""  # faulted retention of the FULL authority claim (A1.5)
    policy: str = ""
    incarnation: int = 0
    reason: str = ""


@dataclass(frozen=True)
class DashMemory:
    entries: list[str] = field(default_factory=list)
    digest: str = ""
    blocked: dict = field(default_factory=dict)  # retained {digest} while blocked
    faulted: dict = field(default_factory=dict)  # retained {digest, reason} (A2)


@dataclass(frozen=True)
class RemState:
    matured: list[str] = field(default_factory=list)
    snoozed: bool = False
    deferred: list[str] = field(default_factory=list)
    pending: dict = field(default_factory=dict)  # timer_id -> True while in flight (A2)
    blocked: dict = field(default_factory=dict)  # timer_id -> True
    faulted: dict = field(default_factory=dict)  # timer_id -> reason (A2 retention)
    closing: str = ""  # close reason retained while a terminal is outstanding


@dataclass(frozen=True)
class Snapshot:
    incarnation: int = 0
    phase: str = "running"
    head: str = ""
    base: str = ""
    mergeable: bool = False
    policy: str = ""
    checks: str = "pending"
    findings_blocking: int = 0
    approval: bool = False
    changes_requested: bool = False
    unresolved: int = 0
    pending: list[str] = field(default_factory=list)
    faults: list[str] = field(default_factory=list)
    announced: list[int] = field(default_factory=list)
    announcing: dict = field(default_factory=dict)  # the EXACT in-flight request (A2)
    blocked: dict = field(default_factory=dict)  # retained announce request
    closing: str = ""  # close reason retained while a terminal is outstanding


# ---------------------------------------------------------------------------
# Directed facts (loop → loop, dedicated colors)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeadWork:
    incarnation: int
    head: str
    base: str
    policy: str
    relation: str  # new | superseded | confirmed | resumed | refreshed
    lineage: str


@dataclass(frozen=True)
class IntentFact:
    id: str
    kind: str
    arg: str
    authorized: bool
    phase: str
    provisional: bool  # lifecycle holds an expected head (A1.2)
    incarnation: int
    head: str
    base: str  # authority claimed at admission time (A1.5)
    policy: str


@dataclass(frozen=True)
class CloseFact:
    reason: str


@dataclass(frozen=True)
class RunWork:
    incarnation: int
    head: str
    run_id: int
    attempt: int
    conclusion: str
    fingerprint: str


@dataclass(frozen=True)
class ChecksFailure:
    fingerprint: str
    head: str
    base: str
    policy: str
    lineage: str  # ladder budget is per fingerprint PER LINEAGE
    incarnation: int


@dataclass(frozen=True)
class MutationRequest:
    op: str
    head: str
    base: str  # full authority claim; the gate compares ALL fields (A1.5)
    policy: str
    incarnation: int
    source: str


@dataclass(frozen=True)
class MutationSettled:
    op: str
    outcome: str  # landed | moved | faulted | declined
    incarnation: int
    fingerprint: str


@dataclass(frozen=True)
class ProvisionalHead:
    expected: str
    op: str
    lineage: str


@dataclass(frozen=True)
class RecoverFact:
    target: str
    op: str


@dataclass(frozen=True)
class DismissFact:
    finding_id: str


@dataclass(frozen=True)
class SnoozeFact:
    mode: str  # snooze | clear | defer
    arg: str


@dataclass(frozen=True)
class GateFact:
    """The projection envelope consumed by readiness and dashboard."""

    kind: str
    incarnation: int
    body: dict


# ---------------------------------------------------------------------------
# Review pipeline colors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoundOpen:
    head: str
    base: str
    policy: str
    incarnation: int
    mem: dict


@dataclass(frozen=True)
class AgentReview:
    head: str
    base: str
    policy: str
    incarnation: int
    findings: list[dict]
    mem: dict


@dataclass(frozen=True)
class Publishable:
    head: str
    base: str
    policy: str
    incarnation: int
    findings: list[dict]
    effect: str
    op: str
    mem: dict


@dataclass(frozen=True)
class EmptyReview:
    head: str
    incarnation: int
    mem: dict


@dataclass(frozen=True)
class LandedR:
    head: str
    incarnation: int
    findings: list[dict]
    effect: str
    mem: dict


@dataclass(frozen=True)
class MovedR:
    head: str
    # the FULL authority the gate observed at effect time (grant + live)
    observed: str
    observed_base: str
    observed_policy: str
    observed_incarnation: int
    observed_phase: str
    findings: list[dict]
    mem: dict


@dataclass(frozen=True)
class BlockedR:
    head: str
    base: str
    policy: str
    incarnation: int
    findings: list[dict]
    effect: str
    op: str
    mem: dict


@dataclass(frozen=True)
class FaultR:
    reason: str
    mem: dict


@dataclass(frozen=True)
class ReviewEnded:
    reviewed: list[str]
    pub_phase: str
    reason: str


# -- other pipeline colors ---------------------------------------------------


@dataclass(frozen=True)
class CiEnded:
    status: str
    reason: str


@dataclass(frozen=True)
class RerunReq:
    fingerprint: str  # composite budget key "{lineage}:{fp}"
    fp: str  # the raw fingerprint (for the moved-echo recheck)
    op: str  # stable operation identity: "rerun:{key}" (lookup-first)
    head: str
    base: str  # full authority claim (A1.5)
    policy: str
    incarnation: int
    mem: dict


@dataclass(frozen=True)
class RerunLanded:
    fingerprint: str
    op: str
    mem: dict


@dataclass(frozen=True)
class RerunMoved:
    fingerprint: str
    fp: str  # raw fingerprint + the ATTEMPTED authority tuple: the echo
    head: str  # lets CI decide between reissue (fresher tuple already
    base: str  # admitted) and park (attempt used my current tuple)
    policy: str
    incarnation: int  # the attempted GRANT (draft→resume changes only this)
    op: str
    mem: dict


@dataclass(frozen=True)
class EscMoved:
    """Echo from escalation to CI: an escalation effect classified MOVED."""

    fp: str
    head: str
    base: str
    policy: str
    incarnation: int  # the ATTEMPTED grant, part of the attempted tuple


@dataclass(frozen=True)
class RerunFault:
    fingerprint: str
    op: str
    reason: str
    fp: str  # A2: the fault retains the EXACT request so the recovery
    head: str  # door can reissue the same operation identity with the
    base: str  # same authority claim (lookup-first reconciles)
    policy: str
    incarnation: int
    mem: dict


@dataclass(frozen=True)
class LadderEnded:
    reruns: dict
    repairs: dict
    reason: str


@dataclass(frozen=True)
class ReplyReq:
    id: str
    text: str


@dataclass(frozen=True)
class Replied:
    id: str
    text: str


@dataclass(frozen=True)
class ReplyBlocked:
    id: str
    text: str


@dataclass(frozen=True)
class ReplyFault:
    id: str
    reason: str


@dataclass(frozen=True)
class MutWork:
    op: str
    op_key: str  # stable operation identity for lookup-first reconciliation
    head: str
    base: str  # full authority claim; head is fenced by CAS, base/policy by fresh read (A1.5)
    policy: str
    incarnation: int


@dataclass(frozen=True)
class Pushed:
    op: str
    op_key: str
    head: str
    new_head: str
    incarnation: int
    lineage: str


@dataclass(frozen=True)
class MovedM:
    op: str
    head: str
    incarnation: int
    # the FULL authority observed at effect time (grant + live)
    observed: str
    observed_incarnation: int
    observed_phase: str


@dataclass(frozen=True)
class FaultM:
    op: str
    op_key: str
    head: str
    base: str  # retained so recovery reissues the FULL authority claim
    policy: str
    reason: str
    incarnation: int


@dataclass(frozen=True)
class MutEnded:
    state: str
    reason: str


@dataclass(frozen=True)
class DashReq:
    # the EXACT effect to execute (recovery reissues a retained request
    # verbatim) ...
    entries: list[str]
    digest: str
    # ... plus the DESIRED state the loop wants on the board. For a live
    # publish they coincide; for a recovery reissue the desired state may
    # have drifted while the fault was held, and the landed fold self-heals
    # by publishing the desired state as a FRESH effect.
    desired_entries: list[str]
    desired_digest: str


@dataclass(frozen=True)
class DashLanded:
    entries: list[str]
    digest: str
    desired_entries: list[str]
    desired_digest: str


@dataclass(frozen=True)
class DashBlocked:
    entries: list[str]
    digest: str
    desired_entries: list[str]
    desired_digest: str


@dataclass(frozen=True)
class DashFault:
    entries: list[str]
    digest: str
    desired_entries: list[str]
    desired_digest: str
    reason: str


@dataclass(frozen=True)
class DashHeal:
    """A poke from the landed fold to the self-heal transition: the board
    landed an exact-but-drifted recovery request. The transition consumes
    the memory baton, so the reissue cycle stays baton-serialized."""

    digest: str


@dataclass(frozen=True)
class DashEnded:
    entries: list[str]
    reason: str


@dataclass(frozen=True)
class RemReq:
    timer_id: str


@dataclass(frozen=True)
class RemLanded:
    timer_id: str


@dataclass(frozen=True)
class RemBlocked:
    timer_id: str


@dataclass(frozen=True)
class RemFault:
    timer_id: str
    reason: str


@dataclass(frozen=True)
class RemEnded:
    matured: list[str]
    reason: str


@dataclass(frozen=True)
class AnnounceReq:
    op: str  # stable operation identity: "ready:{head}:i{incarnation}"
    incarnation: int
    head: str
    base: str
    policy: str


@dataclass(frozen=True)
class ALanded:
    incarnation: int
    head: str


@dataclass(frozen=True)
class ABlocked:
    incarnation: int
    head: str
    base: str
    policy: str


@dataclass(frozen=True)
class AMoved:
    incarnation: int
    # the FULL authority observed at effect time: live provider fields
    # plus the host grant (incarnation + phase). The fold compares ALL of
    # them against its snapshot to decide re-evaluate vs park.
    observed_head: str
    observed_base: str
    observed_policy: str
    observed_incarnation: int
    observed_phase: str


@dataclass(frozen=True)
class AFault:
    op: str  # A2: fault retention keeps the exact operation
    incarnation: int
    reason: str


@dataclass(frozen=True)
class ReadyEnded:
    announced: list[int]
    faults: list[str]
    reason: str


# ---------------------------------------------------------------------------
# Pure-fold helpers
# ---------------------------------------------------------------------------


def _data(binding, color: str) -> dict:
    for _, toks in binding.consumed:
        for token in toks:
            if token.color == color:
                return token.data
    raise AssertionError(f"no consumed token of color {color}")


def _route(outputs, mapping: dict[str, tuple[dict, ...]]):
    """Emit tokens only on the targets named in mapping (subset emission)."""
    return {
        out.target: tuple(Token(out.color, data) for data in mapping[str(out.target)])
        for out in outputs
        if str(out.target) in mapping
    }


def _state_fact(st: dict) -> dict:
    return {
        "kind": "state",
        "incarnation": st["incarnation"],
        "body": {
            "phase": st["phase"],
            "head": st["head"],
            "base": st["base"],
            "mergeable": st["mergeable"],
            "policy": st["policy"],
        },
    }


# ---------------------------------------------------------------------------
# Lifecycle folds — the admission hub (all pure)
# ---------------------------------------------------------------------------


def _admit_head(binding, outputs):
    ev, st = _data(binding, "HeadSeen"), _data(binding, "LifeState")
    if st["phase"] == "terminal":
        return _route(outputs, {"life.state": (st,)})
    if st["phase"] == "quiescent":
        # dormancy absorbs EVERY head observation (same or different,
        # refresh included) with no work emission; resume re-admits
        st2 = {
            **st,
            "head": ev["head"],
            "base": ev["base"],
            "mergeable": ev["mergeable"],
            "policy": ev["policy"],
        }
        return _route(outputs, {"life.state": (st2,)})
    if ev["head"] == st["head"]:
        refreshed = (
            ev["base"] != st["base"]
            or ev["mergeable"] != st["mergeable"]
            or ev["policy"] != st["policy"]
        )
        if not refreshed:
            return _route(outputs, {"life.state": (st,)})
        # base/policy refresh: same lifetime, NO incarnation bump, no new
        # agent round — but review gets a `refreshed` work fact so any
        # provisional findings can republish under the fresh authority
        # (closing A4.8's moved-then-orphaned hole).
        st2 = {**st, "base": ev["base"], "mergeable": ev["mergeable"], "policy": ev["policy"]}
        fact = _state_fact(st2)
        work = {
            "incarnation": st2["incarnation"],
            "head": st2["head"],
            "base": st2["base"],
            "policy": st2["policy"],
            "relation": "refreshed",
            "lineage": st2["lineage"],
        }
        return _route(
            outputs,
            {
                "life.state": (st2,),
                "review.heads": (work,),
                "ci.heads": (work,),
                "ready.facts": (fact,),
                "dash.facts": (fact,),
            },
        )
    confirmed = st["expected"] != "" and st["expected"] == ev["head"]
    relation = "confirmed" if confirmed else ("new" if st["head"] == "" else "superseded")
    lineage = st["lineage"] if confirmed else ""
    st2 = {
        "phase": "running",
        "incarnation": st["incarnation"] + 1,
        "head": ev["head"],
        "base": ev["base"],
        "mergeable": ev["mergeable"],
        "policy": ev["policy"],
        "expected": "",
        "expected_op": "",
        "lineage": lineage,
    }
    work = {
        "incarnation": st2["incarnation"],
        "head": ev["head"],
        "base": ev["base"],
        "policy": ev["policy"],
        "relation": relation,
        "lineage": lineage,
    }
    fact = _state_fact(st2)
    return _route(
        outputs,
        {
            "life.state": (st2,),
            "review.heads": (work,),
            "ci.heads": (work,),
            "ready.facts": (fact,),
            "dash.facts": (fact,),
        },
    )


def _admit_draft(binding, outputs):
    _, st = _data(binding, "DraftSeen"), _data(binding, "LifeState")
    if st["phase"] != "running":
        return _route(outputs, {"life.state": (st,)})
    st2 = {**st, "phase": "quiescent"}
    fact = _state_fact(st2)
    return _route(
        outputs,
        {"life.state": (st2,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _admit_ready(binding, outputs):
    _, st = _data(binding, "ReadySeen"), _data(binding, "LifeState")
    if st["phase"] != "quiescent":
        return _route(outputs, {"life.state": (st,)})
    st2 = {**st, "phase": "running", "incarnation": st["incarnation"] + 1}
    fact = _state_fact(st2)
    work = {
        "incarnation": st2["incarnation"],
        "head": st2["head"],
        "base": st2["base"],
        "policy": st2["policy"],
        "relation": "resumed",
        "lineage": "",
    }
    return _route(
        outputs,
        {
            "life.state": (st2,),
            "review.heads": (work,),
            "ci.heads": (work,),
            "ready.facts": (fact,),
            "dash.facts": (fact,),
        },
    )


def _admit_close(binding, outputs):
    ev, st = _data(binding, "CloseSeen"), _data(binding, "LifeState")
    if st["phase"] == "terminal":
        return _route(outputs, {"life.state": (st,)})
    st2 = {**st, "phase": "terminal"}
    close = {"reason": ev["reason"]}
    return _route(
        outputs,
        {
            "life.state": (st2,),
            "review.closed": (close,),
            "ci.closed": (close,),
            "esc.closed": (close,),
            "mut.closed": (close,),
            "dash.closed": (close,),
            "rem.closed": (close,),
            "ready.closed": (close,),
        },
    )


def _admit_comment(binding, outputs):
    ev, st = _data(binding, "CommentSeen"), _data(binding, "LifeState")
    intent = {
        "id": ev["id"],
        "kind": ev["kind"],
        "arg": ev["arg"],
        "authorized": ev["authorized"],
        "phase": st["phase"],
        "provisional": st["expected"] != "",
        "incarnation": st["incarnation"],
        "head": st["head"],
        "base": st["base"],
        "policy": st["policy"],
    }
    return _route(outputs, {"life.state": (st,), "conv.intents": (intent,)})


def _admit_human(binding, outputs):
    ev, st = _data(binding, "HumanSeen"), _data(binding, "LifeState")
    if st["phase"] == "terminal":
        return _route(outputs, {"life.state": (st,)})
    fact = {
        "kind": "human",
        "incarnation": st["incarnation"],
        "body": {
            "approval": ev["approval"],
            "changes_requested": ev["changes_requested"],
            "unresolved": ev["unresolved"],
        },
    }
    return _route(
        outputs,
        {"life.state": (st,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _admit_runs(binding, outputs):
    ev, st = _data(binding, "RunSeen"), _data(binding, "LifeState")
    if st["phase"] != "running":
        return _route(outputs, {"life.state": (st,)})
    work = {
        "incarnation": st["incarnation"],
        "head": ev["head"],
        "run_id": ev["run_id"],
        "attempt": ev["attempt"],
        "conclusion": ev["conclusion"],
        "fingerprint": ev["fingerprint"],
    }
    return _route(outputs, {"life.state": (st,), "ci.runs": (work,)})


def _note_provisional(binding, outputs):
    ev, st = _data(binding, "ProvisionalHead"), _data(binding, "LifeState")
    st2 = {**st, "expected": ev["expected"], "expected_op": ev["op"], "lineage": ev["lineage"]}
    return _route(outputs, {"life.state": (st2,)})


# ---------------------------------------------------------------------------
# Review folds (pure)
# ---------------------------------------------------------------------------


def _publishable(head: str, base: str, policy: str, incarnation: int, findings: list, mem: dict) -> dict:
    """One publication request with a durable Pending record in its mem (A2)."""
    op = f"findings:{head}:i{incarnation}"
    pending = {
        "phase": "pending",
        "effect": op,
        "op": op,
        "head": head,
        "base": base,
        "policy": policy,
        "incarnation": incarnation,
        "findings": findings,
    }
    return {
        "head": head,
        "base": base,
        "policy": policy,
        "incarnation": incarnation,
        "findings": findings,
        "effect": op,
        "op": op,
        "mem": {**mem, "pub": pending},
    }


def _rev_start(binding, outputs):
    work, mem = _data(binding, "HeadWork"), _data(binding, "ReviewMemory")
    if work["relation"] == "refreshed":
        # no new agent round; but provisional findings retained by an
        # earlier `moved` republish under the fresh authority with the
        # SAME effect identity (incarnation did not bump on refresh)
        live = [f for f in mem["provisional"] if f["id"] not in mem["dismissed"]]
        if not live:
            return _route(outputs, {"review.memory": (mem,)})
        return _route(
            outputs,
            {
                "review.publishable": (
                    _publishable(
                        work["head"], work["base"], work["policy"], work["incarnation"], live, mem
                    ),
                )
            },
        )
    return _route(
        outputs,
        {
            "review.round": (
                {
                    "head": work["head"],
                    "base": work["base"],
                    "policy": work["policy"],
                    "incarnation": work["incarnation"],
                    "mem": mem,
                },
            )
        },
    )


def _rev_judge(binding, outputs):
    out = _data(binding, "AgentReview")
    live = [f for f in out["findings"] if f["id"] not in out["mem"]["dismissed"]]
    if not live:
        return _route(
            outputs,
            {
                "review.empty": (
                    {"head": out["head"], "incarnation": out["incarnation"], "mem": out["mem"]},
                )
            },
        )
    return _route(
        outputs,
        {
            "review.publishable": (
                _publishable(
                    out["head"], out["base"], out["policy"], out["incarnation"], live, out["mem"]
                ),
            )
        },
    )


def _findings_fact(head: str, incarnation: int, findings: list[dict], dismissed: list[str]) -> dict:
    blocking = sum(1 for f in findings if f["blocking"] and f["id"] not in dismissed)
    return {
        "kind": "findings",
        "incarnation": incarnation,
        "body": {"head": head, "blocking": blocking, "count": len(findings)},
    }


def _rev_fold_landed(binding, outputs):
    out = _data(binding, "LandedR")
    mem = {
        **out["mem"],
        "reviewed": [*out["mem"]["reviewed"], out["head"]],
        "provisional": [],
        "findings": out["findings"],
        "pub": {"phase": "idle"},
    }
    fact = _findings_fact(out["head"], out["incarnation"], out["findings"], mem["dismissed"])
    return _route(
        outputs,
        {"review.memory": (mem,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _rev_fold_moved(binding, outputs):
    out = _data(binding, "MovedR")
    mem = {**out["mem"], "provisional": out["findings"], "pub": {"phase": "idle"}}
    return _route(outputs, {"review.memory": (mem,)})


def _rev_fold_blocked(binding, outputs):
    out = _data(binding, "BlockedR")
    mem = {
        **out["mem"],
        "findings": out["findings"],
        "pub": {
            "phase": "blocked",
            "effect": out["effect"],
            "op": out["op"],
            "head": out["head"],
            "base": out["base"],
            "policy": out["policy"],
            "incarnation": out["incarnation"],
            "findings": out["findings"],
        },
    }
    fact = _findings_fact(out["head"], out["incarnation"], out["findings"], mem["dismissed"])
    return _route(
        outputs,
        {"review.memory": (mem,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _rev_fold_fault(binding, outputs):
    out = _data(binding, "FaultR")
    # A2: Faulted retains the operation and reason (mem["pub"] carries
    # the pending descriptor set at judge time)
    mem = {**out["mem"], "pub": {**out["mem"]["pub"], "phase": "faulted", "reason": out["reason"]}}
    fact = {"kind": "fault", "incarnation": 0, "body": {"where": "review", "reason": out["reason"]}}
    return _route(
        outputs,
        {"review.memory": (mem,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _rev_fold_empty(binding, outputs):
    out = _data(binding, "EmptyReview")
    mem = {
        **out["mem"],
        "reviewed": [*out["mem"]["reviewed"], out["head"]],
        "provisional": [],
        "findings": [],
        "pub": {"phase": "idle"},
    }
    fact = _findings_fact(out["head"], out["incarnation"], [], mem["dismissed"])
    return _route(
        outputs,
        {"review.memory": (mem,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _rev_recover(binding, outputs):
    fact, mem = _data(binding, "RecoverFact"), _data(binding, "ReviewMemory")
    pub = mem["pub"]
    if pub["phase"] != "blocked" or fact["op"] != pub["op"]:
        return _route(outputs, {"review.memory": (mem,)})
    # ONE fresh occurrence reusing the SAME effect identity; memory is
    # held through the reopened publication round (folds recreate it).
    return _route(
        outputs,
        {
            "review.publishable": (
                {
                    "head": pub["head"],
                    "base": pub["base"],
                    "policy": pub["policy"],
                    "incarnation": pub["incarnation"],
                    "findings": pub["findings"],
                    "effect": pub["effect"],
                    "op": pub["op"],
                    "mem": {**mem, "pub": {**pub, "phase": "pending"}},
                },
            )
        },
    )


def _rev_dismiss(binding, outputs):
    fact, mem = _data(binding, "DismissFact"), _data(binding, "ReviewMemory")
    dismissed = [*mem["dismissed"], fact["finding_id"]]
    mem2 = {**mem, "dismissed": dismissed}
    blocking = sum(1 for f in mem["findings"] if f["blocking"] and f["id"] not in dismissed)
    fact_out = {
        "kind": "findings",
        "incarnation": 0,
        "body": {"head": "", "blocking": blocking, "count": len(mem["findings"])},
    }
    return _route(
        outputs,
        {"review.memory": (mem2,), "ready.facts": (fact_out,), "dash.facts": (fact_out,)},
    )


def _rev_end(binding, outputs):
    close, mem = _data(binding, "CloseFact"), _data(binding, "ReviewMemory")
    return _route(
        outputs,
        {
            "review.done": (
                {"reviewed": mem["reviewed"], "pub_phase": mem["pub"]["phase"], "reason": close["reason"]},
            )
        },
    )


# ---------------------------------------------------------------------------
# CI folds (pure — observation only)
# ---------------------------------------------------------------------------


def _ci_on_head(binding, outputs):
    work, mem = _data(binding, "HeadWork"), _data(binding, "CiMemory")
    if work["relation"] == "refreshed":
        # base/policy refresh: adopt the fresh authority for future
        # escalation requests WITHOUT churning observed CI state — but
        # REISSUE any escalation that MOVED under the stale authority
        # (order-independence: failure-then-refresh must converge with
        # refresh-then-failure)
        mem2 = {**mem, "base": work["base"], "policy": work["policy"], "parked": []}
        routes = {"ci.memory": (mem2,)}
        if mem["status"] == "failure" and mem["fingerprint"] in mem["parked"]:
            routes["esc.failures"] = (
                {
                    "fingerprint": mem["fingerprint"],
                    "head": mem["head"],
                    "base": work["base"],
                    "policy": work["policy"],
                    "lineage": mem["lineage"],
                    "incarnation": mem["incarnation"],
                },
            )
        return _route(outputs, routes)
    # budget lineage: new code (new/superseded) gets a fresh ladder
    # budget; our own confirmed repair and a resume keep the lineage.
    # L{incarnation} is unique per grant: lifecycle bumps the incarnation
    # on every non-refresh head admission (evidence:
    # test_same_fingerprint_gets_fresh_budget_on_a_new_lineage).
    fresh = work["relation"] in ("new", "superseded") or not mem["lineage"]
    lineage = f"L{work['incarnation']}" if fresh else mem["lineage"]
    mem2 = {
        "head": work["head"],
        "base": work["base"],
        "policy": work["policy"],
        "lineage": lineage,
        "incarnation": work["incarnation"],
        "best": [],
        "status": "pending",
        "fingerprint": "",
        "parked": [],
    }
    fact = {"kind": "checks", "incarnation": work["incarnation"], "body": {"status": "pending"}}
    return _route(
        outputs,
        {"ci.memory": (mem2,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _ci_assess(binding, outputs):
    run, mem = _data(binding, "RunWork"), _data(binding, "CiMemory")
    if run["head"] != mem["head"]:
        return _route(outputs, {"ci.memory": (mem,)})  # not the exact head: inert
    newer = not mem["best"] or (run["run_id"], run["attempt"]) > tuple(mem["best"])
    if not newer:
        return _route(outputs, {"ci.memory": (mem,)})
    mem2 = {
        **mem,
        "best": [run["run_id"], run["attempt"]],
        "status": run["conclusion"],
        "fingerprint": run["fingerprint"],
        "parked": [],  # fresh evidence obsoletes any parked escalation
    }
    fact = {"kind": "checks", "incarnation": mem["incarnation"], "body": {"status": run["conclusion"]}}
    routes = {"ci.memory": (mem2,), "ready.facts": (fact,), "dash.facts": (fact,)}
    if run["conclusion"] == "failure":
        routes["esc.failures"] = (
            {
                "fingerprint": run["fingerprint"],
                "head": run["head"],
                "base": mem["base"],
                "policy": mem["policy"],
                "lineage": mem["lineage"],
                "incarnation": mem["incarnation"],
            },
        )
    return _route(outputs, routes)


def _ci_recheck(binding, outputs):
    """An escalation effect MOVED: decide reissue vs park (pure).

    Order-independence rule: if my admitted authority is already fresher
    than the attempted tuple, reissue the failure now under my tuple; if
    the attempt used my CURRENT tuple, the fresh admission has not folded
    yet — park the fingerprint and let the refresh reissue it. Each
    reissue carries a strictly fresher tuple, so the loop terminates.
    """
    echo, mem = _data(binding, "EscMoved"), _data(binding, "CiMemory")
    fp = echo["fp"]
    if mem["status"] != "failure" or mem["fingerprint"] != fp:
        return _route(outputs, {"ci.memory": (mem,)})  # failure gone: inert
    # the attempted tuple includes the GRANT: a stale-incarnation echo
    # (draft→resume moved an identical head/base/policy) must reissue
    # under the current incarnation, not park forever
    attempted = (echo["head"], echo["base"], echo["policy"], echo["incarnation"])
    if attempted == (mem["head"], mem["base"], mem["policy"], mem["incarnation"]):
        parked = mem["parked"] if fp in mem["parked"] else [*mem["parked"], fp]
        return _route(outputs, {"ci.memory": ({**mem, "parked": parked},)})
    failure = {
        "fingerprint": fp,
        "head": mem["head"],
        "base": mem["base"],
        "policy": mem["policy"],
        "lineage": mem["lineage"],
        "incarnation": mem["incarnation"],
    }
    return _route(outputs, {"ci.memory": (mem,), "esc.failures": (failure,)})


def _ci_end(binding, outputs):
    close, mem = _data(binding, "CloseFact"), _data(binding, "CiMemory")
    return _route(outputs, {"ci.done": ({"status": mem["status"], "reason": close["reason"]},)})


# ---------------------------------------------------------------------------
# Escalation folds (pure) — the ladder
# ---------------------------------------------------------------------------


def _esc_decide(binding, outputs):
    failure, ladder = _data(binding, "ChecksFailure"), _data(binding, "Ladder")
    fp = failure["fingerprint"]
    # budget is per fingerprint PER LINEAGE: the same flake on genuinely
    # new code earns a fresh ladder, our own repair does not reset it
    key = f"{failure['lineage']}:{fp}"
    rung = ladder["reruns"].get(key)  # None | "done" | "fault" (in-flight
    # reruns hold the ladder baton, so decide cannot race one)
    if rung is None:
        # ladder is HELD through the rerun round (folds recreate it)
        return _route(
            outputs,
            {
                "esc.rerun_req": (
                    {
                        "fingerprint": key,
                        "fp": fp,
                        "op": f"rerun:{key}",
                        "head": failure["head"],
                        "base": failure["base"],
                        "policy": failure["policy"],
                        "incarnation": failure["incarnation"],
                        "mem": ladder,
                    },
                )
            },
        )
    if rung == "fault":
        # FAIL-CLOSED: the rerun's terminal is unknown — the provider may
        # or may not hold it. An unproven rung must never authorize the
        # next (mutating!) rung. Surface for the human; the esc.recover
        # door reissues the SAME operation, and lookup-first reconciles.
        fact = {
            "kind": "human_needed",
            "incarnation": failure["incarnation"],
            "body": {"fingerprint": fp, "head": failure["head"], "why": "rerun-fault"},
        }
        return _route(outputs, {"esc.ladder": (ladder,), "dash.facts": (fact,)})
    entry = ladder["repairs"].get(key)
    if entry is None:
        # the pending entry retains the raw fp and ATTEMPTED authority so
        # a moved settle can echo a recheck to CI (order-independence)
        pending = {
            "state": "pending",
            "fp": fp,
            "head": failure["head"],
            "base": failure["base"],
            "policy": failure["policy"],
            "incarnation": failure["incarnation"],
        }
        ladder2 = {**ladder, "repairs": {**ladder["repairs"], key: pending}}
        req = {
            "op": f"repair:{key}",
            "head": failure["head"],
            "base": failure["base"],
            "policy": failure["policy"],
            "incarnation": failure["incarnation"],
            "source": "escalation",
        }
        return _route(outputs, {"esc.ladder": (ladder2,), "mut.requests": (req,)})
    if isinstance(entry, dict) and entry["state"] == "pending":
        # a repair for this rung is ALREADY out: wait, don't escalate.
        # The repair's settle decides the next move; a duplicate failure
        # observation while it is in flight is evidence of the same
        # breakage, not grounds for a second push or a human page.
        return _route(outputs, {"esc.ladder": (ladder,)})
    # the ladder is exhausted (repair done or faulted, still failing)
    fact = {
        "kind": "human_needed",
        "incarnation": failure["incarnation"],
        "body": {"fingerprint": fp, "head": failure["head"]},
    }
    return _route(outputs, {"esc.ladder": (ladder,), "dash.facts": (fact,)})


def _esc_recover(binding, outputs):
    """The escalation recovery door (A2): a faulted RERUN is reissued as
    ONE fresh occurrence under the SAME operation identity; the rerun
    gate reconciles lookup-first, so a rerun the provider already holds
    lands without a duplicate effect."""
    fact, ladder = _data(binding, "RecoverFact"), _data(binding, "Ladder")
    faults = ladder["rerun_faults"]
    key = next((k for k, v in faults.items() if v["op"] == fact["op"]), None)
    if key is None or ladder["reruns"].get(key) != "fault":
        return _route(outputs, {"esc.ladder": (ladder,)})
    held = faults[key]
    mem = {
        **ladder,
        "reruns": {k: v for k, v in ladder["reruns"].items() if k != key},
        "rerun_faults": {k: v for k, v in faults.items() if k != key},
    }
    req = {
        "fingerprint": key,
        "fp": held["fp"],
        "op": held["op"],  # the EXACT retained operation identity
        "head": held["head"],
        "base": held["base"],
        "policy": held["policy"],
        "incarnation": held["incarnation"],
        "mem": mem,
    }
    # the ladder baton is HELD through the reissued round (folds recreate it)
    return _route(outputs, {"esc.rerun_req": (req,)})


def _esc_fold_rerun_landed(binding, outputs):
    out = _data(binding, "RerunLanded")
    mem = out["mem"]
    ladder = {**mem, "reruns": {**mem["reruns"], out["fingerprint"]: "done"}}
    return _route(outputs, {"esc.ladder": (ladder,)})


def _esc_fold_rerun_moved(binding, outputs):
    out = _data(binding, "RerunMoved")
    # moved burns NO budget — and the failure may still stand under the
    # fresh authority, so echo a recheck to CI instead of losing it
    echo = {
        "fp": out["fp"],
        "head": out["head"],
        "base": out["base"],
        "policy": out["policy"],
        "incarnation": out["incarnation"],
    }
    return _route(outputs, {"esc.ladder": (out["mem"],), "ci.echo": (echo,)})


def _esc_fold_rerun_fault(binding, outputs):
    out = _data(binding, "RerunFault")
    mem = out["mem"]
    # A2: Faulted retains the EXACT request (operation identity, raw
    # fingerprint, full authority claim) so recovery can reissue it
    ladder = {
        **mem,
        "reruns": {**mem["reruns"], out["fingerprint"]: "fault"},
        "rerun_faults": {
            **mem["rerun_faults"],
            out["fingerprint"]: {
                "op": out["op"],
                "reason": out["reason"],
                "fp": out["fp"],
                "head": out["head"],
                "base": out["base"],
                "policy": out["policy"],
                "incarnation": out["incarnation"],
            },
        },
    }
    fact = {"kind": "fault", "incarnation": 0, "body": {"where": "rerun", "reason": out["reason"]}}
    return _route(outputs, {"esc.ladder": (ladder,), "ready.facts": (fact,), "dash.facts": (fact,)})


def _esc_fold_settled(binding, outputs):
    settled, ladder = _data(binding, "MutationSettled"), _data(binding, "Ladder")
    key = settled["fingerprint"]
    if not key or key not in ladder["repairs"]:
        return _route(outputs, {"esc.ladder": (ladder,)})
    entry = ladder["repairs"][key]
    repairs = dict(ladder["repairs"])
    if settled["outcome"] == "landed":
        repairs[key] = "done"
    elif settled["outcome"] == "moved":
        # the world did not change: refund the budget AND echo a recheck
        # (the failure may still stand under the fresh authority)
        del repairs[key]
        echo = {
            "fp": entry["fp"],
            "head": entry["head"],
            "base": entry["base"],
            "policy": entry["policy"],
            "incarnation": entry["incarnation"],
        }
        return _route(
            outputs, {"esc.ladder": ({**ladder, "repairs": repairs},), "ci.echo": (echo,)}
        )
    else:
        # A2: a FAULTED rung retains the exact entry (raw fp + attempted
        # authority), not a bare marker — mutation custody may reissue
        # the exact operation later, and if authority moved meanwhile the
        # settle classifies MOVED: the refund branch above then needs the
        # entry's fields to echo the recheck (a bare string would strand
        # the custody and crash the fold)
        repairs[key] = {**entry, "state": "fault"}
    return _route(outputs, {"esc.ladder": ({**ladder, "repairs": repairs},)})


def _esc_end(binding, outputs):
    close, ladder = _data(binding, "CloseFact"), _data(binding, "Ladder")
    return _route(
        outputs,
        {
            "esc.done": (
                {"reruns": ladder["reruns"], "repairs": ladder["repairs"], "reason": close["reason"]},
            )
        },
    )


# ---------------------------------------------------------------------------
# Conversation folds (pure) — grades by state, never ends
# ---------------------------------------------------------------------------

INTENT_GRADE = {
    "reply": "pure",
    "status": "pure",
    "acknowledge": "note",
    "dismiss": "note",
    "defer": "note",
    "snooze": "note",
    "resume": "note",
    "reassign": "note",
    "recover_publication": "note",
    "change": "committing",
    "update_base": "committing",
    "resolve_conflict": "committing",
}


# recover_publication routing: the op prefix names the owning loop
_RECOVER_ROUTES = {
    "rerun": ("esc.recover", "escalation"),
    "findings": ("review.recover", "review"),
    "reply": ("conv.recover", "conversation"),
    "reminder": ("rem.recover", "reminder"),
    "dash": ("dash.recover", "dashboard"),
    "ready": ("ready.recover", "readiness"),
    "push": ("mut.recover", "mutation"),
}


def _conv_classify(binding, outputs):
    intent, mem = _data(binding, "IntentFact"), _data(binding, "ConvMemory")
    if intent["id"] in mem["served"]:
        return _route(outputs, {"conv.memory": (mem,)})
    mem2 = {**mem, "served": [*mem["served"], intent["id"]]}
    routes: dict[str, tuple] = {"conv.memory": (mem2,)}
    grade = INTENT_GRADE.get(intent["kind"])
    reply = {"id": intent["id"], "text": ""}

    if grade is None or not intent["authorized"]:
        reply["text"] = "no workflow change"
    elif grade == "pure":
        reply["text"] = f"answer:{intent['kind']}"
    elif grade == "note":
        if intent["phase"] == "terminal":
            reply["text"] = f"declined:{intent['kind']}:terminal"
        else:
            reply["text"] = f"noted:{intent['kind']}"
            if intent["kind"] == "dismiss":
                routes["review.dismiss"] = ({"finding_id": intent["arg"]},)
            elif intent["kind"] == "snooze":
                routes["rem.snoozes"] = ({"mode": "snooze", "arg": intent["arg"]},)
            elif intent["kind"] == "resume":
                routes["rem.snoozes"] = ({"mode": "clear", "arg": intent["arg"]},)
            elif intent["kind"] == "defer":
                routes["rem.snoozes"] = ({"mode": "defer", "arg": intent["arg"]},)
            elif intent["kind"] == "recover_publication":
                prefix = intent["arg"].split(":", 1)[0]
                route = _RECOVER_ROUTES.get(prefix)
                if route is None:
                    reply["text"] = f"declined:recover_publication:unknown-target"
                else:
                    routes[route[0]] = ({"target": route[1], "op": intent["arg"]},)
    elif grade == "committing":
        if intent["phase"] != "running":
            reply["text"] = f"declined:{intent['kind']}:{intent['phase']}"
        elif intent["provisional"]:
            # A4.3: while lifecycle expects a provisional head, further
            # mutations are declined BEFORE any gate attempt
            reply["text"] = f"declined:{intent['kind']}:provisional"
        else:
            reply["text"] = f"started:{intent['kind']}"
            routes["mut.requests"] = (
                {
                    "op": intent["kind"],
                    "head": intent["head"],
                    "base": intent["base"],
                    "policy": intent["policy"],
                    "incarnation": intent["incarnation"],
                    "source": "conversation",
                },
            )
    # A2: the reply effect is in flight — record Pending custody as data
    # (per-id, because replies are deliberately concurrent)
    mem2 = {**mem2, "pending": {**mem2["pending"], intent["id"]: reply["text"]}}
    routes["conv.memory"] = (mem2,)
    routes["conv.reply_req"] = (reply,)
    return _route(outputs, routes)


def _conv_fold_replied(binding, outputs):
    out, mem = _data(binding, "Replied"), _data(binding, "ConvMemory")
    pending = {k: v for k, v in mem["pending"].items() if k != out["id"]}
    blocked = {k: v for k, v in mem["blocked"].items() if k != out["id"]}
    fact = {"kind": "reply", "incarnation": 0, "body": {"id": out["id"], "text": out["text"]}}
    return _route(
        outputs,
        {"conv.memory": ({**mem, "pending": pending, "blocked": blocked},), "dash.facts": (fact,)},
    )


def _conv_fold_rblocked(binding, outputs):
    out, mem = _data(binding, "ReplyBlocked"), _data(binding, "ConvMemory")
    pending = {k: v for k, v in mem["pending"].items() if k != out["id"]}
    mem2 = {**mem, "pending": pending, "blocked": {**mem["blocked"], out["id"]: out["text"]}}
    return _route(outputs, {"conv.memory": (mem2,)})


def _conv_fold_rfault(binding, outputs):
    out, mem = _data(binding, "ReplyFault"), _data(binding, "ConvMemory")
    pending = {k: v for k, v in mem["pending"].items() if k != out["id"]}
    mem2 = {**mem, "pending": pending, "faulted": {**mem["faulted"], out["id"]: out["reason"]}}
    fact = {"kind": "fault", "incarnation": 0, "body": {"where": "reply", "reason": out["reason"]}}
    return _route(outputs, {"conv.memory": (mem2,), "dash.facts": (fact,)})


def _conv_recover(binding, outputs):
    fact, mem = _data(binding, "RecoverFact"), _data(binding, "ConvMemory")
    reply_id = fact["op"].removeprefix("reply:")
    if reply_id not in mem["blocked"]:
        return _route(outputs, {"conv.memory": (mem,)})
    # blocked -> pending: custody moves back in flight with the SAME identity
    text = mem["blocked"][reply_id]
    mem2 = {
        **mem,
        "pending": {**mem["pending"], reply_id: text},
        "blocked": {k: v for k, v in mem["blocked"].items() if k != reply_id},
    }
    req = {"id": reply_id, "text": text}
    return _route(outputs, {"conv.memory": (mem2,), "conv.reply_req": (req,)})


# ---------------------------------------------------------------------------
# Mutation folds (pure)
# ---------------------------------------------------------------------------


def _mut_start(binding, outputs):
    req, st = _data(binding, "MutationRequest"), _data(binding, "MutState")
    fp = req["op"].removeprefix("repair:") if req["op"].startswith("repair:") else ""
    if st["state"] == "faulted":
        settled = {
            "op": req["op"],
            "outcome": "declined",
            "incarnation": req["incarnation"],
            "fingerprint": fp,
        }
        fact = {"kind": "mutation_settled", "incarnation": req["incarnation"], "body": settled}
        return _route(
            outputs,
            {"mut.state": (st,), "esc.settled": (settled,), "ready.facts": (fact,), "dash.facts": (fact,)},
        )
    # the baton is HELD until a fold returns it: one mutation at a time
    op_key = f"push:{req['op']}:{req['head']}:i{req['incarnation']}"
    fact = {"kind": "mutation_pending", "incarnation": req["incarnation"], "body": {"op": req["op"]}}
    return _route(
        outputs,
        {
            "mut.work": (
                {
                    "op": req["op"],
                    "op_key": op_key,
                    "head": req["head"],
                    "base": req["base"],
                    "policy": req["policy"],
                    "incarnation": req["incarnation"],
                },
            ),
            "ready.facts": (fact,),
            "dash.facts": (fact,),
        },
    )


def _settled(op: str, outcome: str, incarnation: int) -> dict:
    fp = op.removeprefix("repair:") if op.startswith("repair:") else ""
    return {"op": op, "outcome": outcome, "incarnation": incarnation, "fingerprint": fp}


_MUT_IDLE = {
    "state": "idle",
    "op_key": "",
    "op": "",
    "head": "",
    "base": "",
    "policy": "",
    "incarnation": 0,
    "reason": "",
}


def _mut_fold_pushed(binding, outputs):
    out = _data(binding, "Pushed")
    settled = _settled(out["op"], "landed", out["incarnation"])
    fact = {"kind": "mutation_settled", "incarnation": out["incarnation"], "body": settled}
    return _route(
        outputs,
        {
            "mut.state": (_MUT_IDLE,),
            "life.provisional": (
                {"expected": out["new_head"], "op": out["op"], "lineage": out["lineage"]},
            ),
            "esc.settled": (settled,),
            "ready.facts": (fact,),
            "dash.facts": (fact,),
        },
    )


def _mut_fold_moved(binding, outputs):
    out = _data(binding, "MovedM")
    settled = _settled(out["op"], "moved", out["incarnation"])
    fact = {"kind": "mutation_settled", "incarnation": out["incarnation"], "body": settled}
    return _route(
        outputs,
        {"mut.state": (_MUT_IDLE,), "esc.settled": (settled,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _mut_fold_fault(binding, outputs):
    out = _data(binding, "FaultM")
    settled = _settled(out["op"], "faulted", out["incarnation"])
    fact = {"kind": "fault", "incarnation": 0, "body": {"where": "mutation", "reason": out["reason"]}}
    # A2: Faulted retains the exact operation identity for recovery
    faulted = {
        "state": "faulted",
        "op_key": out["op_key"],
        "op": out["op"],
        "head": out["head"],
        "base": out["base"],
        "policy": out["policy"],
        "incarnation": out["incarnation"],
        "reason": out["reason"],
    }
    return _route(
        outputs,
        {"mut.state": (faulted,), "esc.settled": (settled,), "ready.facts": (fact,), "dash.facts": (fact,)},
    )


def _mut_recover(binding, outputs):
    fact, st = _data(binding, "RecoverFact"), _data(binding, "MutState")
    if st["state"] != "faulted" or fact["op"] != st["op_key"]:
        return _route(outputs, {"mut.state": (st,)})
    # ONE fresh occurrence, SAME operation identity; the gate reconciles
    # lookup-first (a crash after the push landed must not push twice).
    # The baton is HELD again until a fold returns it.
    pending = {"kind": "mutation_pending", "incarnation": st["incarnation"], "body": {"op": st["op"]}}
    return _route(
        outputs,
        {
            "mut.work": (
                {
                    "op": st["op"],
                    "op_key": st["op_key"],
                    "head": st["head"],
                    "base": st["base"],
                    "policy": st["policy"],
                    "incarnation": st["incarnation"],
                },
            ),
            "ready.facts": (pending,),
            "dash.facts": (pending,),
        },
    )


def _mut_end(binding, outputs):
    close, st = _data(binding, "CloseFact"), _data(binding, "MutState")
    return _route(outputs, {"mut.done": ({"state": st["state"], "reason": close["reason"]},)})


# ---------------------------------------------------------------------------
# Dashboard folds (pure) — drift is a DECISION (fold), the upsert an effect
# ---------------------------------------------------------------------------


def _dash_fold(binding, outputs):
    fact, mem = _data(binding, "GateFact"), _data(binding, "DashMemory")
    digest = f"{fact['kind']}:{sorted(fact['body'].items())!r}"
    if digest == mem["digest"]:  # republish on digest drift ONLY
        return _route(outputs, {"dash.memory": (mem,)})
    entries = [*mem["entries"], f"{fact['kind']}:{fact['body']}"]
    if mem["blocked"] or mem["faulted"]:
        # fail-closed while blocked/faulted: accumulate the DESIRED state
        # (entries + digest); the retained blocked/faulted request stays
        # EXACTLY as attempted, and recovery reconciles the two
        return _route(outputs, {"dash.memory": ({**mem, "entries": entries, "digest": digest},)})
    # memory is HELD through the upsert round; the fold recreates it
    req = {
        "entries": entries,
        "digest": digest,
        "desired_entries": entries,  # a live publish IS the desired state
        "desired_digest": digest,
    }
    return _route(outputs, {"dash.pub_req": (req,)})


def _dash_fold_landed(binding, outputs):
    out = _data(binding, "DashLanded")
    # memory tracks the DESIRED digest (the dedup key) and the LANDED
    # digest (what the board actually shows) separately; drift between
    # them is the self-heal decision
    mem = {
        "entries": out["desired_entries"],
        "digest": out["desired_digest"],
        "landed": out["digest"],
        "blocked": {},
        "faulted": {},
    }
    if out["desired_digest"] != out["digest"]:
        # a recovery landed the EXACT retained request, but the desired
        # state drifted while the fault was held: poke the self-heal
        # transition (which consumes the baton — every reissue cycle
        # passes through a baton-consuming transition)
        return _route(outputs, {"dash.memory": (mem,), "dash.heal": ({"digest": out["desired_digest"]},)})
    return _route(outputs, {"dash.memory": (mem,)})


def _dash_selfheal(binding, outputs):
    heal, mem = _data(binding, "DashHeal"), _data(binding, "DashMemory")
    if mem["blocked"] or mem["faulted"] or mem["digest"] == mem["landed"]:
        # a newer publish already healed the board (or the loop is
        # fail-closed again): the poke is inert
        return _route(outputs, {"dash.memory": (mem,)})
    req = {
        "entries": mem["entries"],
        "digest": mem["digest"],
        "desired_entries": mem["entries"],
        "desired_digest": mem["digest"],
    }
    # memory is HELD through the healing upsert round
    return _route(outputs, {"dash.pub_req": (req,)})


def _dash_fold_blocked(binding, outputs):
    out = _data(binding, "DashBlocked")
    # A2: custody retains the EXACT attempted request (entries + digest),
    # while memory keeps tracking the evolving DESIRED state
    mem = {
        "entries": out["desired_entries"],
        "digest": out["desired_digest"],
        "landed": "",  # the attempted upsert did NOT land
        "blocked": {"entries": out["entries"], "digest": out["digest"]},
        "faulted": {},
    }
    return _route(outputs, {"dash.memory": (mem,)})


def _dash_fold_fault(binding, outputs):
    out = _data(binding, "DashFault")
    # A2: Faulted retains the EXACT effect (entries + digest) and reason,
    # while memory keeps tracking the evolving DESIRED state
    mem = {
        "entries": out["desired_entries"],
        "digest": out["desired_digest"],
        "landed": "",  # the attempted upsert did NOT land
        "blocked": {},
        "faulted": {"entries": out["entries"], "digest": out["digest"], "reason": out["reason"]},
    }
    # The dashboard is a pure sink (census row 7: no foreign outputs).
    # Its fault is retained here with the exact effect and is recoverable
    # through the dash.recover door — it is NOT a readiness fact, and a
    # dash→ready edge would braid the two projections into a batonless cycle.
    return _route(outputs, {"dash.memory": (mem,)})


def _dash_recover(binding, outputs):
    fact, mem = _data(binding, "RecoverFact"), _data(binding, "DashMemory")
    held = mem["blocked"] or mem["faulted"]
    if not held or fact["op"] != f"dash:{held['digest']}":
        return _route(outputs, {"dash.memory": (mem,)})
    # ONE fresh occurrence reissuing the EXACT retained request — same
    # entries, same digest identity. The desired state travels alongside;
    # if it drifted while the fault was held, the landed fold self-heals
    # with a follow-up upsert of the desired state.
    # A2: the memory baton is HELD through the recovery round — returning
    # it here would let concurrent facts extend `entries` and then be
    # overwritten by the landed fold's snapshot (a real lost-entry race).
    req = {
        "entries": held["entries"],
        "digest": held["digest"],
        "desired_entries": mem["entries"],
        "desired_digest": mem["digest"],
    }
    return _route(outputs, {"dash.pub_req": (req,)})


def _dash_end(binding, outputs):
    close, mem = _data(binding, "CloseFact"), _data(binding, "DashMemory")
    return _route(outputs, {"dash.done": ({"entries": mem["entries"], "reason": close["reason"]},)})


# ---------------------------------------------------------------------------
# Reminder folds (pure)
# ---------------------------------------------------------------------------


def _rem_mature(binding, outputs):
    due, st = _data(binding, "TimerDue"), _data(binding, "RemState")
    st2 = {**st, "matured": [*st["matured"], due["timer_id"]]}  # the FACT is durable
    if st["snoozed"] or st["closing"]:
        return _route(outputs, {"rem.state": (st2,)})  # only the DECISION is suppressed
    if (
        due["timer_id"] in st["pending"]
        or due["timer_id"] in st["blocked"]
        or due["timer_id"] in st["faulted"]  # a faulted timer never reopens
    ):
        # single-flight per timer: a duplicate maturity never doubles the effect
        return _route(outputs, {"rem.state": (st2,)})
    # A2: record Pending custody as data (the baton stays available so
    # snoozes and closes still fold while the comment is in flight)
    st2 = {**st2, "pending": {**st2["pending"], due["timer_id"]: True}}
    return _route(outputs, {"rem.state": (st2,), "rem.pub_req": ({"timer_id": due["timer_id"]},)})


def _rem_snooze(binding, outputs):
    fact, st = _data(binding, "SnoozeFact"), _data(binding, "RemState")
    if fact["mode"] == "snooze":
        st2 = {**st, "snoozed": True}
    elif fact["mode"] == "clear":
        st2 = {**st, "snoozed": False}
    else:  # defer: the host arms the timer; the net records the request
        st2 = {**st, "deferred": [*st["deferred"], fact["arg"]]}
    return _route(outputs, {"rem.state": (st2,)})


def _rem_settle(st2: dict, outputs, extra: dict):
    """After a reminder terminal folds: finish a deferred Close (A3) once
    the LAST outstanding terminal has settled, else return the baton."""
    if st2["closing"] and not st2["pending"]:
        done = {"matured": st2["matured"], "reason": st2["closing"]}
        return _route(outputs, {"rem.done": (done,), **extra})
    return _route(outputs, {"rem.state": (st2,), **extra})


def _rem_fold_landed(binding, outputs):
    out, st = _data(binding, "RemLanded"), _data(binding, "RemState")
    pending = {k: v for k, v in st["pending"].items() if k != out["timer_id"]}
    blocked = {k: v for k, v in st["blocked"].items() if k != out["timer_id"]}
    fact = {"kind": "reminder", "incarnation": 0, "body": {"timer_id": out["timer_id"]}}
    return _rem_settle(
        {**st, "pending": pending, "blocked": blocked}, outputs, {"dash.facts": (fact,)}
    )


def _rem_fold_blocked(binding, outputs):
    out, st = _data(binding, "RemBlocked"), _data(binding, "RemState")
    pending = {k: v for k, v in st["pending"].items() if k != out["timer_id"]}
    st2 = {**st, "pending": pending, "blocked": {**st["blocked"], out["timer_id"]: True}}
    return _rem_settle(st2, outputs, {})


def _rem_fold_fault(binding, outputs):
    out, st = _data(binding, "RemFault"), _data(binding, "RemState")
    # A2: Faulted retains the operation and reason in the baton
    pending = {k: v for k, v in st["pending"].items() if k != out["timer_id"]}
    st2 = {
        **st,
        "pending": pending,
        "faulted": {**st["faulted"], out["timer_id"]: out["reason"]},
    }
    fact = {"kind": "fault", "incarnation": 0, "body": {"where": "reminder", "reason": out["reason"]}}
    return _rem_settle(st2, outputs, {"dash.facts": (fact,)})


def _rem_recover(binding, outputs):
    fact, st = _data(binding, "RecoverFact"), _data(binding, "RemState")
    timer_id = fact["op"].removeprefix("reminder:")
    if timer_id not in st["blocked"] or st["closing"]:
        return _route(outputs, {"rem.state": (st,)})
    # blocked -> pending: one fresh occurrence, same effect identity
    st2 = {
        **st,
        "pending": {**st["pending"], timer_id: True},
        "blocked": {k: v for k, v in st["blocked"].items() if k != timer_id},
    }
    return _route(outputs, {"rem.state": (st2,), "rem.pub_req": ({"timer_id": timer_id},)})


def _rem_end(binding, outputs):
    close, st = _data(binding, "CloseFact"), _data(binding, "RemState")
    if st["pending"]:
        # A3: comment gates are outstanding — record the close INTENT; the
        # last terminal fold finalizes, so late terminals still settle
        return _route(outputs, {"rem.state": ({**st, "closing": close["reason"]},)})
    return _route(outputs, {"rem.done": ({"matured": st["matured"], "reason": close["reason"]},)})


# ---------------------------------------------------------------------------
# Readiness folds (pure) — the projection
# ---------------------------------------------------------------------------


def _ready(snap: dict) -> bool:
    return (
        snap["phase"] == "running"
        and snap["checks"] == "success"
        and snap["findings_blocking"] == 0
        and snap["approval"]
        and not snap["changes_requested"]
        and snap["unresolved"] == 0
        and snap["mergeable"]
        and not snap["pending"]
        and not snap["faults"]
    )


def _ready_fold(binding, outputs):
    fact, snap = _data(binding, "GateFact"), _data(binding, "Snapshot")
    kind, body = fact["kind"], fact["body"]
    if kind == "state":
        if fact["incarnation"] < snap["incarnation"]:
            # a STALE state fact must never roll the projection back
            return _route(outputs, {"ready.snap": (snap,)})
        if fact["incarnation"] != snap["incarnation"]:
            # new authority: per-incarnation gates reset
            snap = {
                **snap,
                "incarnation": fact["incarnation"],
                "checks": "pending",
                "findings_blocking": 0,
                "pending": [],
            }
        snap = {
            **snap,
            "phase": body["phase"],
            "head": body["head"],
            "base": body["base"],
            "mergeable": body["mergeable"],
            "policy": body["policy"],
        }
    elif fact["incarnation"] not in (0, snap["incarnation"]):
        return _route(outputs, {"ready.snap": (snap,)})  # A1.4: mismatched facts are inert
    elif kind == "checks":
        snap = {**snap, "checks": body["status"]}
    elif kind == "findings":
        snap = {**snap, "findings_blocking": body["blocking"]}
    elif kind == "human":
        snap = {
            **snap,
            "approval": body["approval"],
            "changes_requested": body["changes_requested"],
            "unresolved": body["unresolved"],
        }
    elif kind == "mutation_pending":
        snap = {**snap, "pending": [*snap["pending"], body["op"]]}
    elif kind == "mutation_settled":
        snap = {**snap, "pending": [op for op in snap["pending"] if op != body["op"]]}
    elif kind == "fault":
        snap = {**snap, "faults": [*snap["faults"], body["where"]]}
    else:
        return _route(outputs, {"ready.snap": (snap,)})

    return _route(outputs, _announce_open(snap))


def _announce_open(snap: dict) -> dict:
    """Re-evaluate the announce decision for the CURRENT snapshot (pure).

    Called after every fact fold AND after every announce terminal, so a
    new-authority readiness suppressed while an old announcement was in
    flight is re-opened the moment the old terminal settles (A2).
    """
    if (
        _ready(snap)
        and snap["incarnation"] not in snap["announced"]
        and not snap["announcing"]
        and not snap["blocked"]  # a blocked announce reopens only via recovery
        and not snap["closing"]
    ):
        req = {
            "op": f"ready:{snap['head']}:i{snap['incarnation']}",
            "incarnation": snap["incarnation"],
            "head": snap["head"],
            "base": snap["base"],
            "policy": snap["policy"],
        }
        # A2: `announcing` retains the EXACT in-flight request
        snap2 = {**snap, "announcing": req}
        return {"ready.snap": (snap2,), "ready.announce_req": (req,)}
    return {"ready.snap": (snap,)}


def _ready_done(snap: dict) -> dict:
    return {
        "ready.done": (
            {"announced": snap["announced"], "faults": snap["faults"], "reason": snap["closing"]},
        )
    }


def _ready_settle(snap: dict, outputs, extra: dict):
    """After an announce terminal folds: finish a deferred Close (A3),
    otherwise re-evaluate the current snapshot."""
    if snap["closing"]:
        return _route(outputs, {**_ready_done(snap), **extra})
    return _route(outputs, {**_announce_open(snap), **extra})


def _ready_fold_alanded(binding, outputs):
    out, snap = _data(binding, "ALanded"), _data(binding, "Snapshot")
    # A1.6: announce-once is recorded on ACKNOWLEDGMENT — per the
    # TERMINAL's incarnation, so a stale landing never marks the current
    # incarnation announced (adoption fence, amended A1.5)
    snap2 = {**snap, "announced": [*snap["announced"], out["incarnation"]], "announcing": {}}
    fact = {"kind": "announced", "incarnation": out["incarnation"], "body": {"head": out["head"]}}
    return _ready_settle(snap2, outputs, {"dash.facts": (fact,)})


def _ready_fold_amoved(binding, outputs):
    out, snap = _data(binding, "AMoved"), _data(binding, "Snapshot")
    snap2 = {**snap, "announcing": {}}
    if snap2["closing"]:
        return _route(outputs, _ready_done(snap2))
    observed = (
        out["observed_head"],
        out["observed_base"],
        out["observed_policy"],
        out["observed_incarnation"],
        out["observed_phase"],
    )
    current = (snap2["head"], snap2["base"], snap2["policy"], snap2["incarnation"], snap2["phase"])
    if current == observed:
        # the displacing observation ALREADY folded while the gate was out:
        # the snapshot speaks with the gate's FULL observed authority —
        # grant included — so re-evaluate now (announce-once per
        # incarnation then admits the CURRENT incarnation exactly once)
        return _route(outputs, _announce_open(snap2))
    # the displacing observation has NOT folded yet: reissuing the same
    # request would be refused identically forever (livelock). Park; the
    # pending StateFact reopens the decision when it folds.
    return _route(outputs, {"ready.snap": (snap2,)})


def _ready_fold_ablocked(binding, outputs):
    _, snap = _data(binding, "ABlocked"), _data(binding, "Snapshot")
    # custody moves from in-flight to blocked, retaining the EXACT request
    snap2 = {**snap, "announcing": {}, "blocked": snap["announcing"]}
    if snap2["closing"]:
        # A3: Close was deferred while the gate was out; a closed PR has
        # no announcement to recover, so the retained request is dropped
        return _route(outputs, _ready_done(snap2))
    return _route(outputs, {"ready.snap": (snap2,)})


def _ready_recover(binding, outputs):
    fact, snap = _data(binding, "RecoverFact"), _data(binding, "Snapshot")
    blocked = snap["blocked"]
    if not blocked or fact["op"] != blocked["op"] or snap["closing"]:
        return _route(outputs, {"ready.snap": (snap,)})
    # ONE fresh occurrence reusing the SAME operation identity
    return _route(
        outputs,
        {
            "ready.snap": ({**snap, "announcing": blocked, "blocked": {}},),
            "ready.announce_req": (blocked,),
        },
    )


def _ready_fold_afault(binding, outputs):
    out, snap = _data(binding, "AFault"), _data(binding, "Snapshot")
    # A2: fault retention keeps the exact operation identity and reason
    fault = {"op": out["op"], "reason": out["reason"]}
    snap2 = {**snap, "announcing": {}, "faults": [*snap["faults"], fault]}
    fact = {"kind": "fault", "incarnation": 0, "body": {"where": "announce", "reason": out["reason"]}}
    return _ready_settle(snap2, outputs, {"dash.facts": (fact,)})


def _ready_end(binding, outputs):
    close, snap = _data(binding, "CloseFact"), _data(binding, "Snapshot")
    if snap["announcing"]:
        # A3: a terminal is outstanding — record the close INTENT and let
        # the terminal fold finalize, so the late terminal still settles
        return _route(outputs, {"ready.snap": ({**snap, "closing": close["reason"]},)})
    return _route(outputs, _ready_done({**snap, "closing": close["reason"]}))


# ---------------------------------------------------------------------------
# The net — nine loops, one instance
# ---------------------------------------------------------------------------


def build_v5_net() -> BuiltNet:
    net = NetSpec("pr_v5")
    s = net.s
    life, rev, ci, esc = s.life, s.review, s.ci, s.esc
    conv, mut, dash, rem, ready = s.conv, s.mut, s.dash, s.rem, s.ready

    # -- lifecycle: mailboxes, baton, admission folds
    life.p.heads(HeadSeen)
    life.p.drafts(DraftSeen)
    life.p.readies(ReadySeen)
    life.p.closes(CloseSeen)
    life.p.comments(CommentSeen)
    life.p.humans(HumanSeen)
    life.p.runs(RunSeen)
    life.p.provisional(ProvisionalHead)
    life.p.state(LifeState)

    # ingress doors: the host delivers normalized observations
    net.t.on_head >> life.p.heads
    net.t.on_draft >> life.p.drafts
    net.t.on_ready >> life.p.readies
    net.t.on_close >> life.p.closes
    net.t.on_comment >> life.p.comments
    net.t.on_human >> life.p.humans
    net.t.on_runs >> life.p.runs
    net.t.on_timer >> rem.p.timers(TimerDue)

    # -- sibling mailboxes the hub feeds (declared before use in folds)
    rev.p.heads(HeadWork)
    rev.p.memory(ReviewMemory)
    rev.p.recover(RecoverFact)
    rev.p.dismiss(DismissFact)
    rev.p.closed(CloseFact)
    ci.p.heads(HeadWork)
    ci.p.runs(RunWork)
    ci.p.memory(CiMemory)
    ci.p.closed(CloseFact)
    esc.p.failures(ChecksFailure)
    esc.p.settled(MutationSettled)
    esc.p.ladder(Ladder)
    esc.p.closed(CloseFact)
    conv.p.intents(IntentFact)
    conv.p.memory(ConvMemory)
    conv.p.recover(RecoverFact)
    mut.p.requests(MutationRequest)
    mut.p.state(MutState)
    mut.p.recover(RecoverFact)
    mut.p.closed(CloseFact)
    dash.p.facts(GateFact)
    dash.p.memory(DashMemory)
    dash.p.recover(RecoverFact)
    dash.p.closed(CloseFact)
    rem.p.snoozes(SnoozeFact)
    rem.p.state(RemState)
    rem.p.recover(RecoverFact)
    rem.p.closed(CloseFact)
    ready.p.facts(GateFact)
    ready.p.snap(Snapshot)
    ready.p.recover(RecoverFact)
    ready.p.closed(CloseFact)

    # -- lifecycle admission (each fold: one mailbox + the state baton)
    (life.p.heads, life.p.state) >> life.t.admit_head(
        handler=petri_handler(_admit_head)
    ) >> (life.p.state, rev.p.heads, ci.p.heads, ready.p.facts, dash.p.facts)
    (life.p.drafts, life.p.state) >> life.t.admit_draft(
        handler=petri_handler(_admit_draft)
    ) >> (life.p.state, ready.p.facts, dash.p.facts)
    (life.p.readies, life.p.state) >> life.t.admit_ready(
        handler=petri_handler(_admit_ready)
    ) >> (life.p.state, rev.p.heads, ci.p.heads, ready.p.facts, dash.p.facts)
    (life.p.closes, life.p.state) >> life.t.admit_close(
        handler=petri_handler(_admit_close)
    ) >> (
        life.p.state,
        rev.p.closed,
        ci.p.closed,
        esc.p.closed,
        mut.p.closed,
        dash.p.closed,
        rem.p.closed,
        ready.p.closed,
    )
    (life.p.comments, life.p.state) >> life.t.admit_comment(
        handler=petri_handler(_admit_comment)
    ) >> (life.p.state, conv.p.intents)
    (life.p.humans, life.p.state) >> life.t.admit_human(
        handler=petri_handler(_admit_human)
    ) >> (life.p.state, ready.p.facts, dash.p.facts)
    (life.p.runs, life.p.state) >> life.t.admit_runs(
        handler=petri_handler(_admit_runs)
    ) >> (life.p.state, ci.p.runs)
    (life.p.provisional, life.p.state) >> life.t.note_provisional(
        handler=petri_handler(_note_provisional)
    ) >> life.p.state

    # -- review loop
    (rev.p.heads, rev.p.memory) >> rev.t.start(
        handler=petri_handler(_rev_start)
    ) >> (rev.p.round(RoundOpen), rev.p.publishable(Publishable), rev.p.memory)
    rev.p.round >> rev.t.agent(handler="review_agent") >> rev.p.output(AgentReview)
    rev.p.output >> rev.t.judge(handler=petri_handler(_rev_judge)) >> (
        rev.p.publishable,
        rev.p.empty(EmptyReview),
    )
    rev.p.publishable >> rev.t.publish(handler="publish_gate") >> (
        rev.p.landed(LandedR),
        rev.p.moved(MovedR),
        rev.p.blocked(BlockedR),
        rev.p.fault(FaultR),
    )
    rev.p.landed >> rev.t.fold_landed(handler=petri_handler(_rev_fold_landed)) >> (
        rev.p.memory,
        ready.p.facts,
        dash.p.facts,
    )
    rev.p.moved >> rev.t.fold_moved(handler=petri_handler(_rev_fold_moved)) >> rev.p.memory
    rev.p.blocked >> rev.t.fold_blocked(handler=petri_handler(_rev_fold_blocked)) >> (
        rev.p.memory,
        ready.p.facts,
        dash.p.facts,
    )
    rev.p.fault >> rev.t.fold_fault(handler=petri_handler(_rev_fold_fault)) >> (
        rev.p.memory,
        ready.p.facts,
        dash.p.facts,
    )
    rev.p.empty >> rev.t.fold_empty(handler=petri_handler(_rev_fold_empty)) >> (
        rev.p.memory,
        ready.p.facts,
        dash.p.facts,
    )
    (rev.p.recover, rev.p.memory) >> rev.t.recovery(
        handler=petri_handler(_rev_recover)
    ) >> (rev.p.memory, rev.p.publishable)
    (rev.p.dismiss, rev.p.memory) >> rev.t.dismissal(
        handler=petri_handler(_rev_dismiss)
    ) >> (rev.p.memory, ready.p.facts, dash.p.facts)
    (rev.p.closed, rev.p.memory) >> rev.t.end(
        handler=petri_handler(_rev_end)
    ) >> rev.p.done(ReviewEnded)

    # -- ci loop
    (ci.p.heads, ci.p.memory) >> ci.t.on_head(
        handler=petri_handler(_ci_on_head)
    ) >> (ci.p.memory, ready.p.facts, esc.p.failures, dash.p.facts)
    (ci.p.runs, ci.p.memory) >> ci.t.assess(
        handler=petri_handler(_ci_assess)
    ) >> (ci.p.memory, ready.p.facts, esc.p.failures, dash.p.facts)
    (ci.p.echo(EscMoved), ci.p.memory) >> ci.t.recheck(
        handler=petri_handler(_ci_recheck)
    ) >> (ci.p.memory, esc.p.failures)
    (ci.p.closed, ci.p.memory) >> ci.t.end(
        handler=petri_handler(_ci_end)
    ) >> ci.p.done(CiEnded)

    # -- escalation loop
    (esc.p.failures, esc.p.ladder) >> esc.t.decide(
        handler=petri_handler(_esc_decide)
    ) >> (esc.p.ladder, esc.p.rerun_req(RerunReq), mut.p.requests, dash.p.facts)
    esc.p.rerun_req >> esc.t.rerun_gate(handler="rerun_gate") >> (
        esc.p.rerun_landed(RerunLanded),
        esc.p.rerun_moved(RerunMoved),
        esc.p.rerun_fault(RerunFault),
    )
    esc.p.rerun_landed >> esc.t.fold_rerun_landed(
        handler=petri_handler(_esc_fold_rerun_landed)
    ) >> esc.p.ladder
    esc.p.rerun_moved >> esc.t.fold_rerun_moved(
        handler=petri_handler(_esc_fold_rerun_moved)
    ) >> (esc.p.ladder, ci.p.echo)
    esc.p.rerun_fault >> esc.t.fold_rerun_fault(
        handler=petri_handler(_esc_fold_rerun_fault)
    ) >> (esc.p.ladder, ready.p.facts, dash.p.facts)
    (esc.p.settled, esc.p.ladder) >> esc.t.fold_settled(
        handler=petri_handler(_esc_fold_settled)
    ) >> (esc.p.ladder, ci.p.echo)
    # the exact-recovery door (A2): a faulted rerun reissues under the
    # SAME operation identity; the ladder baton is held through the round
    (esc.p.recover(RecoverFact), esc.p.ladder) >> esc.t.recovery(
        handler=petri_handler(_esc_recover)
    ) >> (esc.p.ladder, esc.p.rerun_req)
    (esc.p.closed, esc.p.ladder) >> esc.t.end(
        handler=petri_handler(_esc_end)
    ) >> esc.p.done(LadderEnded)

    # -- conversation loop (never ends: replies in ANY state)
    (conv.p.intents, conv.p.memory) >> conv.t.classify(
        handler=petri_handler(_conv_classify)
    ) >> (
        conv.p.memory,
        conv.p.reply_req(ReplyReq),
        conv.p.recover,
        mut.p.requests,
        mut.p.recover,
        rev.p.recover,
        rev.p.dismiss,
        rem.p.snoozes,
        rem.p.recover,
        dash.p.recover,
        ready.p.recover,
        esc.p.recover,
    )
    conv.p.reply_req >> conv.t.reply_gate(handler="reply_gate") >> (
        conv.p.replied(Replied),
        conv.p.rblocked(ReplyBlocked),
        conv.p.rfault(ReplyFault),
    )
    (conv.p.replied, conv.p.memory) >> conv.t.fold_replied(
        handler=petri_handler(_conv_fold_replied)
    ) >> (conv.p.memory, dash.p.facts)
    (conv.p.rblocked, conv.p.memory) >> conv.t.fold_rblocked(
        handler=petri_handler(_conv_fold_rblocked)
    ) >> conv.p.memory
    (conv.p.rfault, conv.p.memory) >> conv.t.fold_rfault(
        handler=petri_handler(_conv_fold_rfault)
    ) >> (conv.p.memory, dash.p.facts)
    (conv.p.recover, conv.p.memory) >> conv.t.recovery(
        handler=petri_handler(_conv_recover)
    ) >> (conv.p.memory, conv.p.reply_req)

    # -- mutation loop (the baton is the serialization)
    (mut.p.requests, mut.p.state) >> mut.t.start(
        handler=petri_handler(_mut_start)
    ) >> (mut.p.state, mut.p.work(MutWork), esc.p.settled, ready.p.facts, dash.p.facts)
    mut.p.work >> mut.t.git_gate(handler="git_gate") >> (
        mut.p.pushed(Pushed),
        mut.p.movedm(MovedM),
        mut.p.faultm(FaultM),
    )
    mut.p.pushed >> mut.t.fold_pushed(handler=petri_handler(_mut_fold_pushed)) >> (
        mut.p.state,
        life.p.provisional,
        esc.p.settled,
        ready.p.facts,
        dash.p.facts,
    )
    mut.p.movedm >> mut.t.fold_moved(handler=petri_handler(_mut_fold_moved)) >> (
        mut.p.state,
        esc.p.settled,
        ready.p.facts,
        dash.p.facts,
    )
    mut.p.faultm >> mut.t.fold_fault(handler=petri_handler(_mut_fold_fault)) >> (
        mut.p.state,
        esc.p.settled,
        ready.p.facts,
        dash.p.facts,
    )
    (mut.p.recover, mut.p.state) >> mut.t.recovery(
        handler=petri_handler(_mut_recover)
    ) >> (mut.p.state, mut.p.work, ready.p.facts, dash.p.facts)
    (mut.p.closed, mut.p.state) >> mut.t.end(
        handler=petri_handler(_mut_end)
    ) >> mut.p.done(MutEnded)

    # -- dashboard loop (upsert; republish on digest drift only)
    (dash.p.facts, dash.p.memory) >> dash.t.fold(
        handler=petri_handler(_dash_fold)
    ) >> (dash.p.memory, dash.p.pub_req(DashReq))
    dash.p.pub_req >> dash.t.publish(handler="dash_gate") >> (
        dash.p.landed(DashLanded),
        dash.p.dblocked(DashBlocked),
        dash.p.dfault(DashFault),
    )
    dash.p.landed >> dash.t.fold_landed(
        handler=petri_handler(_dash_fold_landed)
    ) >> (dash.p.memory, dash.p.heal(DashHeal))
    # self-heal after a recovery landed an exact-but-drifted retained
    # request: the transition consumes the BATON, so the reissue cycle
    # stays baton-serialized like every other cycle in the net
    (dash.p.heal, dash.p.memory) >> dash.t.selfheal(
        handler=petri_handler(_dash_selfheal)
    ) >> (dash.p.memory, dash.p.pub_req)
    dash.p.dblocked >> dash.t.fold_blocked(
        handler=petri_handler(_dash_fold_blocked)
    ) >> dash.p.memory
    dash.p.dfault >> dash.t.fold_fault(
        handler=petri_handler(_dash_fold_fault)
    ) >> dash.p.memory
    (dash.p.recover, dash.p.memory) >> dash.t.recovery(
        handler=petri_handler(_dash_recover)
    ) >> (dash.p.memory, dash.p.pub_req)
    (dash.p.closed, dash.p.memory) >> dash.t.end(
        handler=petri_handler(_dash_end)
    ) >> dash.p.done(DashEnded)

    # -- reminder loop
    (rem.p.timers, rem.p.state) >> rem.t.mature(
        handler=petri_handler(_rem_mature)
    ) >> (rem.p.state, rem.p.pub_req(RemReq))
    (rem.p.snoozes, rem.p.state) >> rem.t.snooze(
        handler=petri_handler(_rem_snooze)
    ) >> rem.p.state
    rem.p.pub_req >> rem.t.gate(handler="reminder_gate") >> (
        rem.p.rlanded(RemLanded),
        rem.p.rblocked(RemBlocked),
        rem.p.rfault(RemFault),
    )
    (rem.p.rlanded, rem.p.state) >> rem.t.fold_landed(
        handler=petri_handler(_rem_fold_landed)
    ) >> (rem.p.state, dash.p.facts, rem.p.done(RemEnded))
    (rem.p.rblocked, rem.p.state) >> rem.t.fold_blocked(
        handler=petri_handler(_rem_fold_blocked)
    ) >> (rem.p.state, rem.p.done)
    (rem.p.rfault, rem.p.state) >> rem.t.fold_fault(
        handler=petri_handler(_rem_fold_fault)
    ) >> (rem.p.state, dash.p.facts, rem.p.done)
    (rem.p.recover, rem.p.state) >> rem.t.recovery(
        handler=petri_handler(_rem_recover)
    ) >> (rem.p.state, rem.p.pub_req)
    (rem.p.closed, rem.p.state) >> rem.t.end(
        handler=petri_handler(_rem_end)
    ) >> (rem.p.state, rem.p.done)

    # -- readiness loop (the projection)
    (ready.p.facts, ready.p.snap) >> ready.t.fold(
        handler=petri_handler(_ready_fold)
    ) >> (ready.p.snap, ready.p.announce_req(AnnounceReq))
    ready.p.announce_req >> ready.t.gate(handler="announce_gate") >> (
        ready.p.alanded(ALanded),
        ready.p.ablocked(ABlocked),
        ready.p.amoved(AMoved),
        ready.p.afault(AFault),
    )
    (ready.p.alanded, ready.p.snap) >> ready.t.fold_alanded(
        handler=petri_handler(_ready_fold_alanded)
    ) >> (ready.p.snap, dash.p.facts, ready.p.done(ReadyEnded), ready.p.announce_req)
    (ready.p.ablocked, ready.p.snap) >> ready.t.fold_ablocked(
        handler=petri_handler(_ready_fold_ablocked)
    ) >> (ready.p.snap, ready.p.done)
    (ready.p.recover, ready.p.snap) >> ready.t.recovery(
        handler=petri_handler(_ready_recover)
    ) >> (ready.p.snap, ready.p.announce_req)
    (ready.p.amoved, ready.p.snap) >> ready.t.fold_amoved(
        handler=petri_handler(_ready_fold_amoved)
    ) >> (ready.p.snap, ready.p.done, ready.p.announce_req)
    (ready.p.afault, ready.p.snap) >> ready.t.fold_afault(
        handler=petri_handler(_ready_fold_afault)
    ) >> (ready.p.snap, dash.p.facts, ready.p.done)
    (ready.p.closed, ready.p.snap) >> ready.t.end(
        handler=petri_handler(_ready_end)
    ) >> (ready.p.snap, ready.p.done)

    return net.build()


# ---------------------------------------------------------------------------
# Activities — every world touch is a gate (attempt-first)
# ---------------------------------------------------------------------------


def make_activities(world: dict):
    converter = VariantPayloadConverter()

    def _post(key: str, kind: str, head: str, body) -> None:
        world["comments"].append({"key": key, "kind": kind, "head": head, "body": body})
        world["log"].append(("comment", key))

    @motus_activity(converter=converter)
    def review_agent(work: RoundOpen) -> AgentReview:
        # credential-less: sees only the work token, never the world's tokens
        world["agent_calls"] += 1
        fresh = world["agent_findings"].get(
            work.head, [{"id": f"f-{work.head}", "note": f"finding:{work.head}", "blocking": True}]
        )
        return AgentReview(
            head=work.head,
            base=work.base,
            policy=work.policy,
            incarnation=work.incarnation,
            findings=[*work.mem["provisional"], *fresh],
            mem=work.mem,
        )

    @motus_activity(converter=converter)
    def publish_gate(work: Publishable) -> LandedR | MovedR | BlockedR | FaultR:
        # lookup-first: the SAME effect identity never posts twice — and a
        # key collision with DIFFERENT content fails closed (A2)
        prior = next((c for c in world["comments"] if c["key"] == work.effect), None)
        if prior is not None:
            if prior["body"] != work.findings:
                return FaultR(reason=f"effect identity collision: {work.effect}", mem=work.mem)
            return LandedR(
                head=work.head,
                incarnation=work.incarnation,
                findings=work.findings,
                effect=work.effect,
                mem=work.mem,
            )
        for _attempt in range(3):  # bounded classified retry inside ONE occurrence
            world["comment_attempts"] += 1
            mode = world["comments_mode"]
            if mode == "retryable":
                continue
            if mode == "unknown":
                return FaultR(reason="unknown provider terminal", mem=work.mem)
            # A1.5: fresh read of EVERY claimed authority field inside the
            # gate — the live provider fields AND the host grant. The grant
            # (incarnation + phase) is what fences a request issued under a
            # PREVIOUS Running incarnation with an identical
            # head/base/policy tuple (draft → resume).
            auth = world["authority"]
            if (
                auth["phase"] != "running"
                or auth["incarnation"] != work.incarnation
                or world["branch_head"] != work.head
                or world["base_head"] != work.base
                or world["policy"] != work.policy
            ):
                return MovedR(
                    head=work.head,
                    observed=world["branch_head"],
                    observed_base=world["base_head"],
                    observed_policy=world["policy"],
                    observed_incarnation=auth["incarnation"],
                    observed_phase=auth["phase"],
                    findings=work.findings,
                    mem=work.mem,
                )
            _post(work.effect, "findings", work.head, work.findings)
            return LandedR(
                head=work.head,
                incarnation=work.incarnation,
                findings=work.findings,
                effect=work.effect,
                mem=work.mem,
            )
        return BlockedR(
            head=work.head,
            base=work.base,
            policy=work.policy,
            incarnation=work.incarnation,
            findings=work.findings,
            effect=work.effect,
            op=work.op,
            mem=work.mem,
        )

    @motus_activity(converter=converter)
    def git_gate(work: MutWork) -> Pushed | MovedM | FaultM:
        # lookup-first reconciliation: a crash AFTER the push landed but
        # BEFORE acknowledgment must not push twice (same operation identity)
        prior = next((p for p in world["pushes"] if p["key"] == work.op_key), None)
        if prior is not None:
            return Pushed(
                op=work.op,
                op_key=work.op_key,
                head=work.head,
                new_head=prior["to"],
                incarnation=work.incarnation,
                lineage=f"{work.op}({work.head})",
            )
        # A1.5: base/policy/grant are fenced by a fresh read here (the
        # push CAS only covers the head). A resolve_conflict authored under
        # an old base, any op under a revoked policy, any push against a
        # closed or drafted PR, and any op issued under a PREVIOUS Running
        # incarnation (draft → resume, identical tuple) classify `moved`.
        auth = world["authority"]
        if (
            auth["phase"] != "running"
            or auth["incarnation"] != work.incarnation
            or world["base_head"] != work.base
            or world["policy"] != work.policy
        ):
            return MovedM(
                op=work.op,
                head=work.head,
                incarnation=work.incarnation,
                observed=world["branch_head"],
                observed_incarnation=auth["incarnation"],
                observed_phase=auth["phase"],
            )
        # server-side CAS: attempt first, the push itself is the head authority check
        if world["branch_head"] != work.head:
            return MovedM(
                op=work.op,
                head=work.head,
                incarnation=work.incarnation,
                observed=world["branch_head"],
                observed_incarnation=auth["incarnation"],
                observed_phase=auth["phase"],
            )
        if world["git_mode"] == "fault":
            return FaultM(
                op=work.op,
                op_key=work.op_key,
                head=work.head,
                base=work.base,
                policy=work.policy,
                reason="provider exploded",
                incarnation=work.incarnation,
            )
        new_head = f"{work.head}+{work.op}"
        world["branch_head"] = new_head
        world["pushes"].append({"key": work.op_key, "op": work.op, "from": work.head, "to": new_head})
        world["log"].append(("push", work.op_key))
        if world["git_mode"] == "crash":
            # the push LANDED but the terminal was lost before acknowledgment
            return FaultM(
                op=work.op,
                op_key=work.op_key,
                head=work.head,
                base=work.base,
                policy=work.policy,
                reason="link lost after push",
                incarnation=work.incarnation,
            )
        return Pushed(
            op=work.op,
            op_key=work.op_key,
            head=work.head,
            new_head=new_head,
            incarnation=work.incarnation,
            lineage=f"{work.op}({work.head})",
        )

    @motus_activity(converter=converter)
    def reply_gate(work: ReplyReq) -> Replied | ReplyBlocked | ReplyFault:
        key = f"reply:{work.id}"
        if any(c["key"] == key for c in world["comments"]):  # lookup-first
            return Replied(id=work.id, text=work.text)
        for _attempt in range(3):  # bounded classified retry (A2, every kind)
            mode = world["comments_mode"]
            if mode == "retryable":
                continue
            if mode is not None:
                return ReplyFault(id=work.id, reason=str(mode))
            _post(key, "reply", "", work.text)
            return Replied(id=work.id, text=work.text)
        return ReplyBlocked(id=work.id, text=work.text)

    @motus_activity(converter=converter)
    def rerun_gate(work: RerunReq) -> RerunLanded | RerunMoved | RerunFault:
        if work.fingerprint in world["reruns"]:  # lookup-first (A2), BEFORE
            # any failure mode: a crash after the provider accepted the rerun
            # must reconcile as landed, never fault or repeat the effect
            return RerunLanded(fingerprint=work.fingerprint, op=work.op, mem=work.mem)
        if world["reruns_mode"] == "unknown":
            return RerunFault(
                fingerprint=work.fingerprint,
                op=work.op,
                reason="unknown provider terminal",
                fp=work.fp,
                head=work.head,
                base=work.base,
                policy=work.policy,
                incarnation=work.incarnation,
                mem=work.mem,
            )
        # A1.5: the gate compares ALL current authority fields — the live
        # provider fields AND the host grant (phase + incarnation). No
        # rerun lands on a closed or drafted PR, and none lands under a
        # stale Running incarnation (draft → resume, identical tuple).
        # `moved` burns no budget, and the echo lets CI reissue.
        auth = world["authority"]
        if (
            auth["phase"] != "running"
            or auth["incarnation"] != work.incarnation
            or world["branch_head"] != work.head
            or world["base_head"] != work.base
            or world["policy"] != work.policy
        ):
            return RerunMoved(
                fingerprint=work.fingerprint,
                fp=work.fp,
                head=work.head,
                base=work.base,
                policy=work.policy,
                incarnation=work.incarnation,
                op=work.op,
                mem=work.mem,
            )
        world["reruns"].append(work.fingerprint)
        world["log"].append(("rerun", work.fingerprint))
        return RerunLanded(fingerprint=work.fingerprint, op=work.op, mem=work.mem)

    @motus_activity(converter=converter)
    def reminder_gate(work: RemReq) -> RemLanded | RemBlocked | RemFault:
        key = f"reminder:{work.timer_id}"
        if any(c["key"] == key for c in world["comments"]):  # lookup-first
            return RemLanded(timer_id=work.timer_id)
        for _attempt in range(3):  # bounded classified retry (A2, every kind)
            mode = world["comments_mode"]
            if mode == "retryable":
                continue
            if mode is not None:
                return RemFault(timer_id=work.timer_id, reason=str(mode))
            _post(key, "reminder", "", "")
            return RemLanded(timer_id=work.timer_id)
        return RemBlocked(timer_id=work.timer_id)

    @motus_activity(converter=converter)
    def announce_gate(work: AnnounceReq) -> ALanded | ABlocked | AMoved | AFault:
        key = work.op  # stable operation identity: "ready:{head}:i{n}"
        if any(c["key"] == key for c in world["comments"]):  # lookup-first
            return ALanded(incarnation=work.incarnation, head=work.head)
        for _attempt in range(3):  # bounded classified retry (A2, every kind)
            mode = world["comments_mode"]
            if mode == "retryable":
                continue
            if mode == "unknown":
                return AFault(
                    op=work.op, incarnation=work.incarnation, reason="unknown provider terminal"
                )
            # A1.5: the gate compares ALL current authority fields — the
            # live provider fields AND the host grant. The grant's
            # incarnation is the ONLY field that exposes a stale announce
            # issued under a previous Running incarnation whose
            # head/base/policy tuple is IDENTICAL (draft → resume): the
            # provider state is "ready" again, but the grant moved on.
            auth = world["authority"]
            if (
                auth["phase"] != "running"
                or auth["incarnation"] != work.incarnation
                or world["branch_head"] != work.head
                or world["base_head"] != work.base
                or world["policy"] != work.policy
            ):
                return AMoved(
                    incarnation=work.incarnation,
                    observed_head=world["branch_head"],
                    observed_base=world["base_head"],
                    observed_policy=world["policy"],
                    observed_incarnation=auth["incarnation"],
                    observed_phase=auth["phase"],
                )
            _post(key, "ready", work.head, "")
            return ALanded(incarnation=work.incarnation, head=work.head)
        return ABlocked(
            incarnation=work.incarnation, head=work.head, base=work.base, policy=work.policy
        )

    @motus_activity(converter=converter)
    def dash_gate(work: DashReq) -> DashLanded | DashBlocked | DashFault:
        if world["dash_mode"] == "retryable":
            return DashBlocked(
                entries=work.entries,
                digest=work.digest,
                desired_entries=work.desired_entries,
                desired_digest=work.desired_digest,
            )
        if world["dash_mode"] == "unknown":
            return DashFault(
                entries=work.entries,
                digest=work.digest,
                desired_entries=work.desired_entries,
                desired_digest=work.desired_digest,
                reason="unknown provider terminal",
            )
        world["dashboard"] = list(work.entries)  # idempotent overwrite
        world["log"].append(("dash", work.digest))
        return DashLanded(
            entries=work.entries,
            digest=work.digest,
            desired_entries=work.desired_entries,
            desired_digest=work.desired_digest,
        )

    return (
        review_agent,
        publish_gate,
        git_gate,
        reply_gate,
        rerun_gate,
        reminder_gate,
        announce_gate,
        dash_gate,
    )


_DERIVED = {"review.agent": "review_agent"}
_VARIANT = {
    "review.publish": ("publish_gate", ("LandedR", "MovedR", "BlockedR", "FaultR")),
    "mut.git_gate": ("git_gate", ("Pushed", "MovedM", "FaultM")),
    "conv.reply_gate": ("reply_gate", ("Replied", "ReplyBlocked", "ReplyFault")),
    "esc.rerun_gate": ("rerun_gate", ("RerunLanded", "RerunMoved", "RerunFault")),
    "rem.gate": ("reminder_gate", ("RemLanded", "RemBlocked", "RemFault")),
    "ready.gate": ("announce_gate", ("ALanded", "ABlocked", "AMoved", "AFault")),
    "dash.publish": ("dash_gate", ("DashLanded", "DashBlocked", "DashFault")),
}


def _wire(built: BuiltNet, definitions: dict):
    handlers = dict(built.handlers)
    for transition, name in _DERIVED.items():
        uri = built.net.handler_uri(NetPath(transition))
        handlers[uri] = DerivedActivityHandler(built.net, NetPath(transition), definitions[name])
    for transition, (name, variants) in _VARIANT.items():
        uri = built.net.handler_uri(NetPath(transition))
        handlers[uri] = VariantRoutingActivityHandler(
            built.net, NetPath(transition), definitions[name], variants=variants
        )
    return handlers


def _seed_marking() -> Marking:
    return Marking(
        {
            NetPath("life.state"): (
                Token(
                    "LifeState",
                    {
                        "phase": "running",
                        "incarnation": 0,
                        "head": "",
                        "base": "",
                        "mergeable": False,
                        "policy": "",
                        "expected": "",
                        "expected_op": "",
                        "lineage": "",
                    },
                ),
            ),
            NetPath("review.memory"): (
                Token(
                    "ReviewMemory",
                    {
                        "reviewed": [],
                        "provisional": [],
                        "findings": [],
                        "dismissed": [],
                        "pub": {"phase": "idle"},
                    },
                ),
            ),
            NetPath("ci.memory"): (
                Token(
                    "CiMemory",
                    {
                        "head": "",
                        "base": "",
                        "policy": "",
                        "lineage": "",
                        "incarnation": 0,
                        "best": [],
                        "status": "pending",
                        "fingerprint": "",
                        "parked": [],
                    },
                ),
            ),
            NetPath("esc.ladder"): (
                Token("Ladder", {"reruns": {}, "repairs": {}, "rerun_faults": {}}),
            ),
            NetPath("conv.memory"): (
                Token("ConvMemory", {"served": [], "pending": {}, "blocked": {}, "faulted": {}}),
            ),
            NetPath("mut.state"): (Token("MutState", dict(_MUT_IDLE)),),
            NetPath("dash.memory"): (
                Token(
                    "DashMemory",
                    {"entries": [], "digest": "", "landed": "", "blocked": {}, "faulted": {}},
                ),
            ),
            NetPath("rem.state"): (
                Token(
                    "RemState",
                    {
                        "matured": [],
                        "snoozed": False,
                        "deferred": [],
                        "pending": {},
                        "blocked": {},
                        "faulted": {},
                        "closing": "",
                    },
                ),
            ),
            NetPath("ready.snap"): (
                Token(
                    "Snapshot",
                    {
                        "incarnation": 0,
                        "phase": "running",
                        "head": "",
                        "base": "",
                        "mergeable": False,
                        "policy": "",
                        "checks": "pending",
                        "findings_blocking": 0,
                        "approval": False,
                        "changes_requested": False,
                        "unresolved": 0,
                        "pending": [],
                        "faults": [],
                        "announced": [],
                        "announcing": {},
                        "blocked": {},
                        "closing": "",
                    },
                ),
            ),
        }
    )


def fresh_world() -> dict:
    return {
        "branch_head": "h1",
        "base_head": "b1",
        "policy": "p1",
        # the CURRENT lifecycle authority, as the provider itself holds it
        # (A1.5): "ready" | "draft" | "closed". Request fields are claims;
        # THIS is what a gate compares them against at effect time.
        "pr_state": "ready",
        # HOST-owned current-authority record (the lifecycle GRANT). The
        # provider knows nothing of incarnations; the HOST does, because
        # the host admits every webhook and its grant fold is the same
        # deterministic function of that stream as the lifecycle loop's.
        # Gates execute in host custody, so they read this record fresh at
        # effect time and compare it against the request's CLAIMED grant
        # (incarnation + phase + head/base/policy). This is what fences
        # two Running incarnations with an IDENTICAL head/base/policy
        # tuple (draft → resume): only the incarnation differs.
        "authority": {"incarnation": 0, "phase": "running", "head": "", "base": "", "policy": ""},
        "comments": [],
        "comments_mode": None,
        "comment_attempts": 0,
        "pushes": [],
        "git_mode": None,
        "dash_mode": None,
        "reruns": [],
        "reruns_mode": None,
        "dashboard": [],
        "agent_findings": {},
        "agent_calls": 0,
        "log": [],
    }


# the host's webhook custody: one admission point per engine updates the
# world's grant record BEFORE the net observes the event (the world moves
# first). Keyed by engine identity because delivery helpers receive only
# the engine.
_HOST: dict[int, dict] = {}


def _host_admit_head(world: dict, head: str, base: str, policy: str) -> None:
    """The host's grant fold for a head observation — the same
    deterministic rules as the lifecycle loop's `_admit_head`."""
    auth = world["authority"]
    if auth["phase"] == "terminal":
        return
    if auth["phase"] == "quiescent":
        # dormancy absorbs: the grant tracks the head, no new incarnation
        world["authority"] = {**auth, "head": head, "base": base, "policy": policy}
        return
    if head == auth["head"]:
        # refresh: same lifetime, NO incarnation bump
        world["authority"] = {**auth, "base": base, "policy": policy}
        return
    world["authority"] = {
        "incarnation": auth["incarnation"] + 1,
        "phase": "running",
        "head": head,
        "base": base,
        "policy": policy,
    }


def spawn(world: dict, *, instance: str = "pr-v5"):
    built = build_v5_net()
    definitions = {d.declaration.name: d for d in make_activities(world)}
    handlers = _wire(built, definitions)
    history = InMemoryHistoryStore()
    engine = Engine.create(
        built.net,
        instance,
        history=history,
        dispatch=InlineDispatch(definitions),
        marking=_seed_marking(),
        handlers=handlers,
        guards=dict(built.guards),
        activities=tuple(d.declaration for d in definitions.values()),
    )
    _HOST[id(engine)] = world
    return engine, history, built


def spawn_held(world: dict, *, instance: str = "pr-v5"):
    """Spawn with an explicit worker pool so a test can HOLD a gate's
    terminal open — the only honest way to observe in-flight time.

    COHABITATION COST, measured: the default `choose_conservative`
    driving policy begins no second candidate while ANY activity result
    is outstanding — one loop's in-flight gate would freeze all nine
    loops. Cohabiting concerns in one instance therefore requires the
    `choose_throughput` policy (begin every structurally independent
    candidate) for the loops to actually progress independently. A
    sharded assembly gets this isolation for free, per instance."""
    built = build_v5_net()
    definitions = {d.declaration.name: d for d in make_activities(world)}
    handlers = _wire(built, definitions)
    history = InMemoryHistoryStore()
    dispatch = InMemoryDispatch()
    engine = Engine.create(
        built.net,
        instance,
        history=history,
        dispatch=dispatch,
        marking=_seed_marking(),
        handlers=handlers,
        guards=dict(built.guards),
        activities=tuple(d.declaration for d in definitions.values()),
        policy=choose_throughput,
    )
    _HOST[id(engine)] = world
    return engine, history, built, dispatch, definitions


def pump(engine, dispatch, definitions, *, hold: frozenset[str] = frozenset(), limit: int = 400):
    """Advance and work like a worker pool, EXCEPT activities named in
    `hold`, whose invocations stay pending (in flight)."""
    for _ in range(limit):
        progressed = engine.advance().ready
        acted = False
        for occurrence, invocation in list(dispatch.pending.items()):
            if invocation.activity in hold:
                continue
            dispatch.complete(occurrence, definitions[invocation.activity](invocation, context=None))
            acted = True
        if not progressed and not acted:
            return
    raise AssertionError(f"engine did not quiesce in {limit} pumps")


def held_one(dispatch, activity: str):
    """The single pending invocation of `activity` (occurrence, invocation)."""
    [(occurrence, invocation)] = [
        (o, i) for o, i in dispatch.pending.items() if i.activity == activity
    ]
    return occurrence, invocation


def requested(chronicle, activity: str) -> list[ActivityRequested]:
    """Every durable activity request record for `activity`, in order."""
    return [
        r for r in chronicle.records if isinstance(r, ActivityRequested) and r.activity == activity
    ]


def drive(engine: Engine, limit: int = 400) -> None:
    for _ in range(limit):
        if not engine.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def tokens(engine: Engine, place: str) -> list[dict]:
    return [token.data for token in engine.marking.place(NetPath(place))]


def one(engine: Engine, place: str) -> dict:
    [data] = tokens(engine, place)
    return data


# -- delivery helpers ---------------------------------------------------------

_SEQ = {"n": 0}


def deliver(engine, door: str, color: str, data: dict) -> None:
    _SEQ["n"] += 1
    engine.deliver(door, Token(color, data), identity=f"{door}-{_SEQ['n']}")


def see_head(
    engine, head: str, base: str = "b1", mergeable: bool = True, policy: str = "p1"
) -> None:
    # the HOST admits the event: its grant record moves FIRST, then the
    # net observes (gates therefore always read current-or-fresher grant)
    _host_admit_head(_HOST[id(engine)], head, base, policy)
    deliver(
        engine,
        "on_head",
        "HeadSeen",
        {"head": head, "base": base, "mergeable": mergeable, "policy": policy},
    )


def see_run(engine, head: str, conclusion: str, run_id: int = 1, attempt: int = 1, fp: str = "fp1"):
    deliver(
        engine,
        "on_runs",
        "RunSeen",
        {"head": head, "run_id": run_id, "attempt": attempt, "conclusion": conclusion, "fingerprint": fp},
    )


def see_human(engine, approval: bool = True, changes: bool = False, unresolved: int = 0) -> None:
    deliver(
        engine,
        "on_human",
        "HumanSeen",
        {"approval": approval, "changes_requested": changes, "unresolved": unresolved},
    )


def see_draft(engine, world: dict) -> None:
    world["pr_state"] = "draft"  # the world moves FIRST; the net observes
    if world["authority"]["phase"] == "running":
        world["authority"] = {**world["authority"], "phase": "quiescent"}
    deliver(engine, "on_draft", "DraftSeen", {})


def see_resume(engine, world: dict) -> None:
    world["pr_state"] = "ready"
    auth = world["authority"]
    if auth["phase"] == "quiescent":
        # resume mints a NEW incarnation even when head/base/policy are
        # unchanged — the grant is the ONLY thing that distinguishes them
        world["authority"] = {**auth, "phase": "running", "incarnation": auth["incarnation"] + 1}
    deliver(engine, "on_ready", "ReadySeen", {})


def see_close(engine, world: dict, reason: str) -> None:
    world["pr_state"] = "closed"
    world["authority"] = {**world["authority"], "phase": "terminal"}
    deliver(engine, "on_close", "CloseSeen", {"reason": reason})


def see_comment(engine, id: str, kind: str, arg: str = "", authorized: bool = True) -> None:
    deliver(
        engine,
        "on_comment",
        "CommentSeen",
        {"id": id, "kind": kind, "arg": arg, "authorized": authorized},
    )


def ready_keys(world) -> list[str]:
    return [c["key"] for c in world["comments"] if c["kind"] == "ready"]


# ---------------------------------------------------------------------------
# Structural claims
# ---------------------------------------------------------------------------


def metrics(built: BuiltNet) -> dict[str, float]:
    net = built.net
    places, transitions, arcs = len(net.places), len(net.transitions), len(net.arcs)
    return {
        "P": places,
        "T": transitions,
        "A": arcs,
        "ratio": round(arcs / (places + transitions), 3),
        "read_arcs": sum(1 for a in net.arcs if a.is_read),
        "inhibit_arcs": sum(1 for a in net.arcs if a.is_inhibit),
        "filters": sum(1 for a in net.arcs if a.filter is not None),
        "guards": sum(len(net.guard_uris(t)) for t in net.transitions),
    }


BATONS = {
    "life.state",
    "review.memory",
    "ci.memory",
    "esc.ladder",
    "conv.memory",
    "mut.state",
    "dash.memory",
    "rem.state",
    "ready.snap",
}

# every declared cross-loop arc: (transition, foreign mailbox)
DECLARED_SEAMS = {
    # lifecycle hub → sibling mailboxes
    ("life.admit_head", "review.heads"),
    ("life.admit_head", "ci.heads"),
    ("life.admit_head", "ready.facts"),
    ("life.admit_head", "dash.facts"),
    ("life.admit_draft", "ready.facts"),
    ("life.admit_draft", "dash.facts"),
    ("life.admit_ready", "review.heads"),
    ("life.admit_ready", "ci.heads"),
    ("life.admit_ready", "ready.facts"),
    ("life.admit_ready", "dash.facts"),
    ("life.admit_close", "review.closed"),
    ("life.admit_close", "ci.closed"),
    ("life.admit_close", "esc.closed"),
    ("life.admit_close", "mut.closed"),
    ("life.admit_close", "dash.closed"),
    ("life.admit_close", "rem.closed"),
    ("life.admit_close", "ready.closed"),
    ("life.admit_comment", "conv.intents"),
    ("life.admit_human", "ready.facts"),
    ("life.admit_human", "dash.facts"),
    ("life.admit_runs", "ci.runs"),
    # review → projections
    ("review.fold_landed", "ready.facts"),
    ("review.fold_landed", "dash.facts"),
    ("review.fold_blocked", "ready.facts"),
    ("review.fold_blocked", "dash.facts"),
    ("review.fold_fault", "ready.facts"),
    ("review.fold_fault", "dash.facts"),
    ("review.fold_empty", "ready.facts"),
    ("review.fold_empty", "dash.facts"),
    ("review.dismissal", "ready.facts"),
    ("review.dismissal", "dash.facts"),
    # ci → escalation and projections
    ("ci.on_head", "ready.facts"),
    ("ci.on_head", "esc.failures"),  # parked failures reissued on authority refresh
    ("ci.on_head", "dash.facts"),
    ("ci.assess", "ready.facts"),
    ("ci.assess", "esc.failures"),
    ("ci.assess", "dash.facts"),
    # escalation → mutation and projections
    ("esc.decide", "mut.requests"),
    ("esc.decide", "dash.facts"),
    # escalation ↔ ci moved-echoes (order-independence: a `moved` settle
    # must not silently lose a still-standing failure)
    ("esc.fold_rerun_moved", "ci.echo"),
    ("esc.fold_settled", "ci.echo"),
    ("ci.recheck", "esc.failures"),
    ("esc.fold_rerun_fault", "ready.facts"),
    ("esc.fold_rerun_fault", "dash.facts"),
    # conversation → its routed outcomes
    ("conv.classify", "mut.requests"),
    ("conv.classify", "review.recover"),
    ("conv.classify", "review.dismiss"),
    ("conv.classify", "rem.snoozes"),
    # conversation → per-loop recovery mailboxes (A2: every effectful loop
    # exposes exactly one exact-recovery door, all fed by the same intent)
    ("conv.classify", "mut.recover"),
    ("conv.classify", "rem.recover"),
    ("conv.classify", "dash.recover"),
    ("conv.classify", "ready.recover"),
    ("conv.classify", "esc.recover"),
    ("conv.fold_replied", "dash.facts"),
    ("conv.fold_rfault", "dash.facts"),
    # mutation → lifecycle, escalation, projections
    ("mut.start", "esc.settled"),
    ("mut.start", "ready.facts"),
    ("mut.start", "dash.facts"),
    ("mut.fold_pushed", "life.provisional"),
    ("mut.fold_pushed", "esc.settled"),
    ("mut.fold_pushed", "ready.facts"),
    ("mut.fold_pushed", "dash.facts"),
    ("mut.fold_moved", "esc.settled"),
    ("mut.fold_moved", "ready.facts"),
    ("mut.fold_moved", "dash.facts"),
    ("mut.fold_fault", "esc.settled"),
    ("mut.fold_fault", "ready.facts"),
    ("mut.fold_fault", "dash.facts"),
    # mutation exact recovery → projections (reconciled outcome re-projected)
    ("mut.recovery", "ready.facts"),
    ("mut.recovery", "dash.facts"),
    # reminder → projections
    ("rem.fold_landed", "dash.facts"),
    ("rem.fold_fault", "dash.facts"),
    # readiness → dashboard
    ("ready.fold_alanded", "dash.facts"),
    ("ready.fold_afault", "dash.facts"),
}

DOORS = {"on_head", "on_draft", "on_ready", "on_close", "on_comment", "on_human", "on_runs", "on_timer"}


def cycles_removed_by(built: BuiltNet, removed: set[str]) -> bool:
    net = built.net
    out: dict[str, list[str]] = {}
    for a in net.arcs:
        source, target = str(a.source), str(a.target)
        if source in removed or target in removed:
            continue
        out.setdefault(source, []).append(target)
    seen: dict[str, int] = {}

    def visit(node: str) -> bool:
        seen[node] = 1
        for nxt in out.get(node, ()):
            state = seen.get(nxt)
            if state == 1 or (state is None and not visit(nxt)):
                return False
        seen[node] = 2
        return True

    return all(seen.get(str(n)) == 2 or visit(str(n)) for n in (*net.places, *net.transitions))


def components(built: BuiltNet, *, without_nodes: set[str], without_arcs: set[tuple[str, str]]) -> int:
    net = built.net
    kept = [str(n) for n in (*net.places, *net.transitions) if str(n) not in without_nodes]
    parent = {n: n for n in kept}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in net.arcs:
        source, target = str(a.source), str(a.target)
        if source in without_nodes or target in without_nodes:
            continue
        if (source, target) in without_arcs:
            continue
        parent[find(source)] = find(target)
    return len({find(n) for n in kept})


class TestTheCompleteShape:
    def test_inventory(self) -> None:
        """The COMPLETE contract in one instance — and still zero
        guards, zero read arcs, zero filters, zero inhibitors."""
        m = metrics(build_v5_net())
        assert m["read_arcs"] == 0
        assert m["guards"] == 0
        assert m["filters"] == 0
        assert m["inhibit_arcs"] == 0
        # pinned so drift is visible in review (honest count, not a target)
        assert (m["P"], m["T"], m["A"]) == (85, 77, 312)
        assert m["ratio"] == round(312 / 162, 3)

    def test_every_cycle_is_serialized_by_a_baton(self) -> None:
        """The serialization half of the anti-braid invariant.

        Deleting every baton-CONSUMING transition must break every cycle:
        all feedback — a loop folding into its own state, a gate-reopen
        deliberation, the ci↔escalation↔mutation moved-echo mesh — must
        pass through a transition that can only fire while holding some
        loop's single-token baton. What this catches: a gate self-reissue
        loop (req → gate → terminal → fold → req) whose fold does NOT
        hold a baton — the unserialized livelock shape.

        The naive form of this test ("removing the baton PLACES breaks
        every cycle") is unsatisfiable under a guard-free net: a
        legitimate reopen (announce lands → deliberate on the held
        snapshot → maybe reopen) can never put the baton place literally
        on the cycle path without a transition that fires unboundedly.
        The other half of the invariant — WHO may talk to WHOM, which is
        what rejected the dash→ready projection braid — is pinned
        exactly by test_loops_touch_only_at_declared_seams and
        test_batons_are_private.
        """
        built = build_v5_net()
        assert not cycles_removed_by(built, set())  # the net does loop
        baton_consumers = {
            str(a.target) for a in built.net.arcs if str(a.source) in BATONS
        }
        assert cycles_removed_by(built, baton_consumers)

    def test_loops_touch_only_at_declared_seams(self) -> None:
        """Remove the doors and every declared seam arc: the net falls
        apart into nine independent concern subgraphs."""
        built = build_v5_net()
        assert (
            components(built, without_nodes=DOORS, without_arcs=DECLARED_SEAMS) == 9
        )

    def test_batons_are_private(self) -> None:
        """No transition of one loop touches a sibling's places except at
        a declared seam — and the declaration is EXACT: every declared
        seam exists in the net, so the census can never silently rot."""
        net = build_v5_net().net
        actual = set()
        for a in net.arcs:
            source, target = str(a.source), str(a.target)
            owners = {source.split(".")[0], target.split(".")[0]}
            if owners & DOORS or len(owners) == 1:
                continue
            actual.add((source, target))
        assert actual == DECLARED_SEAMS


# ---------------------------------------------------------------------------
# A4 acceptance timelines
# ---------------------------------------------------------------------------


def to_all_green(engine, world, head: str = "h1") -> None:
    """Everything satisfied for `head` except whatever the test perturbs."""
    see_head(engine, head)
    drive(engine)
    see_run(engine, head, "success")
    see_human(engine)
    drive(engine)


class TestHappyPath:
    def test_full_life(self) -> None:
        """h1 reviewed (blocking finding) → CI green → approval →
        dismiss clears the only blocking finding → readiness announces
        once → merged; every loop that ends, ends."""
        world = fresh_world()
        engine, _, _ = spawn(world)
        to_all_green(engine, world)
        assert ready_keys(world) == []  # blocked by the blocking finding
        see_comment(engine, "c1", "dismiss", arg="f-h1")
        drive(engine)
        assert ready_keys(world) == ["ready:h1:i1"]
        see_close(engine, world, "merged")
        drive(engine)
        assert one(engine, "review.done")["reviewed"] == ["h1"]
        assert one(engine, "ci.done")["status"] == "success"
        assert one(engine, "ready.done")["announced"] == [1]
        assert one(engine, "mut.done")["state"] == "idle"
        assert one(engine, "life.state")["phase"] == "terminal"
        # conversation never ends: memory still in place
        assert one(engine, "conv.memory")["served"] == ["c1"]

    def test_announce_is_recorded_on_acknowledgment_only_once(self) -> None:
        world = fresh_world()
        engine, _, _ = spawn(world)
        world["agent_findings"]["h1"] = []  # nothing blocking
        to_all_green(engine, world)
        see_human(engine)  # gates re-satisfied: must NOT announce again
        drive(engine)
        assert ready_keys(world) == ["ready:h1:i1"]
        assert one(engine, "ready.snap")["announced"] == [1]


class TestA4Timelines:
    def test_1_draft_resume_same_head_announces_again(self) -> None:
        """A new lifetime at the SAME head is a new incarnation and
        must announce readiness once more."""
        world = fresh_world()
        engine, _, _ = spawn(world)
        world["agent_findings"]["h1"] = []
        to_all_green(engine, world)
        assert ready_keys(world) == ["ready:h1:i1"]
        see_draft(engine, world)
        drive(engine)
        assert one(engine, "life.state")["phase"] == "quiescent"
        see_resume(engine, world)
        drive(engine)
        # resumed: incarnation 2, per-incarnation gates reset
        assert one(engine, "life.state")["incarnation"] == 2
        see_run(engine, "h1", "success", run_id=2)
        see_human(engine)
        drive(engine)
        assert ready_keys(world) == ["ready:h1:i1", "ready:h1:i2"]

    def test_1b_concern_batons_survive_dormancy_untouched(self) -> None:
        """Nothing was drained, nothing is seeded: findings survive."""
        world = fresh_world()
        engine, _, _ = spawn(world)
        to_all_green(engine, world)
        before = one(engine, "review.memory")
        see_draft(engine, world)
        drive(engine)
        assert one(engine, "review.memory") == before

    def test_2_stale_incarnation_fact_is_inert(self) -> None:
        """An h1 run conclusion arriving after h2's admission folds
        into nothing: not the exact head, not the incarnation."""
        world = fresh_world()
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        world["branch_head"] = "h2"
        see_head(engine, "h2")
        drive(engine)
        snap_before = one(engine, "ready.snap")
        see_run(engine, "h1", "failure", fp="stale")  # late h1 terminal
        drive(engine)
        assert one(engine, "ci.memory")["status"] == "pending"  # h2 untouched
        assert one(engine, "ready.snap") == snap_before
        assert tokens(engine, "esc.rerun_req") == []  # no ladder motion
        assert world["reruns"] == []

    def test_2b_stale_state_fact_cannot_roll_readiness_backward(self) -> None:
        """Defense in depth: even a STATE fact carrying an older
        incarnation (the one fact kind that rewrites the snapshot's
        authority fields) is inert — readiness never rolls back to a
        previous head, and announce-once is not re-opened. The stale
        fact is seeded in the marking: a persisted, not-yet-folded
        leftover from before the last resume."""
        world = fresh_world()
        world["branch_head"] = "h2"
        snap_i2 = {
            "incarnation": 2,
            "phase": "running",
            "head": "h2",
            "base": "b1",
            "mergeable": True,
            "policy": "p1",
            "checks": "success",
            "findings_blocking": 0,
            "approval": True,
            "changes_requested": False,
            "unresolved": 0,
            "pending": [],
            "faults": [],
            "announced": [2],
            "announcing": False,
            "blocked": {},
        }
        stale_i1_state = {
            "kind": "state",
            "incarnation": 1,
            "body": {
                "phase": "running",
                "head": "h1",
                "base": "b1",
                "mergeable": True,
                "policy": "p1",
            },
        }
        marking = _seed_marking()
        [default_snap] = marking.place(NetPath("ready.snap"))
        marking = marking.consume(NetPath("ready.snap"), (default_snap,))
        marking = marking.deposit(NetPath("ready.snap"), Token("Snapshot", snap_i2))
        marking = marking.deposit(NetPath("ready.facts"), Token("GateFact", stale_i1_state))
        built = build_v5_net()
        definitions = {d.declaration.name: d for d in make_activities(world)}
        engine = Engine.create(
            built.net,
            "pr-stale",
            history=InMemoryHistoryStore(),
            dispatch=InlineDispatch(definitions),
            marking=marking,
            handlers=_wire(built, definitions),
            guards=dict(built.guards),
            activities=tuple(d.declaration for d in definitions.values()),
        )
        drive(engine)
        snap = one(engine, "ready.snap")
        assert snap["head"] == "h2"  # NOT rolled back to h1
        assert snap["incarnation"] == 2
        assert snap["checks"] == "success"  # per-incarnation gates kept
        assert snap["announced"] == [2]
        assert ready_keys(world) == []  # no re-announce fired

    def test_3_provisional_head_confirm_and_decline_second_mutation(self) -> None:
        world = fresh_world()
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        see_comment(engine, "c1", "change", arg="fix typo")
        drive(engine)
        # the push landed and moved the branch; lifecycle stored the expectation
        assert world["pushes"] == [
            {"key": "push:change:h1:i1", "op": "change", "from": "h1", "to": "h1+change"}
        ]
        life = one(engine, "life.state")
        assert life["expected"] == "h1+change"
        assert life["lineage"] == "change(h1)"
        # a second mutation is declined at CLASSIFICATION — before any
        # gate attempt — because lifecycle holds a provisional head (A4.3)
        see_comment(engine, "c2", "resolve_conflict")
        drive(engine)
        assert len(world["pushes"]) == 1  # declined WITHOUT effect
        assert any(
            c["key"] == "reply:c2" and c["body"] == "declined:resolve_conflict:provisional"
            for c in world["comments"]
        )
        assert one(engine, "mut.state")["state"] == "idle"
        # exact-head admission confirms and preserves lineage
        see_head(engine, "h1+change")
        drive(engine)
        life = one(engine, "life.state")
        assert life["expected"] == ""
        assert life["lineage"] == "change(h1)"
        assert life["incarnation"] == 2

    def test_3b_confirmed_relation_reaches_the_review_round(self) -> None:
        world = fresh_world()
        engine, chronicle, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        see_comment(engine, "c1", "change")
        drive(engine)
        see_head(engine, "h1+change")
        drive(engine)
        # the confirmed head was reviewed like any other head
        assert one(engine, "review.memory")["reviewed"] == ["h1", "h1+change"]

    def test_4_blocked_publication_recovers_with_the_same_identity(self) -> None:
        world = fresh_world()
        engine, _, _ = spawn(world)
        world["comments_mode"] = "retryable"
        see_head(engine, "h1")
        drive(engine)
        # three attempts inside ONE occurrence, then Blocked
        assert world["comment_attempts"] == 3
        assert [c for c in world["comments"] if c["kind"] == "findings"] == []
        assert one(engine, "review.memory")["pub"]["phase"] == "blocked"
        # unrelated events do NOT reopen it
        see_human(engine)
        drive(engine)
        assert world["comment_attempts"] == 3
        # authorized recovery: ONE fresh occurrence, SAME effect identity
        world["comments_mode"] = None
        see_comment(engine, "c1", "recover_publication", arg="findings:h1:i1")
        drive(engine)
        [posted] = [c for c in world["comments"] if c["kind"] == "findings"]
        assert posted["key"] == "findings:h1:i1"
        assert world["comment_attempts"] == 4
        assert one(engine, "review.memory")["pub"]["phase"] == "idle"

    def test_4c_recovery_is_one_fresh_occurrence_same_effect_identity(self) -> None:
        """The chronicle proves it: recovery durably requests a SECOND
        occurrence of the publish gate, distinct from the first, both
        carrying the SAME effect identity in their frozen input."""
        world = fresh_world()
        engine, chronicle, _ = spawn(world)
        world["comments_mode"] = "retryable"
        see_head(engine, "h1")
        drive(engine)
        world["comments_mode"] = None
        see_comment(engine, "c1", "recover_publication", arg="findings:h1:i1")
        drive(engine)
        records = requested(chronicle, "publish_gate")
        assert len(records) == 2  # original + recovery, nothing else
        assert records[0].occurrence != records[1].occurrence  # FRESH occurrence
        assert (
            records[0].input["work"]["effect"]
            == records[1].input["work"]["effect"]
            == "findings:h1:i1"
        )
        # and the world saw exactly one landed comment under that identity
        assert [c["key"] for c in world["comments"] if c["kind"] == "findings"] == [
            "findings:h1:i1"
        ]

    def test_4b_wrong_recovery_target_is_a_safe_no_op(self) -> None:
        world = fresh_world()
        engine, _, _ = spawn(world)
        world["comments_mode"] = "retryable"
        see_head(engine, "h1")
        drive(engine)
        world["comments_mode"] = None
        see_comment(engine, "c1", "recover_publication", arg="findings:WRONG:i9")
        drive(engine)
        assert one(engine, "review.memory")["pub"]["phase"] == "blocked"
        assert [c for c in world["comments"] if c["kind"] == "findings"] == []

    def test_5_pending_mutation_blocks_readiness_until_settled(self) -> None:
        world = fresh_world()
        engine, _, _ = spawn(world)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        drive(engine)
        see_run(engine, "h1", "success")
        drive(engine)
        # a mutation starts; then the last gate (approval) is satisfied
        see_comment(engine, "c1", "update_base")
        see_human(engine)
        drive(engine)
        # the push moved the head, so i1 never announces; and while the
        # mutation was pending, readiness held its tongue
        assert ready_keys(world) == []
        # confirm the provisional head; re-satisfy gates for i2
        world["agent_findings"]["h1+update_base"] = []
        see_head(engine, "h1+update_base")
        drive(engine)
        see_run(engine, "h1+update_base", "success", run_id=2)
        see_human(engine)
        drive(engine)
        assert ready_keys(world) == ["ready:h1+update_base:i2"]

    def test_5b_readiness_holds_while_the_mutation_is_genuinely_in_flight(self) -> None:
        """Not a simulation: the git gate's invocation is HELD PENDING
        in the worker pool while every other gate goes green — and
        readiness refuses to announce until the terminal returns."""
        world = fresh_world()
        world["agent_findings"]["h1"] = []
        engine, _, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions)
        see_run(engine, "h1", "success")
        pump(engine, dispatch, definitions)
        see_comment(engine, "c1", "update_base")
        pump(engine, dispatch, definitions, hold=frozenset({"git_gate"}))
        # the mutation is in flight RIGHT NOW
        occurrence, invocation = held_one(dispatch, "git_gate")
        # ...and the last readiness gate flips green while it is out
        see_human(engine)
        pump(engine, dispatch, definitions, hold=frozenset({"git_gate"}))
        snap = one(engine, "ready.snap")
        assert snap["pending"] == ["update_base"]  # the snapshot knows
        assert snap["announcing"] == {}  # A2: idle custody is the empty claim
        assert ready_keys(world) == []  # NOT announced
        # the worker finally returns the terminal; the push moved the
        # head, so i1 STILL never announces — that is the point
        dispatch.complete(occurrence, definitions["git_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        assert ready_keys(world) == []
        assert one(engine, "life.state")["expected"] == "h1+update_base"
        assert one(engine, "ready.snap")["pending"] == []  # settled

    def test_6_mutation_fault_fails_closed_but_never_blocks_close(self) -> None:
        world = fresh_world()
        engine, _, _ = spawn(world)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        drive(engine)
        world["git_mode"] = "fault"
        see_comment(engine, "c1", "change")
        drive(engine)
        assert one(engine, "mut.state")["state"] == "faulted"
        # further mutations are declined fail-closed, without effect
        see_comment(engine, "c2", "change")
        drive(engine)
        assert world["pushes"] == []
        # other loops continue: review lands, CI folds, replies serve
        see_run(engine, "h1", "success")
        see_human(engine)
        drive(engine)
        assert one(engine, "ci.memory")["status"] == "success"
        # readiness records the blocker and never announces
        assert "mutation" in one(engine, "ready.snap")["faults"]
        assert ready_keys(world) == []
        # and close is still collectable by EVERY loop
        see_close(engine, world, "closed")
        drive(engine)
        assert one(engine, "mut.done")["state"] == "faulted"
        assert one(engine, "ready.done")["faults"] == ["mutation"]

    def test_6b_crash_after_the_push_recovers_without_a_second_push(self) -> None:
        """The harder idempotency: the push LANDED but the terminal was
        lost. Recovery re-invokes the gate with the SAME operation
        identity; lookup-first reconciliation finds the landed push and
        completes WITHOUT pushing twice."""
        world = fresh_world()
        engine, chronicle, _ = spawn(world)
        world["git_mode"] = "crash"
        see_head(engine, "h1")
        drive(engine)
        see_comment(engine, "c1", "change")
        drive(engine)
        # the push landed in the world...
        assert [(p["key"], p["to"]) for p in world["pushes"]] == [
            ("push:change:h1:i1", "h1+change")
        ]
        # ...but the loop only knows a fault, retaining the identity
        st = one(engine, "mut.state")
        assert st["state"] == "faulted"
        assert st["op_key"] == "push:change:h1:i1"
        assert st["reason"] == "link lost after push"
        assert one(engine, "life.state")["expected"] == ""  # never told
        # authorized exact recovery: reconcile, do NOT push again
        world["git_mode"] = None
        see_comment(engine, "c2", "recover_publication", arg="push:change:h1:i1")
        drive(engine)
        assert len(world["pushes"]) == 1  # STILL exactly one push
        assert one(engine, "mut.state")["state"] == "idle"
        # the reconciled terminal completed the interrupted protocol:
        # lifecycle now expects the pushed head, lineage preserved
        life = one(engine, "life.state")
        assert life["expected"] == "h1+change"
        assert life["lineage"] == "change(h1)"
        # chronicle: two occurrences of the gate, same operation identity
        records = requested(chronicle, "git_gate")
        assert len(records) == 2
        assert records[0].occurrence != records[1].occurrence
        assert (
            records[0].input["work"]["op_key"]
            == records[1].input["work"]["op_key"]
            == "push:change:h1:i1"
        )

    def test_7_terminal_stays_a_responder_not_a_worker(self) -> None:
        world = fresh_world()
        engine, _, _ = spawn(world)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        drive(engine)
        see_close(engine, world, "merged")
        drive(engine)
        # a read-only comment is answered even in Terminal
        see_comment(engine, "c1", "status")
        drive(engine)
        assert any(c["key"] == "reply:c1" and "answer:status" in c["body"] for c in world["comments"])
        # a committing comment is declined without effect
        see_comment(engine, "c2", "change")
        drive(engine)
        assert world["pushes"] == []
        assert any(c["key"] == "reply:c2" and "declined" in c["body"] for c in world["comments"])
        # a late run observation is dropped at admission (terminal)
        see_run(engine, "h1", "failure")
        drive(engine)
        assert tokens(engine, "ci.runs") == []
        assert world["reruns"] == []

    def test_7b_a_late_known_terminal_is_collected_after_close(self) -> None:
        """Close arrives while a publication is in flight. The loop's
        baton is out with the gate, so collection WAITS; when the known
        terminal finally lands it is folded, the baton returns, and the
        loop collects — no terminal is lost, none is re-requested. And
        because the grant is TERMINAL at effect time, the publication
        classifies MOVED: nothing lands on a dead PR."""
        world = fresh_world()
        engine, chronicle, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"publish_gate"}))
        occurrence, invocation = held_one(dispatch, "publish_gate")
        see_close(engine, world, "merged")
        pump(engine, dispatch, definitions, hold=frozenset({"publish_gate"}))
        assert one(engine, "life.state")["phase"] == "terminal"
        assert tokens(engine, "review.done") == []  # waiting for the baton
        # the late terminal arrives and is COLLECTED, not re-requested
        dispatch.complete(occurrence, definitions["publish_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        done = one(engine, "review.done")
        assert done["reviewed"] == []  # moved, not landed: the PR is dead
        assert done["pub_phase"] == "idle"
        assert [c for c in world["comments"] if c["kind"] == "findings"] == []
        assert len(requested(chronicle, "publish_gate")) == 1  # ONE occurrence ever
        assert world["pushes"] == []  # and nothing committing happened

    def test_8_base_movement_starts_no_round_but_fences_effects(self) -> None:
        world = fresh_world()
        engine, _, _ = spawn(world)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        drive(engine)
        see_run(engine, "h1", "success")
        rounds_before = one(engine, "review.memory")["reviewed"]
        # the base moves in the world, and the PR observation reflects it
        # AFTER the announce request was authorized under b1:
        see_human(engine)  # this will flip readiness under base b1
        world["base_head"] = "b2"  # ...but the world has already moved
        drive(engine)
        # the announce gate compared ALL authority fields and refused
        assert ready_keys(world) == []
        # base movement admitted: same head, no new review round — the
        # agent was invoked EXACTLY once in this whole timeline
        see_head(engine, "h1", base="b2")
        drive(engine)
        assert world["agent_calls"] == 1
        assert one(engine, "review.memory")["reviewed"] == rounds_before == ["h1"]
        assert one(engine, "life.state")["incarnation"] == 1  # no bump
        # the refreshed authority re-opens the question and lands
        assert ready_keys(world) == ["ready:h1:i1"]


class TestLadderAndReminders:
    def test_escalation_ladder_rerun_then_repair_then_human(self) -> None:
        world = fresh_world()
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        # failure 1: rerun burns on landed
        see_run(engine, "h1", "failure", run_id=1, fp="fpX")
        drive(engine)
        # budget keys are lineage-scoped: "{lineage}:{fp}" (h1 mints L1)
        assert world["reruns"] == ["L1:fpX"]
        assert one(engine, "esc.ladder")["reruns"] == {"L1:fpX": "done"}
        # failure 2 (same fingerprint): repair via mutation
        see_run(engine, "h1", "failure", run_id=2, fp="fpX")
        drive(engine)
        assert [(p["op"], p["from"], p["to"]) for p in world["pushes"]] == [
            ("repair:L1:fpX", "h1", "h1+repair:L1:fpX")
        ]
        assert one(engine, "esc.ladder")["repairs"] == {"L1:fpX": "done"}
        # confirm the repair head — our OWN repair keeps the lineage (L1),
        # so the fingerprint's burned budget still stands; failure 3: human
        see_head(engine, "h1+repair:L1:fpX")
        drive(engine)
        see_run(engine, "h1+repair:L1:fpX", "failure", run_id=3, fp="fpX")
        drive(engine)
        assert len(world["reruns"]) == 1
        assert len(world["pushes"]) == 1
        assert any("human_needed" in e for e in world["dashboard"])

    def test_snooze_suppresses_the_decision_never_the_fact(self) -> None:
        world = fresh_world()
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        see_comment(engine, "c1", "snooze", arg="t1")
        drive(engine)
        deliver(engine, "on_timer", "TimerDue", {"timer_id": "t1"})
        drive(engine)
        # matured is durable; no reminder was published
        assert one(engine, "rem.state")["matured"] == ["t1"]
        assert [c for c in world["comments"] if c["kind"] == "reminder"] == []
        # resume clears the snooze; the next maturity publishes
        see_comment(engine, "c2", "resume", arg="t1")
        drive(engine)
        deliver(engine, "on_timer", "TimerDue", {"timer_id": "t2"})
        drive(engine)
        assert one(engine, "rem.state")["matured"] == ["t1", "t2"]
        assert [c["key"] for c in world["comments"] if c["kind"] == "reminder"] == ["reminder:t2"]


class TestAuthorityFencesAndCustody:
    """The oracle's two blocking areas, evidenced: A1.5 (every
    authority-sensitive gate fences the FULL claim) and A2 (every
    effectful loop holds durable Pending custody until its terminal)."""

    def test_mutation_gate_fences_moved_base_and_policy(self) -> None:
        """A committing mutation authored under (b1, p1) must classify
        `moved` when base or policy has moved by gate time — no push."""
        world = fresh_world()
        engine, _, _ = spawn(world)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        drive(engine)
        # the base moves in the world before the gate runs
        world["base_head"] = "b2"
        see_comment(engine, "c1", "change")
        drive(engine)
        assert world["pushes"] == []  # fenced: nothing landed
        assert one(engine, "mut.state")["state"] == "idle"  # baton returned
        assert one(engine, "ready.snap")["pending"] == []  # settled as moved
        # policy movement fences identically (base restored)
        world["base_head"] = "b1"
        world["policy"] = "p2"
        see_comment(engine, "c2", "change")
        drive(engine)
        assert world["pushes"] == []
        assert one(engine, "mut.state")["state"] == "idle"
        assert one(engine, "ready.snap")["pending"] == []

    def test_rerun_gate_fences_moved_base_without_burning_budget(self) -> None:
        """A rerun request under a moved base classifies `moved` and
        burns NO rerun budget; the next failure retries the rerun."""
        world = fresh_world()
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        world["base_head"] = "b2"
        see_run(engine, "h1", "failure", run_id=1, fp="fpZ")
        drive(engine)
        assert world["reruns"] == []  # fenced
        assert one(engine, "esc.ladder")["reruns"] == {}  # budget NOT burned
        # authority restored: the same fingerprint still gets its rerun
        world["base_head"] = "b1"
        see_run(engine, "h1", "failure", run_id=2, fp="fpZ")
        drive(engine)
        assert world["reruns"] == ["L1:fpZ"]
        assert one(engine, "esc.ladder")["reruns"] == {"L1:fpZ": "done"}

    def test_reminder_pending_custody_is_single_flight(self) -> None:
        """While a reminder comment is in flight the baton records
        Pending: a duplicate maturity cannot double the effect, yet the
        baton stays available (a snooze still folds mid-flight)."""
        world = fresh_world()
        engine, _, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"reminder_gate"}))
        deliver(engine, "on_timer", "TimerDue", {"timer_id": "t1"})
        pump(engine, dispatch, definitions, hold=frozenset({"reminder_gate"}))
        assert one(engine, "rem.state")["pending"] == {"t1": True}
        # duplicate maturity while in flight: recorded, NOT re-requested
        deliver(engine, "on_timer", "TimerDue", {"timer_id": "t1"})
        # the baton is available mid-flight: a snooze folds NOW
        see_comment(engine, "c1", "snooze", arg="t1")
        pump(engine, dispatch, definitions, hold=frozenset({"reminder_gate"}))
        st = one(engine, "rem.state")
        assert st["matured"] == ["t1", "t1"]  # the fact is durable, twice
        assert st["snoozed"] is True  # folded while the gate was held
        [(occurrence, invocation)] = [
            (o, i) for o, i in dispatch.pending.items() if i.activity == "reminder_gate"
        ]  # exactly ONE in-flight reminder effect
        dispatch.complete(occurrence, definitions["reminder_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        assert one(engine, "rem.state")["pending"] == {}
        assert [c["key"] for c in world["comments"] if c["kind"] == "reminder"] == ["reminder:t1"]

    def test_reminder_fault_retains_reason_and_stays_closed(self) -> None:
        """An unknown reminder terminal folds Faulted with retention;
        unrelated maturities neither reopen nor duplicate it."""
        world = fresh_world()
        engine, _, _ = spawn(world)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        drive(engine)
        world["comments_mode"] = "unknown"
        deliver(engine, "on_timer", "TimerDue", {"timer_id": "t1"})
        drive(engine)
        st = one(engine, "rem.state")
        assert st["faulted"] == {"t1": "unknown"}
        assert st["pending"] == {}
        # an unrelated timer proceeds; the fault stays exactly as retained
        world["comments_mode"] = None
        deliver(engine, "on_timer", "TimerDue", {"timer_id": "t2"})
        drive(engine)
        st = one(engine, "rem.state")
        assert st["faulted"] == {"t1": "unknown"}
        assert [c["key"] for c in world["comments"] if c["kind"] == "reminder"] == ["reminder:t2"]

    def test_reply_pending_custody_is_per_id_and_concurrent(self) -> None:
        """Replies are deliberately concurrent: two intents hold two
        Pending records at once; each terminal clears only its own."""
        world = fresh_world()
        engine, _, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"reply_gate"}))
        see_comment(engine, "c1", "status")
        see_comment(engine, "c2", "status")
        pump(engine, dispatch, definitions, hold=frozenset({"reply_gate"}))
        assert set(one(engine, "conv.memory")["pending"]) == {"c1", "c2"}
        held = [(o, i) for o, i in dispatch.pending.items() if i.activity == "reply_gate"]
        assert len(held) == 2  # genuinely concurrent effects
        occurrence, invocation = held[0]
        dispatch.complete(occurrence, definitions["reply_gate"](invocation, context=None))
        pump(engine, dispatch, definitions, hold=frozenset({"reply_gate"}))
        assert len(one(engine, "conv.memory")["pending"]) == 1  # only its own cleared
        occurrence, invocation = held[1]
        dispatch.complete(occurrence, definitions["reply_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        assert one(engine, "conv.memory")["pending"] == {}
        assert {c["key"] for c in world["comments"]} >= {"reply:c1", "reply:c2"}

    def test_dash_blocked_recovery_publishes_accumulated_entries(self) -> None:
        """Entries accumulated while the dashboard was blocked are all
        carried by the recovery upsert — nothing is lost to the race
        the held-baton custody closes."""
        world = fresh_world()
        world["dash_mode"] = "retryable"
        engine, _, _ = spawn(world)
        world["agent_findings"]["h1"] = []
        see_head(engine, "h1")
        drive(engine)
        see_run(engine, "h1", "success")  # accumulates while blocked
        see_human(engine)  # accumulates while blocked
        drive(engine)
        mem = one(engine, "dash.memory")
        assert mem["blocked"]  # fail-closed, entries retained
        accumulated = list(mem["entries"])
        assert len(accumulated) >= 3
        world["dash_mode"] = None
        see_comment(engine, "c1", "recover_publication", arg=f"dash:{mem['blocked']['digest']}")
        drive(engine)
        assert one(engine, "dash.memory")["blocked"] == {}
        # every entry accumulated during the blocked window is on the board
        assert set(accumulated) <= set(world["dashboard"])


class TestOracleBlockers:
    """Focused evidence for the third oracle verdict's three blockers:
    incarnation fencing against CURRENT authority (A1.5), terminal
    custody surviving Close with exact-effect retention (A2/A3), and
    lineage-scoped escalation budgets with exact operation identity."""

    def test_stale_incarnation_announce_is_fenced_by_current_state(self) -> None:
        """Same head, same base, same policy — but the PR flipped to
        draft while the announce was in flight. Request fields cannot
        expose this; only the gate's read of CURRENT authority can. The
        stale announce must not land, and the resumed incarnation must
        announce exactly once."""
        world = fresh_world()
        world["agent_findings"]["h1"] = []
        engine, _, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"announce_gate"}))
        see_run(engine, "h1", "success")
        see_human(engine)
        pump(engine, dispatch, definitions, hold=frozenset({"announce_gate"}))
        occurrence, invocation = held_one(dispatch, "announce_gate")
        # the world moves FIRST (draft), then the net observes it
        see_draft(engine, world)
        pump(engine, dispatch, definitions, hold=frozenset({"announce_gate"}))
        # the held i1 announce now executes against the CURRENT authority
        dispatch.complete(occurrence, definitions["announce_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        assert ready_keys(world) == []  # the stale effect never landed
        snap = one(engine, "ready.snap")
        assert snap["announced"] == []  # and was never recorded as announced
        # resume: a NEW incarnation announces once, under fresh authority
        see_resume(engine, world)
        pump(engine, dispatch, definitions)
        see_run(engine, "h1", "success")
        see_human(engine)
        pump(engine, dispatch, definitions)
        assert ready_keys(world) == ["ready:h1:i2"]
        assert one(engine, "ready.snap")["announced"] == [2]

    def test_close_while_announce_is_in_flight_settles_exactly_once(self) -> None:
        """Close arrives while the announce gate is out. The loop defers
        its end, the late terminal is collected, and the loop ends
        exactly once — no lost terminal, no double end."""
        world = fresh_world()
        world["agent_findings"]["h1"] = []
        engine, _, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"announce_gate"}))
        see_run(engine, "h1", "success")
        see_human(engine)
        pump(engine, dispatch, definitions, hold=frozenset({"announce_gate"}))
        occurrence, invocation = held_one(dispatch, "announce_gate")
        see_close(engine, world, "closed")
        pump(engine, dispatch, definitions, hold=frozenset({"announce_gate"}))
        assert tokens(engine, "ready.done") == []  # deferred: terminal is out
        assert one(engine, "ready.snap")["closing"] == "closed"
        dispatch.complete(occurrence, definitions["announce_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        [done] = tokens(engine, "ready.done")  # exactly one end
        assert done["reason"] == "closed"

    def test_close_while_reminder_is_in_flight_settles_exactly_once(self) -> None:
        """The reminder analog: a matured reminder's comment is in
        flight when Close arrives; the loop waits for its terminal and
        ends exactly once."""
        world = fresh_world()
        engine, _, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"reminder_gate"}))
        deliver(engine, "on_timer", "TimerDue", {"timer_id": "t1"})
        pump(engine, dispatch, definitions, hold=frozenset({"reminder_gate"}))
        occurrence, invocation = held_one(dispatch, "reminder_gate")
        see_close(engine, world, "merged")
        pump(engine, dispatch, definitions, hold=frozenset({"reminder_gate"}))
        assert tokens(engine, "rem.done") == []  # deferred: terminal is out
        assert one(engine, "rem.state")["closing"] == "merged"
        dispatch.complete(occurrence, definitions["reminder_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        [done] = tokens(engine, "rem.done")  # exactly one end
        assert done["reason"] == "merged"
        # the terminal settled BEFORE the end: the effect landed, and the
        # ended loop retires its baton (no zombie custody)
        assert [c["key"] for c in world["comments"] if c["kind"] == "reminder"] == ["reminder:t1"]
        assert tokens(engine, "rem.state") == []

    def test_dashboard_unknown_terminal_retains_exact_effect_and_recovers_once(self) -> None:
        """An unknown dashboard terminal folds Faulted with the EXACT
        effect (entries + digest) and reason; recovery reissues the
        upsert once with the same digest identity."""
        world = fresh_world()
        world["dash_mode"] = "unknown"
        world["agent_findings"]["h1"] = []
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        mem = one(engine, "dash.memory")
        assert mem["faulted"]["reason"] == "unknown provider terminal"
        digest = mem["faulted"]["digest"]
        assert digest  # the exact attempted effect identity is retained
        retained = list(mem["entries"])
        assert world["dashboard"] == []  # nothing landed
        world["dash_mode"] = None
        see_comment(engine, "c1", "recover_publication", arg=f"dash:{digest}")
        drive(engine)
        mem2 = one(engine, "dash.memory")
        assert mem2["faulted"] == {} and mem2["blocked"] == {}
        assert set(retained) <= set(world["dashboard"])  # the exact effect landed
        assert [d for _, d in world["log"] if _ == "dash"].count(digest) <= 1

    def test_same_fingerprint_gets_fresh_budget_on_a_new_lineage(self) -> None:
        """The same flake fingerprint on GENUINELY new code (a
        superseding head) earns a fresh ladder: rerun again, not repair."""
        world = fresh_world()
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        see_run(engine, "h1", "failure", run_id=1, fp="flake")
        drive(engine)
        assert world["reruns"] == ["L1:flake"]
        # the author pushes new code; the SAME flake bites again
        world["branch_head"] = "h2"
        see_head(engine, "h2")
        drive(engine)
        see_run(engine, "h2", "failure", run_id=2, fp="flake")
        drive(engine)
        assert world["reruns"] == ["L1:flake", "L2:flake"]  # fresh budget: h2 is L2
        assert world["pushes"] == []  # no repair was reached

    def test_rerun_crash_after_provider_success_recovers_without_duplicate(self) -> None:
        """The provider accepted the rerun but the terminal was lost.
        The reissued operation reconciles lookup-first under the SAME
        operation identity: landed, no duplicate provider effect."""
        world = fresh_world()
        # the provider already holds this rerun from the lost round
        world["reruns"].append("L1:flake")
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        see_run(engine, "h1", "failure", run_id=1, fp="flake")
        drive(engine)
        assert world["reruns"] == ["L1:flake"]  # ONE provider effect ever
        assert one(engine, "esc.ladder")["reruns"] == {"L1:flake": "done"}

    def test_failure_then_refresh_converges_by_park_and_reissue(self) -> None:
        """The base moves before the failure's rerun executes and the
        refresh has NOT yet folded: the moved echo parks the fingerprint
        (no blind reissue), and the authority refresh reissues it."""
        world = fresh_world()
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        world["base_head"] = "b2"  # the world moves first
        see_run(engine, "h1", "failure", run_id=1, fp="fpQ")
        drive(engine)
        assert world["reruns"] == []  # moved: fenced, budget intact
        assert one(engine, "ci.memory")["parked"] == ["fpQ"]  # parked, not lost
        assert one(engine, "esc.ladder")["reruns"] == {}
        # the refresh arrives: the parked failure is reissued and lands
        see_head(engine, "h1", base="b2")
        drive(engine)
        assert world["reruns"] == ["L1:fpQ"]
        assert one(engine, "ci.memory")["parked"] == []

    def test_refresh_then_failure_converges_by_immediate_reissue(self) -> None:
        """The refresh folds while the rerun is still in flight: the
        moved echo sees a fresher admitted tuple and reissues at once —
        order-independence with the park case, same converged outcome."""
        world = fresh_world()
        engine, _, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"rerun_gate"}))
        see_run(engine, "h1", "failure", run_id=1, fp="fpQ")
        pump(engine, dispatch, definitions, hold=frozenset({"rerun_gate"}))
        occurrence, invocation = held_one(dispatch, "rerun_gate")
        # the world moves AND the refresh folds while the gate is out
        world["base_head"] = "b2"
        see_head(engine, "h1", base="b2")
        pump(engine, dispatch, definitions, hold=frozenset({"rerun_gate"}))
        dispatch.complete(occurrence, definitions["rerun_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        assert world["reruns"] == ["L1:fpQ"]  # reissued under b2, landed
        assert one(engine, "ci.memory")["parked"] == []
        assert one(engine, "esc.ladder")["reruns"] == {"L1:fpQ": "done"}


class TestFourthVerdictBlockers:
    """Focused evidence for the fourth oracle verdict's three blockers:
    (1) the HOST-owned grant fences a stale Running incarnation whose
    head/base/policy tuple is IDENTICAL to the current one (the
    draft→resume race, executed while the PR is ready again); (2) the
    dashboard's recovery reissues the EXACT retained request and then
    self-heals the drift; (3) the escalation ladder's rungs are
    discriminated — pending waits, faulted fails closed, and a faulted
    rerun recovers through its own exact-recovery door."""

    def test_stale_announce_across_draft_and_resume_never_lands(self) -> None:
        """THE incarnation race: hold the i1 announce, flip to draft,
        resume to i2 with the SAME head/base/policy, and only then let
        the i1 gate execute — while the PR is 'ready'. Every provider
        field matches the claim; only the grant's incarnation (i2 ≠ i1)
        exposes the staleness. The stale announce must not land, and i2
        announces exactly once when it earns readiness."""
        world = fresh_world()
        world["agent_findings"]["h1"] = []
        engine, _, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"announce_gate"}))
        see_run(engine, "h1", "success")
        see_human(engine)
        pump(engine, dispatch, definitions, hold=frozenset({"announce_gate"}))
        occurrence, invocation = held_one(dispatch, "announce_gate")
        see_draft(engine, world)
        see_resume(engine, world)  # SAME tuple; the grant moves i1 → i2
        pump(engine, dispatch, definitions, hold=frozenset({"announce_gate"}))
        assert world["pr_state"] == "ready"  # the provider looks ready again
        dispatch.complete(occurrence, definitions["announce_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        assert ready_keys(world) == []  # the stale effect NEVER landed
        assert one(engine, "ready.snap")["announced"] == []
        # i2 earns readiness under its own grant and announces once
        see_run(engine, "h1", "success")
        see_human(engine)
        pump(engine, dispatch, definitions)
        assert ready_keys(world) == ["ready:h1:i2"]
        assert one(engine, "ready.snap")["announced"] == [2]

    def test_stale_findings_publish_across_draft_and_resume_moves(self) -> None:
        """The findings analog of the announce race: the i1 publication
        executes after resume minted i2 under an identical tuple. It
        classifies MOVED (nothing posts), the findings survive as
        provisional, and the i2 round republishes them exactly once."""
        world = fresh_world()
        engine, chronicle, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"publish_gate"}))
        occurrence, invocation = held_one(dispatch, "publish_gate")
        see_draft(engine, world)
        see_resume(engine, world)  # SAME tuple; the grant moves i1 → i2
        pump(engine, dispatch, definitions, hold=frozenset({"publish_gate"}))
        dispatch.complete(occurrence, definitions["publish_gate"](invocation, context=None))
        pump(engine, dispatch, definitions, hold=frozenset({"publish_gate"}))
        # the stale publication landed NOTHING; the findings are custody
        assert [c for c in world["comments"] if c["kind"] == "findings"] == []
        pump(engine, dispatch, definitions)  # release the i2 round
        posted = [c for c in world["comments"] if c["kind"] == "findings"]
        assert [c["key"] for c in posted] == ["findings:h1:i2"]
        assert len(requested(chronicle, "publish_gate")) == 2  # i1 moved, i2 landed

    def test_stale_mutation_across_draft_and_resume_moves(self) -> None:
        """A committing op authored under i1 executes after resume
        minted i2 — same head, same base, same policy, PR ready. The
        push CAS CANNOT catch this (the head never moved); only the
        grant comparison can. No push happens."""
        world = fresh_world()
        world["agent_findings"]["h1"] = []
        engine, _, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"git_gate"}))
        see_comment(engine, "c1", "change")
        pump(engine, dispatch, definitions, hold=frozenset({"git_gate"}))
        occurrence, invocation = held_one(dispatch, "git_gate")
        see_draft(engine, world)
        see_resume(engine, world)  # SAME tuple; the grant moves i1 → i2
        pump(engine, dispatch, definitions, hold=frozenset({"git_gate"}))
        assert world["pr_state"] == "ready" and world["branch_head"] == "h1"
        dispatch.complete(occurrence, definitions["git_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        assert world["pushes"] == []  # the stale op NEVER pushed
        assert one(engine, "mut.state") == dict(_MUT_IDLE)  # settled moved

    def test_stale_rerun_across_draft_and_resume_moves_then_reissues(self) -> None:
        """A rerun issued under i1 executes after resume minted i2 with
        the identical tuple: it classifies MOVED (no provider effect, no
        budget burned, no unmarked rung poisoning the ladder). Resume
        reset CI to pending, so the moved echo is inert — the failure
        re-enters through the admission contract (the host redelivers
        the standing run observation, as every resume test does), and
        the reissued rerun lands under i2 with the KEPT lineage."""
        world = fresh_world()
        world["agent_findings"]["h1"] = []
        engine, _, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"rerun_gate"}))
        see_run(engine, "h1", "failure", run_id=1, fp="fpS")
        pump(engine, dispatch, definitions, hold=frozenset({"rerun_gate"}))
        occurrence, invocation = held_one(dispatch, "rerun_gate")
        see_draft(engine, world)
        see_resume(engine, world)  # SAME tuple; the grant moves i1 → i2
        pump(engine, dispatch, definitions, hold=frozenset({"rerun_gate"}))
        dispatch.complete(occurrence, definitions["rerun_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        # the stale attempt never landed, and the moved echo minted NO
        # spurious escalation against the reset (pending) CI memory
        assert world["reruns"] == []
        assert one(engine, "ci.memory")["status"] == "pending"
        # the host redelivers the standing failure at admission
        # (at-least-once): the ladder decides afresh — the moved round
        # never marked the rung — and the rerun lands under i2
        see_run(engine, "h1", "failure", run_id=1, fp="fpS")
        pump(engine, dispatch, definitions)
        assert world["reruns"] == ["L1:fpS"]  # resume KEEPS the lineage
        assert one(engine, "esc.ladder")["reruns"] == {"L1:fpS": "done"}

    def test_dash_recovery_reissues_the_exact_request_then_self_heals(self) -> None:
        """The faulted upsert is retained EXACTLY (entries + digest).
        While the fault is held, more facts accumulate — the desired
        state drifts. Recovery reissues the retained request verbatim
        (the operation the human was told about), and the landed fold
        self-heals the drift with a follow-up upsert of the desired
        state. The board ends up current; the exact digest lands once."""
        world = fresh_world()
        world["dash_mode"] = "unknown"
        world["agent_findings"]["h1"] = []
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        mem = one(engine, "dash.memory")
        exact = mem["faulted"]
        assert exact["entries"] and exact["digest"]
        desired_before = list(mem["entries"])
        assert len(desired_before) > len(exact["entries"])  # real drift
        world["dash_mode"] = None
        see_comment(engine, "c1", "recover_publication", arg=f"dash:{exact['digest']}")
        drive(engine)
        upserts = [d for k, d in world["log"] if k == "dash"]
        assert upserts[0] == exact["digest"]  # the EXACT request, first
        assert upserts.count(exact["digest"]) == 1  # and only once
        # the drift healed: every accumulated entry is on the board, and
        # memory agrees with what actually landed
        assert set(desired_before) <= set(world["dashboard"])
        mem2 = one(engine, "dash.memory")
        assert mem2["faulted"] == {} and mem2["blocked"] == {}
        assert mem2["digest"] == mem2["landed"]

    def test_second_failure_waits_while_repair_is_pending(self) -> None:
        """A repair is in flight when the same fingerprint fails again:
        the ladder WAITS — no second push, no human page. The repair's
        settle decides the next move."""
        world = fresh_world()
        world["agent_findings"]["h1"] = []
        engine, chronicle, _, dispatch, definitions = spawn_held(world)
        see_head(engine, "h1")
        pump(engine, dispatch, definitions, hold=frozenset({"git_gate"}))
        see_run(engine, "h1", "failure", run_id=1, fp="fpW")
        pump(engine, dispatch, definitions, hold=frozenset({"git_gate"}))  # rerun lands
        see_run(engine, "h1", "failure", run_id=2, fp="fpW")
        pump(engine, dispatch, definitions, hold=frozenset({"git_gate"}))  # repair out
        assert len(requested(chronicle, "git_gate")) == 1
        see_run(engine, "h1", "failure", run_id=3, fp="fpW")
        pump(engine, dispatch, definitions, hold=frozenset({"git_gate"}))
        # the duplicate failure WAITED: one repair ever, nobody paged
        assert len(requested(chronicle, "git_gate")) == 1
        assert not any("human_needed" in e for e in one(engine, "dash.memory")["entries"])
        occurrence, invocation = held_one(dispatch, "git_gate")
        dispatch.complete(occurrence, definitions["git_gate"](invocation, context=None))
        pump(engine, dispatch, definitions)
        assert [p["op"] for p in world["pushes"]] == ["repair:L1:fpW"]
        assert one(engine, "esc.ladder")["repairs"] == {"L1:fpW": "done"}

    def test_faulted_repair_recovery_after_base_move_refunds_and_relands(self) -> None:
        """The fifth-verdict blocker: a FAULTED repair rung retains its
        entry (not a bare marker). Timeline — repair faults; the base
        refreshes; exact recovery reissues the OLD request, which the
        gate classifies MOVED (stale base, no push); the moved settle
        REFUNDS the rung and echoes a recheck; CI reissues the standing
        failure under the fresh base; exactly ONE repair lands."""
        world = fresh_world()
        world["agent_findings"]["h1"] = []
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        see_run(engine, "h1", "failure", run_id=1, fp="fpV")
        drive(engine)  # rung 1: the rerun lands
        assert world["reruns"] == ["L1:fpV"]
        world["git_mode"] = "fault"
        see_run(engine, "h1", "failure", run_id=2, fp="fpV")
        drive(engine)  # rung 2: the repair FAULTS
        entry = one(engine, "esc.ladder")["repairs"]["L1:fpV"]
        assert entry["state"] == "fault" and entry["base"] == "b1"  # retained
        assert one(engine, "mut.state")["op_key"] == "push:repair:L1:fpV:h1:i1"
        # the base moves while the fault is held (same head: a refresh)
        world["base_head"] = "b2"
        see_head(engine, "h1", base="b2")
        drive(engine)
        # authorized exact recovery reissues the OLD request (base b1):
        # the gate's fresh read classifies MOVED — no stale push
        world["git_mode"] = None
        see_comment(engine, "c1", "recover_publication", arg="push:repair:L1:fpV:h1:i1")
        drive(engine)
        pushes = [p for p in world["pushes"] if p["op"] == "repair:L1:fpV"]
        assert len(pushes) == 1  # exactly ONE repair ever pushed...
        # ...authored under the FRESH base: the moved settle refunded the
        # rung, echoed the recheck, and CI reissued under b2
        assert one(engine, "esc.ladder")["repairs"]["L1:fpV"] == "done"
        assert one(engine, "mut.state")["state"] == "idle"

    def test_faulted_rerun_fails_closed_and_recovers_by_the_door(self) -> None:
        """An unknown rerun terminal marks the rung FAULTED. A later
        failure on the same rung must NOT advance to repair (the rung is
        unproven — the provider may or may not hold the rerun): it fails
        closed and pages the human. The esc.recover door reissues the
        SAME operation identity; lookup-first reconciles."""
        world = fresh_world()
        world["reruns_mode"] = "unknown"
        world["agent_findings"]["h1"] = []
        engine, _, _ = spawn(world)
        see_head(engine, "h1")
        drive(engine)
        see_run(engine, "h1", "failure", run_id=1, fp="fpF")
        drive(engine)
        ladder = one(engine, "esc.ladder")
        assert ladder["reruns"] == {"L1:fpF": "fault"}
        assert ladder["rerun_faults"]["L1:fpF"]["op"] == "rerun:L1:fpF"
        # the same rung fails again: FAIL-CLOSED, no repair authorized
        see_run(engine, "h1", "failure", run_id=2, fp="fpF")
        drive(engine)
        assert world["pushes"] == []  # the unproven rung authorized NOTHING
        assert any("rerun-fault" in e for e in world["dashboard"])
        # the provider answers again: the door reissues the exact op
        world["reruns_mode"] = None
        see_comment(engine, "c1", "recover_publication", arg="rerun:L1:fpF")
        drive(engine)
        assert world["reruns"] == ["L1:fpF"]  # ONE provider effect, same op
        ladder2 = one(engine, "esc.ladder")
        assert ladder2["reruns"] == {"L1:fpF": "done"}
        assert ladder2["rerun_faults"] == {}


class TestReplay:
    def test_the_resurrected_instance_holds_the_final_marking(self) -> None:
        world = fresh_world()
        engine, chronicle, built = spawn(world)
        to_all_green(engine, world)
        see_comment(engine, "c1", "dismiss", arg="f-h1")
        drive(engine)
        see_close(engine, world, "merged")
        drive(engine)
        effects_before = (list(world["comments"]), list(world["pushes"]), list(world["dashboard"]))

        definitions = {d.declaration.name: d for d in make_activities(world)}
        resurrected = Engine.load(
            built.net,
            "pr-v5",
            history=chronicle,
            dispatch=InlineDispatch(definitions),
            handlers=_wire(built, definitions),
            guards=dict(built.guards),
            activities=tuple(d.declaration for d in definitions.values()),
        )
        # the ENTIRE marking is bit-identical, not just headline places
        assert resurrected.marking == engine.marking
        assert one(resurrected, "review.done")["reviewed"] == ["h1"]
        assert one(resurrected, "ready.done")["announced"] == [1]
        assert one(resurrected, "life.state")["phase"] == "terminal"
        assert not resurrected.advance().ready  # nothing re-fires
        assert (world["comments"], world["pushes"], world["dashboard"]) == effects_before
