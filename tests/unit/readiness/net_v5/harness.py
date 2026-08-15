"""Shared test harness for the V5 actor-loop topology.

Spawns the composed net on the frozen engine with inline dispatch and
drives host-normalized observations through the ingress doors.
"""

from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import NetPath, Token
from petrus.motus.dispatch import InlineDispatch

from hamsterdan.readiness.net_v5 import build_net_v5, seed_marking


def spawn(instance: str = "pr-v5"):
    built = build_net_v5()
    engine = Engine.create(
        built.net,
        instance,
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=seed_marking(),
        handlers=dict(built.handlers),
        guards=dict(built.guards),
    )
    return engine, built


def drive(engine: Engine, limit: int = 200) -> None:
    for _ in range(limit):
        if not engine.advance().ready:
            return
    raise AssertionError(f"engine did not quiesce in {limit} advances")


_SEQ = {"n": 0}


def deliver(engine: Engine, door: str, color: str, data: dict) -> None:
    _SEQ["n"] += 1
    engine.deliver(door, Token(color, data), identity=f"{door}-{_SEQ['n']}")
    drive(engine)


def tokens(engine: Engine, place: str) -> list[dict]:
    return [token.data for token in engine.marking.place(NetPath(place))]


def one(engine: Engine, place: str) -> dict:
    [data] = tokens(engine, place)
    return data


def see_head(engine, head: str, base: str = "b1", mergeable: bool = True, policy: str = "p1"):
    deliver(
        engine,
        "on_head",
        "HeadSeen",
        {"head": head, "base": base, "mergeable": mergeable, "policy": policy},
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
