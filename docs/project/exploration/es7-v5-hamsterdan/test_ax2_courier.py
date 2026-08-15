"""ES-007 AX2 — the courier: a generic cross-instance delivery primitive.

THE QUESTION. AX3 wants to shard the AX1 loops across instances with
only the assembly changing. That needs one primitive: a token minted
inside instance A lands exactly once inside instance B, surviving a
transport crash at each pinned boundary below, with zero new engine
features.

THE SHAPE (all Hamsterdan-independent):

    producer net                 host                consumer net
    ┌───────────────┐      ┌──────────────┐      ┌────────────────┐
    │ out.box baton │─read─│   Courier    │─────▶│ on_parcel door │
    │ {next,parcels}│      │  (STATELESS) │      │ (engine dedups │
    │               │◀─ack─│              │      │  by identity)  │
    └───────────────┘      └──────────────┘      └────────────────┘

1. The OUTBOX is one baton token: `{"next": n, "parcels": [...]}`.
   Each parcel is a TOKEN ENVELOPE the producing fold authors:
   `{"n": seq, "token": {"color": ..., "data": {...}}}` — the courier
   reconstructs and delivers `token` verbatim, never reading its data.
   The producing fold mints each parcel's sequence number from the
   baton — durable, single-writer, replay-stable. The parcel identity
   is `{route_id}:{seq}`: derived from durable source state, never
   from the transport (a per-transmission identity would break dedup).
   The route_id must be globally unique per (source instance/
   incarnation, outbox channel, target route) — delivery identity is
   instance-global at the target, and one outbox is single-consumer
   route custody (see Courier's docstring).
2. The COURIER holds NO durable state and NO domain schema. It reads
   the outbox marking, delivers each envelope's token to the target's
   door with the parcel identity, then delivers a protocol-owned,
   exact-seq ACK (`CourierAck`) back to the source. Both deliveries
   are idempotent AT THE ENGINE DOOR: a redelivered identity returns
   PriorAcknowledgement — no token, no firing (petrus.impetus
   Instance.deliver, DR 2026-07-14). The courier can therefore die at
   each of the three pinned crash boundaries (after target accept,
   before ack, after ack accept) and simply run again; the pinned
   stale-snapshot overlap of two same-route drains also converges
   (each claim has its own test below).
3. The ACK is itself a delivery (`ack:{route_id}:{seq}`) whose fold
   drops the acknowledged parcel from the outbox queue. Matching is
   pure fold data — no guards, no filters (V5 style), which is WHY
   the outbox is one queue token and not one token per parcel.

At-least-once transport + door-identity dedup = exactly-once landing.
The alternative identity source — the chronicle occurrence that
produced the parcel (TokensProduced.occurrence) — is documented in
ax2-courier.md; the baton sequence was chosen because the fold can
mint it without chronicle correlation and the ack can name it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from petrus.engine import Engine
from petrus.impetus.dsl import BuiltNet, NetSpec, petri_handler
from petrus.impetus.history import ExternalEventDelivered
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch


# ---------------------------------------------------------------------------
# Token types (toy domain: greetings travel from producer to consumer)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkSeen:
    text: str


@dataclass(frozen=True)
class Outbox:
    next: int
    label: str
    parcels: tuple  # ({"n": int, "token": {"color": str, "data": dict}}, ...)


@dataclass(frozen=True)
class CourierAck:
    """PROTOCOL-owned ack color: the one token the courier constructs
    itself. Domain tokens travel inside parcel envelopes, untouched."""

    n: int


@dataclass(frozen=True)
class ParcelSeen:
    stream: str
    n: int
    text: str


@dataclass(frozen=True)
class MetricSeen:
    """A second, materially different domain schema — nested point
    tuples, no text — proving the courier never reads token data."""

    series: str
    points: tuple  # ((tick, value), ...)


@dataclass(frozen=True)
class ReceivedLog:
    received: tuple  # ((stream, n, text), ...)


# ---------------------------------------------------------------------------
# Producer net: one loop, one outbox baton, two doors (work in, ack in)
# ---------------------------------------------------------------------------


def _data(binding, color: str) -> dict:
    for _, toks in binding.consumed:
        for token in toks:
            if token.color == color:
                return token.data
    raise AssertionError(f"no consumed token of color {color}")


def _route(outputs, mapping: dict[str, tuple[tuple[str, dict], ...]]):
    return {
        out.target: tuple(Token(color, data) for color, data in mapping[str(out.target)])
        for out in outputs
        if str(out.target) in mapping
    }


def _parcel_token(work: dict, seq: int, label: str) -> dict:
    """The DEFAULT domain token maker. The producing fold — never the
    courier — authors the complete target token; the envelope carries
    it verbatim across the seam."""
    return {"color": "ParcelSeen", "data": {"stream": label, "n": seq, "text": work["text"]}}


def _make_emit(make_token):
    def _emit(binding, outputs):
        """Producing fold: mint the parcel's sequence number from the
        baton and author the domain token into the envelope."""
        work, box = _data(binding, "WorkSeen"), _data(binding, "Outbox")
        parcel = {"n": box["next"], "token": make_token(work, box["next"], box["label"])}
        box2 = {**box, "next": box["next"] + 1, "parcels": (*box["parcels"], parcel)}
        return _route(outputs, {"out.box": (("Outbox", box2),)})

    return _emit


def _ack(binding, outputs):
    """Ack fold: drop the exact acknowledged parcel (pure data match)."""
    ack, box = _data(binding, "CourierAck"), _data(binding, "Outbox")
    parcels = tuple(p for p in box["parcels"] if p["n"] != ack["n"])
    return _route(outputs, {"out.box": (("Outbox", {**box, "parcels": parcels}),)})


def build_producer(make_token=_parcel_token) -> BuiltNet:
    net = NetSpec("producer")
    out = net.s.out
    out.p.work(WorkSeen)
    out.p.acks(CourierAck)
    out.p.box(Outbox)
    net.t.on_work >> out.p.work
    net.t.on_ack >> out.p.acks
    emit = petri_handler(_make_emit(make_token))
    (out.p.work, out.p.box) >> out.t.emit(handler=emit) >> out.p.box
    (out.p.acks, out.p.box) >> out.t.fold_ack(handler=petri_handler(_ack)) >> out.p.box
    return net.build()


# ---------------------------------------------------------------------------
# Consumer net: one door, one log baton — NO dedup logic of its own.
# The engine's delivery door is the only thing preventing duplicates:
# that absence is the point of the experiment.
# ---------------------------------------------------------------------------


def _receive(binding, outputs):
    parcel, log = _data(binding, "ParcelSeen"), _data(binding, "ReceivedLog")
    entry = (parcel["stream"], parcel["n"], parcel["text"])
    log2 = {"received": (*log["received"], entry)}
    return _route(outputs, {"in.log": (("ReceivedLog", log2),)})


def _receive_metric(binding, outputs):
    metric, log = _data(binding, "MetricSeen"), _data(binding, "ReceivedLog")
    entry = (metric["series"], metric["points"])
    log2 = {"received": (*log["received"], entry)}
    return _route(outputs, {"in.log": (("ReceivedLog", log2),)})


def build_consumer(token_type=ParcelSeen, fold=_receive) -> BuiltNet:
    net = NetSpec("consumer")
    inn = net.s["in"]
    inn.p.parcels(token_type)
    inn.p.log(ReceivedLog)
    net.t.on_parcel >> inn.p.parcels
    (inn.p.parcels, inn.p.log) >> inn.t.receive(handler=petri_handler(fold)) >> inn.p.log
    return net.build()


# ---------------------------------------------------------------------------
# The courier — the primitive under test. STATELESS by construction:
# every field is assembly wiring; all durable state lives in the two
# instances and their delivery doors.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Courier:
    """Drains one outbox into one target door. Generic: knows places,
    doors, and a route — nothing about the domain. Each parcel is a
    token ENVELOPE (`{"n": seq, "token": {"color", "data"}}`): the
    courier reconstructs and delivers the domain token verbatim,
    never reading or constructing domain data. The only token it
    authors is the protocol's own `CourierAck`.

    THE IDENTITY NAMESPACE INVARIANT (oracle amendment 3): delivery
    identity is INSTANCE-GLOBAL at the target, not door-local. The
    route_id must therefore be an immutable, globally unique route
    identifier — distinguishing the source instance (and incarnation,
    if sources can be replaced with restarted counters), the outbox
    channel, and the target route — never a friendly label. Two
    ingresses reusing one identity string at the same target is a
    delivery CONFLICT, by engine design.

    CUSTODY CONTRACT: one outbox is ordered, SINGLE-CONSUMER route
    custody — every courier on it must share the exact same wiring
    (same target, same door, same route_id). The first ack removes the
    parcel for everyone, so couriers with different targets on one
    outbox lose parcels; fan-out needs one outbox place per route.
    Same-route couriers may overlap: with engine access serialized,
    dedup at both doors converges — pinned below for the three crash
    boundaries and one genuine stale-snapshot interleave (not an
    exhaustive schedule proof)."""

    source: Engine
    outbox: str  # place holding the queue baton
    ack_door: str  # source door acknowledging a drained parcel
    target: Engine
    door: str  # target door receiving parcels
    route_id: str  # globally unique route: identity = "{route_id}:{n}"

    def drain(self, *, crash: str | None = None, after_drive=None) -> None:
        """One at-least-once pass over the parcels, lowest seq first.
        `crash` names an exact boundary to die at (oracle amendment 1:
        the boundaries are distinct and each is separately pinned):
          "after_accept"     — target accepted the delivery (durable:
                               Engine.deliver commits the door firing
                               before returning), target NOT driven
          "before_ack"       — target driven, source never told
          "after_ack_accept" — source accepted the ack, NOT driven
        A fresh courier draining after any of these converges without
        duplicates: all durable state is in the two instances.
        `after_drive` is a TEST-ONLY interleave hook, called with the
        parcel seq after the target is driven — a second same-route
        drain invoked there overlaps this loop's now-stale snapshot,
        which is exactly the racing-courier schedule to pin."""
        [box] = [t.data for t in self.source.marking.place(NetPath(self.outbox))]
        for parcel in tuple(box["parcels"]):
            identity = f"{self.route_id}:{parcel['n']}"
            envelope = parcel["token"]
            self.target.deliver(
                self.door, Token(envelope["color"], envelope["data"]), identity=identity
            )
            if crash == "after_accept":
                return
            _drive(self.target)
            if after_drive is not None:
                after_drive(parcel["n"])
            if crash == "before_ack":
                return
            self.source.deliver(
                self.ack_door, Token("CourierAck", {"n": parcel["n"]}), identity=f"ack:{identity}"
            )
            if crash == "after_ack_accept":
                return
            _drive(self.source)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def spawn_producer(instance: str = "producer-1", label: str = "greet", make_token=_parcel_token):
    built = build_producer(make_token)
    history = InMemoryHistoryStore()
    box = {"next": 1, "label": label, "parcels": ()}
    engine = Engine.create(
        built.net,
        instance,
        history=history,
        dispatch=InlineDispatch({}),  # pure folds only: no activities
        marking=Marking({NetPath("out.box"): (Token("Outbox", box),)}),
        handlers=dict(built.handlers),
        guards=dict(built.guards),
    )
    return engine, history, built


def spawn_consumer(instance: str = "consumer-1", token_type=ParcelSeen, fold=_receive):
    built = build_consumer(token_type, fold)
    history = InMemoryHistoryStore()
    engine = Engine.create(
        built.net,
        instance,
        history=history,
        dispatch=InlineDispatch({}),  # pure folds only: no activities
        marking=Marking({NetPath("in.log"): (Token("ReceivedLog", {"received": ()}),)}),
        handlers=dict(built.handlers),
        guards=dict(built.guards),
    )
    return engine, history, built


def _drive(engine: Engine, limit: int = 100) -> None:
    for _ in range(limit):
        if not engine.advance().ready:
            return
    raise AssertionError("engine did not quiesce")


_SEQ = {"n": 0}


def produce(engine: Engine, text: str) -> None:
    _SEQ["n"] += 1
    engine.deliver("on_work", Token("WorkSeen", {"text": text}), identity=f"work-{_SEQ['n']}")
    _drive(engine)


def outbox(engine: Engine) -> dict:
    [box] = [t.data for t in engine.marking.place(NetPath("out.box"))]
    return box


def received(engine: Engine) -> list:
    [log] = [t.data for t in engine.marking.place(NetPath("in.log"))]
    return list(log["received"])


def landings(chronicle, door: str) -> list:
    """Every delivery that actually LANDED (fired) at a door — a
    PriorAcknowledgement records nothing new, which is the dedup proof."""
    return [
        r
        for r in chronicle.records
        if isinstance(r, ExternalEventDelivered) and str(r.source).endswith(door)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_parcels_flow_in_order_and_the_outbox_drains(self) -> None:
        src, _, _ = spawn_producer()
        dst, _, _ = spawn_consumer()
        courier = Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet")
        produce(src, "hello")
        produce(src, "world")
        assert [p["n"] for p in outbox(src)["parcels"]] == [1, 2]
        courier.drain()
        assert received(dst) == [("greet", 1, "hello"), ("greet", 2, "world")]
        assert outbox(src)["parcels"] == ()  # acknowledged and dropped
        assert outbox(src)["next"] == 3  # the counter never rewinds


class TestCrashAndRedeliver:
    def test_crash_after_target_delivery_before_ack_never_duplicates(self) -> None:
        """THE AX2 question. The parcel lands at the target; the courier
        dies before telling the source. The parcel is still in the
        outbox, so a FRESH courier (no shared memory: statelessness is
        the proof) redelivers it — the engine door answers with the
        prior acknowledgment, no second firing, and the ack finally
        drains the outbox."""
        src, _, _ = spawn_producer()
        dst, dst_hist, _ = spawn_consumer()
        produce(src, "hello")
        Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet").drain(crash="before_ack")
        assert received(dst) == [("greet", 1, "hello")]  # landed...
        assert [p["n"] for p in outbox(src)["parcels"]] == [1]  # ...source never told
        # the fresh courier converges: dedup at the door, then the ack
        Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet").drain()
        assert received(dst) == [("greet", 1, "hello")]  # STILL exactly once
        assert outbox(src)["parcels"] == ()
        assert len(landings(dst_hist, "on_parcel")) == 1  # one landed firing ever

    def test_production_continues_across_the_crash(self) -> None:
        """A second parcel minted while the first is stranded in the
        crash window: the fresh courier delivers both, in order, each
        exactly once."""
        src, _, _ = spawn_producer()
        dst, dst_hist, _ = spawn_consumer()
        produce(src, "one")
        Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet").drain(crash="before_ack")
        produce(src, "two")  # the world moves while the transport is down
        Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet").drain()
        assert received(dst) == [("greet", 1, "one"), ("greet", 2, "two")]
        assert outbox(src)["parcels"] == ()
        assert len(landings(dst_hist, "on_parcel")) == 2

    def test_crash_after_target_accept_before_drive_is_already_durable(self) -> None:
        """Oracle amendment 1, the REAL accept boundary: the courier
        dies after Engine.deliver returned but before driving the
        target. The delivery is already durable — Engine.deliver
        commits the door firing before returning — so the parcel sits
        in the target's parcels place, in the chronicle. Resurrect the
        target from its chronicle, drain with a fresh courier: ONE
        landed delivery ever, ONE downstream receipt, outbox drained."""
        src, _, _ = spawn_producer()
        dst, dst_hist, dst_built = spawn_consumer()
        produce(src, "hello")
        Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet").drain(crash="after_accept")
        assert received(dst) == []  # accepted, but the receive fold never ran
        assert len(landings(dst_hist, "on_parcel")) == 1  # ...yet DURABLE
        resurrected = Engine.load(
            dst_built.net,
            "consumer-1",
            history=dst_hist,
            dispatch=InlineDispatch({}),
            handlers=dict(dst_built.handlers),
            guards=dict(dst_built.guards),
        )
        Courier(src, "out.box", "on_ack", resurrected, "on_parcel", "greet").drain()
        assert received(resurrected) == [("greet", 1, "hello")]  # exactly once
        assert len(landings(dst_hist, "on_parcel")) == 1  # redelivery: NO new landing
        assert outbox(src)["parcels"] == ()

    def test_crash_after_ack_accept_before_source_drive_converges(self) -> None:
        """Oracle amendment 2a, the symmetric ack boundary: the source
        accepted the ack but was never driven — the CourierAck token
        and the still-queued parcel coexist durably. Resurrect the
        source, drain with a fresh courier: the parcel redelivery
        dedups, the ack redelivery dedups (PriorAcknowledgement, no
        second CourierAck),
        and driving fires the pending fold — the outbox drains."""
        src, src_hist, src_built = spawn_producer()
        dst, dst_hist, _ = spawn_consumer()
        produce(src, "hello")
        Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet").drain(crash="after_ack_accept")
        assert received(dst) == [("greet", 1, "hello")]
        assert [p["n"] for p in outbox(src)["parcels"]] == [1]  # ack accepted, not folded
        resurrected = Engine.load(
            src_built.net,
            "producer-1",
            history=src_hist,
            dispatch=InlineDispatch({}),
            handlers=dict(src_built.handlers),
            guards=dict(src_built.guards),
        )
        assert [p["n"] for p in outbox(resurrected)["parcels"]] == [1]
        # the accepted ack SURVIVED the reload as a pending CourierAck token
        acks = [t.data for t in resurrected.marking.place(NetPath("out.acks"))]
        assert acks == [{"n": 1}]
        Courier(resurrected, "out.box", "on_ack", dst, "on_parcel", "greet").drain()
        assert outbox(resurrected)["parcels"] == ()  # the pending fold fired
        assert received(dst) == [("greet", 1, "hello")]  # STILL exactly once
        assert len(landings(dst_hist, "on_parcel")) == 1
        # the ack REDELIVERY deduped: exactly one landed on_ack firing
        # ever — a second landing would prove a broken implementation
        # that drains by duplicate ack rather than by the pending fold
        assert len(landings(src_hist, "on_ack")) == 1

    def test_two_same_route_couriers_racing_converge_in_order(self) -> None:
        """Oracle amendment 2b, a REAL overlap: courier B runs a full
        drain INSIDE courier A's loop — after A delivered parcel 1 but
        before A acked it. A then CONTINUES its original loop over its
        now-stale two-parcel snapshot: its ack of parcel 1 dedups
        (B already acked), its redelivery of parcel 2 dedups (B already
        delivered), its ack of parcel 2 dedups. Engine calls stay
        serialized (one thread); the stale snapshot is the race.
        FIFO landing order, ONE landing per parcel, ONE ack landing
        per parcel, drained outbox."""
        src, src_hist, _ = spawn_producer()
        dst, dst_hist, _ = spawn_consumer()
        produce(src, "one")
        produce(src, "two")
        a = Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet")
        b = Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet")
        fired = []

        def interleave(n: int) -> None:
            if n == 1 and not fired:  # exactly once, mid-A, after parcel 1
                fired.append(n)
                b.drain()  # B sweeps BOTH parcels while A holds its snapshot

        a.drain(after_drive=interleave)  # A finishes its stale loop
        assert received(dst) == [("greet", 1, "one"), ("greet", 2, "two")]  # FIFO
        assert len(landings(dst_hist, "on_parcel")) == 2  # one landing each
        assert len(landings(src_hist, "on_ack")) == 2  # one ACK landing each
        assert outbox(src)["parcels"] == ()

    def test_repeated_drains_are_idempotent(self) -> None:
        """Running the courier any number of times — including with
        nothing pending — is safe: at-least-once transport is the
        contract, the door makes it exactly-once landing."""
        src, _, _ = spawn_producer()
        dst, dst_hist, _ = spawn_consumer()
        produce(src, "hello")
        courier = Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet")
        for _ in range(3):
            courier.drain()
        assert received(dst) == [("greet", 1, "hello")]
        assert len(landings(dst_hist, "on_parcel")) == 1


class TestReplayAndIdentity:
    def test_a_resurrected_source_redelivers_the_same_identities(self) -> None:
        """Replay safety: resurrect the producer from its chronicle
        mid-crash-window and drain with a fresh courier. The baton
        sequence numbers replay identically, so the identities are the
        SAME strings — and the target deduplicates them."""
        src, src_hist, built = spawn_producer()
        dst, _, _ = spawn_consumer()
        produce(src, "hello")
        Courier(src, "out.box", "on_ack", dst, "on_parcel", "greet").drain(crash="before_ack")
        assert received(dst) == [("greet", 1, "hello")]
        resurrected = Engine.load(
            built.net,
            "producer-1",
            history=src_hist,
            dispatch=InlineDispatch({}),
            handlers=dict(built.handlers),
            guards=dict(built.guards),
        )
        assert outbox(resurrected) == outbox(src)  # the outbox IS the durable state
        Courier(resurrected, "out.box", "on_ack", dst, "on_parcel", "greet").drain()
        assert received(dst) == [("greet", 1, "hello")]  # deduped by identity
        assert outbox(resurrected)["parcels"] == ()

    def test_identity_reuse_with_different_payload_is_refused(self) -> None:
        """The door's honesty, pinned: the same identity carrying
        DIFFERENT content is a conflict, never a silent overwrite and
        never a duplicate."""
        dst, _, _ = spawn_consumer()
        dst.deliver(
            "on_parcel",
            Token("ParcelSeen", {"stream": "greet", "n": 1, "text": "hello"}),
            identity="greet:1",
        )
        _drive(dst)
        with pytest.raises(ValueError, match="conflict"):
            dst.deliver(
                "on_parcel",
                Token("ParcelSeen", {"stream": "greet", "n": 1, "text": "TAMPERED"}),
                identity="greet:1",
            )


class TestGenerality:
    def test_two_streams_into_one_consumer_do_not_collide(self) -> None:
        """The stream name namespaces the identity: two producers with
        the SAME sequence numbers land as distinct parcels."""
        src_a, _, _ = spawn_producer("producer-a", label="a")
        src_b, _, _ = spawn_producer("producer-b", label="b")
        dst, _, _ = spawn_consumer()
        produce(src_a, "from-a")
        produce(src_b, "from-b")
        Courier(src_a, "out.box", "on_ack", dst, "on_parcel", "a").drain()
        Courier(src_b, "out.box", "on_ack", dst, "on_parcel", "b").drain()
        assert received(dst) == [("a", 1, "from-a"), ("b", 1, "from-b")]

    def test_one_producer_into_two_consumers_with_distinct_streams(self) -> None:
        """Fan-out is assembly, not topology: the SAME outbox definition
        drains into different targets under different stream names —
        each pairing is just another courier."""
        src, _, _ = spawn_producer()
        dst_1, _, _ = spawn_consumer("consumer-1")
        dst_2, _, _ = spawn_consumer("consumer-2")
        produce(src, "hello")
        # NOTE the deliberate limitation: ONE outbox serves ONE courier
        # (the ack drops the parcel for everyone). Fan-out therefore
        # needs one outbox place per target stream — the finding, not a
        # bug: delivery custody is per-consumer state, so it must be a
        # per-consumer place. Here we prove the single-consumer drain
        # and pin the limitation.
        Courier(src, "out.box", "on_ack", dst_1, "on_parcel", "greet").drain()
        assert received(dst_1) == [("greet", 1, "hello")]
        assert received(dst_2) == []  # the parcel is GONE for consumer-2
        assert outbox(src)["parcels"] == ()

    def test_the_unchanged_courier_transports_a_second_token_color(self) -> None:
        """The genericity proof (oracle round 3): the courier never
        reads the domain token — the producing fold authors a complete
        `{"color", "data"}` envelope, and the SAME Courier class,
        untouched, transports a materially different schema
        (MetricSeen: nested point tuples, no `text`, no `n` field)
        into a MetricSeen-typed door. Only the emitting fold and the
        receiving fold know the schema; the transport is colorblind."""

        def metric_token(work: dict, seq: int, label: str) -> dict:
            return {
                "color": "MetricSeen",
                "data": {"series": label, "points": ((seq, work["text"]), (seq + 1, "peak"))},
            }

        src, _, _ = spawn_producer("metrics-1", label="cpu", make_token=metric_token)
        dst, dst_hist, _ = spawn_consumer("metrics-sink", MetricSeen, _receive_metric)
        produce(src, "load-avg")
        Courier(src, "out.box", "on_ack", dst, "on_parcel", "metrics").drain()
        assert received(dst) == [("cpu", ((1, "load-avg"), (2, "peak")))]
        assert outbox(src)["parcels"] == ()
        assert len(landings(dst_hist, "on_parcel")) == 1
