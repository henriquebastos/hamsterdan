from typing import Any

import pytest
from pydantic import ValidationError

from hamsterdan.contracts.readiness import (
    ActionsObservation,
    ActionsState,
    Authority,
    ChangeResult,
    DashboardPublicationRequest,
    HumanState,
    MutationState,
    PublicationState,
    ReadinessSnapshot,
    RepairResult,
    ReviewState,
    project_readiness,
)
from hamsterdan.host.payloads import PydanticPayloadConverter


def test_converter_round_trips_strict_json_workflow_model() -> None:
    converter = PydanticPayloadConverter()
    value = ActionsObservation(epoch=1, head="head", run_id="run", attempt=1, conclusion="success")

    encoded = converter.encode(value, ActionsObservation)

    assert encoded == value.dump()
    assert converter.decode(encoded, ActionsObservation) == value


@pytest.mark.parametrize(
    "payload",
    [
        {
            "repository_id": "repo",
            "pr_number": "7",
            "epoch": 1,
            "head": "h",
            "base_head": "b",
            "strict_base": True,
            "base_current": True,
        },
        {
            "repository_id": "repo",
            "pr_number": 7,
            "epoch": 1,
            "head": "h",
            "base_head": "b",
            "strict_base": True,
            "base_current": True,
            "unknown": True,
        },
    ],
)
def test_converter_rejects_coercion_and_extra_fields(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PydanticPayloadConverter().decode(payload, Authority)


def test_closed_workflow_vocabulary_rejects_unknown_actions_state() -> None:
    with pytest.raises(ValidationError):
        ActionsState(actions="provider-private")


def test_converter_rejects_a_different_nominal_result_contract() -> None:
    repair = RepairResult(epoch=1, head="head", ok=True)

    assert not isinstance(repair, ChangeResult)
    with pytest.raises(TypeError, match="must be ChangeResult"):
        PydanticPayloadConverter().encode(repair, ChangeResult)


def test_readiness_state_tokens_partition_snapshot_fields() -> None:
    token_types = (Authority, ActionsState, ReviewState, HumanState, MutationState, PublicationState)
    field_sets = [set(value_type.__dataclass_fields__) for value_type in token_types]

    for index, fields in enumerate(field_sets):
        assert not fields.intersection(*field_sets[index + 1 :]) if field_sets[index + 1 :] else True
    assert all(field_sets[0].isdisjoint(fields) for fields in field_sets[1:])
    assert set().union(*field_sets, {"dashboard_current", "wait"}) == set(ReadinessSnapshot.__dataclass_fields__)


@pytest.mark.parametrize(
    "tokens",
    [
        (
            Authority("repo", 7, 1, "head", "base", True, True),
            ActionsState(),
            ReviewState(),
            HumanState(),
            MutationState(),
            PublicationState(),
        ),
        (
            Authority("repo", 7, 3, "head-3", "base-2", True, False, "policy", ["test"], 2),
            ActionsState(actions="green", run_id="run", attempt=2),
            ReviewState(review="clear", findings=[{"id": "f1", "blocking": False}]),
            HumanState(human_requested=True, human_approved=True, mergeable=True, author="octocat"),
            MutationState(),
            PublicationState(findings_published=True),
        ),
    ],
)
def test_concern_tokens_project_to_derived_snapshots(tokens: tuple) -> None:
    projected = project_readiness(*tokens)

    expected = {key: value for token in tokens for key, value in token.dump().items()} | {
        "dashboard_current": projected.dashboard_current,
        "wait": projected.wait,
    }
    assert projected.dump() == expected


def test_split_tokens_are_strict_and_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ActionsState(attempt="1")
    with pytest.raises(ValidationError):
        HumanState(unknown=True)


def test_converter_round_trips_readiness_snapshot() -> None:
    converter = PydanticPayloadConverter()
    snapshot = project_readiness(
        Authority("repo", 7, 1, "head", "base", True, True),
        ActionsState(),
        ReviewState(),
        HumanState(),
        MutationState(),
        PublicationState(),
    )

    encoded = converter.encode(snapshot, ReadinessSnapshot)

    assert converter.decode(encoded, ReadinessSnapshot) == snapshot


def test_converter_round_trips_immutable_dashboard_request() -> None:
    snapshot = project_readiness(
        Authority("repo", 7, 1, "head", "base", True, True),
        ActionsState(),
        ReviewState(),
        HumanState(),
        MutationState(),
        PublicationState(),
    )
    request = DashboardPublicationRequest(1, "head", "dashboard:1", "base", "policy", snapshot)
    converter = PydanticPayloadConverter()

    assert (
        converter.decode(converter.encode(request, DashboardPublicationRequest), DashboardPublicationRequest) == request
    )
