"""Durable custody contracts for V5 webhook ingress."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from petrus.impetus.history import ExternalEventDelivered
from petrus.impetus.petrinet import NetPath
from petrus.motus.dispatch import LocalDispatch

from hamsterdan.agents.protocol import ConversationResult, ReviewResult
from hamsterdan.contracts.readiness import AdmittedConversation
from hamsterdan.contracts.readiness_v5 import CommentSeen, DraftSeen, HeadSeen, HumanSeen, ReadySeen
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
from hamsterdan.host.v5.application import PrReadinessV5Application
from hamsterdan.host.v5.ingress import IngressEntry, V5IngressNormalizer, V5IngressStore

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
