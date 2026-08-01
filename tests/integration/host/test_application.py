from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from hamsterdan.agents import AgentProtocolError, CodingResult, ConversationResult, ReviewResult
from hamsterdan.contracts.readiness import workflow_gates_ready
from hamsterdan.github_app.models import (
    ActionsJobSnapshot,
    ActionsRunSnapshot,
    HumanReviewSnapshot,
    PullRequestSnapshot,
    RepositoryPolicy,
    WireResponse,
)
from hamsterdan.host.application import PrReadinessApplication

HEAD, HEAD_2, BASE = "a" * 40, "c" * 40, "b" * 40
BOT = "hamster-dan[bot]"
SECRETS = ("ghs_installation_secret_value", "github_pat_secret_value")


class CommentTransport:
    def __init__(self) -> None:
        self.comments: list[dict[str, Any]] = []
        self.writes: list[tuple[str, str, dict[str, Any]]] = []

    def pages(self, path: str) -> tuple[dict[str, Any], ...]:
        assert path.endswith("/issues/3/comments?per_page=100")
        return tuple(self.comments)

    def request(self, method: str, path: str, body=None) -> WireResponse:
        assert method in {"POST", "PATCH"} and isinstance(body, dict)
        self.writes.append((method, path, body))
        if method == "POST":
            item = {
                "id": len(self.comments) + 1,
                "html_url": f"https://example.invalid/comments/{len(self.comments) + 1}",
                "body": body["body"],
                "user": {"id": 999, "login": BOT},
            }
            self.comments.append(item)
            return WireResponse(201, item)
        identifier = int(path.rsplit("/", 1)[1])
        item = next(comment for comment in self.comments if comment["id"] == identifier)
        item["body"] = body["body"]
        return WireResponse(200, item)


class Authority:
    repository, pr_number = "owner/repo", 3

    def __init__(self) -> None:
        self.transport = CommentTransport()
        self.pull = PullRequestSnapshot(
            self.repository,
            self.pr_number,
            "open",
            True,
            HEAD,
            BASE,
            "topic",
            "main",
            True,
            False,
            False,
            "author",
            "clean",
            "https://example.invalid/pr/3",
            self.repository,
        )
        self.policy_value = RepositoryPolicy(False, False, ("unit",), 0, False, "test", "policy")
        self.review = HumanReviewSnapshot((), (), (), (), 0, "available")
        self.run = ActionsRunSnapshot(11, HEAD, ".github/workflows/ci.yml", 1, "completed", "success")

    def pull_request(self):
        return self.pull

    def policy(self, base_ref: str):
        assert base_ref == "main"
        return self.policy_value

    def base_current(self, pull: PullRequestSnapshot):
        return pull.base == BASE

    def human_review(self):
        return self.review

    def comments(self):
        return tuple(self.transport.comments)

    def select_run(self, workflow: str, head: str):
        return self.run if self.run.head == head else None

    def workflow_runs(self, workflow: str, head: str):
        run = self.select_run(workflow, head)
        return () if run is None else (run,)

    def jobs(self, run: ActionsRunSnapshot, required: tuple[str, ...]):
        return replace(run, jobs=(ActionsJobSnapshot(21, "unit", "completed", run.conclusion, True),))

    def run_result(self, run: ActionsRunSnapshot):
        return {
            "run_id": str(run.id),
            "head": run.head,
            "attempt": run.attempt,
            "status": run.status,
            "conclusion": run.conclusion or "pending",
            "required_jobs": ("unit",),
        }


class Runner:
    def __init__(self) -> None:
        self.reviews = self.conversations = self.codes = 0
        self.requests: list[object] = []

    def review(self, repository_url, request, *, is_current=None):
        self.reviews += 1
        self.requests.append(request)
        assert is_current is None or is_current()
        return ReviewResult(
            request.repository, request.pull_request, request.epoch, request.head, request.base, "clear", [], []
        )

    def converse(self, repository_url, request, *, is_current=None):
        self.conversations += 1
        self.requests.append(request)
        text = str(request.comment_context.get("text", ""))
        pending = request.dashboard.get("pending_intent", {})
        if text == "Please fix the finding":
            intents = [
                {
                    "type": "change",
                    "arguments": {"request": "fix the finding"},
                    "mutation": True,
                    "explicit": True,
                    "confidence": 1,
                    "confirmation": False,
                }
            ]
        elif (
            text == "This is not a confirmation"
            and isinstance(pending, dict)
            or text.startswith("Confirm the pending change mutation with digest")
            and isinstance(pending, dict)
        ) and pending.get("arguments"):
            intents = [
                {
                    "type": "change",
                    "arguments": pending["arguments"],
                    "mutation": True,
                    "explicit": True,
                    "confidence": 1,
                    "confirmation": True,
                }
            ]
        else:
            intents = [
                {
                    "type": "status",
                    "arguments": {},
                    "mutation": False,
                    "explicit": False,
                    "confidence": 1,
                    "confirmation": False,
                }
            ]
        return ConversationResult(
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            intents,
        )

    def code(self, repository_url, request, *, is_current=None):
        self.codes += 1
        self.requests.append(request)
        return CodingResult(
            request.kind,
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            request.ref,
            "unchanged",
            "not_attempted",
            "",
            [],
            [],
            "",
        )


class UnavailableRunner(Runner):
    def review(self, repository_url, request, *, is_current=None):
        self.reviews += 1
        raise AgentProtocolError("provider unavailable")

    def code(self, repository_url, request, *, is_current=None):
        self.codes += 1
        raise AgentProtocolError("provider unavailable")


class RecoveringReviewRunner(Runner):
    def review(self, repository_url, request, *, is_current=None):
        if self.reviews < 2:
            self.reviews += 1
            raise AgentProtocolError("provider unavailable")
        return super().review(repository_url, request, is_current=is_current)


def application(tmp_path: Path, authority: Authority, runner: Runner) -> PrReadinessApplication:
    return PrReadinessApplication(
        tmp_path / "state",
        "github-1-pr-3",
        authority,
        runner,  # type: ignore[arg-type]
        bot_login=BOT,
        public_clone_url=str(tmp_path),
        reminder_delay=10**30,
    )


def ready(authority: Authority) -> None:
    authority.pull = replace(authority.pull, draft=False)


def test_draft_ready_dormant_and_same_head_resume(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    subject = application(tmp_path, authority, runner)
    assert subject.reconcile() == {"instance": "absent", "provider_state": "open", "wait": "first ready observation"}
    assert not (tmp_path / "state/history.jsonl").exists()
    ready(authority)
    assert subject.reconcile("ready")["epoch"] == 1
    assert runner.reviews == 1 and any("hamsterdan:dashboard" in x["body"] for x in authority.transport.comments)
    writes = len(authority.transport.writes)
    authority.pull = replace(authority.pull, draft=True)
    assert subject.reconcile("draft")["instance"] == "dormant" and len(authority.transport.writes) == writes
    ready(authority)
    resumed = subject.reconcile("ready-again")
    assert (resumed["epoch"], resumed["head"], runner.reviews) == (2, HEAD, 2)
    subject.close()


def test_new_head_and_closed_terminal_absorb_late_poll(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    assert subject.reconcile()["epoch"] == 1
    authority.pull = replace(authority.pull, head=HEAD_2)
    authority.run = replace(authority.run, head=HEAD_2, id=12)
    assert subject.reconcile("synchronize")["epoch"] == 2
    authority.pull = replace(authority.pull, state="closed", closed=True)
    assert subject.reconcile("closed")["status"] == "abort"
    writes = len(authority.transport.writes)
    assert subject.reconcile("late")["status"] == "abort" and len(authority.transport.writes) == writes
    subject.close()


def test_merged_is_terminal_success_without_merge_commit_identity(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    subject.reconcile()
    authority.pull = replace(authority.pull, state="closed", closed=True, merged=True)
    terminal = subject.reconcile("merged")
    assert (terminal["instance"], terminal["status"], terminal["head"]) == ("terminal", "success", HEAD)
    subject.close()


def test_mention_conversation_uses_current_dashboard_and_exact_two_comment_confirmation(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    subject.reconcile()
    common = {"actor_id": 7, "actor_login": "author", "actor_type": "User", "association": "OWNER"}
    assert not subject.route_comment(delivery_id="old", comment_id=30, text="/impetus status", **common)["routed"]
    assert not subject.route_comment(delivery_id="slash", comment_id=30, text="/hamsterdan status", **common)["routed"]
    authority.transport.comments.append({"id": 90, "body": "<!-- impetus:dashboard -->", "user": {"login": BOT}})
    subject.route_comment(delivery_id="status", comment_id=31, text="@hamster-dan How is this looking?", **common)
    assert runner.conversations == 1 and any(
        "Readiness is ready; no current blockers" in x["body"] for x in authority.transport.comments
    )
    request = runner.requests[-1]
    assert request.comment_context["text"] == "How is this looking?"
    assert request.dashboard["head"] == HEAD
    assert request.dashboard["findings"] == []
    assert request.gates[0] == {"name": "overall", "ready": True, "blocker": ""}
    subject.route_comment(delivery_id="change", comment_id=32, text="@hamster-dan Please fix the finding", **common)
    control = subject.host.control  # type: ignore[union-attr]
    assert runner.codes == 0 and control is not None and control.mutation_pending
    assert any(
        "@hamster-dan" in comment["body"] and control.pending_intent_digest in comment["body"]
        for comment in authority.transport.comments
    )
    subject.route_comment(
        delivery_id="not-confirmation",
        comment_id=33,
        text="@hamster-dan This is not a confirmation",
        **common,
    )
    assert runner.codes == 0
    control = subject.host.control  # type: ignore[union-attr]
    assert control is not None and control.mutation_pending
    assert any("could not interpret" in comment["body"] for comment in authority.transport.comments)
    subject.route_comment(
        delivery_id="wrong-digest",
        comment_id=34,
        text=f"@hamster-dan Confirm the pending change mutation with digest {'0' * 64}",
        **common,
    )
    assert runner.codes == 0
    subject.route_comment(
        delivery_id="confirm",
        comment_id=35,
        text=f"@hamster-dan Confirm the pending change mutation with digest {control.pending_intent_digest}",
        **common,
    )
    assert runner.codes == 3
    subject.route_comment(
        delivery_id="duplicate-confirmation",
        comment_id=36,
        text=f"@hamster-dan Confirm the pending change mutation with digest {control.pending_intent_digest}",
        **common,
    )
    assert runner.codes == 3
    subject.close()


@pytest.mark.parametrize("changes", [{"actor_type": "Bot"}, {"association": "NONE"}, {"actor_login": BOT}])
def test_only_trusted_addressed_users_route(tmp_path: Path, changes: dict[str, str]) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    subject.reconcile()
    values = {
        "delivery_id": "x",
        "comment_id": 4,
        "actor_id": 999,
        "actor_login": "human",
        "actor_type": "User",
        "association": "MEMBER",
        "text": "@hamster-dan explain the blockers",
    } | changes
    assert not subject.route_comment(**values)["routed"]
    assert runner.conversations == 0
    subject.close()


def test_first_failure_reruns_once_then_flaky_green(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.run = replace(authority.run, conclusion="failure")
    subject = application(tmp_path, authority, runner)
    assert subject.reconcile()["actions"] in {"failed", "waiting"}
    markers = lambda: [x for x in authority.transport.comments if "hamsterdan-rerun" in x["body"]]
    assert len(markers()) == 1
    subject.reconcile("same-failure")
    assert len(markers()) == 1
    authority.run = replace(authority.run, attempt=2, conclusion="success")
    assert subject.reconcile("complete")["actions"] == "flaky_green"
    subject.close()


def test_failed_rerun_reproduces_after_running_observation(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.run = replace(authority.run, conclusion="failure")
    subject = application(tmp_path, authority, runner)
    subject.reconcile()
    authority.run = replace(authority.run, attempt=2, status="in_progress", conclusion=None)
    assert subject.reconcile("running")["actions"] == "running"
    authority.run = replace(authority.run, status="completed", conclusion="failure")
    assert subject.reconcile("failed")["actions"] == "reproduced" and runner.codes == 3
    subject.close()


def test_first_later_attempt_failure_still_reruns_before_repair(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.run = replace(authority.run, attempt=2, conclusion="failure")
    subject = application(tmp_path, authority, runner)
    assert subject.reconcile()["actions"] == "waiting" and runner.codes == 0
    subject.reconcile("same")
    assert runner.codes == 0
    authority.run = replace(authority.run, attempt=3)
    assert subject.reconcile("failed")["actions"] == "reproduced" and runner.codes == 3
    subject.close()


def test_provider_failures_are_typed_inability_and_recovery(tmp_path: Path) -> None:
    authority, runner = Authority(), UnavailableRunner()
    ready(authority)
    authority.run = replace(authority.run, attempt=2, conclusion="failure")
    subject = application(tmp_path, authority, runner)
    first = subject.reconcile()
    assert first["review"] == "unable" and first["actions"] == "waiting"
    authority.run = replace(authority.run, attempt=3)
    recovered = subject.reconcile("failed")
    control = subject.host.control  # type: ignore[union-attr]
    assert recovered["actions"] == "reproduced" and control is not None and not control.repair_in_flight
    assert control.wait == "repair recovery" and runner.codes == 3
    subject.close()


def test_same_basis_reconciliation_recovers_review_with_bounded_distinct_attempts(tmp_path: Path) -> None:
    authority, runner = Authority(), RecoveringReviewRunner()
    ready(authority)
    subject = application(tmp_path, authority, runner)

    assert subject.reconcile("attempt-1")["review"] == "unable"
    assert subject.reconcile("attempt-2")["review"] == "unable"
    assert subject.reconcile("attempt-3")["review"] == "clear"
    assert runner.reviews == 3
    subject.reconcile("settled")
    assert runner.reviews == 3
    subject.close()


def test_same_basis_reconciliation_stops_after_three_unavailable_reviews(tmp_path: Path, caplog) -> None:
    authority, runner = Authority(), UnavailableRunner()
    ready(authority)
    subject = application(tmp_path, authority, runner)

    projection = {}
    for attempt in range(1, 7):
        projection = subject.reconcile(f"attempt-{attempt}")

    control = subject.host.control  # type: ignore[union-attr]
    assert runner.reviews == 3
    assert projection["review"] == "unable"
    assert control is not None and control.review_attempts == 3
    assert "agent activity unavailable kind=review category=protocol" in caplog.text
    assert "provider unavailable" not in caplog.text
    subject.close()


def test_restart_one_history_has_no_duplicate_agent_or_publication(tmp_path: Path) -> None:
    authority, first_runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, first_runner)
    initial = first.reconcile()
    writes = len(authority.transport.writes)
    first.close()
    second_runner = Runner()
    second = application(tmp_path, authority, second_runner)
    assert second.reconcile("restart") == initial
    assert second_runner.reviews == 0 and len(authority.transport.writes) == writes
    second.close()


def test_close_reopen_restart_preserves_pending_durable_activity_without_duplicate_effect(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.run = replace(authority.run, conclusion="failure")
    first = application(tmp_path, authority, runner)
    first.reconcile()
    marker_count = sum("hamsterdan-rerun" in x["body"] for x in authority.transport.comments)
    history_before = (tmp_path / "state/history.jsonl").read_text()
    first.close()
    second_runner = Runner()
    second = application(tmp_path, authority, second_runner)
    second.reconcile("reopened")
    assert sum("hamsterdan-rerun" in x["body"] for x in authority.transport.comments) == marker_count == 1
    assert second_runner.reviews == 0 and history_before in (tmp_path / "state/history.jsonl").read_text()
    second.close()


def test_same_head_policy_changes_reverts_and_deduplicates(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    original = authority.policy_value
    subject = application(tmp_path, authority, runner)
    subject.reconcile()
    authority.policy_value = replace(original, strict=True, update_required=True, digest="policy-b")
    subject.reconcile("b")
    assert subject.host.control.policy_digest == "policy-b"  # type: ignore[union-attr]
    authority.policy_value = original
    subject.reconcile("a")
    assert subject.host.control.policy_digest == original.digest and runner.reviews == 3  # type: ignore[union-attr]
    writes = len(authority.transport.writes)
    subject.reconcile("duplicate")
    assert runner.reviews == 3 and len(authority.transport.writes) == writes
    subject.close()


def test_strict_policy_requires_base_alignment(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    subject.reconcile()
    authority.pull = replace(authority.pull, base="d" * 40)
    non_strict = subject.reconcile("moved")
    control = subject.host.control  # type: ignore[union-attr]
    assert (
        non_strict["epoch"] == 1 and control is not None and not control.base_current and workflow_gates_ready(control)
    )
    authority.policy_value = replace(authority.policy_value, strict=True, update_required=True, digest="strict")
    strict = subject.reconcile("strict")
    control = subject.host.control  # type: ignore[union-attr]
    assert control is not None and not workflow_gates_ready(control) and strict["wait"] == "base update"
    subject.close()


def test_state_root_refuses_rebinding(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    subject.reconcile()
    subject.close()
    rebound = Authority()
    rebound.repository, rebound.pr_number = "other/repo", 99
    rebound.pull = replace(rebound.pull, repository="other/repo", number=99, head_repository="other/repo")
    with pytest.raises(RuntimeError, match="different PR Instance"):
        application(tmp_path, rebound, Runner())


def test_credentials_never_enter_agent_requests_or_durable_history(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = PrReadinessApplication(
        tmp_path / "state",
        "github-1-pr-3",
        authority,
        runner,  # type: ignore[arg-type]
        bot_login=BOT,
        public_clone_url=f"https://example.invalid/repo?x={SECRETS[0]}",
        reminder_delay=10**30,
    )
    subject.reconcile()
    encoded_requests = json.dumps([asdict(x) for x in runner.requests])
    encoded_history = (tmp_path / "state/history.jsonl").read_text()
    assert all(secret not in encoded_requests and secret not in encoded_history for secret in SECRETS)
    subject.close()
