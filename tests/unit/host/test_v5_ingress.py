"""Durable custody contracts for V5 webhook ingress."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    ExternalEventDelivered,
    FiringFailed,
)
from petrus.impetus.petrinet import NetPath, Token
from petrus.motus.dispatch import LocalDispatch

from hamsterdan.agents.protocol import ConversationResult, ReviewResult
from hamsterdan.contracts.readiness import AdmittedConversation
from hamsterdan.contracts.readiness_v5 import AWake, CommentSeen, DraftSeen, HeadSeen, HumanSeen, ReadySeen, RoundWake
from hamsterdan.github_app.models import (
    ActionsEvidence,
    ActionsRunSnapshot,
    GitHubBoundaryError,
    HumanReviewSnapshot,
    PullRequestSnapshot,
    RepositoryPolicy,
    WireResponse,
)
from hamsterdan.github_app.webhooks import Observation
from hamsterdan.host.runnable import RunnableIndex
from hamsterdan.host.v5.application import PrReadinessV5Application
from hamsterdan.host.v5.ingress import IngressEntry, ProjectedEntry, V5IngressNormalizer, V5IngressStore

SUBJECT = "github:44:31:pr:7"


def delivery() -> str:
    return str(uuid.uuid4())


def head(identity: str, value: str = "a" * 40) -> IngressEntry:
    return IngressEntry.from_value(
        "on_head",
        HeadSeen(head=value, base="b" * 40, mergeable=True, policy="policy-1"),
        f"github-delivery:{identity}:on_head",
    )


def lifecycle(identity: str, source: str) -> IngressEntry:
    value = DraftSeen() if source == "on_draft" else ReadySeen()
    return IngressEntry.from_value(source, value, f"github-delivery:{identity}:{source}")


def human(identity: str) -> IngressEntry:
    return IngressEntry.from_value(
        "on_human",
        HumanSeen(approval=False, changes_requested=False, unresolved=0),
        f"github-delivery:{identity}:on_human",
    )


def projection(identity: str, source: str, value: str = "a" * 40) -> tuple[IngressEntry, ...]:
    return head(identity, value), lifecycle(identity, source), human(identity)


def reconciliation_projection(source: str, value: str = "a" * 40) -> tuple[ProjectedEntry, ...]:
    lifecycle_value = DraftSeen() if source == "on_draft" else ReadySeen()
    return (
        ProjectedEntry.from_value("on_head", HeadSeen(head=value, base="b" * 40, mergeable=True, policy="policy-1")),
        ProjectedEntry.from_value(source, lifecycle_value),
        ProjectedEntry.from_value("on_human", HumanSeen(approval=False, changes_requested=False, unresolved=0)),
    )


def test_manifest_and_authority_grant_commit_together_before_replay(tmp_path: Path) -> None:
    identity = delivery()
    store = V5IngressStore(tmp_path / "webhooks.sqlite3")

    manifest = store.stage(identity, SUBJECT, projection(identity, "on_draft"))

    assert [entry.source for entry in manifest.entries] == ["on_head", "on_draft", "on_human"]
    assert store.claim(SUBJECT).__dict__ == {
        "phase": "quiescent",
        "incarnation": 1,
        "head": "a" * 40,
        "base": "b" * 40,
        "policy": "policy-1",
    }
    with sqlite3.connect(tmp_path / "webhooks.sqlite3") as database:
        stored = database.execute(
            "SELECT topology,schema_version,entries FROM v5_ingress_manifests WHERE delivery_id=?",
            (identity,),
        ).fetchone()
    assert stored is not None and stored[:2] == ("v5", 1)
    assert [entry["identity"] for entry in json.loads(stored[2])] == [
        f"github-delivery:{identity}:on_head",
        f"github-delivery:{identity}:on_draft",
        f"github-delivery:{identity}:on_human",
    ]
    store.close()


def test_replay_uses_frozen_manifest_even_when_fresh_projection_differs(tmp_path: Path) -> None:
    identity = delivery()
    store = V5IngressStore(tmp_path / "webhooks.sqlite3")
    original = store.stage(identity, SUBJECT, projection(identity, "on_draft"))

    replayed = store.stage(
        identity,
        SUBJECT,
        projection(identity, "on_ready", "c" * 40),
    )

    assert replayed == original
    assert store.claim(SUBJECT).phase == "quiescent"
    assert store.claim(SUBJECT).head == "a" * 40
    store.close()


def test_legacy_webhook_manifest_replays_then_fresh_reconciliation_adds_base_evidence(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    identity = delivery()
    values = [entry.dump() for entry in projection(identity, "on_ready")]
    values[0]["payload"].pop("strict_base")
    values[0]["payload"].pop("base_current")
    store = V5IngressStore(path)
    with sqlite3.connect(path) as database:
        database.execute(
            "INSERT INTO v5_ingress_manifests"
            "(delivery_id,subject,revision,topology,schema_version,entries) VALUES(?,?,?,?,?,?)",
            (identity, SUBJECT, 1, "v5", 1, json.dumps(values, sort_keys=True, separators=(",", ":"))),
        )
        database.execute(
            "INSERT INTO v5_authority_grants"
            "(subject,phase,incarnation,head,base,policy,revision,source_kind,source_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (SUBJECT, "running", 1, "a" * 40, "b" * 40, "policy-1", 1, "github-delivery", identity),
        )

    legacy = store.manifest(identity, SUBJECT)
    refreshed = store.stage_reconciliation(SUBJECT, reconciliation_projection("on_ready"))

    assert legacy is not None and set(legacy.entries[0].payload) == {"head", "base", "mergeable", "policy"}
    assert refreshed is not None and refreshed.revision == 2
    assert refreshed.entries[0].payload["strict_base"] is True
    assert refreshed.entries[0].payload["base_current"] is False
    store.close()


def test_legacy_reconciliation_manifest_keeps_its_digest_then_refreshes_base_evidence(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    projected = [entry.dump() for entry in reconciliation_projection("on_ready")]
    projected[0]["payload"].pop("strict_base")
    projected[0]["payload"].pop("base_current")
    digest = sha256(
        json.dumps(
            {"topology": "v5", "schema_version": 1, "entries": projected},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    source_id = f"host-reconcile:{SUBJECT}:1:{digest}"
    entries = [{**entry, "identity": f"{source_id}:{entry['source']}"} for entry in projected]
    store = V5IngressStore(path)
    with sqlite3.connect(path) as database:
        database.execute(
            "INSERT INTO v5_reconciliation_manifests"
            "(source_id,subject,revision,digest,topology,schema_version,entries) VALUES(?,?,?,?,?,?,?)",
            (source_id, SUBJECT, 1, digest, "v5", 1, json.dumps(entries, sort_keys=True, separators=(",", ":"))),
        )
        database.execute(
            "INSERT INTO v5_authority_grants"
            "(subject,phase,incarnation,head,base,policy,revision,source_kind,source_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (SUBJECT, "running", 1, "a" * 40, "b" * 40, "policy-1", 1, "host-reconcile", source_id),
        )

    legacy = store.latest_reconciliation(SUBJECT)
    refreshed = store.stage_reconciliation(SUBJECT, reconciliation_projection("on_ready"))

    assert legacy is not None and legacy.source_id == source_id
    assert set(legacy.entries[0].payload) == {"head", "base", "mergeable", "policy"}
    assert refreshed is not None and refreshed.revision == 2 and refreshed.source_id != source_id
    assert refreshed.entries[0].payload["strict_base"] is True
    assert refreshed.entries[0].payload["base_current"] is False
    store.close()


def test_unchanged_reconciliation_reuses_one_lineaged_manifest_and_grant_revision(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)
    projected = reconciliation_projection("on_ready")

    first = store.stage_reconciliation(SUBJECT, projected)
    second = store.stage_reconciliation(SUBJECT, projected)

    assert first is not None and second == first
    digest = sha256(
        json.dumps(
            {"topology": "v5", "schema_version": 1, "entries": [entry.dump() for entry in projected]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert first.source_id == f"host-reconcile:{SUBJECT}:1:{digest}"
    assert all(entry.identity == f"{first.source_id}:{entry.source}" for entry in first.entries)
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT COUNT(*) FROM v5_reconciliation_manifests").fetchone() == (1,)
        assert database.execute(
            "SELECT revision,source_kind,source_id FROM v5_authority_grants WHERE subject=?", (SUBJECT,)
        ).fetchone() == (1, "host-reconcile", first.source_id)
    store.close()


def test_intervening_webhook_makes_byte_identical_reconciliation_a_new_lifecycle_occurrence(
    tmp_path: Path,
) -> None:
    store = V5IngressStore(tmp_path / "webhooks.sqlite3")
    first = store.stage_reconciliation(SUBJECT, reconciliation_projection("on_draft"))
    assert first is not None
    readied = delivery()
    store.stage(readied, SUBJECT, projection(readied, "on_ready"))

    second = store.stage_reconciliation(SUBJECT, reconciliation_projection("on_draft"))

    assert second is not None and second.source_id != first.source_id
    assert first.entries[1].identity != second.entries[1].identity
    assert (store.claim(SUBJECT).phase, store.claim(SUBJECT).incarnation) == ("quiescent", 2)
    store.close()


def test_pending_webhook_custody_wins_reconciliation_stage_without_manifest_or_grant(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)
    pending = delivery()
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE inbox (delivery_id TEXT PRIMARY KEY, status TEXT NOT NULL, observation TEXT NOT NULL)"
        )
        database.execute(
            "INSERT INTO inbox VALUES (?, 'pending', ?)",
            (
                pending,
                json.dumps({"installation_id": 44, "repository_id": 31, "pull_request_number": 7}),
            ),
        )

    assert store.stage_reconciliation(SUBJECT, reconciliation_projection("on_ready")) is None
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT COUNT(*) FROM v5_reconciliation_manifests").fetchone() == (0,)
        assert database.execute("SELECT COUNT(*) FROM v5_authority_grants").fetchone() == (0,)
    store.close()


def test_legacy_webhook_grant_migrates_to_a_discriminated_source_before_reconciliation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "webhooks.sqlite3"
    identity = delivery()
    entries = projection(identity, "on_ready")
    encoded = json.dumps(
        [entry.dump() for entry in entries],
        sort_keys=True,
        separators=(",", ":"),
    )
    with sqlite3.connect(path) as database:
        database.executescript(
            """
            CREATE TABLE v5_ingress_manifests (
              delivery_id TEXT PRIMARY KEY, subject TEXT NOT NULL, topology TEXT NOT NULL,
              schema_version INTEGER NOT NULL, entries TEXT NOT NULL
            );
            CREATE TABLE v5_authority_grants (
              subject TEXT PRIMARY KEY, phase TEXT NOT NULL, incarnation INTEGER NOT NULL,
              head TEXT NOT NULL, base TEXT NOT NULL, policy TEXT NOT NULL,
              revision INTEGER NOT NULL, source_delivery TEXT NOT NULL
            );
            """
        )
        database.execute(
            "INSERT INTO v5_ingress_manifests VALUES(?,?,?,?,?)",
            (identity, SUBJECT, "v5", 1, encoded),
        )
        database.execute(
            "INSERT INTO v5_authority_grants VALUES(?,?,?,?,?,?,?,?)",
            (SUBJECT, "running", 1, "a" * 40, "b" * 40, "policy-1", 1, identity),
        )

    store = V5IngressStore(path)

    assert store.claim(SUBJECT).head == "a" * 40
    reconciled = store.stage_reconciliation(SUBJECT, reconciliation_projection("on_ready"))
    assert reconciled is not None and f":{SUBJECT}:2:" in reconciled.source_id
    store.close()

    reopened = V5IngressStore(path)
    assert reopened.latest_reconciliation(SUBJECT) == reconciled
    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT revision,source_kind,source_id,source_delivery FROM v5_authority_grants WHERE subject=?",
            (SUBJECT,),
        ).fetchone() == (2, "host-reconcile", reconciled.source_id, reconciled.source_id)
    reopened.close()
    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE v5_authority_grants SET source_delivery=? WHERE subject=?",
            (identity, SUBJECT),
        )
    divergent = V5IngressStore(path)
    with pytest.raises(RuntimeError, match="grant is malformed"):
        divergent.claim(SUBJECT)
    divergent.close()


def test_reconciliation_manifest_and_grant_corruption_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)
    manifest = store.stage_reconciliation(SUBJECT, reconciliation_projection("on_ready"))
    assert manifest is not None
    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE v5_reconciliation_manifests SET digest=? WHERE source_id=?",
            ("0" * 64, manifest.source_id),
        )

    with pytest.raises(RuntimeError, match="manifest is malformed"):
        store.latest_reconciliation(SUBJECT)
    with pytest.raises(RuntimeError, match="manifest is malformed"):
        store.claim(SUBJECT)
    store.close()


def test_current_webhook_grant_validates_its_manifest_and_exact_revision(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    identity = delivery()
    store = V5IngressStore(path)
    store.stage(identity, SUBJECT, projection(identity, "on_ready"))
    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE v5_ingress_manifests SET entries='[]' WHERE delivery_id=?",
            (identity,),
        )

    with pytest.raises(ValueError, match="door order"):
        store.claim(SUBJECT)

    with sqlite3.connect(path) as database:
        database.execute(
            "UPDATE v5_ingress_manifests SET entries=? WHERE delivery_id=?",
            (
                json.dumps(
                    [entry.dump() for entry in projection(identity, "on_ready")],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                identity,
            ),
        )
        database.execute("UPDATE v5_authority_grants SET revision=7 WHERE subject=?", (SUBJECT,))

    with pytest.raises(RuntimeError, match="grant is malformed"):
        store.claim(SUBJECT)
    store.close()


def test_cross_kind_revision_collision_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)
    reconciled = store.stage_reconciliation(SUBJECT, reconciliation_projection("on_ready"))
    assert reconciled is not None
    identity = delivery()
    with sqlite3.connect(path) as database:
        database.execute(
            "INSERT INTO v5_ingress_manifests"
            "(delivery_id,subject,revision,topology,schema_version,entries) VALUES(?,?,?,?,?,?)",
            (
                identity,
                SUBJECT,
                1,
                "v5",
                1,
                json.dumps(
                    [entry.dump() for entry in projection(identity, "on_ready")],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )

    with pytest.raises(RuntimeError, match="grant is malformed"):
        store.claim(SUBJECT)
    store.close()


def test_partial_source_pointer_migration_fails_closed_instead_of_repairing(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    identity = delivery()
    encoded = json.dumps(
        [entry.dump() for entry in projection(identity, "on_ready")],
        sort_keys=True,
        separators=(",", ":"),
    )
    with sqlite3.connect(path) as database:
        database.executescript(
            """
            CREATE TABLE v5_ingress_manifests (
              delivery_id TEXT PRIMARY KEY, subject TEXT NOT NULL, topology TEXT NOT NULL,
              schema_version INTEGER NOT NULL, entries TEXT NOT NULL
            );
            CREATE TABLE v5_authority_grants (
              subject TEXT PRIMARY KEY, phase TEXT NOT NULL, incarnation INTEGER NOT NULL,
              head TEXT NOT NULL, base TEXT NOT NULL, policy TEXT NOT NULL,
              revision INTEGER NOT NULL, source_delivery TEXT NOT NULL, source_kind TEXT
            );
            """
        )
        database.execute(
            "INSERT INTO v5_ingress_manifests VALUES(?,?,?,?,?)",
            (identity, SUBJECT, "v5", 1, encoded),
        )
        database.execute(
            "INSERT INTO v5_authority_grants VALUES(?,?,?,?,?,?,?,?,?)",
            (SUBJECT, "running", 1, "a" * 40, "b" * 40, "policy-1", 1, identity, "github-delivery"),
        )

    with pytest.raises(RuntimeError, match="source pointer migration is partial"):
        V5IngressStore(path)


def test_draft_ready_same_claim_mints_a_new_host_incarnation(tmp_path: Path) -> None:
    store = V5IngressStore(tmp_path / "webhooks.sqlite3")
    drafted, readied = delivery(), delivery()
    store.stage(drafted, SUBJECT, projection(drafted, "on_draft"))

    store.stage(readied, SUBJECT, projection(readied, "on_ready"))

    claim = store.claim(SUBJECT)
    assert (claim.phase, claim.incarnation, claim.head, claim.base, claim.policy) == (
        "running",
        2,
        "a" * 40,
        "b" * 40,
        "policy-1",
    )
    store.close()


def test_manifest_and_grant_roll_back_as_one_transaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    identity = delivery()
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)

    def fail(*args: object) -> None:
        raise RuntimeError("grant write interrupted")

    monkeypatch.setattr(store, "_write_claim", fail)
    with pytest.raises(RuntimeError, match="grant write interrupted"):
        store.stage(identity, SUBJECT, projection(identity, "on_ready"))

    with sqlite3.connect(path) as database:
        assert (
            database.execute("SELECT 1 FROM v5_ingress_manifests WHERE delivery_id=?", (identity,)).fetchone() is None
        )
        assert database.execute("SELECT 1 FROM v5_authority_grants WHERE subject=?", (SUBJECT,)).fetchone() is None
    store.close()


def test_reconciliation_manifest_and_grant_roll_back_as_one_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)

    def fail(*args: object) -> None:
        raise RuntimeError("grant write interrupted")

    monkeypatch.setattr(store, "_write_claim", fail)
    with pytest.raises(RuntimeError, match="grant write interrupted"):
        store.stage_reconciliation(SUBJECT, reconciliation_projection("on_ready"))

    with sqlite3.connect(path) as database:
        assert database.execute("SELECT 1 FROM v5_reconciliation_manifests").fetchone() is None
        assert database.execute("SELECT 1 FROM v5_authority_grants WHERE subject=?", (SUBJECT,)).fetchone() is None
    store.close()


@pytest.mark.parametrize(
    "entries",
    [
        lambda identity: (head(identity), head(identity)),
        lambda identity: (lifecycle(identity, "on_draft"), head(identity)),
    ],
)
def test_manifest_rejects_duplicate_or_out_of_order_doors(tmp_path: Path, entries) -> None:
    identity = delivery()
    store = V5IngressStore(tmp_path / "webhooks.sqlite3")

    with pytest.raises(ValueError, match="door order"):
        store.stage(identity, SUBJECT, entries(identity))
    store.close()


def test_manifest_rejects_a_door_payload_that_does_not_match_its_strict_color(tmp_path: Path) -> None:
    identity = delivery()
    store = V5IngressStore(tmp_path / "webhooks.sqlite3")
    malformed = IngressEntry(
        "on_head",
        "HeadSeen",
        {"head": 7, "base": "b" * 40, "mergeable": True, "policy": "policy-1"},
        f"github-delivery:{identity}:on_head",
    )

    with pytest.raises(ValueError, match="payload"):
        store.stage(identity, SUBJECT, (malformed, lifecycle(identity, "on_ready"), human(identity)))
    store.close()


def test_manifest_rejects_an_incomplete_open_projection(tmp_path: Path) -> None:
    identity = delivery()
    store = V5IngressStore(tmp_path / "webhooks.sqlite3")

    with pytest.raises(ValueError, match="complete batch"):
        store.stage(identity, SUBJECT, (lifecycle(identity, "on_ready"),))
    store.close()


def test_manifest_replay_requires_its_subject_grant(tmp_path: Path) -> None:
    identity = delivery()
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)
    store.stage(identity, SUBJECT, projection(identity, "on_ready"))
    with sqlite3.connect(path) as database:
        database.execute("DELETE FROM v5_authority_grants WHERE subject=?", (SUBJECT,))

    with pytest.raises(RuntimeError, match="grant is missing"):
        store.manifest(identity, SUBJECT)
    store.close()


def test_new_delivery_cannot_replace_a_missing_grant_from_prior_custody(tmp_path: Path) -> None:
    first, second = delivery(), delivery()
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)
    store.stage(first, SUBJECT, projection(first, "on_ready"))
    with sqlite3.connect(path) as database:
        database.execute("DELETE FROM v5_authority_grants WHERE subject=?", (SUBJECT,))

    with pytest.raises(RuntimeError, match="grant is missing"):
        store.stage(second, SUBJECT, projection(second, "on_draft"))
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT 1 FROM v5_ingress_manifests WHERE delivery_id=?", (second,)).fetchone() is None
    store.close()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("incarnation", 1.5),
        ("head", sqlite3.Binary(b"not-text")),
    ],
)
def test_manifest_and_claim_reject_persisted_grant_type_coercion(
    tmp_path: Path,
    column: str,
    value: object,
) -> None:
    identity = delivery()
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)
    store.stage(identity, SUBJECT, projection(identity, "on_ready"))
    with sqlite3.connect(path) as database:
        database.execute(f"UPDATE v5_authority_grants SET {column}=? WHERE subject=?", (value, SUBJECT))

    with pytest.raises(RuntimeError, match="grant is malformed"):
        store.manifest(identity, SUBJECT)
    with pytest.raises(RuntimeError, match="grant is malformed"):
        store.claim(SUBJECT)
    store.close()


def test_existing_delivery_cannot_be_staged_for_a_different_subject(tmp_path: Path) -> None:
    identity = delivery()
    store = V5IngressStore(tmp_path / "webhooks.sqlite3")
    store.stage(identity, SUBJECT, projection(identity, "on_ready"))

    with pytest.raises(RuntimeError, match="different subject"):
        store.stage(identity, "github:44:31:pr:8", projection(identity, "on_ready"))
    store.close()


def test_unstaged_inbox_custody_fences_the_claim_until_its_manifest_commits(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)
    initial, pending = delivery(), delivery()
    store.stage(initial, SUBJECT, projection(initial, "on_ready"))
    observation = {
        "installation_id": 44,
        "repository_id": 31,
        "pull_request_number": 7,
    }
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE inbox (delivery_id TEXT PRIMARY KEY, status TEXT NOT NULL, observation TEXT NOT NULL)"
        )
        database.execute(
            "INSERT INTO inbox VALUES (?, 'pending', ?)",
            (pending, json.dumps(observation)),
        )

    assert store.has_unstaged_custody(SUBJECT)
    store.stage(pending, SUBJECT, projection(pending, "on_draft"))
    assert not store.has_unstaged_custody(SUBJECT)
    store.close()


class Authority:
    def __init__(self, *, draft: bool = False, closed: bool = False, merged: bool = False):
        self.pull = PullRequestSnapshot(
            "owner/repo",
            7,
            "closed" if closed else "open",
            draft,
            "a" * 40,
            "b" * 40,
            "feature",
            "main",
            True,
            merged,
            closed,
            "author",
            "clean",
            "https://example.test/pr/7",
            "owner/repo",
        )
        self.repo_policy = RepositoryPolicy(True, True, ("test",), 1, True, "rules", "policy-1")
        self.review = HumanReviewSnapshot((), (), ("reviewer",), (), 0, "available")
        self.runs = (
            ActionsRunSnapshot(9, "a" * 40, ".github/workflows/ci.yml", 5, "completed", "failure"),
            ActionsRunSnapshot(10, "a" * 40, ".github/workflows/ci.yml", 1, "completed", "success"),
        )
        self.evidence_calls: list[tuple[int, int]] = []
        self.base_current_calls: list[PullRequestSnapshot] = []
        self.pull_calls = 0
        self.repository = "owner/repo"
        self.pr_number = 7
        self.transport = Transport()

    def pull_request(self):
        self.pull_calls += 1
        return self.pull

    def policy(self, base_ref: str):
        assert base_ref == "main"
        return self.repo_policy

    def base_current(self, pull: PullRequestSnapshot):
        self.base_current_calls.append(pull)
        return True

    def human_review(self):
        return self.review

    def workflow_runs(self, workflow: str, head: str):
        assert workflow == ".github/workflows/ci.yml" and head == "a" * 40
        return self.runs

    def actions_evidence(self, run: ActionsRunSnapshot, required_checks: tuple[str, ...]):
        self.evidence_calls.append((run.id, run.attempt))
        return ActionsEvidence(run, "success", ())

    def comments(self):
        return ()

    def select_run(self, workflow: str, head: str):
        return None


class Transport:
    def __init__(self):
        self.comments: list[dict[str, object]] = []

    def pages(self, path: str):
        return tuple(self.comments)

    def request(self, method: str, path: str, body: object | None = None):
        assert isinstance(body, dict) and isinstance(body.get("body"), str)
        if method == "POST":
            item = {
                "id": len(self.comments) + 1,
                "html_url": f"https://example.test/comments/{len(self.comments) + 1}",
                "body": body["body"],
                "user": {"login": "hamsterdan-test[bot]"},
            }
            self.comments.append(item)
            return WireResponse(201, item)
        if method == "PATCH":
            identifier = int(path.rsplit("/", 1)[-1])
            item = next(item for item in self.comments if item["id"] == identifier)
            item["body"] = body["body"]
            return WireResponse(200, item)
        raise AssertionError("unexpected provider operation")


class Runner:
    def __init__(self):
        self.conversation_calls = 0

    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        assert attempt == 1 and (is_current is None or is_current())
        return ReviewResult(
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            "clear",
            [],
            [],
        )

    def converse(self, repository_url, request, *, operation, attempt, is_current=None):
        self.conversation_calls += 1
        assert attempt == 1 and is_current is not None and is_current()
        return ConversationResult(
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            [{"type": "change", "arguments": {"request": "rename the value"}}],
        )


def test_normalizer_freezes_fixed_door_order_and_newest_run_by_v5_identity() -> None:
    identity = delivery()
    authority = Authority()
    comment = CommentSeen(id="comment-9", kind="change", arg="fix it", authorized=True)

    entries = V5IngressNormalizer(authority, ".github/workflows/ci.yml").project(identity, comment=comment)

    assert [entry.source for entry in entries] == [
        "on_head",
        "on_ready",
        "on_human",
        "on_runs",
        "on_comment",
    ]
    assert authority.evidence_calls == [(10, 1)]
    assert authority.base_current_calls == [authority.pull]
    assert entries[0].payload["strict_base"] is True
    assert entries[0].payload["base_current"] is True
    assert entries[3].payload == {
        "head": "a" * 40,
        "run_id": 10,
        "attempt": 1,
        "conclusion": "success",
        "fingerprint": "",
    }
    assert all(entry.identity == f"github-delivery:{identity}:{entry.source}" for entry in entries)


def test_normalizer_preserves_authenticated_draft_and_ready_edges_after_provider_state_collapses(
    tmp_path: Path,
) -> None:
    authority = Authority()
    normalizer = V5IngressNormalizer(authority, ".github/workflows/ci.yml")
    drafted, readied = delivery(), delivery()

    draft_entries = normalizer.project(drafted, event="pull_request", action="converted_to_draft")
    ready_entries = normalizer.project(readied, event="pull_request", action="ready_for_review")

    assert [entry.source for entry in draft_entries][:2] == ["on_head", "on_draft"]
    assert [entry.source for entry in ready_entries][:2] == ["on_head", "on_ready"]

    store = V5IngressStore(tmp_path / "webhooks.sqlite3")
    store.stage(drafted, SUBJECT, draft_entries)
    store.stage(readied, SUBJECT, ready_entries)
    assert (store.claim(SUBJECT).phase, store.claim(SUBJECT).incarnation) == ("running", 2)
    store.close()


@pytest.mark.parametrize(("closed", "merged", "reason"), [(True, False, "closed"), (True, True, "merged")])
def test_normalizer_closes_without_opening_new_work(closed: bool, merged: bool, reason: str) -> None:
    identity = delivery()
    authority = Authority(closed=closed, merged=merged)

    entries = V5IngressNormalizer(authority, ".github/workflows/ci.yml").project(identity)

    assert [(entry.source, entry.color, entry.payload) for entry in entries] == [
        ("on_close", "CloseSeen", {"reason": reason})
    ]
    assert authority.evidence_calls == []


def test_v5_application_stages_grant_before_identified_delivery_and_replays_frozen_manifest(tmp_path: Path) -> None:
    identity = delivery()
    authority = Authority()
    settled: list[set[str]] = []
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: settled.append(operations),
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    observation = Observation(identity, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7)
    runtime = application._runtime()
    deliver = runtime.deliver
    observed_claims = []

    def observe(entry: IngressEntry):
        observed_claims.append(application.ingress.claim(SUBJECT))
        return deliver(entry)

    runtime.deliver = observe  # type: ignore[method-assign]
    application.process_observation(observation)
    first_provider_reads = authority.pull_calls
    first_records = tuple(runtime.engine.records)

    authority.pull = PullRequestSnapshot(**(authority.pull.__dict__ | {"head": "c" * 40}))
    application.process_observation(observation)

    assert observed_claims and all(claim.head == "a" * 40 and claim.incarnation == 1 for claim in observed_claims)
    assert authority.pull_calls == first_provider_reads
    identities = [record.identity for record in runtime.engine.records if isinstance(record, ExternalEventDelivered)]
    assert identities == [
        f"github-delivery:{identity}:on_head",
        f"github-delivery:{identity}:on_ready",
        f"github-delivery:{identity}:on_human",
        f"github-delivery:{identity}:on_runs",
    ]
    assert tuple(runtime.engine.records) == first_records
    assert settled == []
    application.close()


def test_v5_finding_publication_heartbeat_covers_the_transient_retry_pause(tmp_path: Path) -> None:
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        Authority(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )

    definition = application._runtime().activity("publish_gate")

    assert definition is not None and definition.declaration.heartbeat_timeout == 360
    application.close()


def test_v5_application_reconciliation_is_stable_across_startup_and_periodic_reasons(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=path,
    )

    assert application.reconcile("startup:44:31:7")
    first = tuple(application._runtime().engine.records)
    assert application.reconcile("periodic:44:31:7")

    assert tuple(application._runtime().engine.records) == first
    identities = [record.identity for record in first if isinstance(record, ExternalEventDelivered)]
    assert len(identities) == 4
    assert all(identity.startswith(f"host-reconcile:{SUBJECT}:1:") for identity in identities)
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT COUNT(*) FROM v5_reconciliation_manifests").fetchone() == (1,)
        assert database.execute(
            "SELECT revision,source_kind FROM v5_authority_grants WHERE subject=?", (SUBJECT,)
        ).fetchone() == (1, "host-reconcile")
    application.close()


def test_v5_application_replays_committed_reconciliation_before_reading_changed_provider_truth(
    tmp_path: Path,
) -> None:
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    runtime = application._runtime()
    deliver = runtime.deliver
    crashed = False

    def fail_before_first_delivery(entry: IngressEntry):
        nonlocal crashed
        if not crashed:
            crashed = True
            raise RuntimeError("crash after reconciliation commit")
        return deliver(entry)

    runtime.deliver = fail_before_first_delivery  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="crash after reconciliation commit"):
        application.reconcile("startup")
    authority.review = HumanReviewSnapshot(("reviewer",), (), (), (), 0, "available")
    provider_reads = authority.pull_calls

    assert application.reconcile("restart")

    deliveries = [record for record in runtime.engine.records if isinstance(record, ExternalEventDelivered)]
    assert authority.pull_calls == provider_reads
    assert len(deliveries) == 4
    assert deliveries[2].tokens[0].data["approval"] is True

    assert application.reconcile("periodic")

    deliveries = [record for record in runtime.engine.records if isinstance(record, ExternalEventDelivered)]
    assert len(deliveries) == 8
    first_sources = {record.identity.rsplit(":", 1)[0] for record in deliveries[:4]}
    second_sources = {record.identity.rsplit(":", 1)[0] for record in deliveries[4:]}
    assert len(first_sources) == len(second_sources) == 1
    assert first_sources != second_sources
    assert deliveries[6].tokens[0].data["approval"] is False
    application.close()


def test_v5_application_restart_replays_committed_reconciliation_without_provider_reads(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    store = V5IngressStore(path)
    committed = store.stage_reconciliation(SUBJECT, reconciliation_projection("on_ready"))
    assert committed is not None
    store.close()
    authority = Authority()
    authority.pull = PullRequestSnapshot(**(authority.pull.__dict__ | {"head": "c" * 40}))
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=path,
    )

    assert application.reconcile("restart")

    assert authority.pull_calls == 0
    identities = tuple(
        record.identity
        for record in application._runtime().engine.records
        if isinstance(record, ExternalEventDelivered)
    )
    assert identities == tuple(entry.identity for entry in committed.entries)
    application.close()


def test_reconciliation_folds_a_final_row_accepted_before_the_prior_host_crashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    committed = application.ingress.stage_reconciliation(
        SUBJECT,
        application.normalizer.project_reconciliation(),
    )
    assert committed is not None
    runtime = application._runtime()
    for entry in committed.entries[:-1]:
        runtime.deliver(entry)
        runtime.fold_ingress(entry)
    final = committed.entries[-1]
    runtime.deliver(final)  # the process died after acceptance, before its fold
    assert runtime.manifest_accepted(committed.entries)
    assert Token(final.color, final.payload) in runtime.engine.marking.place(NetPath("life.runs"))
    project = V5IngressNormalizer.project_reconciliation

    def observe_after_replay(normalizer):
        assert Token(final.color, final.payload) not in runtime.engine.marking.place(NetPath("life.runs"))
        return project(normalizer)

    monkeypatch.setattr(V5IngressNormalizer, "project_reconciliation", observe_after_replay)

    assert application.reconcile("restart")
    application.close()


def test_v5_application_fails_closed_when_manifest_identity_conflicts_with_canonical_history(tmp_path: Path) -> None:
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    committed = application.ingress.stage_reconciliation(
        SUBJECT,
        application.normalizer.project_reconciliation(),
    )
    assert committed is not None
    conflicting = replace(
        committed.entries[0],
        payload=HeadSeen(head="c" * 40, base="b" * 40, mergeable=True, policy="policy-1").dump(),
    )
    runtime = application._runtime()
    runtime.deliver(conflicting)
    for entry in committed.entries[1:]:
        runtime.deliver(entry)

    with pytest.raises(RuntimeError, match="conflicts with canonical History"):
        application.reconcile("restart")
    application.close()


def test_v5_application_checks_later_history_conflicts_before_replaying_an_earlier_gap(tmp_path: Path) -> None:
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    committed = application.ingress.stage_reconciliation(
        SUBJECT,
        application.normalizer.project_reconciliation(),
    )
    assert committed is not None
    runtime = application._runtime()
    runtime.deliver(committed.entries[1])
    runtime.deliver(
        replace(
            committed.entries[2],
            payload=HumanSeen(approval=False, changes_requested=False, unresolved=0).dump(),
        )
    )
    for entry in committed.entries[3:]:
        runtime.deliver(entry)
    before = tuple(runtime.engine.records)

    with pytest.raises(RuntimeError, match="conflicts with canonical History"):
        application.reconcile("restart")
    assert tuple(runtime.engine.records) == before
    application.close()


def test_v5_application_does_not_deliver_reconciliation_when_webhook_custody_commits_after_stage(
    tmp_path: Path,
) -> None:
    path = tmp_path / "webhooks.sqlite3"
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=path,
    )
    stage = application.ingress.stage_reconciliation

    def admit_after_stage(subject: str, projected: tuple[ProjectedEntry, ...]):
        manifest = stage(subject, projected)
        with sqlite3.connect(path) as database:
            database.execute(
                "CREATE TABLE inbox (delivery_id TEXT PRIMARY KEY, status TEXT NOT NULL, observation TEXT NOT NULL)"
            )
            database.execute(
                "INSERT INTO inbox VALUES (?, 'pending', ?)",
                (
                    delivery(),
                    json.dumps({"installation_id": 44, "repository_id": 31, "pull_request_number": 7}),
                ),
            )
        return manifest

    application.ingress.stage_reconciliation = admit_after_stage  # type: ignore[method-assign]

    assert not application.reconcile("startup")
    assert not any(isinstance(record, ExternalEventDelivered) for record in application._runtime().engine.records)
    application.close()


def test_v5_application_does_not_read_provider_while_webhook_custody_is_pending(tmp_path: Path) -> None:
    path = tmp_path / "webhooks.sqlite3"
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=path,
    )
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE inbox (delivery_id TEXT PRIMARY KEY, status TEXT NOT NULL, observation TEXT NOT NULL)"
        )
        database.execute(
            "INSERT INTO inbox VALUES (?, 'pending', ?)",
            (
                delivery(),
                json.dumps({"installation_id": 44, "repository_id": 31, "pull_request_number": 7}),
            ),
        )

    assert not application.reconcile("startup")
    assert authority.pull_calls == 0
    assert not any(isinstance(record, ExternalEventDelivered) for record in application._runtime().engine.records)
    application.close()


def test_v5_application_does_not_stage_provider_projection_when_custody_arrives_during_read(
    tmp_path: Path,
) -> None:
    path = tmp_path / "webhooks.sqlite3"
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=path,
    )
    pull_request = authority.pull_request

    def admit_during_read():
        pull = pull_request()
        with sqlite3.connect(path) as database:
            database.execute(
                "CREATE TABLE inbox (delivery_id TEXT PRIMARY KEY, status TEXT NOT NULL, observation TEXT NOT NULL)"
            )
            database.execute(
                "INSERT INTO inbox VALUES (?, 'pending', ?)",
                (
                    delivery(),
                    json.dumps({"installation_id": 44, "repository_id": 31, "pull_request_number": 7}),
                ),
            )
        return pull

    authority.pull_request = admit_during_read  # type: ignore[method-assign]

    assert not application.reconcile("startup")
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT COUNT(*) FROM v5_reconciliation_manifests").fetchone() == (0,)
    assert not any(isinstance(record, ExternalEventDelivered) for record in application._runtime().engine.records)
    application.close()


def test_current_claim_fails_closed_until_fresh_provider_lifecycle_is_in_the_host_grant(tmp_path: Path) -> None:
    identity = delivery()
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    application.process_observation(Observation(identity, "pull_request", "opened", 44, 23, 31, "owner/repo", 7))
    authority.pull = PullRequestSnapshot(**(authority.pull.__dict__ | {"draft": True}))

    with pytest.raises(GitHubBoundaryError, match="not staged"):
        application.current_claim()

    drafted = delivery()
    application.process_observation(
        Observation(drafted, "pull_request", "converted_to_draft", 44, 23, 31, "owner/repo", 7)
    )
    assert application.current_claim().phase == "quiescent"
    application.close()


def test_v5_application_folds_draft_and_ready_in_the_host_grants_canonical_order(tmp_path: Path) -> None:
    authority = Authority(draft=True)
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )

    drafted = delivery()
    application.process_observation(Observation(drafted, "pull_request", "opened", 44, 23, 31, "owner/repo", 7))
    [life] = application._runtime().engine.marking.place(NetPath("life.state"))
    claim = application.ingress.claim(SUBJECT)
    assert (
        (life.data["phase"], life.data["incarnation"], life.data["head"])
        == (
            claim.phase,
            claim.incarnation,
            claim.head,
        )
        == ("quiescent", 1, "a" * 40)
    )
    assert authority.transport.comments == []

    authority.pull = PullRequestSnapshot(**(authority.pull.__dict__ | {"draft": False}))
    readied = delivery()
    application.process_observation(
        Observation(readied, "pull_request", "ready_for_review", 44, 23, 31, "owner/repo", 7)
    )
    [life] = application._runtime().engine.marking.place(NetPath("life.state"))
    claim = application.ingress.claim(SUBJECT)
    assert (
        (life.data["phase"], life.data["incarnation"], life.data["head"])
        == (
            claim.phase,
            claim.incarnation,
            claim.head,
        )
        == ("running", 2, "a" * 40)
    )
    application.close()


def test_v5_application_drains_the_real_topology_against_provider_backed_gates(tmp_path: Path) -> None:
    identity = delivery()
    authority = Authority()
    settled: list[set[str]] = []
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        Runner(),  # type: ignore[arg-type]
        agent_settle=lambda operations: settled.append(operations),
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    observation = Observation(identity, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7)

    application.process_observation(observation)
    outcome = application.settle()

    [life] = application._runtime().engine.marking.place(NetPath("life.state"))
    [ready] = application._runtime().engine.marking.place(NetPath("ready.snap"))
    assert life.data["incarnation"] == 1 and life.data["head"] == "a" * 40
    assert ready.data["review"] == "clear" and ready.data["checks"] == "success"
    assert not outcome.ready
    assert any(operations for operations in settled)
    assert any("hamsterdan:readiness" in str(item["body"]) for item in authority.transport.comments)
    application.close()


def _application_after_dashboard_custody_race(
    tmp_path: Path,
    *,
    terminalize_during_claim: bool = False,
) -> tuple[PrReadinessV5Application, Authority, Path, str]:
    identity = delivery()
    blocker = delivery()
    path = tmp_path / "webhooks.sqlite3"
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        Runner(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=path,
    )
    original_request = authority.transport.request
    inserted = False

    def dashboard_callback(method: str, endpoint: str, body: object | None = None):
        nonlocal inserted
        result = original_request(method, endpoint, body)
        text = str(body.get("body", "")) if isinstance(body, dict) else ""
        if (
            not inserted
            and method == "PATCH"
            and "hamsterdan:dashboard" in text
            and "| Human review |" in text
            and "no review yet" not in text
        ):
            inserted = True
            with sqlite3.connect(path) as database:
                database.execute(
                    "CREATE TABLE IF NOT EXISTS inbox"
                    " (delivery_id TEXT PRIMARY KEY, status TEXT NOT NULL, observation TEXT NOT NULL)"
                )
                database.execute(
                    "INSERT INTO inbox VALUES (?, 'pending', ?)",
                    (
                        blocker,
                        json.dumps({"installation_id": 44, "repository_id": 31, "pull_request_number": 7}),
                    ),
                )
        return result

    authority.transport.request = dashboard_callback  # type: ignore[method-assign]
    if terminalize_during_claim:
        unstaged_custody_id = application.ingress.unstaged_custody_id
        terminalized = False

        def terminalize_after_read(subject: str) -> str | None:
            nonlocal terminalized
            pending = unstaged_custody_id(subject)
            if pending is not None and not terminalized:
                terminalized = True
                with sqlite3.connect(path) as database:
                    database.execute("UPDATE inbox SET status='terminal' WHERE delivery_id=?", (pending,))
            return pending

        application.ingress.unstaged_custody_id = terminalize_after_read  # type: ignore[method-assign]
    application.process_observation(Observation(identity, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))
    application.settle()
    assert inserted
    return application, authority, path, blocker


def test_v5_readiness_announcement_defers_behind_dashboard_webhook_custody_then_wakes(tmp_path: Path) -> None:
    application, authority, path, blocker = _application_after_dashboard_custody_race(tmp_path)

    records = tuple(application._runtime().engine.records)
    [deferred] = application._runtime().engine.marking.place(NetPath("ready.deferred"))
    assert deferred.data["blocker"] == blocker
    assert any(
        isinstance(record, ActivityCompleted)
        and str(record.transition) == "ready.gate"
        and record.result.get("$variant") == "ADeferred"
        for record in records
    )
    assert not any(
        isinstance(record, ActivityCompleted)
        and str(record.transition) == "ready.gate"
        and record.result.get("$variant") == "ABlocked"
        for record in records
    )
    assert not any("hamsterdan:readiness" in str(item["body"]) for item in authority.transport.comments)

    unrelated = delivery()
    with sqlite3.connect(path) as database:
        database.execute(
            "INSERT INTO inbox VALUES (?, 'terminal', ?)",
            (
                unrelated,
                json.dumps({"installation_id": 44, "repository_id": 31, "pull_request_number": 7}),
            ),
        )
    application.settle()
    assert application._runtime().engine.marking.place(NetPath("ready.deferred"))
    assert not any("hamsterdan:readiness" in str(item["body"]) for item in authority.transport.comments)

    with sqlite3.connect(path) as database:
        database.execute("UPDATE inbox SET status='terminal' WHERE delivery_id=?", (blocker,))
    application.settle()

    assert application._runtime().engine.marking.place(NetPath("ready.deferred")) == ()
    assert len([item for item in authority.transport.comments if "hamsterdan:readiness" in str(item["body"])]) == 1
    wakes = [
        record
        for record in application._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and str(record.source) == "on_announce_wake"
    ]
    assert len(wakes) == 1 and wakes[0].identity.startswith("v5-announce-wake:")
    requests = [
        record.input["work"]
        for record in application._runtime().engine.records
        if isinstance(record, ActivityRequested) and str(record.transition) == "ready.gate"
    ]
    assert len(requests) == 2 and requests[0] == requests[1]
    application.close()


def test_v5_readiness_wakes_after_the_exact_blocker_manifest_folds_before_inbox_ack(tmp_path: Path) -> None:
    application, authority, _path, blocker = _application_after_dashboard_custody_race(tmp_path)

    application.process_observation(Observation(blocker, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))
    application.settle()

    assert application._runtime().engine.marking.place(NetPath("ready.deferred")) == ()
    assert len([item for item in authority.transport.comments if "hamsterdan:readiness" in str(item["body"])]) == 1
    wakes = [
        record
        for record in application._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and str(record.source) == "on_announce_wake"
    ]
    assert len(wakes) == 1
    application.close()


def test_v5_deferred_announcement_settles_old_authority_moved_before_fresh_request(tmp_path: Path) -> None:
    application, authority, _path, blocker = _application_after_dashboard_custody_race(tmp_path)
    authority.pull = replace(authority.pull, base="c" * 40)
    authority.repo_policy = replace(authority.repo_policy, digest="policy-2")

    application.process_observation(Observation(blocker, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))
    application.settle()

    records = tuple(application._runtime().engine.records)
    requests = [
        record.input["work"]
        for record in records
        if isinstance(record, ActivityRequested) and str(record.transition) == "ready.gate"
    ]
    terminals = [
        record.result["$variant"]
        for record in records
        if isinstance(record, ActivityCompleted) and str(record.transition) == "ready.gate"
    ]
    assert len(requests) == 3
    assert requests[0] == requests[1]
    assert (requests[2]["base"], requests[2]["policy"]) == ("c" * 40, "policy-2")
    assert terminals == ["ADeferred", "AMoved", "ALanded"]
    assert len([item for item in authority.transport.comments if "hamsterdan:readiness" in str(item["body"])]) == 1
    application.close()


def test_v5_readiness_wakes_when_custody_terminalizes_during_the_deferral_fold(tmp_path: Path) -> None:
    application, authority, _path, blocker = _application_after_dashboard_custody_race(
        tmp_path,
        terminalize_during_claim=True,
    )

    records = tuple(application._runtime().engine.records)
    assert application._runtime().engine.marking.place(NetPath("ready.deferred")) == ()
    deferred = [
        record
        for record in records
        if isinstance(record, ActivityCompleted)
        and str(record.transition) == "ready.gate"
        and record.result.get("$variant") == "ADeferred"
    ]
    assert len(deferred) == 1 and deferred[0].result["blocker"] == blocker
    assert len([item for item in authority.transport.comments if "hamsterdan:readiness" in str(item["body"])]) == 1
    wakes = [
        record
        for record in records
        if isinstance(record, ExternalEventDelivered) and str(record.source) == "on_announce_wake"
    ]
    assert len(wakes) == 1
    application.close()


def test_v5_announcement_wake_replays_after_restart_when_delivery_ack_is_lost(tmp_path: Path) -> None:
    first, authority, path, blocker = _application_after_dashboard_custody_race(tmp_path)
    first.close()
    with sqlite3.connect(path) as database:
        database.execute("UPDATE inbox SET status='terminal' WHERE delivery_id=?", (blocker,))

    def opened() -> PrReadinessV5Application:
        return PrReadinessV5Application(
            tmp_path / "application",
            SUBJECT,
            authority,  # type: ignore[arg-type]
            Runner(),  # type: ignore[arg-type]
            agent_settle=lambda operations: None,
            bot_login="hamsterdan-test[bot]",
            public_clone_url="https://github.com/owner/repo.git",
            custody_path=path,
        )

    second = opened()
    runtime = second._runtime()
    deliver_wake = runtime.deliver_announce_wake

    def commit_then_lose_ack(value, identity):
        deliver_wake(value, identity)
        raise RuntimeError("announcement wake acknowledgement lost")

    runtime.deliver_announce_wake = commit_then_lose_ack  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="acknowledgement lost"):
        second.settle()
    second.close()

    third = opened()
    third.settle()

    assert len([item for item in authority.transport.comments if "hamsterdan:readiness" in str(item["body"])]) == 1
    wake_deliveries = [
        record.identity
        for record in third._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and str(record.source) == "on_announce_wake"
    ]
    assert len(wake_deliveries) == 1 and wake_deliveries[0].startswith("v5-announce-wake:")
    third.close()


def test_v5_review_waits_for_custodied_authority_then_retries_without_losing_its_baton(tmp_path: Path) -> None:
    class AttemptRunner(Runner):
        def __init__(self) -> None:
            super().__init__()
            self.review_calls: list[tuple[str, int]] = []

        def review(self, repository_url, request, *, operation, attempt, is_current=None):
            self.review_calls.append((operation, attempt))
            assert is_current is not None and is_current()
            return ReviewResult(
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                "clear",
                [],
                [],
            )

    identity = delivery()
    blocker = delivery()
    path = tmp_path / "webhooks.sqlite3"
    runner = AttemptRunner()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        Authority(),  # type: ignore[arg-type]
        runner,  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=path,
    )
    application.process_observation(Observation(identity, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE inbox (delivery_id TEXT PRIMARY KEY, status TEXT NOT NULL, observation TEXT NOT NULL)"
        )
        database.execute(
            "INSERT INTO inbox VALUES (?, 'pending', ?)",
            (
                blocker,
                json.dumps({"installation_id": 44, "repository_id": 31, "pull_request_number": 7}),
            ),
        )

    application.settle()

    records = tuple(application._runtime().engine.records)
    assert runner.review_calls == []
    assert not any(isinstance(record, (ActivityFailed, FiringFailed)) for record in records)
    [deferred] = application._runtime().engine.marking.place(NetPath("review.deferred"))
    assert deferred.data["blocker"] == blocker

    with sqlite3.connect(path) as database:
        database.execute("UPDATE inbox SET status='terminal' WHERE delivery_id=?", (blocker,))
    application.settle()

    assert runner.review_calls == [(f"review:{SUBJECT}:{'a' * 40}:i1", 2)]
    assert application._runtime().engine.marking.place(NetPath("review.deferred")) == ()
    [ready] = application._runtime().engine.marking.place(NetPath("ready.snap"))
    assert ready.data["review"] == "clear"
    application.close()


def test_v5_review_wake_replays_after_restart_when_delivery_ack_is_lost(tmp_path: Path) -> None:
    class AttemptRunner(Runner):
        def __init__(self) -> None:
            super().__init__()
            self.review_calls: list[int] = []

        def review(self, repository_url, request, *, operation, attempt, is_current=None):
            self.review_calls.append(attempt)
            assert is_current is not None and is_current()
            return ReviewResult(
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                "clear",
                [],
                [],
            )

    path = tmp_path / "webhooks.sqlite3"
    root = tmp_path / "application"
    blocker = delivery()
    runner = AttemptRunner()

    def opened() -> PrReadinessV5Application:
        return PrReadinessV5Application(
            root,
            SUBJECT,
            Authority(),  # type: ignore[arg-type]
            runner,  # type: ignore[arg-type]
            agent_settle=lambda operations: None,
            bot_login="hamsterdan-test[bot]",
            public_clone_url="https://github.com/owner/repo.git",
            custody_path=path,
        )

    first = opened()
    first.process_observation(Observation(delivery(), "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE inbox (delivery_id TEXT PRIMARY KEY, status TEXT NOT NULL, observation TEXT NOT NULL)"
        )
        database.execute(
            "INSERT INTO inbox VALUES (?, 'pending', ?)",
            (
                blocker,
                json.dumps({"installation_id": 44, "repository_id": 31, "pull_request_number": 7}),
            ),
        )
    first.settle()
    first.close()
    with sqlite3.connect(path) as database:
        database.execute("UPDATE inbox SET status='terminal' WHERE delivery_id=?", (blocker,))

    second = opened()
    runtime = second._runtime()
    deliver_wake = runtime.deliver_review_wake

    def commit_then_lose_ack(value, identity):
        deliver_wake(value, identity)
        raise RuntimeError("review wake acknowledgement lost")

    runtime.deliver_review_wake = commit_then_lose_ack  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="acknowledgement lost"):
        second.settle()
    second.close()

    third = opened()
    third.settle()

    assert runner.review_calls == [2]
    wake_deliveries = [
        record.identity
        for record in third._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and str(record.source) == "on_review_round_wake"
    ]
    assert len(wake_deliveries) == 1 and wake_deliveries[0].startswith("v5-review-wake:")
    third.close()


@pytest.mark.parametrize(
    ("derived_identity", "message"),
    [(False, "identity is malformed"), (True, "has no deferred round")],
)
def test_v5_restart_fails_closed_on_malformed_review_wake_history(
    tmp_path: Path,
    derived_identity: bool,
    message: str,
) -> None:
    root = tmp_path / "application"
    options = {
        "agent_settle": lambda operations: None,
        "bot_login": "hamsterdan-test[bot]",
        "public_clone_url": "https://github.com/owner/repo.git",
        "custody_path": tmp_path / "webhooks.sqlite3",
    }
    first = PrReadinessV5Application(
        root,
        SUBJECT,
        Authority(),  # type: ignore[arg-type]
        Runner(),  # type: ignore[arg-type]
        **options,
    )
    runtime = first._runtime()
    wake = RoundWake(
        operation=f"review:{SUBJECT}:{'a' * 40}:i1",
        attempt=1,
        blocker=delivery(),
    )
    identity = runtime.review_wake_identity(wake) if derived_identity else "malformed-review-wake-identity"
    runtime.deliver_review_wake(wake, identity)
    first.close()

    with pytest.raises(RuntimeError, match=message):
        PrReadinessV5Application(
            root,
            SUBJECT,
            Authority(),  # type: ignore[arg-type]
            Runner(),  # type: ignore[arg-type]
            **options,
        )


@pytest.mark.parametrize(
    ("derived_identity", "message"),
    [(False, "identity is malformed"), (True, "has no deferred request")],
)
def test_v5_restart_fails_closed_on_malformed_announcement_wake_history(
    tmp_path: Path,
    derived_identity: bool,
    message: str,
) -> None:
    root = tmp_path / "application"
    options = {
        "agent_settle": lambda operations: None,
        "bot_login": "hamsterdan-test[bot]",
        "public_clone_url": "https://github.com/owner/repo.git",
        "custody_path": tmp_path / "webhooks.sqlite3",
    }
    first = PrReadinessV5Application(
        root,
        SUBJECT,
        Authority(),  # type: ignore[arg-type]
        Runner(),  # type: ignore[arg-type]
        **options,
    )
    runtime = first._runtime()
    wake = AWake(
        op=f"ready:{'a' * 40}:i1",
        incarnation=1,
        head="a" * 40,
        base="b" * 40,
        policy="policy-1",
        strict_base=True,
        base_current=True,
        blocker=delivery(),
    )
    identity = runtime.announce_wake_identity(wake) if derived_identity else "malformed-announce-wake-identity"
    runtime.deliver_announce_wake(wake, identity)
    first.close()

    with pytest.raises(RuntimeError, match=message):
        PrReadinessV5Application(
            root,
            SUBJECT,
            Authority(),  # type: ignore[arg-type]
            Runner(),  # type: ignore[arg-type]
            **options,
        )


def test_v5_durable_publications_use_an_instance_queue_owned_by_the_application(tmp_path: Path) -> None:
    identity = delivery()
    authority = Authority()
    dispatch_path = tmp_path / "activity-dispatch.sqlite3"
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        Runner(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
        dispatch_path=dispatch_path,
    )
    application.process_observation(Observation(identity, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))
    application.settle()
    production = LocalDispatch(dispatch_path, instance="inspector").worker(("publication",))

    assert production.claim() is None
    assert application.run_durable_activities(20) > 0
    application.settle()

    production.close()
    application.close()


def test_v5_comment_classification_is_frozen_and_settled_only_after_manifest_commit(tmp_path: Path) -> None:
    identity = delivery()
    authority = Authority()
    runner = Runner()
    settled: list[set[str]] = []
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        runner,  # type: ignore[arg-type]
        agent_settle=lambda operations: settled.append(operations),
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    observation = Observation(identity, "issue_comment", "created", 44, 23, 31, "owner/repo", 7)
    conversation = AdmittedConversation(identity, 19, 5, "human", "MEMBER", "please change it")

    application.process_observation(observation, conversation=conversation)
    application.process_observation(observation, conversation=conversation)

    manifest = application.ingress.manifest(identity, SUBJECT)
    assert manifest is not None and manifest.entries[-1].payload == {
        "id": "19",
        "kind": "change",
        "arg": "rename the value",
        "authorized": True,
    }
    operation = f"conversation:owner/repo:pr:7:delivery:{identity}"
    assert runner.conversation_calls == 1
    assert settled == [{operation}, {operation}]
    application.close()


@pytest.mark.parametrize(
    "recovery_operation",
    [
        "push:comment:5312521927:" + "a" * 40 + ":i1",
        "findings:" + "a" * 40 + ":i1",
        "rerun:L1:fingerprint",
        "reminder:timer-1",
        "reply:comment-1",
        "dash:digest-1",
        "ready:" + "a" * 40 + ":i1",
    ],
)
def test_v5_publication_recovery_preserves_the_explicit_operation_at_ingress(
    tmp_path: Path, recovery_operation: str
) -> None:
    identity = delivery()

    class RecoveryRunner(Runner):
        def converse(self, repository_url, request, *, operation: str, attempt: int, is_current=None):
            declaration = next(item for item in request.allowed_intents if item["type"] == "recover_publication")
            assert declaration == {
                "type": "recover_publication",
                "mutation": False,
                "arguments": ["operation"],
                "requires_explicit": True,
            }
            assert attempt == 1 and is_current is not None and is_current()
            return ConversationResult(
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                [{"type": "recover_publication", "arguments": {"operation": recovery_operation}}],
            )

    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        Authority(),  # type: ignore[arg-type]
        RecoveryRunner(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    observation = Observation(identity, "issue_comment", "created", 44, 23, 31, "owner/repo", 7)
    conversation = AdmittedConversation(
        identity,
        19,
        5,
        "human",
        "MEMBER",
        f"recover publication for `{recovery_operation}`",
    )

    application.process_observation(observation, conversation=conversation)

    manifest = application.ingress.manifest(identity, SUBJECT)
    assert manifest is not None and manifest.entries[-1].payload == {
        "id": "19",
        "kind": "recover_publication",
        "arg": recovery_operation,
        "authorized": True,
    }
    application.close()


@pytest.mark.parametrize(
    ("arguments", "comment"),
    [
        ({"operation": "push:comment:1:head:i1"}, "recover the publication"),
        (
            {"target": "mutation", "operation": "push:comment:1:head:i1"},
            "recover push:comment:1:head:i1",
        ),
        ({"operation": "push:bad operation"}, "recover push:bad operation"),
        ({"operation": "p" * 257}, "recover " + "p" * 257),
    ],
)
def test_v5_publication_recovery_requires_one_bounded_verbatim_operation(
    tmp_path: Path, arguments: dict[str, str], comment: str
) -> None:
    identity = delivery()

    class InvalidRecoveryRunner(Runner):
        def converse(self, repository_url, request, *, operation: str, attempt: int, is_current=None):
            return ConversationResult(
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                [{"type": "recover_publication", "arguments": arguments}],
            )

    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        Authority(),  # type: ignore[arg-type]
        InvalidRecoveryRunner(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    observation = Observation(identity, "issue_comment", "created", 44, 23, 31, "owner/repo", 7)
    conversation = AdmittedConversation(identity, 19, 5, "human", "MEMBER", comment)

    application.process_observation(observation, conversation=conversation)

    manifest = application.ingress.manifest(identity, SUBJECT)
    assert manifest is not None and manifest.entries[-1].payload == {
        "id": "19",
        "kind": "",
        "arg": "",
        "authorized": False,
    }
    application.close()


def test_comment_route_settlement_replays_after_crash_following_manifest_commit(tmp_path: Path) -> None:
    identity = delivery()
    authority = Authority()
    runner = Runner()
    operation = f"conversation:owner/repo:pr:7:delivery:{identity}"
    settlements = 0

    def crash_once(operations: set[str]) -> None:
        nonlocal settlements
        assert operations == {operation}
        settlements += 1
        if settlements == 1:
            raise RuntimeError("crash after manifest commit")

    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        runner,  # type: ignore[arg-type]
        agent_settle=crash_once,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    observation = Observation(identity, "issue_comment", "created", 44, 23, 31, "owner/repo", 7)
    conversation = AdmittedConversation(identity, 19, 5, "human", "MEMBER", "please change it")

    with pytest.raises(RuntimeError, match="crash after manifest commit"):
        application.process_observation(observation, conversation=conversation)
    application.process_observation(observation, conversation=conversation)

    assert runner.conversation_calls == 1
    assert settlements == 2
    application.close()


def test_ambiguous_petrus_delivery_reopens_history_before_exact_retry(tmp_path: Path) -> None:
    identity = delivery()
    authority = Authority()
    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        authority,  # type: ignore[arg-type]
        Runner(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    observation = Observation(identity, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7)
    runtime = application._runtime()
    engine = runtime.engine
    deliver = engine.deliver

    def commit_then_lose_ack(*args, **kwargs):
        deliver(*args, **kwargs)
        raise RuntimeError("acknowledgement lost")

    engine.deliver = commit_then_lose_ack  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="acknowledgement lost"):
        application.process_observation(observation)

    assert runtime.engine is not engine
    application.process_observation(observation)
    identities = [record.identity for record in runtime.engine.records if isinstance(record, ExternalEventDelivered)]
    assert identities == [
        f"github-delivery:{identity}:on_head",
        f"github-delivery:{identity}:on_ready",
        f"github-delivery:{identity}:on_human",
        f"github-delivery:{identity}:on_runs",
    ]
    application.close()


def timer_application(
    tmp_path: Path,
    clock: list[int],
    authority: Authority | None = None,
) -> PrReadinessV5Application:
    return PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        Authority() if authority is None else authority,  # type: ignore[arg-type]
        Runner(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
        reminder_delay=10,
        timer_clock_us=lambda: clock[0],
    )


def test_v5_settle_reaches_timer_fixed_point_and_returns_canonical_store_deadline(tmp_path: Path) -> None:
    clock = [1_000_000]
    identity = delivery()
    application = timer_application(tmp_path, clock)
    application.process_observation(Observation(identity, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))

    armed = application.settle()

    assert armed.next_maturation == 11.0
    assert application._runtime().timer_command() is None
    [state] = application._runtime().engine.marking.place(NetPath("rem.state"))
    assert state.data["clock"]["kind"] == "armed"

    clock[0] = 11_000_000
    rearmed = application.settle()

    assert rearmed.next_maturation == 21.0
    [state] = application._runtime().engine.marking.place(NetPath("rem.state"))
    assert state.data["matured"] == [f"timer:{SUBJECT}:i1:s0"]
    timer_events = [
        record.identity
        for record in application._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and str(record.source) == "on_timer"
    ]
    assert timer_events == [f"v5-timer-due:timer:{SUBJECT}:i1:s0:11000000"]
    application.close()


@pytest.mark.parametrize("cut", ["before_history", "after_history"])
def test_timer_ack_crash_cuts_replay_one_identity_and_original_deadline(tmp_path: Path, cut: str) -> None:
    clock = [1_000_000]
    identity = delivery()
    first = timer_application(tmp_path, clock)
    first.process_observation(Observation(identity, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))
    runtime = first._runtime()
    runtime.drain()  # freeze the TimerCommand in canonical History
    original = runtime.deliver_timer_ack

    def crash(value, timer_identity):
        if cut == "after_history":
            original(value, timer_identity)
        raise RuntimeError(f"{cut} timer ack")

    runtime.deliver_timer_ack = crash  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match=cut):
        first.settle()
    first.close()

    second = timer_application(tmp_path, clock)
    outcome = second.settle()

    assert outcome.next_maturation == 11.0
    timer_acks = [
        record.identity
        for record in second._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and str(record.source) == "on_timer_command_applied"
    ]
    assert timer_acks == [f"v5-timer-command-applied:timer-command:{SUBJECT}:g1"]
    second.close()


def test_timer_maturity_history_marker_crash_replays_without_duplicate_fact(tmp_path: Path) -> None:
    clock = [1_000_000]
    identity = delivery()
    first = timer_application(tmp_path, clock)
    first.process_observation(Observation(identity, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))
    assert first.settle().next_maturation == 11.0
    clock[0] = 11_000_000
    runtime = first._runtime()
    original = runtime.deliver_timer_due

    def commit_then_crash(value, timer_identity):
        original(value, timer_identity)
        raise RuntimeError("maturity marker lost")

    runtime.deliver_timer_due = commit_then_crash  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="maturity marker lost"):
        first.settle()
    first.close()

    second = timer_application(tmp_path, clock)
    assert second.settle().next_maturation == 21.0
    due = [
        record.identity
        for record in second._runtime().engine.records
        if isinstance(record, ExternalEventDelivered) and str(record.source) == "on_timer"
    ]
    assert due == [f"v5-timer-due:timer:{SUBJECT}:i1:s0:11000000"]
    second.close()


def test_disposable_runnable_index_rebuilds_from_intact_timer_custody(tmp_path: Path) -> None:
    clock = [1_000_000]
    identity = delivery()
    first = timer_application(tmp_path, clock)
    first.process_observation(Observation(identity, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))
    deadline = first.settle().next_maturation
    first.close()
    assert deadline == 11.0

    path = tmp_path / "runnable.sqlite3"
    index = RunnableIndex(path)
    index.replace_timer(SUBJECT, deadline)
    index.close()
    path.unlink()

    second = timer_application(tmp_path, clock)
    rebuilt_deadline = second.settle().next_maturation
    rebuilt = RunnableIndex(path)
    rebuilt.replace_timer(SUBJECT, rebuilt_deadline)

    assert rebuilt_deadline == deadline
    assert rebuilt.take_due(now=11.0) == (SUBJECT,)
    rebuilt.close()
    second.close()


def test_v5_close_cancels_exact_host_timer_before_reminder_loop_retires(tmp_path: Path) -> None:
    clock = [1_000_000]
    authority = Authority()
    application = timer_application(tmp_path, clock, authority)
    opened = delivery()
    application.process_observation(Observation(opened, "pull_request", "synchronize", 44, 23, 31, "owner/repo", 7))
    assert application.settle().next_maturation == 11.0

    authority.pull = replace(authority.pull, state="closed", closed=True)
    closed = delivery()
    application.process_observation(Observation(closed, "pull_request", "closed", 44, 23, 31, "owner/repo", 7))
    outcome = application.settle()

    assert outcome.next_maturation is None
    assert not application._runtime().engine.marking.place(NetPath("rem.state"))
    [done] = application._runtime().engine.marking.place(NetPath("rem.done"))
    assert done.data["reason"] == "closed"
    with sqlite3.connect(tmp_path / "application" / "timers.sqlite3") as database:
        assert database.execute("SELECT state FROM v5_timers ORDER BY timer_id").fetchall() == [("cancelled",)]
    application.close()


def test_v5_comment_classification_reads_the_published_findings_and_board_facts(tmp_path: Path) -> None:
    """A comment such as "apply your suggested fixes" must be interpreted
    against the findings and gate states its author saw on the PR — an
    empty context makes the agent deny its own published review."""
    finding = {
        "id": "f-ttl-unit",
        "path": "gate.py",
        "line": 10,
        "related_locations": [],
        "title": "Interpret the lease TTL as seconds",
        "body": "ttl_seconds is passed as minutes.",
        "severity": "high",
        "confidence": 1.0,
        "evidence": "timedelta(minutes=ttl_seconds)",
        "blocking": True,
        "suggestion": "",
    }
    captured = []

    class BlockingRunner(Runner):
        def review(self, repository_url, request, *, operation, attempt, is_current=None):
            return ReviewResult(
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                "blocking",
                [dict(finding)],
                [],
            )

        def converse(self, repository_url, request, *, operation, attempt, is_current=None):
            captured.append(request)
            return super().converse(
                repository_url, request, operation=operation, attempt=attempt, is_current=is_current
            )

    application = PrReadinessV5Application(
        tmp_path / "application",
        SUBJECT,
        Authority(),  # type: ignore[arg-type]
        BlockingRunner(),  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login="hamsterdan-test[bot]",
        public_clone_url="https://github.com/owner/repo.git",
        custody_path=tmp_path / "webhooks.sqlite3",
    )
    application.process_observation(Observation(delivery(), "pull_request", "opened", 44, 23, 31, "owner/repo", 7))
    application.settle()

    identity = delivery()
    observation = Observation(identity, "issue_comment", "created", 44, 23, 31, "owner/repo", 7)
    conversation = AdmittedConversation(identity, 19, 5, "human", "MEMBER", "apply your suggested fixes")
    application.process_observation(observation, conversation=conversation)

    [request] = captured
    assert request.findings == [finding]
    kinds = [fact["kind"] for fact in request.gates]
    assert {"state", "checks", "review", "findings"} <= set(kinds)
    [findings_fact] = [fact for fact in request.gates if fact["kind"] == "findings"]
    assert (findings_fact["body"]["count"], findings_fact["body"]["blocking"]) == (1, 1)
    application.close()
