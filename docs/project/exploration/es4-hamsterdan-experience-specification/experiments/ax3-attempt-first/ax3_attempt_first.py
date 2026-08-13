"""ES-004 AX3 — attempt-first gates: the operation is the fence.

Navigator doctrine under test:

    Don't pre-check authority. Just do the operation. Where the
    provider is atomic (git CAS), failure IS the staleness signal —
    classify it as "preconditions changed", discard, and wait for the
    webhook. Where the provider is not atomic (comments), a stale
    write lands as tolerable noise; toleration is mandatory anyway
    because no pre-check can close the race.

Verified provider facts this module encodes:

- Production advances refs by GraphQL exact compare-and-swap with an
  expected head (src/hamsterdan/host/git_publish.py:249-258). A moved
  branch rejects the CAS — no force, no overwrite.
- GitHub accepts review comments whose commit_id is no longer the PR
  head and merely renders them "outdated"; issue comments have no
  head binding at all. A stale comment cannot fail — it lands.

Consequence for shape M: the fence transition disappears. The gate
classifies its own provider outcome, and the subnet needs no
authority context at all — entry→exits, context-free.
"""

from __future__ import annotations

from ax23_blocks import Block, classify, then
from ax25_rail import attempt, rail_then


class AgentOutage(Exception):
    """Transient coding-agent failure — retryable by classification."""


# -- shape M, attempt-first ------------------------------------------------------------


def prepare_change() -> Block:
    """Pure: shape the request into an agent instruction."""
    return attempt(
        "prepare_change",
        lambda request: {**request, "instruction": f"apply {request['operation']} onto {request['expected_head']}"},
        accepts="ChangeRequest",
        returns="ChangeInstruction",
        pure=True,
    )


def agent_patch(world: dict) -> Block:
    """Spendable effect: the coding agent works in an isolated
    checkout with no credentials. It costs money; it mutates nothing
    anyone can observe."""

    def invoke(instruction: dict) -> dict:
        if world.get("agent_down"):
            raise AgentOutage("coding agent unavailable")
        world["agent_runs"] += 1
        return {
            "operation": instruction["operation"],
            "expected_head": instruction["expected_head"],
            "payload_digest": f"digest-of-{instruction['operation']}",
            "patch": "diff --git a/x b/x",
        }

    return attempt("agent_patch", invoke, accepts="ChangeInstruction", returns="ValidatedPatch", retryable=(AgentOutage,))


def commit_gate(world: dict) -> Block:
    """The git gate, attempt-first. No authority pre-check anywhere:

    - lookup-first by commit trailers (kind-1: already done → reuse);
    - trailer collision (same operation, different digest) → fault;
    - exact CAS advance: a moved branch rejects — kind-2, classified
      as "preconditions changed", NOT an error;
    - success → provisional head for the control layer to verify.
    """

    def advance(patch: dict) -> tuple[str, dict]:
        head = world["branch"]["head"]
        trailers = world["branch"].get("trailers", {})
        if trailers.get("operation") == patch["operation"]:
            if trailers.get("digest") != patch["payload_digest"]:
                return ("fault", {"kind": "trailer_collision", "operation": patch["operation"]})
            return ("committed", {"provisional_head": head, "reused": True})
        if head != patch["expected_head"]:  # the provider CAS, simulated exactly
            return ("moved", {"expected": patch["expected_head"], "actual": head})
        new_head = f"commit-of-{patch['operation']}"
        world["branch"] = {
            "head": new_head,
            "trailers": {"operation": patch["operation"], "digest": patch["payload_digest"]},
        }
        return ("committed", {"provisional_head": new_head, "reused": False})

    return classify(
        "commit_gate",
        advance,
        accepts="ValidatedPatch",
        outcomes={"committed": "ProvisionalHead", "moved": "BranchMoved", "fault": "NonrecoverableFault"},
    )


def mutation_subnet(world: dict) -> Block:
    """Shape M, attempt-first: three steps, zero context places, no
    fence transition. `moved` is the discarded exit — the control
    layer waits for the webhook instead of retrying here."""
    interior = rail_then(prepare_change(), agent_patch(world))
    return then(interior, commit_gate(world), on="out")


# -- the comment gate, attempt-first ------------------------------------------------------


def publish_comment(world: dict) -> Block:
    """The comment gate with NO pre-fence. GitHub cannot reject a
    stale comment, so there is no 'stale' outcome here — a comment
    for an old head lands, identifiable forever by the head baked
    into its marker (supersession handles it later)."""

    def post(request: dict) -> tuple[str, dict]:
        marker = ["finding", request["operation"], request["head"]]
        for comment in world["comments"]:
            if comment["marker"] == marker:
                return ("acknowledged", {"comment_id": comment["id"], "reused": True})
        comment = {
            "id": len(world["comments"]) + 1,
            "marker": marker,
            "outdated": request["head"] != world["branch"]["head"],  # GitHub UI behavior, simulated
        }
        world["comments"].append(comment)
        return ("acknowledged", {"comment_id": comment["id"], "reused": False})

    return classify(
        "publish_comment",
        post,
        accepts="FindingPublicationRequest",
        outcomes={"acknowledged": "FindingPublicationResult"},
    )


def fresh_world(head: str = "h1") -> dict:
    return {"agent_runs": 0, "branch": {"head": head}, "comments": []}
