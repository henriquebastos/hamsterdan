# Copyright (c) 2026 Henrique Bastos

"""Values shared across the new host/readiness workflow boundary."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


PositiveIdentifier = Annotated[int, Field(strict=True, gt=0)]


class PullRequestSubject(BaseModel):
    """Immutable identity of one GitHub installation's pull request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    installation_id: PositiveIdentifier
    repository_id: PositiveIdentifier
    pull_request_number: PositiveIdentifier


class AwaitingObservation(BaseModel):
    """Detached posture of a lifecycle that needs its first observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: PullRequestSubject
    posture: Literal["awaiting_observation"] = "awaiting_observation"
