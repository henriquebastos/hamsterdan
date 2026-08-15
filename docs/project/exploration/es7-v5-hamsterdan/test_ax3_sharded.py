"""AX3 — the sharded assembly: the SAME loops across several instances.

THE QUESTION. Can placement change without rewriting workflows? AX1
authored the complete V5 Hamsterdan as nine actor loops cohabiting one
instance. AX3 deploys THE SAME authored net — same folds, same
activities, same seed batons, zero edits — across several Petrus
instances, with AX2's courier carrying every cross-shard seam.

THE PRIMITIVE UNDER TEST is a generic net splitter:

    split(built_net, placement) -> one shard net per placement group

- A LOOP is a section of the authored net (`life.*`, `review.*`, ...).
- A PLACEMENT maps each loop to a shard name. One shard = cohabited;
  nine shards = every loop alone; anything between is legal.
- Each shard net contains: its loops' places and transitions COPIED BY
  OBJECT IDENTITY from the one authored net; a PROXY for every foreign
  mailbox its transitions feed (the same Place object, so the folds'
  declared routes still name their targets); an export PUMP per proxy
  (proxy + outbox baton -> outbox baton, wrapping the token verbatim
  into an AX2 envelope); an ACK door + fold per outbox; and a delivery
  DOOR per mailbox that foreign shards feed.
- The host assembly wires one AX2 `Courier` per (shard, foreign
  mailbox) route. All shard nets, pumps, doors, and couriers are
  DERIVED — no loop logic is written, changed, or even seen.

THE SHARDABLE-NET PROFILE. `split` is generic over nets that satisfy
a documented profile, and REFUSES (ValueError) anything outside it
rather than silently mis-splitting:
- sections-as-loops naming: every place, and every transition except
  ingress doors, has a dotted loop prefix;
- output-only seams (AX7's anti-braid rule, now load-bearing): every
  cross-loop arc is transition -> foreign MAILBOX. A foreign INPUT of
  any mode (consume, read, inhibit) would braid custody;
- placement covers exactly the loops present, ingress doors target
  one shard each, no authored node or color collides with the
  courier's reserved namespace, and the net declares no net-level
  completion (a global predicate has no per-shard meaning).
So the headline is deliberately narrow: placement among ALREADY
SHARDABLE loops is deployment-only; shardability itself remains a
design property the profile makes checkable.

THE EQUIVALENCE CLAIM, stated honestly: selected-outcome equivalence
plus per-seam FIFO — the same scenario script lands the same world
effects (readiness, comments kind/key, pushes, reruns, dashboard,
authority) and the same tokens in 14 selected baton/terminal places,
on the two- and nine-shard placements (solo is compared too, and
additionally proven node-identical). Global interleaving across seams
is NOT claimed identical (the dashboard's arrival-ordered entries are
compared as a sorted multiset), and engine access stays serialized
(one thread) as in AX1 and AX2.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

import pytest
import test_ax1_complete_v5 as ax1
import test_ax2_courier as ax2
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.impetus.petrinet.schema import Arc, ArcMode, Net, Place, Transition
from petrus.motus.dispatch import InlineDispatch

# ---------------------------------------------------------------------------
# The splitter — generic over any built net whose sections are loops
# ---------------------------------------------------------------------------


def loop_of(node: str) -> str:
    return node.split(".")[0] if "." in node else ""


def _mangle(place: str) -> str:
    return place.replace(".", "_")


def _export(binding, outputs):
    """Generic pump fold: wrap the one non-Outbox token verbatim into
    an AX2 envelope and append it to the route's outbox queue."""
    box = tok = None
    for _, toks in binding.consumed:
        for t in toks:
            if t.color == "Outbox":
                box = t.data
            else:
                tok = t
    parcel = {"n": box["next"], "token": {"color": tok.color, "data": tok.data}}
    box2 = {**box, "next": box["next"] + 1, "parcels": (*box["parcels"], parcel)}
    [out] = list(outputs)
    return {out.target: (Token("Outbox", box2),)}


def _ack(binding, outputs):
    """Generic ack fold: drop the exact acknowledged parcel."""
    ack = box = None
    for _, toks in binding.consumed:
        for t in toks:
            if t.color == "Outbox":
                box = t.data
            else:
                ack = t.data
    parcels = tuple(p for p in box["parcels"] if p["n"] != ack["n"])
    [out] = list(outputs)
    return {out.target: (Token("Outbox", {**box, "parcels": parcels}),)}


@dataclass(frozen=True)
class ShardPlan:
    net: Net
    courier_handlers: dict  # NetUri -> fold (pumps and ack folds)
    outboxes: tuple[str, ...]  # outbox place paths to seed
    routes_out: tuple[tuple[str, str, str], ...]  # (foreign mailbox, outbox, ack door)
    doors_in: dict  # local mailbox path -> delivery door name
    proxies: tuple[str, ...]  # foreign mailboxes duplicated here; NEVER seeded


def seams(net: Net) -> set[tuple[str, str]]:
    """Every cross-loop arc (transition path, foreign mailbox path)."""
    places = {str(p) for p in net.places}
    transitions = {str(t) for t in net.transitions}
    return {
        (str(a.source), str(a.target))
        for a in net.arcs
        if str(a.source) in transitions
        and str(a.target) in places
        and loop_of(str(a.source))
        and loop_of(str(a.target))
        and loop_of(str(a.source)) != loop_of(str(a.target))
    }


RESERVED_COLORS = ("Outbox", "CourierAck")
RESERVED_PREFIXES = ("courier.", "on_courier_", "on_ack_")


def split(built, placement: dict[str, str]) -> dict[str, ShardPlan]:
    """Derive one shard net per placement group from ONE authored net.

    Copies places/transitions/arcs by object identity, keeps foreign
    seam targets as local proxies drained by export pumps into AX2
    outboxes, and adds delivery/ack doors. Source transitions (ingress
    doors) follow the shard of their target places.

    Refuses (ValueError) any net outside the shardable profile — see
    the module docstring — instead of silently mis-splitting."""
    net = built.net
    if net.completion is not None:
        raise ValueError("net-level completion has no per-shard meaning; cannot split")
    place_names = {str(p) for p in net.places}
    transition_names = {str(t) for t in net.transitions}

    for name in place_names | transition_names:
        if name.startswith(RESERVED_PREFIXES):
            raise ValueError(f"authored node {name} collides with the courier namespace")
    for p in net.places.values():
        if p.color in RESERVED_COLORS:
            raise ValueError(f"place {p.path} uses reserved protocol color {p.color}")

    ingress_doors = {
        str(t) for t in net.transitions if not any(str(a.target) == str(t) for a in net.arcs)
    }
    loops = {loop_of(n) for n in place_names} | {
        loop_of(n) for n in transition_names - ingress_doors
    }
    if "" in loops:
        nameless = sorted(
            n for n in place_names | (transition_names - ingress_doors) if not loop_of(n)
        )
        raise ValueError(f"nodes without a loop owner: {nameless}")

    # the anti-braid rule is a NET property, checked before placement:
    # a co-located braid is still a braid (the net is not shardable)
    for a in net.arcs:
        src, dst = str(a.source), str(a.target)
        if src in place_names and dst in transition_names and loop_of(src) != loop_of(dst):
            raise ValueError(f"braided seam: {dst} takes foreign input {src} ({a.mode})")

    # route naming must be injective over ALL seam targets, not per shard:
    # two colliding mailboxes fed from different shards would share a door
    targets = sorted({t for _, t in seams(net)})
    if len({_mangle(t) for t in targets}) != len(targets):
        raise ValueError(f"seam mailbox paths collide under mangling: {targets}")

    if loops != set(placement):
        raise ValueError(f"placement must cover exactly the loops {sorted(loops)}, got {sorted(placement)}")
    for loop, shard in placement.items():
        if not shard or not isinstance(shard, str):
            raise ValueError(f"shard name for loop {loop} must be a non-empty string, got {shard!r}")

    door_home: dict[str, str] = {}
    for name in ingress_doors:
        homes = {placement[loop_of(str(a.target))] for a in net.arcs if str(a.source) == name}
        if len(homes) != 1:
            raise ValueError(f"ingress door {name} must target exactly one shard, got {homes}")
        door_home[name] = homes.pop()

    # (source loop, target mailbox) pairs, for inbound door derivation
    seam_pairs = {(loop_of(s), t) for s, t in seams(net)}

    plans: dict[str, ShardPlan] = {}
    for shard in sorted(set(placement.values())):
        places = {str(p.path): p for p in net.places.values() if placement[loop_of(str(p.path))] == shard}
        transitions: dict[str, Transition] = {}
        for t in net.transitions.values():
            name = str(t.path)
            home = door_home.get(name) or placement[loop_of(name)]
            if home == shard:
                transitions[name] = t
        arcs: list[Arc] = []
        for a in net.arcs:
            src, dst = str(a.source), str(a.target)
            if src in transition_names:  # transition -> place
                if src in transitions:
                    arcs.append(a)  # kept even when dst is a foreign proxy
            elif dst in transitions:  # place -> transition (consume, read, or inhibit)
                # locality is guaranteed by the preflight braid check;
                # this guard only protects against splitter bugs
                if src not in places:  # pragma: no cover - internal invariant
                    raise AssertionError(f"splitter bug: {dst} kept foreign input {src}")
                arcs.append(a)

        proxies = sorted(
            {str(a.target) for a in arcs if str(a.target) in place_names and str(a.target) not in places}
        )
        courier_handlers: dict = {}
        outboxes: list[str] = []
        routes_out: list[tuple[str, str, str]] = []
        for proxy in proxies:
            places[proxy] = net.places[NetPath(proxy)]  # the SAME Place object
            m = _mangle(proxy)
            box, acks = f"courier.box_{m}", f"courier.acks_{m}"
            pump, fold, ack_door = f"courier.pump_{m}", f"courier.ackfold_{m}", f"on_ack_{m}"
            color = net.places[NetPath(proxy)].color
            places[box] = Place(NetPath(box), color="Outbox")
            places[acks] = Place(NetPath(acks), color="CourierAck")
            transitions[pump] = Transition(NetPath(pump), handler="courier_export")
            transitions[fold] = Transition(NetPath(fold), handler="courier_ack")
            transitions[ack_door] = Transition(NetPath(ack_door))
            arcs += [
                Arc(NetPath(proxy), NetPath(pump), ArcMode.CONSUME, color=color),
                Arc(NetPath(box), NetPath(pump), ArcMode.CONSUME, color="Outbox"),
                Arc(NetPath(pump), NetPath(box), color="Outbox"),
                Arc(NetPath(ack_door), NetPath(acks), color="CourierAck"),
                Arc(NetPath(acks), NetPath(fold), ArcMode.CONSUME, color="CourierAck"),
                Arc(NetPath(box), NetPath(fold), ArcMode.CONSUME, color="Outbox"),
                Arc(NetPath(fold), NetPath(box), color="Outbox"),
            ]
            outboxes.append(box)
            routes_out.append((proxy, box, ack_door))

        doors_in: dict[str, str] = {}
        for src_loop, target in sorted(seam_pairs):
            if placement[src_loop] != shard and placement[loop_of(target)] == shard:
                door = f"on_courier_{_mangle(target)}"
                if door not in transitions:
                    transitions[door] = Transition(NetPath(door))
                    arcs.append(
                        Arc(NetPath(door), NetPath(target), color=net.places[NetPath(target)].color)
                    )
                doors_in[target] = door

        shard_net = Net(places.values(), transitions.values(), arcs, name=f"pr-v5-{shard}")
        for name in transitions:
            if name.startswith("courier.pump_"):
                courier_handlers[shard_net.handler_uri(NetPath(name))] = _export
            elif name.startswith("courier.ackfold_"):
                courier_handlers[shard_net.handler_uri(NetPath(name))] = _ack
        plans[shard] = ShardPlan(
            shard_net, courier_handlers, tuple(outboxes), tuple(routes_out), doors_in, tuple(proxies)
        )
    return plans


# ---------------------------------------------------------------------------
# Placements
# ---------------------------------------------------------------------------

LOOPS = ("life", "review", "ci", "esc", "conv", "mut", "dash", "rem", "ready")
SOLO = {name: "all" for name in LOOPS}
TWO = {
    "life": "edge", "conv": "edge", "mut": "edge", "rem": "edge",
    "review": "core", "ci": "core", "esc": "core", "dash": "core", "ready": "core",
}
NINE = {name: name for name in LOOPS}


# ---------------------------------------------------------------------------
# Systems — one scenario API over both assemblies
# ---------------------------------------------------------------------------


class Cohabited:
    """AX1's single-instance assembly behind the shared scenario API."""

    def __init__(self, world: dict):
        self.world = world
        self.engine, self.history, self.built = ax1.spawn(world)

    def door_engine(self, door: str):
        return self.engine

    def settle(self) -> None:
        ax1.drive(self.engine)

    def tokens(self, place: str) -> list[dict]:
        return ax1.tokens(self.engine, place)


class Sharded:
    """The derived assembly: shard engines + AX2 couriers, same API."""

    def __init__(self, world: dict, placement: dict[str, str], prefix: str = "pr"):
        self.world = world
        self.placement = dict(placement)
        self.prefix = prefix
        self.built = ax1.build_v5_net()
        self.definitions = {d.declaration.name: d for d in ax1.make_activities(world)}
        self.all_handlers = ax1._wire(self.built, self.definitions)
        self.plans = split(self.built, self.placement)
        seed_all = ax1._seed_marking()
        self.engines: dict[str, Engine] = {}
        self.histories: dict[str, InMemoryHistoryStore] = {}
        self.handlers: dict[str, dict] = {}
        for shard, plan in self.plans.items():
            handlers = dict(plan.courier_handlers)
            for t in plan.net.transitions:
                uri = plan.net.handler_uri(NetPath(str(t)))
                if uri is not None and uri in self.all_handlers:
                    handlers[uri] = self.all_handlers[uri]
            seed = {}
            for place in plan.net.places:
                if str(place) in plan.proxies:
                    continue  # a proxy is transport, never state: it must start empty
                toks = seed_all.place(NetPath(str(place)))
                if toks:
                    seed[NetPath(str(place))] = toks
            for box in plan.outboxes:
                seed[NetPath(box)] = (
                    Token("Outbox", {"next": 1, "label": f"{shard}:{box}", "parcels": ()}),
                )
            self.handlers[shard] = handlers
            self.histories[shard] = InMemoryHistoryStore()
            self.engines[shard] = Engine.create(
                plan.net,
                f"{prefix}-{shard}",
                history=self.histories[shard],
                dispatch=InlineDispatch(self.definitions),
                marking=Marking(seed),
                handlers=handlers,
                guards={},
                activities=tuple(d.declaration for d in self.definitions.values()),
            )
        self._wire_couriers()
        ax1._HOST[id(self.engines[self.placement["life"]])] = world

    def _wire_couriers(self) -> None:
        self.couriers: dict[tuple[str, str], ax2.Courier] = {}
        for shard, plan in self.plans.items():
            for mailbox, box, ack_door in plan.routes_out:
                target = self.placement[loop_of(mailbox)]
                door = self.plans[target].doors_in[mailbox]
                self.couriers[(shard, mailbox)] = ax2.Courier(
                    self.engines[shard],
                    box,
                    ack_door,
                    self.engines[target],
                    door,
                    f"{self.prefix}-{shard}:{mailbox}",
                )

    def door_engine(self, door: str):
        loop = "rem" if door == "on_timer" else "life"
        return self.engines[self.placement[loop]]

    def outbox(self, courier: ax2.Courier) -> dict:
        [box] = [t.data for t in courier.source.marking.place(NetPath(courier.outbox))]
        return box

    def settle(self, limit: int = 100) -> None:
        for _ in range(limit):
            for engine in self.engines.values():
                ax1.drive(engine)
            moved = False
            for courier in self.couriers.values():
                if self.outbox(courier)["parcels"]:
                    courier.drain()
                    moved = True
            if not moved:
                return
        raise AssertionError("sharded assembly did not settle")

    def tokens(self, place: str) -> list[dict]:
        engine = self.engines[self.placement[loop_of(place)]]
        return ax1.tokens(engine, place)

    def resurrect(self, shard: str) -> None:
        """Reload one shard engine from its chronicle (crash recovery)."""
        self.engines[shard] = Engine.load(
            self.plans[shard].net,
            f"{self.prefix}-{shard}",
            history=self.histories[shard],
            dispatch=InlineDispatch(self.definitions),
            handlers=self.handlers[shard],
            guards={},
            activities=tuple(d.declaration for d in self.definitions.values()),
        )
        self._wire_couriers()
        if shard == self.placement["life"]:
            ax1._HOST[id(self.engines[shard])] = self.world


# ---------------------------------------------------------------------------
# Scenario scripts — identical ingress against either system
# ---------------------------------------------------------------------------


def full_life(sys) -> None:
    """AX1's happy path: review blocks, CI green, approval, dismiss,
    announce once, merged; every loop that ends, ends."""
    life = sys.door_engine("on_head")
    ax1.see_head(life, "h1")
    sys.settle()
    ax1.see_run(life, "h1", "success")
    ax1.see_human(life)
    sys.settle()
    ax1.see_comment(life, "c1", "dismiss", arg="f-h1")
    sys.settle()
    ax1.see_close(life, sys.world, "merged")
    sys.settle()


def announce_once(sys) -> None:
    sys.world["agent_findings"]["h1"] = []
    life = sys.door_engine("on_head")
    ax1.see_head(life, "h1")
    sys.settle()
    ax1.see_run(life, "h1", "success")
    ax1.see_human(life)
    sys.settle()
    ax1.see_human(life)  # re-satisfied: must NOT announce again
    sys.settle()


def ladder(sys) -> None:
    """Escalation: rerun burns, repair pushes, third failure -> human."""
    life = sys.door_engine("on_head")
    ax1.see_head(life, "h1")
    sys.settle()
    ax1.see_run(life, "h1", "failure", run_id=1, fp="fpX")
    sys.settle()
    ax1.see_run(life, "h1", "failure", run_id=2, fp="fpX")
    sys.settle()
    ax1.see_head(life, "h1+repair:L1:fpX")
    sys.settle()
    ax1.see_run(life, "h1+repair:L1:fpX", "failure", run_id=3, fp="fpX")
    sys.settle()


def snooze_reminders(sys) -> None:
    life = sys.door_engine("on_head")
    timers = sys.door_engine("on_timer")
    ax1.see_head(life, "h1")
    sys.settle()
    ax1.see_comment(life, "c1", "snooze", arg="t1")
    sys.settle()
    ax1.deliver(timers, "on_timer", "TimerDue", {"timer_id": "t1"})
    sys.settle()
    ax1.see_comment(life, "c2", "resume", arg="t1")
    sys.settle()
    ax1.deliver(timers, "on_timer", "TimerDue", {"timer_id": "t2"})
    sys.settle()


def draft_resume(sys) -> None:
    """Dormancy absorbs; resume mints a new incarnation and re-admits."""
    life = sys.door_engine("on_head")
    ax1.see_head(life, "h1")
    sys.settle()
    ax1.see_draft(life, sys.world)
    sys.settle()
    ax1.see_head(life, "h1")  # absorbed by dormancy
    sys.settle()
    ax1.see_resume(life, sys.world)
    sys.settle()
    ax1.see_run(life, "h1", "success")
    ax1.see_human(life)
    sys.settle()
    ax1.see_comment(life, "c1", "dismiss", arg="f-h1")
    sys.settle()


def supersede(sys) -> None:
    """h2 supersedes h1 mid-flight; all green lands on h2 only."""
    life = sys.door_engine("on_head")
    ax1.see_head(life, "h1")
    sys.settle()
    ax1.see_head(life, "h2")
    sys.settle()
    ax1.see_run(life, "h2", "success")
    ax1.see_human(life)
    sys.settle()
    ax1.see_comment(life, "c1", "dismiss", arg="f-h2")
    sys.settle()


SCENARIOS = {
    "full_life": full_life,
    "announce_once": announce_once,
    "ladder": ladder,
    "snooze_reminders": snooze_reminders,
    "draft_resume": draft_resume,
    "supersede": supersede,
}

# batons and terminal places compared token-for-token across variants
COMPARED_PLACES = (
    "life.state",
    "review.memory",
    "review.done",
    "ci.memory",
    "ci.done",
    "esc.ladder",
    "esc.done",
    "conv.memory",
    "mut.state",
    "mut.done",
    "rem.state",
    "rem.done",
    "ready.snap",
    "ready.done",
)


def outcome(sys) -> dict:
    """The SELECTED outcome of a run: externally visible world effects
    (readiness, comment kind/key, pushes, reruns, dashboard, authority)
    plus the 14 selected baton/terminal places, token-for-token. Not
    every internal marking is compared — that is what TestShardReplay's
    whole-marking check covers per shard. Dashboard entries are
    arrival-ordered across seams, so the world's dashboard is compared
    as a sorted multiset — the one deliberate order-insensitive
    comparison (see the module docstring)."""
    world = sys.world
    return {
        "ready": ax1.ready_keys(world),
        "comments": sorted((c["kind"], c["key"]) for c in world["comments"]),
        "pushes": [(p["op"], p["from"], p["to"]) for p in world["pushes"]],
        "reruns": world["reruns"],
        "dashboard": sorted(world["dashboard"]),
        "authority": world["authority"],
        **{place: sys.tokens(place) for place in COMPARED_PLACES},
    }


def run_both(name: str, placement: dict[str, str]):
    scenario = SCENARIOS[name]
    world_a, world_b = ax1.fresh_world(), ax1.fresh_world()
    cohabited = Cohabited(world_a)
    sharded = Sharded(world_b, placement)
    scenario(cohabited)
    scenario(sharded)
    return cohabited, sharded


# ---------------------------------------------------------------------------
# Structural claims
# ---------------------------------------------------------------------------


def _toy_net(**spec_kwargs):
    """A two-loop toy net whose `braid` transition takes a foreign
    input — the smallest net OUTSIDE the shardable profile."""
    from petrus.impetus.dsl import NetSpec, petri_handler

    net = NetSpec("braided", **spec_kwargs)
    a, b = net.s.a, net.s.b
    a.p.inbox(ax2.WorkSeen)
    b.p.shared(ax2.WorkSeen)
    net.t.door >> a.p.inbox

    def fold(binding, outputs):  # pragma: no cover - never fires
        return {}

    (a.p.inbox, b.p.shared) >> a.t.braid(handler=petri_handler(fold)) >> b.p.shared
    return net


class TestSplitterShape:
    def test_the_seam_census_is_mechanical(self) -> None:
        """The splitter derives the seams from the net itself — and the
        derivation exactly matches AX1's hand-declared census."""
        built = ax1.build_v5_net()
        assert seams(built.net) == ax1.DECLARED_SEAMS

    def test_solo_placement_reproduces_the_cohabited_net(self) -> None:
        """The degenerate split (all loops on one shard) adds NOTHING:
        no proxies, no pumps, no doors, no couriers — the very same
        Place/Transition/Arc OBJECTS, not merely equal counts."""
        built = ax1.build_v5_net()
        [plan] = split(built, SOLO).values()
        assert plan.routes_out == ()
        assert plan.doors_in == {}
        assert plan.proxies == ()
        assert {id(p) for p in plan.net.places.values()} == {
            id(p) for p in built.net.places.values()
        }
        assert {id(t) for t in plan.net.transitions.values()} == {
            id(t) for t in built.net.transitions.values()
        }
        assert {id(a) for a in plan.net.arcs} == {id(a) for a in built.net.arcs}

    @pytest.mark.parametrize("placement", [TWO, NINE], ids=["two", "nine"])
    def test_loop_definitions_are_shared_by_object_identity(self, placement) -> None:
        """No loop is rewritten: every loop place and transition in a
        shard IS the authored net's object, and every loop handler
        REGISTERED on a shard engine IS the same callable the cohabited
        wiring produced — checked as identity, not equality."""
        built = ax1.build_v5_net()
        for plan in split(built, placement).values():
            for path, place in plan.net.places.items():
                if not str(path).startswith("courier."):
                    assert place is built.net.places[path]
            for path, transition in plan.net.transitions.items():
                name = str(path)
                if not name.startswith(("courier.", "on_courier_", "on_ack_")):
                    assert transition is built.net.transitions[path]
        sharded = Sharded(ax1.fresh_world(), placement)
        for shard, plan in sharded.plans.items():
            authored = {
                plan.net.handler_uri(NetPath(str(t)))
                for t in plan.net.transitions
                if not str(t).startswith(("courier.", "on_courier_", "on_ack_"))
            } - {None}
            assert authored, f"shard {shard} registered no authored handlers"
            for uri in authored:
                assert sharded.handlers[shard][uri] is sharded.all_handlers[uri]

    @pytest.mark.parametrize("placement", [TWO, NINE], ids=["two", "nine"])
    def test_the_machinery_bill_is_a_formula(self, placement) -> None:
        """Sharding overhead is exactly: per route (proxy duplicate +
        outbox + ack place, pump + ack fold + ack door, 7 arcs) and per
        inbound door (1 transition + 1 arc). Nothing else changes."""
        built = ax1.build_v5_net()
        plans = split(built, placement)
        routes = sum(len(p.routes_out) for p in plans.values())
        doors = sum(len(p.doors_in) for p in plans.values())
        assert sum(len(p.net.places) for p in plans.values()) == len(built.net.places) + 3 * routes
        assert (
            sum(len(p.net.transitions) for p in plans.values())
            == len(built.net.transitions) + 3 * routes + doors
        )
        assert sum(len(p.net.arcs) for p in plans.values()) == len(built.net.arcs) + 7 * routes + doors

    def test_a_braided_net_is_refused(self) -> None:
        """The shardability invariant is a NET property, not a
        placement property: a transition taking a foreign input is
        refused whether the loops are separated OR co-located — a
        co-located braid is still a braid."""
        with pytest.raises(ValueError, match="braided seam"):
            split(_toy_net().build(), {"a": "a", "b": "b"})
        with pytest.raises(ValueError, match="braided seam"):
            split(_toy_net().build(), {"a": "all", "b": "all"})

    def test_the_profile_is_enforced_not_documented(self) -> None:
        """Every remaining profile clause refuses with ValueError:
        placement coverage, empty shard names, nameless nodes,
        straddling ingress doors, reserved namespace and colors, and
        net-level completion. (Braid and mangle collisions have their
        own tests.)"""
        from petrus.impetus.dsl import NetSpec

        built = ax1.build_v5_net()
        with pytest.raises(ValueError, match="placement must cover exactly"):
            split(built, {**NINE, "extra": "extra"})
        with pytest.raises(ValueError, match="placement must cover exactly"):
            split(built, {k: v for k, v in NINE.items() if k != "dash"})

        straddle = NetSpec("straddle")
        straddle.s.a.p.inbox(ax2.WorkSeen)
        straddle.s.b.p.inbox(ax2.WorkSeen)
        straddle.t.door >> straddle.s.a.p.inbox
        straddle.t.door >> straddle.s.b.p.inbox
        with pytest.raises(ValueError, match="exactly one shard"):
            split(straddle.build(), {"a": "a1", "b": "b1"})

        squatter = NetSpec("squatter")
        squatter.s.courier.p.smuggled(ax2.WorkSeen)
        squatter.t.door >> squatter.s.courier.p.smuggled
        with pytest.raises(ValueError, match="courier namespace"):
            split(squatter.build(), {"courier": "c"})

        plain = NetSpec("plain")
        plain.s.a.p.inbox(ax2.WorkSeen)
        plain.t.door >> plain.s.a.p.inbox
        with pytest.raises(ValueError, match="non-empty string"):
            split(plain.build(), {"a": ""})

        orphan = NetSpec("orphan")
        orphan.p.stray(ax2.WorkSeen)
        orphan.t.door >> orphan.p.stray
        with pytest.raises(ValueError, match="without a loop owner"):
            split(orphan.build(), {})

        done = NetSpec("completed", completion="all_done")
        done.s.a.p.out(ax2.WorkSeen)
        done.t.door >> done.s.a.p.out
        with pytest.raises(ValueError, match="completion"):
            split(done.build(), {"a": "a"})

        reserved = NetSpec("reserved")
        reserved.s.a.p.box(ax2.Outbox)
        reserved.t.door >> reserved.s.a.p.box
        with pytest.raises(ValueError, match="reserved protocol color"):
            split(reserved.build(), {"a": "a"})

    def test_colliding_seam_targets_are_refused_globally(self) -> None:
        """Injectivity must hold across ALL seam targets, not per
        shard: `c.foo_bar` and `c.foo.bar` both mangle to `c_foo_bar`,
        so two DIFFERENT source shards feeding them would share one
        inbound door — refused up front, on any placement."""
        from petrus.impetus.dsl import NetSpec, petri_handler

        def forward(binding, outputs):  # pragma: no cover - never fires
            [out] = list(outputs)
            [(_, toks)] = list(binding.consumed)
            return {out.target: toks}

        net = NetSpec("collide")
        a, b, c = net.s.a, net.s.b, net.s.c
        a.p.src(ax2.WorkSeen)
        b.p.src(ax2.WorkSeen)
        c.p.foo_bar(ax2.WorkSeen)
        c.s.foo.p.bar(ax2.WorkSeen)
        net.t.door_a >> a.p.src
        net.t.door_b >> b.p.src
        a.p.src >> a.t.send(handler=petri_handler(forward)) >> c.p.foo_bar
        b.p.src >> b.t.send(handler=petri_handler(forward)) >> c.s.foo.p.bar
        for placement in ({"a": "a", "b": "b", "c": "c"}, {"a": "x", "b": "x", "c": "x"}):
            with pytest.raises(ValueError, match="collide under mangling"):
                split(net.build(), placement)


# ---------------------------------------------------------------------------
# Outcome equivalence — the same scenarios, every placement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("placement", [SOLO, TWO, NINE], ids=["solo", "two", "nine"])
@pytest.mark.parametrize("name", sorted(SCENARIOS))
class TestOutcomeEquivalence:
    def test_scenario_lands_identically(self, name: str, placement) -> None:
        cohabited, sharded = run_both(name, placement)
        assert outcome(sharded) == outcome(cohabited)


class TestEquivalenceIsMeaningful:
    """Pin a few absolute facts so the equivalence tests can never pass
    vacuously (two equally-empty worlds would also be 'equal')."""

    def test_full_life_reaches_the_terminal_states(self) -> None:
        _, sharded = run_both("full_life", NINE)
        assert ax1.ready_keys(sharded.world) == ["ready:h1:i1"]
        assert sharded.tokens("life.state")[0]["phase"] == "terminal"
        assert sharded.tokens("review.done")[0]["reviewed"] == ["h1"]
        assert sharded.tokens("ci.done")[0]["status"] == "success"
        assert sharded.tokens("ready.done")[0]["announced"] == [1]
        assert sharded.tokens("conv.memory")[0]["served"] == ["c1"]

    def test_ladder_burned_the_budget_across_four_shards(self) -> None:
        _, sharded = run_both("ladder", NINE)
        assert sharded.world["reruns"] == ["L1:fpX"]
        assert [(p["op"]) for p in sharded.world["pushes"]] == ["repair:L1:fpX"]
        assert any("human_needed" in e for e in sharded.world["dashboard"])

    def test_draft_resume_minted_the_second_incarnation(self) -> None:
        _, sharded = run_both("draft_resume", NINE)
        assert ax1.ready_keys(sharded.world) == ["ready:h1:i2"]


class TestGeneratedRouteFifo:
    def test_two_queued_parcels_cross_one_seam_in_emission_order(self) -> None:
        """The lowering itself preserves order: two heads admitted
        before any drain sit in ONE outbox as sequenced parcels, and
        the target folds them in exactly that order. This tests AX3's
        proxy -> pump -> outbox derivation, not (again) AX2's courier."""
        sharded = Sharded(ax1.fresh_world(), NINE, "fifo")
        life = sharded.door_engine("on_head")
        ax1.see_head(life, "h1")
        ax1.drive(life)
        ax1.see_head(life, "h2")
        ax1.drive(life)
        courier = sharded.couriers[(sharded.placement["life"], "review.heads")]
        parcels = sharded.outbox(courier)["parcels"]
        assert [p["n"] for p in parcels] == [1, 2]
        assert [p["token"]["data"]["head"] for p in parcels] == ["h1", "h2"]
        assert {p["token"]["color"] for p in parcels} == {"HeadWork"}
        sharded.settle()
        assert sharded.outbox(courier)["parcels"] == ()
        # each round's completion appended its finding: fold order is visible
        mem = sharded.tokens("review.memory")[0]
        assert [f["id"] for f in mem["provisional"]] == ["f-h1", "f-h2"], (
            "target folded parcels out of emission order"
        )
        assert sharded.world["agent_calls"] == 2  # both rounds really ran


# ---------------------------------------------------------------------------
# Seam crashes and shard resurrection
# ---------------------------------------------------------------------------


def _head_and_drive_life_only(sharded: Sharded) -> ax2.Courier:
    """Deliver h1 and advance ONLY the life shard: the review work fact
    is now a parcel sitting in the life shard's outbox, undelivered."""
    life = sharded.door_engine("on_head")
    ax1.see_head(life, "h1")
    ax1.drive(life)
    courier = sharded.couriers[(sharded.placement["life"], "review.heads")]
    assert sharded.outbox(courier)["parcels"], "expected an undelivered seam parcel"
    return courier


class TestSeamCrashes:
    def test_courier_crash_mid_seam_then_fresh_drain_matches_the_clean_run(self) -> None:
        """The AX2 guarantee holds inside the real assembly: a courier
        dying between target delivery and source ack neither loses nor
        duplicates the review round — the finished world and batons are
        exactly the clean run's."""
        clean, crashed = Sharded(ax1.fresh_world(), NINE, "a"), Sharded(ax1.fresh_world(), NINE, "b")
        courier = _head_and_drive_life_only(crashed)
        courier.drain(crash="before_ack")  # died mid-seam
        assert crashed.outbox(courier)["parcels"], "source was never told"
        crashed.settle()  # a fresh pass converges

        full_life(clean)
        # finish the crashed run with the same remaining script
        life = crashed.door_engine("on_head")
        ax1.see_run(life, "h1", "success")
        ax1.see_human(life)
        crashed.settle()
        ax1.see_comment(life, "c1", "dismiss", arg="f-h1")
        crashed.settle()
        ax1.see_close(life, crashed.world, "merged")
        crashed.settle()
        assert outcome(crashed) == outcome(clean)
        # exactly one review round ever ran despite the redelivery
        assert crashed.world["agent_calls"] == clean.world["agent_calls"] == 1

    def test_target_shard_resurrected_mid_delivery_converges(self) -> None:
        """Crash the TARGET after the parcel landed durably but before
        its folds ran; resurrect the shard from its chronicle and the
        scenario completes as if nothing happened."""
        clean, crashed = Sharded(ax1.fresh_world(), NINE, "c"), Sharded(ax1.fresh_world(), NINE, "d")
        courier = _head_and_drive_life_only(crashed)
        courier.drain(crash="after_accept")  # accepted, review never driven
        assert crashed.tokens("review.memory")[0]["reviewed"] == []
        crashed.resurrect("review")
        crashed.settle()

        full_life(clean)
        life = crashed.door_engine("on_head")
        ax1.see_run(life, "h1", "success")
        ax1.see_human(life)
        crashed.settle()
        ax1.see_comment(life, "c1", "dismiss", arg="f-h1")
        crashed.settle()
        ax1.see_close(life, crashed.world, "merged")
        crashed.settle()
        assert outcome(crashed) == outcome(clean)
        assert crashed.world["agent_calls"] == 1


class TestShardReplay:
    def test_every_shard_replays_to_its_live_marking(self) -> None:
        """After a complete scenario, each shard's chronicle rebuilds
        the exact live marking — sharding costs no replayability."""
        _, sharded = run_both("full_life", NINE)
        for shard, plan in sharded.plans.items():
            replayed = Engine.load(
                plan.net,
                f"pr-{shard}",
                history=sharded.histories[shard],
                dispatch=InlineDispatch(sharded.definitions),
                handlers=sharded.handlers[shard],
                guards={},
                activities=tuple(d.declaration for d in sharded.definitions.values()),
            )
            live = sharded.engines[shard]
            for place in plan.net.places:
                path = NetPath(str(place))
                assert list(replayed.marking.place(path)) == list(
                    live.marking.place(path)
                ), f"{shard}:{place}"  # whole tokens: color AND data
