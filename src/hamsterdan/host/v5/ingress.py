"""Durable V5 ingress manifests and host-owned authority grants."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import TypeAdapter, ValidationError

from hamsterdan.contracts.readiness import WorkflowModel
from hamsterdan.contracts.readiness_v5 import (
    CloseSeen,
    CommentSeen,
    DraftSeen,
    HeadSeen,
    HumanSeen,
    ReadySeen,
    RunSeen,
)
from hamsterdan.github_app.models import (
    ActionsEvidence,
    ActionsRunSnapshot,
    HumanReviewSnapshot,
    PullRequestSnapshot,
    RepositoryPolicy,
)
from hamsterdan.host.v5.claim import CurrentClaim

_DOOR_ORDER = {
    "on_head": 0,
    "on_draft": 1,
    "on_ready": 1,
    "on_close": 1,
    "on_human": 2,
    "on_runs": 3,
    "on_comment": 4,
}
_LIFECYCLE_DOORS = frozenset({"on_draft", "on_ready", "on_close"})
_DOOR_TYPES = {
    "on_head": HeadSeen,
    "on_draft": DraftSeen,
    "on_ready": ReadySeen,
    "on_close": CloseSeen,
    "on_human": HumanSeen,
    "on_runs": RunSeen,
    "on_comment": CommentSeen,
}
_DOOR_COLORS = {door: value.__name__ for door, value in _DOOR_TYPES.items()}
_SCHEMA_VERSION = 1
_TOPOLOGY = "v5"
_SUBJECT = re.compile(r"github:([1-9][0-9]*):([1-9][0-9]*):pr:([1-9][0-9]*)\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class ProjectedEntry:
    """One canonical V5 door value before a custody source binds its identity."""

    source: str
    color: str
    payload: dict[str, Any]

    @classmethod
    def from_value(cls, source: str, value: WorkflowModel) -> ProjectedEntry:
        return cls(source, type(value).__name__, value.dump())

    def bind(self, source_id: str) -> IngressEntry:
        return IngressEntry(self.source, self.color, self.payload, f"{source_id}:{self.source}")

    def dump(self) -> dict[str, object]:
        return {"source": self.source, "color": self.color, "payload": self.payload}


@dataclass(frozen=True)
class IngressEntry:
    """One exact Petrus identified delivery frozen by webhook custody."""

    source: str
    color: str
    payload: dict[str, Any]
    identity: str

    @classmethod
    def from_value(cls, source: str, value: WorkflowModel, identity: str) -> IngressEntry:
        return cls(source, type(value).__name__, value.dump(), identity)

    @classmethod
    def load(cls, value: object) -> IngressEntry:
        if not isinstance(value, dict) or set(value) != {"source", "color", "payload", "identity"}:
            raise RuntimeError("V5 ingress manifest entry is malformed")
        raw = cast(dict[str, Any], value)
        source, color, payload, identity = (
            raw["source"],
            raw["color"],
            raw["payload"],
            raw["identity"],
        )
        if (
            not isinstance(source, str)
            or source not in _DOOR_ORDER
            or not isinstance(color, str)
            or not color
            or not isinstance(payload, dict)
            or not isinstance(identity, str)
            or not identity
        ):
            raise RuntimeError("V5 ingress manifest entry is malformed")
        return cls(source, color, payload, identity)

    def dump(self) -> dict[str, object]:
        return {
            "source": self.source,
            "color": self.color,
            "payload": self.payload,
            "identity": self.identity,
        }


@dataclass(frozen=True)
class IngressManifest:
    source_id: str
    subject: str
    revision: int
    entries: tuple[IngressEntry, ...]


@dataclass(frozen=True)
class _StoredGrant:
    claim: CurrentClaim
    revision: int
    source_kind: str | None
    source_id: str | None


class IngressAuthority(Protocol):
    def pull_request(self) -> PullRequestSnapshot: ...

    def policy(self, base_ref: str) -> RepositoryPolicy: ...

    def human_review(self) -> HumanReviewSnapshot: ...

    def workflow_runs(self, workflow: str, head: str) -> tuple[ActionsRunSnapshot, ...]: ...

    def actions_evidence(self, run: ActionsRunSnapshot, required_checks: tuple[str, ...]) -> ActionsEvidence: ...


@dataclass(frozen=True)
class V5IngressNormalizer:
    """Freeze current provider truth into the V5 webhook doors."""

    authority: IngressAuthority
    workflow_path: str

    def project(
        self,
        delivery_id: str,
        *,
        event: str | None = None,
        action: str | None = None,
        comment: CommentSeen | None = None,
    ) -> tuple[IngressEntry, ...]:
        source_id = f"github-delivery:{delivery_id}"
        return tuple(entry.bind(source_id) for entry in self._project(event=event, action=action, comment=comment))

    def project_reconciliation(self) -> tuple[ProjectedEntry, ...]:
        return self._project()

    def _project(
        self,
        *,
        event: str | None = None,
        action: str | None = None,
        comment: CommentSeen | None = None,
    ) -> tuple[ProjectedEntry, ...]:
        def entry(source: str, value: WorkflowModel) -> ProjectedEntry:
            return ProjectedEntry.from_value(source, value)

        pull = self.authority.pull_request()
        closed_edge = event == "pull_request" and action == "closed"
        if closed_edge or pull.closed or pull.merged:
            reason = "merged" if pull.merged else "closed"
            return (entry("on_close", CloseSeen(reason=reason)),)

        policy = self.authority.policy(pull.base_ref)
        lifecycle = "on_draft" if pull.draft else "on_ready"
        if event == "pull_request" and action == "converted_to_draft":
            lifecycle = "on_draft"
        elif event == "pull_request" and action == "ready_for_review":
            lifecycle = "on_ready"
        values: list[ProjectedEntry] = [
            entry(
                "on_head",
                HeadSeen(
                    head=pull.head,
                    base=pull.base,
                    mergeable=pull.mergeable is True,
                    policy=policy.digest,
                ),
            ),
            entry("on_draft", DraftSeen()) if lifecycle == "on_draft" else entry("on_ready", ReadySeen()),
        ]
        review = self.authority.human_review()
        approvals = {name.casefold() for name in review.approvals if name.casefold() != pull.author.casefold()}
        unresolved = review.unresolved_threads
        if unresolved is None:
            unresolved = 1 if policy.conversation_resolution else 0
        values.append(
            entry(
                "on_human",
                HumanSeen(
                    approval=len(approvals) >= policy.required_approvals and not review.requested_reviewers,
                    changes_requested=bool(review.changes_requested),
                    unresolved=unresolved,
                ),
            )
        )
        runs = self.authority.workflow_runs(self.workflow_path, pull.head)
        if runs:
            newest = max(runs, key=lambda run: (run.id, run.attempt))
            evidence = self.authority.actions_evidence(newest, policy.required_checks)
            fingerprint = ""
            if evidence.conclusion == "failure":
                fingerprint = sha256(
                    json.dumps(
                        evidence.failed_required_jobs,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
            values.append(
                entry(
                    "on_runs",
                    RunSeen(
                        head=evidence.run.head,
                        run_id=evidence.run.id,
                        attempt=evidence.run.attempt,
                        conclusion=evidence.conclusion,
                        fingerprint=fingerprint,
                    ),
                )
            )
        if comment is not None:
            values.append(entry("on_comment", comment))
        return tuple(values)


class V5IngressStore:
    """Co-located replay metadata for the topology-neutral webhook inbox.

    A manifest and its resulting host authority grant commit in one
    SQLite transaction before any Petrus delivery. The manifest freezes
    provider normalization across crash/replay; Petrus History remains
    canonical for which frozen entries the workflow accepted.
    """

    def __init__(self, path: Path) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        with self._db:
            self._db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS v5_ingress_manifests (
                  delivery_id TEXT PRIMARY KEY,
                  subject TEXT NOT NULL,
                  revision INTEGER NOT NULL,
                  topology TEXT NOT NULL,
                  schema_version INTEGER NOT NULL,
                  entries TEXT NOT NULL,
                  UNIQUE(subject, revision)
                );
                CREATE TABLE IF NOT EXISTS v5_authority_grants (
                  subject TEXT PRIMARY KEY,
                  phase TEXT NOT NULL,
                  incarnation INTEGER NOT NULL,
                  head TEXT NOT NULL,
                  base TEXT NOT NULL,
                  policy TEXT NOT NULL,
                  revision INTEGER NOT NULL,
                  source_kind TEXT NOT NULL,
                  source_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v5_reconciliation_manifests (
                  source_id TEXT PRIMARY KEY,
                  subject TEXT NOT NULL,
                  revision INTEGER NOT NULL,
                  digest TEXT NOT NULL,
                  topology TEXT NOT NULL,
                  schema_version INTEGER NOT NULL,
                  entries TEXT NOT NULL,
                  UNIQUE(subject, revision)
                );
                """
            )
            grant_columns = {row[1] for row in self._db.execute("PRAGMA table_info(v5_authority_grants)").fetchall()}
            manifest_columns = {
                row[1] for row in self._db.execute("PRAGMA table_info(v5_ingress_manifests)").fetchall()
            }
            has_kind, has_id = "source_kind" in grant_columns, "source_id" in grant_columns
            legacy_pointer = not has_kind and not has_id
            legacy_manifest = "revision" not in manifest_columns
            if has_kind != has_id or legacy_pointer != legacy_manifest:
                raise RuntimeError("V5 source pointer migration is partial")
            if legacy_pointer:
                if "source_delivery" not in grant_columns:
                    raise RuntimeError("V5 source pointer migration is partial")
                self._db.execute("ALTER TABLE v5_ingress_manifests ADD COLUMN revision INTEGER")
                self._db.execute(
                    "UPDATE v5_ingress_manifests AS current SET revision=("
                    "SELECT COUNT(*) FROM v5_ingress_manifests AS prior"
                    " WHERE prior.subject=current.subject AND prior.rowid<=current.rowid)"
                )
                malformed = self._db.execute(
                    "SELECT 1 FROM v5_authority_grants AS grant_row"
                    " LEFT JOIN v5_ingress_manifests AS manifest"
                    " ON manifest.delivery_id=grant_row.source_delivery"
                    " AND manifest.subject=grant_row.subject"
                    " AND manifest.revision=grant_row.revision"
                    " WHERE manifest.delivery_id IS NULL"
                    " OR grant_row.revision!=(SELECT COUNT(*) FROM v5_ingress_manifests"
                    " WHERE subject=grant_row.subject) LIMIT 1"
                ).fetchone()
                orphan = self._db.execute(
                    "SELECT 1 FROM v5_ingress_manifests AS manifest"
                    " LEFT JOIN v5_authority_grants AS grant_row ON grant_row.subject=manifest.subject"
                    " WHERE grant_row.subject IS NULL LIMIT 1"
                ).fetchone()
                if malformed is not None or orphan is not None:
                    raise RuntimeError("V5 legacy authority lineage is malformed")
                self._db.execute("ALTER TABLE v5_authority_grants ADD COLUMN source_kind TEXT")
                self._db.execute("ALTER TABLE v5_authority_grants ADD COLUMN source_id TEXT")
                self._db.execute(
                    "UPDATE v5_authority_grants SET source_kind='github-delivery',source_id=source_delivery"
                )
            self._db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS v5_ingress_manifest_subject_revision"
                " ON v5_ingress_manifests(subject,revision)"
            )
            self._legacy_source_delivery = "source_delivery" in grant_columns

    def stage(
        self,
        delivery_id: str,
        subject: str,
        entries: tuple[IngressEntry, ...],
    ) -> IngressManifest:
        canonical = self._validate(delivery_id, subject, entries)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT subject,revision,topology,schema_version,entries"
                    " FROM v5_ingress_manifests WHERE delivery_id=?",
                    (canonical,),
                ).fetchone()
                if row is not None:
                    manifest = self._load(canonical, row)
                    if manifest.subject != subject:
                        raise RuntimeError("V5 ingress delivery belongs to a different subject")
                    self._claim_row(subject, required=True)
                    self._db.commit()
                    return manifest
                current = self._claim_row(subject)
                revision = current.revision + 1
                encoded = json.dumps(
                    [entry.dump() for entry in entries],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                self._db.execute(
                    "INSERT INTO v5_ingress_manifests"
                    "(delivery_id,subject,revision,topology,schema_version,entries) VALUES(?,?,?,?,?,?)",
                    (canonical, subject, revision, _TOPOLOGY, _SCHEMA_VERSION, encoded),
                )
                claim = self._reduce(current.claim, entries)
                self._write_claim(subject, claim, revision, "github-delivery", canonical)
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise
        return IngressManifest(canonical, subject, revision, entries)

    def latest_reconciliation(self, subject: str) -> IngressManifest | None:
        self._validate_subject(subject)
        with self._lock:
            self._db.execute("BEGIN")
            try:
                current = self._claim_row(subject)
                manifest = (
                    None
                    if current.source_kind != "host-reconcile" or current.source_id is None
                    else self._reconciliation_manifest(current.source_id, subject)
                )
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise
        return manifest

    def stage_reconciliation(
        self,
        subject: str,
        projected: tuple[ProjectedEntry, ...],
    ) -> IngressManifest | None:
        self._validate_subject(subject)
        digest = self._projection_digest(projected)
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if self._pending_custody_row(subject) is not None:
                    self._db.rollback()
                    return None
                current = self._claim_row(subject)
                if current.source_kind == "host-reconcile" and current.source_id is not None:
                    latest = self._reconciliation_manifest(current.source_id, subject)
                    row = self._db.execute(
                        "SELECT digest FROM v5_reconciliation_manifests WHERE source_id=?",
                        (current.source_id,),
                    ).fetchone()
                    if row == (digest,):
                        self._db.commit()
                        return latest
                revision = current.revision + 1
                source_id = f"host-reconcile:{subject}:{revision}:{digest}"
                entries = tuple(entry.bind(source_id) for entry in projected)
                self._validate_reconciliation(source_id, subject, revision, digest, entries)
                encoded = json.dumps(
                    [entry.dump() for entry in entries],
                    sort_keys=True,
                    separators=(",", ":"),
                )
                self._db.execute(
                    "INSERT INTO v5_reconciliation_manifests"
                    "(source_id,subject,revision,digest,topology,schema_version,entries) VALUES(?,?,?,?,?,?,?)",
                    (source_id, subject, revision, digest, _TOPOLOGY, _SCHEMA_VERSION, encoded),
                )
                claim = self._reduce(current.claim, entries)
                self._write_claim(subject, claim, revision, "host-reconcile", source_id)
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise
        return IngressManifest(source_id, subject, revision, entries)

    def manifest(self, delivery_id: str, subject: str) -> IngressManifest | None:
        try:
            canonical = str(uuid.UUID(delivery_id))
        except AttributeError, ValueError:
            raise ValueError("V5 ingress delivery identity is malformed") from None
        if canonical != delivery_id:
            raise ValueError("V5 ingress delivery identity is malformed")
        with self._lock:
            self._db.execute("BEGIN")
            try:
                row = self._db.execute(
                    "SELECT subject,revision,topology,schema_version,entries"
                    " FROM v5_ingress_manifests WHERE delivery_id=?",
                    (canonical,),
                ).fetchone()
                if row is not None:
                    manifest = self._load(canonical, row)
                    if manifest.subject != subject:
                        raise RuntimeError("V5 ingress delivery belongs to a different subject")
                    self._claim_row(subject, required=True)
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise
        if row is None:
            return None
        return manifest

    def claim(self, subject: str) -> CurrentClaim:
        with self._lock:
            return self._claim_row(subject, required=True).claim

    def has_pending_custody(self, subject: str) -> bool:
        self._validate_subject(subject)
        with self._lock:
            return self._pending_custody_row(subject) is not None

    def has_unstaged_custody(self, subject: str) -> bool:
        """Whether this PR has inbox authority not yet represented by a manifest."""
        match = _SUBJECT.fullmatch(subject)
        if match is None:
            raise ValueError("V5 ingress subject is malformed")
        with self._lock:
            inbox = self._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbox'").fetchone()
            if inbox is None:
                return False
            row = self._db.execute(
                "SELECT 1 FROM inbox i LEFT JOIN v5_ingress_manifests m"
                " ON m.delivery_id=i.delivery_id AND m.subject=?"
                " WHERE i.status='pending' AND m.delivery_id IS NULL"
                " AND json_extract(i.observation,'$.installation_id')=?"
                " AND json_extract(i.observation,'$.repository_id')=?"
                " AND json_extract(i.observation,'$.pull_request_number')=? LIMIT 1",
                (subject, *(int(value) for value in match.groups())),
            ).fetchone()
        return row is not None

    def preview(self, subject: str, entries: tuple[IngressEntry, ...]) -> CurrentClaim:
        """Project the grant which staging these exact entries will commit."""
        with self._lock:
            return self._reduce(self._claim_row(subject).claim, entries)

    def _claim_row(self, subject: str, *, required: bool = False) -> _StoredGrant:
        source_delivery_column = ",source_delivery" if self._legacy_source_delivery else ""
        row = self._db.execute(
            "SELECT phase,incarnation,head,base,policy,revision,source_kind,source_id"
            f"{source_delivery_column}"
            " FROM v5_authority_grants WHERE subject=?",
            (subject,),
        ).fetchone()
        if row is None:
            prior_manifest = self._db.execute(
                "SELECT 1 FROM v5_ingress_manifests WHERE subject=?"
                " UNION ALL SELECT 1 FROM v5_reconciliation_manifests WHERE subject=? LIMIT 1",
                (subject, subject),
            ).fetchone()
            if required or prior_manifest is not None:
                raise RuntimeError("V5 authority grant is missing")
            return _StoredGrant(CurrentClaim("running", 0, "", "", ""), 0, None, None)
        phase, incarnation, head, base, policy, revision, source_kind, source_id, *legacy = row
        if (
            not isinstance(phase, str)
            or phase not in {"running", "quiescent", "terminal"}
            or type(incarnation) is not int
            or incarnation < 0
            or not isinstance(head, str)
            or not isinstance(base, str)
            or not isinstance(policy, str)
            or type(revision) is not int
            or revision < 1
            or source_kind not in {"github-delivery", "host-reconcile"}
            or not isinstance(source_id, str)
            or (self._legacy_source_delivery and legacy != [source_id])
        ):
            raise RuntimeError("V5 authority grant is malformed")
        self._validate_lineage(subject, revision, cast(str, source_kind), source_id)
        if source_kind == "github-delivery":
            try:
                canonical_source = str(uuid.UUID(source_id))
            except ValueError:
                raise RuntimeError("V5 authority grant is malformed") from None
            source = self._db.execute(
                "SELECT subject,revision,topology,schema_version,entries FROM v5_ingress_manifests WHERE delivery_id=?",
                (source_id,),
            ).fetchone()
            if source is None:
                raise RuntimeError("V5 authority grant is malformed")
            manifest = self._load(source_id, source)
            if canonical_source != source_id or manifest.subject != subject or manifest.revision != revision:
                raise RuntimeError("V5 authority grant is malformed")
        else:
            manifest = self._reconciliation_manifest(source_id, subject)
            if manifest.source_id != source_id or manifest.revision != revision:
                raise RuntimeError("V5 authority grant is malformed")
        return _StoredGrant(
            CurrentClaim(phase, incarnation, head, base, policy),
            revision,
            cast(str, source_kind),
            source_id,
        )

    def _validate_lineage(self, subject: str, revision: int, source_kind: str, source_id: str) -> None:
        lineage = self._db.execute(
            "SELECT revision,'github-delivery',delivery_id FROM v5_ingress_manifests WHERE subject=?"
            " UNION ALL SELECT revision,'host-reconcile',source_id"
            " FROM v5_reconciliation_manifests WHERE subject=?"
            " ORDER BY revision",
            (subject, subject),
        ).fetchall()
        if len(lineage) != revision:
            raise RuntimeError("V5 authority grant is malformed")
        for expected, item in enumerate(lineage, start=1):
            observed_revision, observed_kind, observed_id = item
            if (
                type(observed_revision) is not int
                or observed_revision != expected
                or observed_kind not in {"github-delivery", "host-reconcile"}
                or not isinstance(observed_id, str)
            ):
                raise RuntimeError("V5 authority grant is malformed")
        if lineage[-1][1:] != (source_kind, source_id):
            raise RuntimeError("V5 authority grant is malformed")

    def _pending_custody_row(self, subject: str) -> tuple[object, ...] | None:
        match = _SUBJECT.fullmatch(subject)
        if match is None:
            raise ValueError("V5 ingress subject is malformed")
        inbox = self._db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inbox'").fetchone()
        if inbox is None:
            return None
        return self._db.execute(
            "SELECT 1 FROM inbox WHERE status='pending'"
            " AND json_extract(observation,'$.installation_id')=?"
            " AND json_extract(observation,'$.repository_id')=?"
            " AND json_extract(observation,'$.pull_request_number')=? LIMIT 1",
            tuple(int(value) for value in match.groups()),
        ).fetchone()

    def _write_claim(
        self,
        subject: str,
        claim: CurrentClaim,
        revision: int,
        source_kind: str,
        source_id: str,
    ) -> None:
        values = (
            subject,
            claim.phase,
            claim.incarnation,
            claim.head,
            claim.base,
            claim.policy,
            revision,
            source_kind,
            source_id,
        )
        if self._legacy_source_delivery:
            self._db.execute(
                "INSERT INTO v5_authority_grants"
                "(subject,phase,incarnation,head,base,policy,revision,source_kind,source_id,source_delivery) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(subject) DO UPDATE SET "
                "phase=excluded.phase,incarnation=excluded.incarnation,head=excluded.head,"
                "base=excluded.base,policy=excluded.policy,revision=excluded.revision,"
                "source_kind=excluded.source_kind,source_id=excluded.source_id,source_delivery=excluded.source_delivery",
                (*values, source_id),
            )
            return
        self._db.execute(
            "INSERT INTO v5_authority_grants"
            "(subject,phase,incarnation,head,base,policy,revision,source_kind,source_id) "
            "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(subject) DO UPDATE SET "
            "phase=excluded.phase,incarnation=excluded.incarnation,head=excluded.head,"
            "base=excluded.base,policy=excluded.policy,revision=excluded.revision,"
            "source_kind=excluded.source_kind,source_id=excluded.source_id",
            values,
        )

    @staticmethod
    def _reduce(claim: CurrentClaim, entries: tuple[IngressEntry, ...]) -> CurrentClaim:
        current = claim
        for entry in entries:
            if entry.source == "on_head":
                try:
                    head, base, policy = (
                        str(entry.payload["head"]),
                        str(entry.payload["base"]),
                        str(entry.payload["policy"]),
                    )
                except KeyError:
                    raise ValueError("V5 head ingress payload is malformed") from None
                if current.phase == "terminal":
                    continue
                if current.phase == "quiescent" or head == current.head:
                    current = CurrentClaim(current.phase, current.incarnation, head, base, policy)
                else:
                    current = CurrentClaim("running", current.incarnation + 1, head, base, policy)
            elif entry.source == "on_draft" and current.phase == "running":
                current = CurrentClaim("quiescent", current.incarnation, current.head, current.base, current.policy)
            elif entry.source == "on_ready" and current.phase == "quiescent":
                current = CurrentClaim("running", current.incarnation + 1, current.head, current.base, current.policy)
            elif entry.source == "on_close":
                current = CurrentClaim("terminal", current.incarnation, current.head, current.base, current.policy)
        return current

    @staticmethod
    def _validate(delivery_id: str, subject: str, entries: tuple[IngressEntry, ...]) -> str:
        try:
            canonical = str(uuid.UUID(delivery_id))
        except AttributeError, ValueError:
            raise ValueError("V5 ingress delivery identity is malformed") from None
        V5IngressStore._validate_subject(subject)
        if canonical != delivery_id:
            raise ValueError("V5 ingress subject is malformed")
        V5IngressStore._validate_values(entries, allow_comment=True)
        if any(entry.identity != f"github-delivery:{canonical}:{entry.source}" for entry in entries):
            raise ValueError("V5 ingress door order or identity is malformed")
        return canonical

    @staticmethod
    def _validate_subject(subject: str) -> None:
        if not isinstance(subject, str) or len(subject.encode()) > 900 or _SUBJECT.fullmatch(subject) is None:
            raise ValueError("V5 ingress subject is malformed")

    @staticmethod
    def _validate_values(
        entries: tuple[ProjectedEntry, ...] | tuple[IngressEntry, ...],
        *,
        allow_comment: bool,
    ) -> None:
        sources = [entry.source for entry in entries]
        order = [_DOOR_ORDER.get(source, -1) for source in sources]
        closed_batches = (["on_close"], ["on_close", "on_comment"]) if allow_comment else (["on_close"],)
        open_tails = ([], ["on_runs"], ["on_comment"], ["on_runs", "on_comment"])
        if not allow_comment:
            open_tails = ([], ["on_runs"])
        complete = sources in closed_batches or (
            len(sources) >= 3
            and sources[:3][0] == "on_head"
            and sources[:3][1] in _LIFECYCLE_DOORS - {"on_close"}
            and sources[:3][2] == "on_human"
            and sources[3:] in open_tails
        )
        if (
            not entries
            or any(item < 0 for item in order)
            or order != sorted(order)
            or len(sources) != len(set(sources))
            or sum(source in _LIFECYCLE_DOORS for source in sources) > 1
            or any(_DOOR_COLORS.get(entry.source) != entry.color for entry in entries)
        ):
            raise ValueError("V5 ingress door order or identity is malformed")
        if not complete:
            raise ValueError("V5 ingress manifest is not a complete batch")
        for entry in entries:
            try:
                value = TypeAdapter(_DOOR_TYPES[entry.source]).validate_json(json.dumps(entry.payload))
            except TypeError, ValueError, ValidationError:
                raise ValueError("V5 ingress door payload is malformed") from None
            if value.dump() != entry.payload:
                raise ValueError("V5 ingress door payload is not canonical")

    @staticmethod
    def _projection_digest(projected: tuple[ProjectedEntry, ...]) -> str:
        if not isinstance(projected, tuple) or any(not isinstance(entry, ProjectedEntry) for entry in projected):
            raise ValueError("V5 reconciliation projection is malformed")
        V5IngressStore._validate_values(projected, allow_comment=False)
        encoded = json.dumps(
            {
                "topology": _TOPOLOGY,
                "schema_version": _SCHEMA_VERSION,
                "entries": [entry.dump() for entry in projected],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(encoded.encode()).hexdigest()

    @staticmethod
    def _validate_reconciliation(
        source_id: str,
        subject: str,
        revision: int,
        digest: str,
        entries: tuple[IngressEntry, ...],
    ) -> None:
        V5IngressStore._validate_subject(subject)
        if (
            type(revision) is not int
            or revision < 1
            or _DIGEST.fullmatch(digest) is None
            or source_id != f"host-reconcile:{subject}:{revision}:{digest}"
            or any(entry.identity != f"{source_id}:{entry.source}" for entry in entries)
        ):
            raise RuntimeError("V5 reconciliation manifest is malformed")
        try:
            projected = tuple(ProjectedEntry(entry.source, entry.color, entry.payload) for entry in entries)
            if V5IngressStore._projection_digest(projected) != digest:
                raise ValueError
        except ValueError:
            raise RuntimeError("V5 reconciliation manifest is malformed") from None

    def _reconciliation_manifest(self, source_id: str, subject: str) -> IngressManifest:
        row = self._db.execute(
            "SELECT subject,revision,digest,topology,schema_version,entries"
            " FROM v5_reconciliation_manifests WHERE source_id=?",
            (source_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("V5 reconciliation manifest is missing")
        stored_subject, revision, digest, topology, schema_version, encoded = row
        if (
            stored_subject != subject
            or topology != _TOPOLOGY
            or schema_version != _SCHEMA_VERSION
            or type(revision) is not int
            or not isinstance(digest, str)
            or not isinstance(encoded, str)
        ):
            raise RuntimeError("V5 reconciliation manifest is incompatible")
        try:
            raw = json.loads(encoded)
        except json.JSONDecodeError:
            raise RuntimeError("V5 reconciliation manifest is malformed") from None
        if not isinstance(raw, list):
            raise TypeError("V5 reconciliation manifest is malformed")
        entries = tuple(IngressEntry.load(value) for value in raw)
        self._validate_reconciliation(source_id, subject, revision, digest, entries)
        return IngressManifest(source_id, subject, revision, entries)

    @staticmethod
    def _load(delivery_id: str, row: tuple[object, ...]) -> IngressManifest:
        subject, revision, topology, schema_version, encoded = row
        if (
            not isinstance(subject, str)
            or type(revision) is not int
            or revision < 1
            or topology != _TOPOLOGY
            or schema_version != _SCHEMA_VERSION
            or not isinstance(encoded, str)
        ):
            raise RuntimeError("V5 ingress manifest is incompatible")
        try:
            raw = json.loads(encoded)
        except json.JSONDecodeError:
            raise RuntimeError("V5 ingress manifest is malformed") from None
        if not isinstance(raw, list):
            raise TypeError("V5 ingress manifest is malformed")
        entries = tuple(IngressEntry.load(value) for value in raw)
        V5IngressStore._validate(delivery_id, subject, entries)
        return IngressManifest(delivery_id, subject, revision, entries)

    def close(self) -> None:
        self._db.close()


__all__ = ["IngressEntry", "IngressManifest", "ProjectedEntry", "V5IngressNormalizer", "V5IngressStore"]
