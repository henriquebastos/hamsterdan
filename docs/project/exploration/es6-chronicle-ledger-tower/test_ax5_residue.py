"""AX5 — the residue probe: a kill cannot undo the world, and doesn't need to.

Executable demonstration on the FROZEN engine of the tower's honest
residue (tower-model §4): killing an instance is bookkeeping — it
stops feeding events — while a worker dispatched under the dead epoch
may still land its effect later (at-least-once guarantees it
eventually will). Safety never comes from the kill; it comes from the
gate: the world's own compare-and-swap classifies the orphan as
``moved`` and the two chronicles never mix.

Cast:

- one WORLD — a fake git server whose CAS is server-side, like
  GitHub's: push applies only when the branch head equals the
  expected head;
- two engine INSTANCES of the same push-gate net (AX1's shape-M tail),
  each with its own ``InMemoryHistoryStore`` — two cells, two
  chronicles;
- the CASE NET's role is played by the test timeline itself: observe
  authority moved -> abandon epoch 1 (stop advancing) -> spawn epoch 2.

Reuses ES-003 AX5's ``VariantPayloadConverter`` /
``VariantRoutingActivityHandler`` unchanged for union-result routing.
"""

from dataclasses import asdict, dataclass

from ax5_compiler import VariantPayloadConverter, VariantRoutingActivityHandler
from petrus.engine import Engine
from petrus.impetus.dsl import NetSpec
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.activity import activity as motus_activity
from petrus.motus.dispatch import InlineDispatch

# -- colors ------------------------------------------------------------------


@dataclass(frozen=True)
class PushRequest:
    operation: str
    expected_head: str
    new_head: str


@dataclass(frozen=True)
class Committed:
    operation: str
    head: str


@dataclass(frozen=True)
class Moved:
    operation: str
    observed_head: str


# -- the world: server-side CAS, like GitHub ----------------------------------


def fresh_world(head: str = "h1") -> dict:
    return {"branch_head": head, "commits": []}


def make_git_push(world: dict):
    @motus_activity(converter=VariantPayloadConverter())
    def git_push(work: PushRequest) -> Committed | Moved:
        if world["branch_head"] != work.expected_head:
            return Moved(operation=work.operation, observed_head=world["branch_head"])
        world["branch_head"] = work.new_head
        world["commits"].append(work.operation)
        return Committed(operation=work.operation, head=work.new_head)

    return git_push


# -- the net: AX1's gate step, verbatim shape ---------------------------------


def build_push_net():
    net = NetSpec("push")
    p, t = net.p, net.t
    (
        p.request(PushRequest)
        >> t.commit(handler="git_push")
        >> (p.committed(Committed), p.moved(Moved))
    )
    return net.build(), abs(t.commit)


def spawn(
    world: dict, *, instance: str, operation: str, expected: str, new: str
) -> tuple[Engine, InMemoryHistoryStore]:
    """What the case net's ``spawn_instance`` activity would do.

    Returns the engine AND its private history store — one chronicle
    per cell; the meta level holds the handle.
    """
    built, commit_path = build_push_net()
    definition = make_git_push(world)
    uri = built.net.handler_uri(commit_path)
    handlers = dict(built.handlers)
    handlers[uri] = VariantRoutingActivityHandler(
        built.net, commit_path, definition, variants=("Committed", "Moved")
    )
    request = PushRequest(operation=operation, expected_head=expected, new_head=new)
    history = InMemoryHistoryStore()
    engine = Engine.create(
        built.net,
        instance,
        history=history,
        dispatch=InlineDispatch({definition.declaration.name: definition}),
        marking=Marking({NetPath("request"): (Token("PushRequest", asdict(request)),)}),
        handlers=handlers,
        guards=dict(built.guards),
        activities=(definition.declaration,),
    )
    return engine, history


def drive_bounded(subject: Engine, limit: int = 50) -> None:
    for _ in range(limit):
        if not subject.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


def tokens(engine: Engine, place: str) -> list[dict]:
    return [token.data for token in engine.marking.place(NetPath(place))]


# -- the timeline --------------------------------------------------------------


def killed_epoch_timeline() -> tuple[
    dict, Engine, Engine, InMemoryHistoryStore, InMemoryHistoryStore
]:
    world = fresh_world(head="h1")

    # Epoch 1 computes a repair under h1; its push worker is dispatched
    # but slow — we deliberately do not advance yet.
    epoch1, chronicle1 = spawn(
        world, instance="pr7-epoch1", operation="op-e1", expected="h1", new="h1b"
    )

    # The author pushes: authority moves. The case net observes it,
    # ABANDONS epoch 1 (the kill is: stop advancing — no poison tokens,
    # no drain, nothing sent into the dead net) and spawns epoch 2.
    world["branch_head"] = "h2"
    epoch2, chronicle2 = spawn(
        world, instance="pr7-epoch2", operation="op-e2", expected="h2", new="h3"
    )
    drive_bounded(epoch2)

    # The orphaned epoch-1 worker finally lands its effect
    # (at-least-once guarantees it eventually will). Graveyard policy:
    # the dead chronicle may still record its completion.
    drive_bounded(epoch1)
    return world, epoch1, epoch2, chronicle1, chronicle2


class TestTheResidue:
    def test_the_new_epoch_commits_under_the_new_authority(self) -> None:
        _, _, epoch2, _, _ = killed_epoch_timeline()
        assert tokens(epoch2, "committed") == [{"operation": "op-e2", "head": "h3"}]
        assert tokens(epoch2, "moved") == []

    def test_the_orphan_cannot_touch_the_world(self) -> None:
        """The gate absorbs the late effect: server-side CAS, no force."""
        world, _, _, _, _ = killed_epoch_timeline()
        assert world["branch_head"] == "h3"
        assert world["commits"] == ["op-e2"]  # op-e1 never applied

    def test_the_orphan_lands_as_a_classified_outcome_not_an_error(self) -> None:
        _, epoch1, _, _, _ = killed_epoch_timeline()
        assert tokens(epoch1, "committed") == []
        assert tokens(epoch1, "moved") == [{"operation": "op-e1", "observed_head": "h3"}]

    def test_the_chronicles_never_mix(self) -> None:
        """Each cell owns its history: no operation identity leaks
        across instances, in either direction."""
        _, _, _, chronicle1, chronicle2 = killed_epoch_timeline()
        one = repr(chronicle1.records)
        two = repr(chronicle2.records)
        assert "op-e1" in one and "op-e2" not in one
        assert "op-e2" in two and "op-e1" not in two


class TestReplayNeverPassesTheDrop:
    def test_the_dead_instance_replays_as_safely_as_a_finished_one(self) -> None:
        """Nothing was truncated: Engine.load on the dead cell's
        history reproduces its final marking — including the late
        `moved` token — and the instance is quiescent, not poisoned."""
        world, _, _, chronicle1, _ = killed_epoch_timeline()

        built, commit_path = build_push_net()
        definition = make_git_push(world)
        handlers = dict(built.handlers)
        handlers[built.net.handler_uri(commit_path)] = VariantRoutingActivityHandler(
            built.net, commit_path, definition, variants=("Committed", "Moved")
        )
        resurrected = Engine.load(
            built.net,
            "pr7-epoch1",
            history=chronicle1,
            dispatch=InlineDispatch({definition.declaration.name: definition}),
            handlers=handlers,
            guards=dict(built.guards),
            activities=(definition.declaration,),
        )
        assert tokens(resurrected, "moved") == [{"operation": "op-e1", "observed_head": "h3"}]
        assert tokens(resurrected, "request") == []
        assert not resurrected.advance().ready  # abandoned = quiesced forever
        assert world["commits"] == ["op-e2"]  # replay re-fired nothing
