from typing import Any

import pytest
from pydantic import ValidationError

from hamsterdan.contracts.readiness import ActionsObservation, Control
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
        PydanticPayloadConverter().decode(payload, Control)


def test_closed_workflow_vocabulary_rejects_unknown_actions_state() -> None:
    with pytest.raises(ValidationError):
        Control(
            repository_id="repo",
            pr_number=7,
            epoch=1,
            head="head",
            base_head="base",
            strict_base=True,
            base_current=True,
            actions="provider-private",
        )
