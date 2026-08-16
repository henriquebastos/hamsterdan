"""Shared test harness for the V5 actor-loop topology.

Spawns the composed net on the frozen engine and drives host-normalized
observations through the ingress doors. The harness plays the HOST: it
owns a fake world with the current-authority grant record, moves the
world BEFORE the net observes any event (gates therefore always read a
current-or-fresher grant), and binds every gate to a world-backed fake
activity.
"""

import ast

from petrus.engine import Engine, choose_throughput
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import NetPath, Token
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch, InMemoryDispatch

from hamsterdan.contracts.readiness_v5 import (
    ABlocked,
    AFault,
    AgentReview,
    ALanded,
    AMoved,
    AnnounceReq,
    DashBlocked,
    DashFault,
    DashLanded,
    DashReq,
    DeclinedM,
    FaultM,
    MovedM,
    MutWork,
    Publishable,
    Pushed,
    RemBlocked,
    RemFault,
    RemLanded,
    RemReq,
    Replied,
    ReplyBlocked,
    ReplyFault,
    ReplyReq,
    RerunFault,
    RerunLanded,
    RerunMoved,
    RerunReq,
    ReviewBlocked,
    ReviewFault,
    ReviewLanded,
    ReviewMoved,
    RoundOpen,
    RoundUnable,
)
from hamsterdan.readiness.net_v5 import build_net_v5, seed_marking
from hamsterdan.readiness.net_v5.gating import VariantPayloadConverter, wire_gates
from hamsterdan.readiness.net_v5.topology import DERIVED, GATES

# -- the fake world ---------------------------------------------------------


def fresh_world() -> dict:
    return {
        # the provider's live fields, compared by gates at effect time
        "branch_head": "",
        "base_head": "",
        "policy": "",
        "pr_state": "ready",
        # HOST-owned current-authority record (the lifecycle GRANT); the
        # provider knows nothing of incarnations, the host does
        "authority": {"incarnation": 0, "phase": "running", "head": "", "base": "", "policy": ""},
        "reruns": [],
        "reruns_mode": None,
        "runs_by_head": {},  # provider truth: newest (run_id, attempt) per head
        # review: agent output per head and the provider's comment store
        "agent_calls": 0,
        "agent_findings": {},  # head -> findings list (default: one blocker)
        "agent_results": {},  # head -> exact {findings, lineage} result
        "agent_mode": None,  # None | "unable"
        "comments": [],
        "comments_mode": None,  # None | "retryable" | "unknown"
        "comment_attempts": 0,
        # mutation: the provider's push ledger, keyed by operation identity
        "pushes": [],  # {"key", "op", "from", "to"}
        "git_mode": None,  # None | "fault" | "crash" (landed, terminal lost)
        # dashboard: the provider's board (an idempotent overwrite target)
        "dashboard": [],
        "dash_mode": None,  # None | "retryable" | "unknown"
        "dash_requests": [],  # EVERY attempted upsert {entries, digest}
        "log": [],
    }


def make_activities(world: dict):
    converter = VariantPayloadConverter()

    @motus_activity(converter=converter)
    def rerun_gate(work: RerunReq) -> RerunLanded | RerunMoved | RerunFault:
        if work.fingerprint in world["reruns"]:  # lookup-first (A2), BEFORE
            # any failure mode: a crash after the provider accepted the
            # rerun must reconcile as landed, never fault or repeat
            return RerunLanded(
                fingerprint=work.fingerprint,
                op=work.op,
                run_id=work.run_id,
                attempt=work.attempt,
                disposition="existing",
                cut_run_id=work.run_id,  # meaningless for existing:
                cut_attempt=work.attempt,  # echo the answered evidence
                mem=work.mem,
            )
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
                run_id=work.run_id,
                attempt=work.attempt,
                mem=work.mem,
            )
        # A1.5: the gate compares ALL current authority fields — the live
        # provider fields AND the host grant (phase + incarnation)
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
        # the pre-request evidence CUT: the newest run the provider
        # reports for this head, read immediately before issuance
        cut = world["runs_by_head"].get(work.head, (0, 0))
        world["reruns"].append(work.fingerprint)
        world["log"].append(("rerun", work.fingerprint))
        return RerunLanded(
            fingerprint=work.fingerprint,
            op=work.op,
            run_id=work.run_id,
            attempt=work.attempt,
            disposition="requested",
            cut_run_id=cut[0],
            cut_attempt=cut[1],
            mem=work.mem,
        )

    @motus_activity(converter=converter)
    def review_agent(work: RoundOpen) -> AgentReview | RoundUnable:
        # credential-less: sees only the work token, never the world
        world["agent_calls"] += 1
        if world["agent_mode"] == "unable":
            return RoundUnable(
                head=work.head,
                incarnation=work.incarnation,
                category="unable",
                mem=work.mem,
            )
        configured = world["agent_results"].get(work.head)
        if configured is not None:
            findings = configured["findings"]
            lineage = configured["lineage"]
        else:
            # The fake agent, like the real provider contract, returns
            # the COMPLETE current open set and explicit lineage. Prior
            # findings are not blindly concatenated: fresh findings
            # replace the same identity, while absent prior identities
            # remain still-open by the fake world's default policy.
            fresh = world["agent_findings"].get(
                work.head,
                [{"id": f"f-{work.head}", "note": f"finding:{work.head}", "blocking": True}],
            )
            by_id = {finding["id"]: finding for finding in work.prior_findings}
            by_id.update({finding["id"]: finding for finding in fresh})
            findings = list(by_id.values())
            prior_ids = {finding["id"] for finding in work.prior_findings}
            lineage = [
                {
                    "finding_id": finding["id"],
                    "state": "still_open" if finding["id"] in prior_ids else "new",
                    "supersedes": None,
                }
                for finding in findings
            ]
        return AgentReview(
            head=work.head,
            base=work.base,
            policy=work.policy,
            incarnation=work.incarnation,
            findings=findings,
            lineage=lineage,
            mem=work.mem,
        )

    @motus_activity(converter=converter)
    def publish_gate(work: Publishable) -> ReviewLanded | ReviewMoved | ReviewBlocked | ReviewFault:
        # lookup-first: the SAME effect identity never posts twice — and
        # a key collision with DIFFERENT content fails closed (A2)
        prior = next((c for c in world["comments"] if c["key"] == work.effect), None)
        if prior is not None:
            if prior["body"] != list(work.findings):
                return ReviewFault(reason=f"effect identity collision: {work.effect}", mem=work.mem)
            return ReviewLanded(
                head=work.head,
                incarnation=work.incarnation,
                findings=work.findings,
                effect=work.effect,
                mem=work.mem,
            )
        for _attempt in range(3):  # bounded classified retry, ONE occurrence
            world["comment_attempts"] += 1
            mode = world["comments_mode"]
            if mode == "retryable":
                continue
            if mode == "unknown":
                return ReviewFault(reason="unknown provider terminal", mem=work.mem)
            # A1.5: fresh read of EVERY claimed authority field inside
            # the gate — live provider fields AND the host grant
            auth = world["authority"]
            if (
                auth["phase"] != "running"
                or auth["incarnation"] != work.incarnation
                or world["branch_head"] != work.head
                or world["base_head"] != work.base
                or world["policy"] != work.policy
            ):
                return ReviewMoved(
                    head=work.head,
                    observed=world["branch_head"],
                    observed_base=world["base_head"],
                    observed_policy=world["policy"],
                    observed_incarnation=auth["incarnation"],
                    observed_phase=auth["phase"],
                    findings=work.findings,
                    mem=work.mem,
                )
            world["comments"].append(
                {"key": work.effect, "kind": "findings", "head": work.head, "body": list(work.findings)}
            )
            world["log"].append(("comment", work.effect))
            return ReviewLanded(
                head=work.head,
                incarnation=work.incarnation,
                findings=work.findings,
                effect=work.effect,
                mem=work.mem,
            )
        return ReviewBlocked(
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
    def git_gate(work: MutWork) -> Pushed | MovedM | FaultM | DeclinedM:
        # lookup-first reconciliation (A2): a crash AFTER the push landed
        # but BEFORE acknowledgment must not push twice — the SAME
        # operation identity reconciles to the landed outcome
        prior = next((p for p in world["pushes"] if p["key"] == work.op_key), None)
        if prior is not None:
            return Pushed(
                op=work.op,
                op_key=work.op_key,
                head=work.head,
                new_head=prior["to"],
                incarnation=work.incarnation,
                lineage=work.lineage,
            )
        # A1.5: base/policy/grant are fenced by a fresh read BEFORE the
        # coding agent starts (the push CAS only covers the head): any
        # op authored under an old base, a revoked policy, a non-running
        # phase, or a previous grant incarnation classifies MOVED — the
        # agent never runs against authority already known to be gone
        auth = world["authority"]
        if (
            auth["phase"] != "running"
            or auth["incarnation"] != work.incarnation
            or world["base_head"] != work.base
            or world["policy"] != work.policy
        ):
            return MovedM(
                op=work.op,
                op_key=work.op_key,
                head=work.head,
                incarnation=work.incarnation,
                observed=world["branch_head"],
                observed_base=world["base_head"],
                observed_policy=world["policy"],
                observed_incarnation=auth["incarnation"],
                observed_phase=auth["phase"],
            )
        # the coding agent runs here, AFTER the fence and BEFORE the
        # push: an agent that produced no change never reaches the CAS —
        # nothing was pushed, the branch state is fully known, and the
        # authority it began under stood: a clean decline
        if world["git_mode"] == "unable":
            return DeclinedM(
                op=work.op,
                op_key=work.op_key,
                head=work.head,
                incarnation=work.incarnation,
                category="unable",
                reason="agent produced no change",
            )
        # server-side CAS: the push itself is the head authority check
        if world["branch_head"] != work.head:
            return MovedM(
                op=work.op,
                op_key=work.op_key,
                head=work.head,
                incarnation=work.incarnation,
                observed=world["branch_head"],
                observed_base=world["base_head"],
                observed_policy=world["policy"],
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
                reason="unknown provider terminal",
                incarnation=work.incarnation,
                kind=work.kind,
                instruction=work.instruction,
                run_id=work.run_id,
                attempt=work.attempt,
            )
        new_head = f"{work.head}+{work.op}"
        world["branch_head"] = new_head
        world["pushes"].append({"key": work.op_key, "op": work.op, "from": work.head, "to": new_head})
        world["log"].append(("push", work.op_key))
        if world["git_mode"] == "crash":
            # the push LANDED but the terminal was lost before the ack
            return FaultM(
                op=work.op,
                op_key=work.op_key,
                head=work.head,
                base=work.base,
                policy=work.policy,
                reason="link lost after push",
                incarnation=work.incarnation,
                kind=work.kind,
                instruction=work.instruction,
                run_id=work.run_id,
                attempt=work.attempt,
            )
        return Pushed(
            op=work.op,
            op_key=work.op_key,
            head=work.head,
            new_head=new_head,
            incarnation=work.incarnation,
            lineage=work.lineage,
        )

    @motus_activity(converter=converter)
    def reply_gate(work: ReplyReq) -> Replied | ReplyBlocked | ReplyFault:
        # lookup-first (A2): the SAME reply identity never posts twice —
        # and a key collision with DIFFERENT content fails closed.
        # Replies carry NO authority fence by design — a human may talk
        # to a drafted or closed PR, and the answer still lands.
        key = f"reply:{work.id}"
        prior = next((c for c in world["comments"] if c["key"] == key), None)
        if prior is not None:
            if prior["body"] != work.text:
                return ReplyFault(id=work.id, text=work.text, reason=f"effect identity collision: {key}")
            return Replied(id=work.id, text=work.text)
        for _attempt in range(3):  # bounded classified retry, ONE occurrence
            mode = world["comments_mode"]
            if mode == "retryable":
                continue
            if mode == "unknown":
                return ReplyFault(id=work.id, text=work.text, reason="unknown provider terminal")
            world["comments"].append({"key": key, "kind": "reply", "head": "", "body": work.text})
            world["log"].append(("comment", key))
            return Replied(id=work.id, text=work.text)
        return ReplyBlocked(id=work.id, text=work.text)

    @motus_activity(converter=converter)
    def reminder_gate(work: RemReq) -> RemLanded | RemBlocked | RemFault:
        # lookup-first (A2): the SAME nudge identity never posts twice.
        # Reminders carry NO authority fence by design — a nudge is a
        # human-facing note, corrected by conversation, never fenced.
        key = f"reminder:{work.timer_id}"
        if any(c["key"] == key for c in world["comments"]):
            return RemLanded(timer_id=work.timer_id)
        for _attempt in range(3):  # bounded classified retry, ONE occurrence
            mode = world["comments_mode"]
            if mode == "retryable":
                continue
            if mode is not None:
                return RemFault(timer_id=work.timer_id, reason=str(mode))
            world["comments"].append({"key": key, "kind": "reminder", "head": "", "body": ""})
            world["log"].append(("comment", key))
            return RemLanded(timer_id=work.timer_id)
        return RemBlocked(timer_id=work.timer_id)

    @motus_activity(converter=converter)
    def announce_gate(work: AnnounceReq) -> ALanded | ABlocked | AMoved | AFault:
        key = work.op  # stable operation identity: "ready:{head}:i{n}"
        if any(c["key"] == key for c in world["comments"]):  # lookup-first (A2)
            return ALanded(incarnation=work.incarnation, head=work.head)
        for _attempt in range(3):  # bounded classified retry, ONE occurrence
            mode = world["comments_mode"]
            if mode == "retryable":
                continue
            if mode == "unknown":
                return AFault(op=work.op, incarnation=work.incarnation, reason="unknown provider terminal")
            # A1.5: the gate compares ALL current authority fields — the
            # live provider fields AND the host grant. The grant's
            # incarnation is the ONLY field that exposes a stale announce
            # issued under a previous Running incarnation whose
            # head/base/policy tuple is IDENTICAL (draft -> resume): the
            # provider state is "ready" again, but the grant moved on.
            auth = world["authority"]
            if (
                (work.strict_base and not work.base_current)
                or auth["phase"] != "running"
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
            world["comments"].append({"key": key, "kind": "ready", "head": work.head, "body": ""})
            world["log"].append(("comment", key))
            return ALanded(incarnation=work.incarnation, head=work.head)
        return ABlocked(incarnation=work.incarnation, head=work.head, base=work.base, policy=work.policy)

    @motus_activity(converter=converter)
    def dash_gate(work: DashReq) -> DashLanded | DashBlocked | DashFault:
        # the dashboard is authority-orthogonal by design (A5): no
        # fence — a stale board row is corrected by the next upsert.
        # The upsert is an idempotent overwrite, so no lookup-first
        # ledger is needed either: reissuing a digest is harmless.
        world["dash_requests"].append({"entries": list(work.entries), "digest": work.digest})
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

    return (rerun_gate, review_agent, publish_gate, git_gate, reply_gate, reminder_gate, announce_gate, dash_gate)


# the host's webhook custody, keyed by engine identity: one admission
# point per engine moves the world's grant record BEFORE the net observes
_HOST: dict[int, dict] = {}


def world_of(engine: Engine) -> dict:
    return _HOST[id(engine)]


def _move_world(world: dict, door: str, data: dict) -> None:
    """The host's grant fold — the same deterministic rules as the
    lifecycle loop's admission folds, applied to the world FIRST."""
    auth = world["authority"]
    if door == "on_head":
        world["branch_head"] = data["head"]
        world["base_head"] = data["base"]
        world["policy"] = data["policy"]
        if auth["phase"] == "terminal":
            return
        if auth["phase"] == "quiescent":
            world["authority"] = {
                **auth,
                "head": data["head"],
                "base": data["base"],
                "policy": data["policy"],
            }
            return
        if data["head"] == auth["head"]:
            world["authority"] = {**auth, "base": data["base"], "policy": data["policy"]}
            return
        world["authority"] = {
            "incarnation": auth["incarnation"] + 1,
            "phase": "running",
            "head": data["head"],
            "base": data["base"],
            "policy": data["policy"],
        }
    elif door == "on_draft":
        world["pr_state"] = "draft"
        if auth["phase"] == "running":
            world["authority"] = {**auth, "phase": "quiescent"}
    elif door == "on_ready":
        world["pr_state"] = "ready"
        if auth["phase"] == "quiescent":
            # resume mints a NEW incarnation even when head/base/policy
            # are unchanged — the grant alone distinguishes them
            world["authority"] = {
                **auth,
                "phase": "running",
                "incarnation": auth["incarnation"] + 1,
            }
    elif door == "on_close":
        world["pr_state"] = "closed"
        world["authority"] = {**auth, "phase": "terminal"}
    elif door == "on_runs":
        # a run observation proves the provider held this run BEFORE the
        # webhook: the gate's pre-request evidence cut reads this record
        newest = world["runs_by_head"].get(data["head"], (0, 0))
        world["runs_by_head"][data["head"]] = max(newest, (data["run_id"], data["attempt"]))


# -- spawning ----------------------------------------------------------------


def spawn(
    instance: str = "pr-v5",
    world: dict | None = None,
    initial_mail: tuple[tuple[str, str, dict], ...] = (),
):
    """Spawn with inline dispatch: every gate settles within the drive."""
    world = fresh_world() if world is None else world
    built = build_net_v5()
    definitions = {d.declaration.name: d for d in make_activities(world)}
    marking = seed_marking(f"test:{instance}")
    for place, color, data in initial_mail:
        marking = marking.deposit(NetPath(place), Token(color, data))
    engine = Engine.create(
        built.net,
        instance,
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch(definitions),
        marking=marking,
        handlers=wire_gates(built, GATES, definitions, DERIVED),
        guards=dict(built.guards),
        activities=tuple(d.declaration for d in definitions.values()),
    )
    _HOST[id(engine)] = world
    return engine, built


def spawn_held(instance: str = "pr-v5", world: dict | None = None):
    """Spawn with an explicit worker pool so a test can HOLD a gate's
    terminal open — the only honest way to observe in-flight time.
    Cohabited loops require `choose_throughput`; the conservative policy
    begins no second candidate while ANY activity is outstanding."""
    world = fresh_world() if world is None else world
    built = build_net_v5()
    definitions = {d.declaration.name: d for d in make_activities(world)}
    dispatch = InMemoryDispatch()
    engine = Engine.create(
        built.net,
        instance,
        history=InMemoryHistoryStore(),
        dispatch=dispatch,
        marking=seed_marking(f"test:{instance}"),
        handlers=wire_gates(built, GATES, definitions, DERIVED),
        guards=dict(built.guards),
        activities=tuple(d.declaration for d in definitions.values()),
        policy=choose_throughput,
    )
    _HOST[id(engine)] = world
    return engine, built, dispatch, definitions


# -- driving -----------------------------------------------------------------


def drive(engine: Engine, limit: int = 200) -> None:
    for _ in range(limit):
        if not engine.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


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


def release_one(engine, dispatch, definitions, activity: str) -> None:
    """Complete the single pending invocation of `activity`, then pump."""
    [(occurrence, invocation)] = [(o, i) for o, i in dispatch.pending.items() if i.activity == activity]
    dispatch.complete(occurrence, definitions[invocation.activity](invocation, context=None))
    pump(engine, dispatch, definitions)


_SEQ = {"n": 0}


def deliver(engine: Engine, door: str, color: str, data: dict) -> None:
    _SEQ["n"] += 1
    if color == "HeadSeen":
        data = {"strict_base": True, "base_current": True, **data}
    _move_world(_HOST[id(engine)], door, data)  # the world moves FIRST
    engine.deliver(door, Token(color, data), identity=f"{door}-{_SEQ['n']}")
    drive(engine)


def deliver_held(engine, dispatch, definitions, door: str, color: str, data: dict, *, hold=frozenset()):
    _SEQ["n"] += 1
    if color == "HeadSeen":
        data = {"strict_base": True, "base_current": True, **data}
    _move_world(_HOST[id(engine)], door, data)  # the world moves FIRST
    engine.deliver(door, Token(color, data), identity=f"{door}-{_SEQ['n']}")
    pump(engine, dispatch, definitions, hold=hold)


# -- observation --------------------------------------------------------------


def tokens(engine: Engine, place: str) -> list[dict]:
    return [token.data for token in engine.marking.place(NetPath(place))]


def one(engine: Engine, place: str) -> dict:
    [data] = tokens(engine, place)
    return data


def projection(engine: Engine) -> list[dict]:
    """Every fact the dashboard loop accumulated, parsed back into
    {kind, body} — the durable observation window for loop-mailed facts
    (the dashboard now consumes `dash.facts`, so the mailbox is empty at
    quiescence). Reads the live baton, or the terminal record after
    close. Consecutive digest-identical facts collapse by design."""
    place = "dash.memory" if tokens(engine, "dash.memory") else "dash.done"
    facts = []
    for entry in one(engine, place)["entries"]:
        kind, _, body = entry.partition(":")
        facts.append({"kind": kind, "body": ast.literal_eval(body)})
    return facts


# -- observation shorthand ----------------------------------------------------


def see_head(
    engine,
    head: str,
    base: str = "b1",
    mergeable: bool = True,
    policy: str = "p1",
    strict_base: bool = True,
    base_current: bool = True,
):
    deliver(
        engine,
        "on_head",
        "HeadSeen",
        {
            "head": head,
            "base": base,
            "mergeable": mergeable,
            "policy": policy,
            "strict_base": strict_base,
            "base_current": base_current,
        },
    )


def see_run(
    engine,
    head: str = "h1",
    run_id: int = 1,
    attempt: int = 1,
    conclusion: str = "success",
    fingerprint: str = "",
):
    deliver(
        engine,
        "on_runs",
        "RunSeen",
        {
            "head": head,
            "run_id": run_id,
            "attempt": attempt,
            "conclusion": conclusion,
            "fingerprint": fingerprint,
        },
    )


def comment(engine, id: str, kind: str, arg: str = "", authorized: bool = True):
    """A human comment: the ONLY ingress for dismiss/recover/snooze and
    the conversation-sourced committing intents."""
    deliver(
        engine,
        "on_comment",
        "CommentSeen",
        {"id": id, "kind": kind, "arg": arg, "authorized": authorized},
    )


def comment_held(
    engine,
    dispatch,
    definitions,
    id: str,
    kind: str,
    arg: str = "",
    authorized: bool = True,
    hold=frozenset(),
):
    deliver_held(
        engine,
        dispatch,
        definitions,
        "on_comment",
        "CommentSeen",
        {"id": id, "kind": kind, "arg": arg, "authorized": authorized},
        hold=hold,
    )
