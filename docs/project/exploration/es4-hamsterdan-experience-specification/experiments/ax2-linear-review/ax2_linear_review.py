"""ES-004 AX2 — the review subnet as a linear block chain.

AX1 drafted this contract for review production feeding the comment
gate (shape P):

    entry   ReviewRequest (authority basis + diff + lineage)
    work    prepare (pure) → agent (disposable effect) →
            draft publication (pure) → fence (reads authority) →
            publish (comment gate: lookup-first)
    exits   acknowledged | discarded(stale) | failed(retryable rail) |
            blocked(recoverable fault)

This module expresses that contract with ES-003 primitives ONLY
(AX23 blocks + AX25 rail). The world is a plain dict standing in for
GitHub and the agent provider; colors reuse the production contract
vocabulary (ReviewRequest, ReviewResult, FindingPublicationRequest…)
without importing production code.

The one deliberate mismatch — the algebra's ``pure`` cannot say
"effectful but world-neutral" for the agent call — is left visible;
the test suite captures the refusal as evidence (Finding for the
record, not something to patch silently here).
"""

from __future__ import annotations

from ax23_blocks import Block, classify, then, transform
from ax25_rail import attempt, rail_then


class AgentOutage(Exception):
    """A transient provider failure — retryable by classification."""


# -- leaves, in AX1-contract order ---------------------------------------------------


def prepare_basis() -> Block:
    """Pure: assemble the agent prompt basis from the request."""
    return attempt(
        "prepare_basis",
        lambda request: {**request, "prompt": f"review {request['head']} against {request['base_head']}"},
        accepts="ReviewRequest",
        returns="ReviewPrompt",
        pure=True,
    )


def run_agent(world: dict) -> Block:
    """Disposable effect: costs an agent run, mutates nothing in the
    world that anyone else can observe. May raise transiently."""

    def invoke(prompt: dict) -> dict:
        if world.get("agent_down"):
            raise AgentOutage("review agent unavailable")
        world["agent_runs"] += 1
        return {
            "epoch": prompt["epoch"],
            "head": prompt["head"],
            "base_head": prompt["base_head"],
            "operation": prompt["operation"],
            "findings": [{"path": "src/x.py", "note": "unbounded retry"}],
        }

    return attempt("run_agent", invoke, accepts="ReviewPrompt", returns="ReviewResult", retryable=(AgentOutage,))


def draft_publication() -> Block:
    """Pure: shape the agent result into a publication request that
    carries its own authority basis and immutable operation."""
    return attempt(
        "draft_publication",
        lambda result: {key: result[key] for key in ("epoch", "head", "base_head", "operation", "findings")},
        accepts="ReviewResult",
        returns="FindingPublicationRequest",
        pure=True,
    )


def fence_authority() -> Block:
    """The AX20 fence as data-driven classification: read the shared
    authority place and compare the token's basis against it. Stale
    work exits through ``stale`` — discarded, never published."""

    def fenced(request: dict, contexts: dict) -> tuple[str, dict]:
        [authority] = contexts.values()
        current = (authority["epoch"], authority["head"], authority["base_head"])
        basis = (request["epoch"], request["head"], request["base_head"])
        if basis == current:
            return ("current", request)
        return ("stale", {"basis": list(basis), "authority": list(current)})

    return classify(
        "fence_authority",
        fenced,
        accepts="FindingPublicationRequest",
        outcomes={"current": "FencedPublication", "stale": "StaleAuthority"},
        reads=(("authority", "Authority"),),
    )


def publish_findings(world: dict) -> Block:
    """The comment gate: lookup-first by (kind, operation, head), then
    post. Kind-1 idempotency (already did it → return the existing
    payload); capability failure after bounded retries → blocked."""

    def publish(request: dict) -> tuple[str, dict]:
        marker = ("finding", request["operation"], request["head"])
        for comment in world["comments"]:
            if comment["marker"] == list(marker):
                return ("acknowledged", {"comment_id": comment["id"], "reused": True})
        if world.get("github_down"):
            return ("blocked", {"kind": "capability", "operation": request["operation"], "retryable": True})
        comment = {"id": len(world["comments"]) + 1, "marker": list(marker), "findings": request["findings"]}
        world["comments"].append(comment)
        return ("acknowledged", {"comment_id": comment["id"], "reused": False})

    return classify(
        "publish_findings",
        publish,
        accepts="FencedPublication",
        outcomes={"acknowledged": "FindingPublicationResult", "blocked": "RecoverableFault"},
    )


# -- the subnet: one linear composition ------------------------------------------------


def review_subnet(world: dict) -> Block:
    """The whole AX1 contract as a chain. Reads top-to-bottom in
    exactly the order work happens; every branch is an exit."""
    interior = rail_then(rail_then(prepare_basis(), run_agent(world)), draft_publication())
    fenced = then(interior, fence_authority(), on="out")
    return then(fenced, publish_findings(world), on="current")


def fresh_world() -> dict:
    return {"agent_runs": 0, "comments": []}
