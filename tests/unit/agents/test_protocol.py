"""Provider-neutral agent request and result contract tests."""

import pytest

from hamsterdan.agents import AgentProtocolError, CodingRequest, ConversationRequest, ReviewRequest
from hamsterdan.agents.protocol import _validate_result


def review_request() -> ReviewRequest:
    return ReviewRequest(
        "owner/repo",
        3,
        2,
        "a" * 40,
        "b" * 40,
        "diff.patch",
        {"required_checks": ["unit"], "digest": "policy"},
        ["correctness", "tests"],
    )


def result_for(request: object, **extra: object) -> dict[str, object]:
    result = {name: getattr(request, name) for name in ("repository", "pull_request", "epoch", "head", "base")}
    result.update(extra)
    return result


def finding(*, related_locations: list[dict[str, object]] | None = None, identity: str = "F1") -> dict[str, object]:
    return {
        "id": identity,
        "path": "src/one.py",
        "line": 4,
        "related_locations": related_locations or [],
        "title": "Keep both guards aligned",
        "body": "These guards enforce one invariant but currently disagree.",
        "severity": "high",
        "confidence": 0.99,
        "evidence": "The primary path allows the state rejected by the related path.",
        "blocking": True,
        "suggestion": "if state.is_ready:",
    }


def test_review_accepts_non_contiguous_related_locations() -> None:
    request = review_request()
    value = finding(related_locations=[{"path": "src/two.py", "line": 19}])

    result = _validate_result(
        "review",
        result_for(
            request,
            status="blocking",
            findings=[value],
            lineage=[{"finding_id": "F1", "state": "new", "supersedes": None}],
        ),
        request,
    )

    assert result.findings == [value]


@pytest.mark.parametrize(
    "related",
    [
        [{"path": "src/one.py", "line": 4}],
        [{"path": "../escape.py", "line": 2}],
        [{"path": "src/two.py", "line": 0}],
    ],
)
def test_review_rejects_unsafe_or_duplicate_related_locations(related: list[dict[str, object]]) -> None:
    request = review_request()
    with pytest.raises(AgentProtocolError, match="related location"):
        _validate_result(
            "review",
            result_for(
                request,
                status="blocking",
                findings=[finding(related_locations=related)],
                lineage=[{"finding_id": "F1", "state": "new", "supersedes": None}],
            ),
            request,
        )


def test_review_rejects_marker_unsafe_finding_identity() -> None:
    request = review_request()
    identity = "F1 -->\n<!-- hamsterdan:dashboard -->"
    with pytest.raises(AgentProtocolError, match="finding id"):
        _validate_result(
            "review",
            result_for(
                request,
                status="blocking",
                findings=[finding(identity=identity)],
                lineage=[{"finding_id": identity, "state": "new", "supersedes": None}],
            ),
            request,
        )


def conversation_request() -> ConversationRequest:
    return ConversationRequest(
        "owner/repo",
        1,
        0,
        "a" * 40,
        "b" * 40,
        {},
        {},
        {},
        [],
        [],
        [{"type": "apply", "mutation": True, "arguments": ["id"]}],
    )


def test_conversation_accepts_one_declared_explicit_mutation() -> None:
    request = conversation_request()
    intent = {
        "type": "apply",
        "arguments": {"id": "F1"},
        "mutation": True,
        "explicit": True,
        "confidence": 1,
    }

    result = _validate_result("conversation", result_for(request, intents=[intent]), request)

    assert result.intents == [intent]


def test_conversation_rejects_undeclared_intent() -> None:
    request = conversation_request()
    intent = {
        "type": "invented",
        "arguments": {"id": "F1"},
        "mutation": True,
        "explicit": True,
        "confidence": 1,
    }

    with pytest.raises(AgentProtocolError, match="unauthorized"):
        _validate_result("conversation", result_for(request, intents=[intent]), request)


@pytest.mark.parametrize("intents", [[], [{}, {}]])
def test_conversation_requires_exactly_one_raw_intent(intents: list[dict[str, object]]) -> None:
    request = conversation_request()
    with pytest.raises(AgentProtocolError, match="exactly one intent"):
        _validate_result("conversation", result_for(request, intents=intents), request)


@pytest.mark.parametrize(
    ("name", "mutation", "arguments", "value"),
    [
        ("change", True, ["request"], ""),
        ("change", True, ["request"], "   "),
        ("reply", False, ["message"], []),
        ("reassign", False, ["assignee"], {"login": "octocat"}),
        ("dismiss", False, ["findings"], "F1"),
        ("dismiss", False, ["findings"], [""]),
    ],
)
def test_conversation_rejects_malformed_intent_argument_values(
    name: str, mutation: bool, arguments: list[str], value: object
) -> None:
    request = ConversationRequest(
        "owner/repo",
        1,
        0,
        "a" * 40,
        "b" * 40,
        {},
        {},
        {},
        [],
        [],
        [{"type": name, "mutation": mutation, "arguments": arguments}],
    )
    intent = {
        "type": name,
        "arguments": {arguments[0]: value},
        "mutation": mutation,
        "explicit": mutation,
        "confidence": 1,
    }

    with pytest.raises(AgentProtocolError, match="invalid intent"):
        _validate_result("conversation", result_for(request, intents=[intent]), request)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"epoch": True}, "correlation mismatch"),
        ({"findings": "bad"}, "invalid findings"),
        ({"findings": [{"id": "incomplete"}]}, "fields differ"),
    ],
)
def test_review_rejects_malformed_shape_or_correlation(change: dict[str, object], message: str) -> None:
    request = review_request()
    data = result_for(request, status="clear", findings=[], lineage=[])
    data.update(change)

    with pytest.raises(AgentProtocolError, match=message):
        _validate_result("review", data, request)


def test_repair_change_requires_confirmed_reproduction() -> None:
    request = CodingRequest("repair", "owner/repo", 1, 0, "a" * 40, "b" * 40, "repair/test")
    data = result_for(
        request,
        kind="repair",
        ref="repair/test",
        status="changed",
        reproduction_status="not_reproduced",
        diff="x",
        changed_files=["x.py"],
        validation_evidence=[{"status": "passed"}],
        proposed_commit_message="Repair bug",
    )

    with pytest.raises(AgentProtocolError, match="confirmed reproduction"):
        _validate_result("coding", data, request, ["x.py"])
