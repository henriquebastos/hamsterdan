# Copyright (c) 2026 Henrique Bastos

"""Values shared across the replacement host/readiness workflow boundary."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


MAX_DURABLE_IDENTIFIER = 9_223_372_036_854_775_807
PositiveIdentifier = Annotated[int, Field(strict=True, gt=0, le=MAX_DURABLE_IDENTIFIER)]


class PullRequestIdentity(BaseModel):
    """Immutable identity of one GitHub installation's pull request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    installation_id: PositiveIdentifier
    repository_id: PositiveIdentifier
    pull_request_number: PositiveIdentifier


class AwaitingObservation(BaseModel):
    """Detached stage of a PR workflow waiting for an observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pr_identity: PullRequestIdentity
    stage: Literal["awaiting_observation"] = "awaiting_observation"
