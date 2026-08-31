# Copyright (c) 2026 Henrique Bastos

"""Project provider snapshots into canonical source-neutral workflow evidence."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import TYPE_CHECKING

from hamsterdan2.readiness.ingress_values import (
    MAX_CANONICAL_OBSERVATION_BYTES,
    MAX_MANIFEST_BYTES,
    AcquisitionIdentity,
    AdmissionDecision,
    AdmissionGrant,
    AdmissionGrantId,
    CanonicalObservation,
    DecisionReason,
    Disposition,
    IngressEntry,
    IngressManifest,
    ManifestId,
    ObservationKey,
)
from hamsterdan2.workflow.observations import BranchRef, BranchTip, CommitSha, HeadObservation
from hamsterdan2.workflow.values import PullRequestSubject


if TYPE_CHECKING:
    from pydantic import BaseModel

    from hamsterdan2.github_app.models import PullRequestSnapshot


def sha256_digest(content: bytes) -> str:
    return sha256(content).hexdigest()


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
        subject=PullRequestSubject(
            installation_id=snapshot.subject.installation_id,
            repository_id=snapshot.subject.repository_id,
            pull_request_number=snapshot.subject.pull_request_number,
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


def observation_key_for(canonical: bytes) -> ObservationKey:
    return ObservationKey(f"obs:v1:sha256:{sha256_digest(canonical)}")


def observation_entry(observation: HeadObservation) -> IngressEntry:
    canonical = CanonicalObservation(canonical_json(observation, maximum_bytes=MAX_CANONICAL_OBSERVATION_BYTES))
    return IngressEntry(
        order=0,
        observation_key=observation_key_for(canonical),
        canonical_bytes=canonical,
        observation=observation,
    )


def manifest_id_for(acquisition: AcquisitionIdentity) -> ManifestId:
    identity_bytes = canonical_json(acquisition, maximum_bytes=512)
    return ManifestId(f"manifest:v1:sha256:{sha256_digest(identity_bytes)}")


def grant_for(manifest: IngressManifest) -> AdmissionGrant:
    manifest_bytes = canonical_json(manifest, maximum_bytes=MAX_MANIFEST_BYTES)
    manifest_digest = sha256_digest(manifest_bytes)
    return AdmissionGrant(
        grant_id=AdmissionGrantId(f"grant:v1:sha256:{manifest_digest}"),
        manifest_id=manifest.manifest_id,
        manifest_digest=manifest_digest,
    )


def decision(
    entry: IngressEntry | None,
    *,
    disposition: Disposition,
    reason: DecisionReason,
    fatal: bool,
    refresh_required: bool,
) -> AdmissionDecision:
    return AdmissionDecision(
        entry_order=None if entry is None else entry.order,
        observation_key=None if entry is None else entry.observation_key,
        disposition=disposition,
        reason=reason,
        fatal=fatal,
        refresh_required=refresh_required,
    )


def classify_matching_key(entry: IngressEntry, matching: tuple[IngressEntry, ...]) -> AdmissionDecision:
    if any(prior.canonical_bytes != entry.canonical_bytes for prior in matching):
        return decision(
            entry,
            disposition="semantic_collision",
            reason="key_bytes_mismatch",
            fatal=True,
            refresh_required=False,
        )
    return decision(
        entry,
        disposition="corroborating",
        reason="same_semantics",
        fatal=False,
        refresh_required=False,
    )


def classify_changed_head(entry: IngressEntry, prior_entries: tuple[IngressEntry, ...]) -> AdmissionDecision:
    same_tips = any(
        prior.observation.head == entry.observation.head and prior.observation.base == entry.observation.base
        for prior in prior_entries
    )
    if same_tips:
        return decision(
            entry,
            disposition="conflicting",
            reason="contradictory_head",
            fatal=True,
            refresh_required=False,
        )
    return decision(
        entry,
        disposition="incomparable",
        reason="unordered_head",
        fatal=False,
        refresh_required=True,
    )


def classify_head(entry: IngressEntry, prior_entries: tuple[IngressEntry, ...]) -> AdmissionDecision:
    matching = tuple(prior for prior in prior_entries if prior.observation_key == entry.observation_key)
    if matching:
        return classify_matching_key(entry, matching)
    same_subject = tuple(prior for prior in prior_entries if prior.observation.subject == entry.observation.subject)
    if same_subject:
        return classify_changed_head(entry, same_subject)
    return decision(
        entry,
        disposition="novel",
        reason="first_observation",
        fatal=False,
        refresh_required=False,
    )
