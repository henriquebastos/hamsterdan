# Copyright (c) 2026 Henrique Bastos

"""Project provider snapshots into canonical source-neutral observations."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import TYPE_CHECKING

from hamsterdan2.readiness.intake_values import (
    MAX_CANONICAL_OBSERVATION_BYTES,
    CanonicalObservation,
    ObservationKey,
)
from hamsterdan2.workflow.observations import BranchRef, BranchTip, CommitSha, HeadObservation
from hamsterdan2.workflow.values import PullRequestIdentity


if TYPE_CHECKING:
    from pydantic import BaseModel

    from hamsterdan2.github_app.models import PullRequestSnapshot


def canonical_json(value: BaseModel, *, maximum_bytes: int) -> bytes:
    encoded = json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    if not 1 <= len(encoded) <= maximum_bytes:
        raise ValueError(f"canonical value must contain 1-{maximum_bytes} bytes")
    return encoded


def project_head(snapshot: PullRequestSnapshot) -> HeadObservation:
    return HeadObservation(
        pr_identity=PullRequestIdentity(
            installation_id=snapshot.pr_identity.installation_id,
            repository_id=snapshot.pr_identity.repository_id,
            pull_request_number=snapshot.pr_identity.pull_request_number,
        ),
        head=BranchTip(
            repository_id=snapshot.head.repository_id,
            ref=BranchRef(snapshot.head.ref),
            sha=CommitSha(snapshot.head.sha),
        ),
        base=BranchTip(
            repository_id=snapshot.base.repository_id,
            ref=BranchRef(snapshot.base.ref),
            sha=CommitSha(snapshot.base.sha),
        ),
        lifecycle_state=snapshot.state,
        draft=snapshot.draft,
        merged=snapshot.merged,
        mergeable=snapshot.mergeable,
    )


def canonical_observation_for(observation: HeadObservation) -> CanonicalObservation:
    return CanonicalObservation(
        canonical_json(
            observation,
            maximum_bytes=MAX_CANONICAL_OBSERVATION_BYTES,
        )
    )


def observation_key_for(canonical: bytes) -> ObservationKey:
    return ObservationKey(f"obs:v1:sha256:{sha256(canonical).hexdigest()}")
