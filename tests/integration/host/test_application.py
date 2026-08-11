from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    FiringFailed,
    ScopeClosed,
    ScopeReset,
)
from petrus.motus.activity import ActivityError, ExecutionPolicy
from petrus.motus.dispatch import LocalDispatch
from petrus.motus.worker import Worker

from hamsterdan.agents import AgentProtocolError, CodingResult, ConversationResult, ReviewResult
from hamsterdan.contracts.readiness import AdmittedConversation, workflow_gates_ready, workflow_wait
from hamsterdan.github_app.gateway import GitHubAuthority
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
        self.rejection: tuple[str, int] | None = None

    def pages(self, path: str) -> tuple[dict[str, Any], ...]:
        assert path.endswith("/issues/3/comments?per_page=100")
        return tuple(self.comments)

    def request(self, method: str, path: str, body=None) -> WireResponse:
        assert method in {"POST", "PATCH"} and isinstance(body, dict)
        self.writes.append((method, path, body))
        if self.rejection is not None and self.rejection[0] in str(body["body"]):
            return WireResponse(self.rejection[1], {"message": "provider detail must not escape"})
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
    actions_evidence = GitHubAuthority.actions_evidence

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

    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        self.reviews += 1
        self.requests.append(request)
        assert is_current is None or is_current()
        return ReviewResult(
            request.repository, request.pull_request, request.epoch, request.head, request.base, "clear", [], []
        )

    def converse(self, repository_url, request, *, operation, attempt, is_current=None):
        self.conversations += 1
        self.requests.append(request)
        text = str(request.comment_context.get("text", ""))
        if text == "Please fix the finding":
            intents = [
                {
                    "type": "change",
                    "arguments": {"request": "fix the finding"},
                    "mutation": True,
                    "explicit": True,
                    "confidence": 1,
                }
            ]
        elif text == "Please fix it":
            intents = [
                {
                    "type": "reply",
                    "arguments": {"message": "Please clarify the requested change."},
                    "mutation": False,
                    "explicit": False,
                    "confidence": 1,
                }
            ]
        elif text == "Retry the blocked publication":
            target = next(
                name
                for name in ("conversation", "dashboard", "readiness")
                if request.dashboard[f"{name}_capability_blocking"]
            )
            intents = [
                {
                    "type": "recover_publication",
                    "arguments": {
                        "target": target,
                        "operation": request.dashboard[f"{target}_operation"],
                    },
                    "mutation": False,
                    "explicit": True,
                    "confidence": 1,
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

    def code(self, repository_url, request, *, operation, attempt, is_current=None):
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
    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        self.reviews += 1
        raise AgentProtocolError("provider unavailable")

    def code(self, repository_url, request, *, operation, attempt, is_current=None):
        self.codes += 1
        raise AgentProtocolError("provider unavailable")


class RecoveringReviewRunner(Runner):
    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        if self.reviews < 2:
            self.reviews += 1
            raise AgentProtocolError("provider unavailable")
        return super().review(repository_url, request, operation=operation, attempt=attempt, is_current=is_current)


class TerminalReviewRunner(Runner):
    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        self.reviews += 1
        raise RuntimeError("terminal review failure")


def application(
    tmp_path: Path,
    authority: Authority,
    runner: Runner,
    *,
    dispatch_path: Path | None = None,
    instance_id: str = "github-1-pr-3",
) -> PrReadinessApplication:
    return PrReadinessApplication(
        tmp_path / "state",
        instance_id,
        authority,
        runner,  # type: ignore[arg-type]
        agent_settle=lambda operations: None,
        bot_login=BOT,
        public_clone_url=str(tmp_path),
        reminder_delay=10**30,
        dispatch_path=dispatch_path,
    )


def ready(authority: Authority) -> None:
    authority.pull = replace(authority.pull, draft=False)


def comment(subject: PrReadinessApplication, **values: Any) -> None:
    delivery_id = str(values["delivery_id"])
    values.pop("actor_type", None)
    text = str(values["text"])
    mention = "@hamster-dan"
    values["text"] = "" if text.casefold() == mention else text[len(mention) + 1 :].lstrip()
    subject.activate(
        f"comment-preflight:{delivery_id}",
        conversation=AdmittedConversation(**values),
    )


def snapshot(subject: PrReadinessApplication, trigger: str):
    subject.activate(trigger)
    assert subject.host is not None and subject.host.snapshot is not None
    return subject.host.snapshot


def test_draft_ready_dormant_and_same_head_resume(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    subject = application(tmp_path, authority, runner)
    subject.activate("poll")
    assert subject.host is None
    assert not (tmp_path / "state/history.jsonl").exists()
    ready(authority)
    assert snapshot(subject, "ready").epoch == 1
    assert runner.reviews == 1 and any("hamsterdan:dashboard" in x["body"] for x in authority.transport.comments)
    writes = len(authority.transport.writes)
    authority.pull = replace(authority.pull, draft=True)
    subject.activate("draft")
    assert subject.host is not None and subject.host.place("dormant") and len(authority.transport.writes) == writes
    assert subject.host is not None and subject.host.generation_scope is None
    assert any(isinstance(record, ScopeClosed) for record in subject.host.engine.records)
    ready(authority)
    resumed = snapshot(subject, "ready-again")
    assert (resumed.epoch, resumed.head, runner.reviews) == (2, HEAD, 2)
    assert subject.host.generation_scope is not None and subject.host.generation_scope.generation == 2
    subject.close()


def test_active_generation_scope_and_activity_provenance_survive_restart(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, runner)

    first.activate("ready")

    assert first.host is not None
    scope = first.host.generation_scope
    assert scope is not None and (scope.name, scope.generation) == ("readiness-generation", 1)
    requests = [record for record in first.host.engine.records if isinstance(record, ActivityRequested)]
    assert requests and all(record.scope == scope for record in requests)
    first.close()

    second = application(tmp_path, authority, Runner())
    assert second.host is not None and second.host.generation_scope == scope
    second.close()


def test_new_head_and_closed_terminal_absorb_late_poll(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    assert snapshot(subject, "poll").epoch == 1
    authority.pull = replace(authority.pull, head=HEAD_2)
    authority.run = replace(authority.run, head=HEAD_2, id=12)
    assert snapshot(subject, "synchronize").epoch == 2
    assert subject.host is not None and subject.host.generation_scope is not None
    assert subject.host.generation_scope.generation == 2
    assert any(isinstance(record, ScopeReset) for record in subject.host.engine.records)
    authority.pull = replace(authority.pull, state="closed", closed=True)
    subject.activate("closed")
    assert subject.host.place("terminal") == ({"status": "abort", "last_epoch": 2, "head": HEAD_2},)
    assert subject.host.generation_scope is None
    writes = len(authority.transport.writes)
    history = (tmp_path / "state/history.jsonl").read_text()
    subject.activate("late")
    assert subject.host.place("terminal") == ({"status": "abort", "last_epoch": 2, "head": HEAD_2},)
    assert len(authority.transport.writes) == writes
    assert (tmp_path / "state/history.jsonl").read_text() == history
    subject.close()


def test_restart_repairs_generation_reset_after_scope_commit(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, runner)
    first.activate("initial")
    authority.pull = replace(authority.pull, head=HEAD_2)
    authority.run = replace(authority.run, head=HEAD_2, id=12)
    assert first.host is not None
    reset = first.host.reset_generation

    def crash_after_reset():
        reset()
        raise RuntimeError("simulated crash after scope reset")

    first.host.reset_generation = crash_after_reset  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="simulated crash"):
        first.activate("supersede")
    first.close()

    second = application(tmp_path, authority, Runner())
    projection = snapshot(second, "restart")
    assert (projection.epoch, projection.head) == (2, HEAD_2)
    assert second.host is not None and not second.host.place("generation_start")
    second.close()


def test_restart_opens_missing_scope_after_initial_create_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hamsterdan.host import runtime

    authority, runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, runner)
    open_scope = runtime.Engine.open_scope

    def crash_before_scope(engine, name):
        raise RuntimeError("simulated crash before initial scope")

    monkeypatch.setattr(runtime.Engine, "open_scope", crash_before_scope)
    with pytest.raises(RuntimeError, match="simulated crash"):
        first.activate("initial")
    monkeypatch.setattr(runtime.Engine, "open_scope", open_scope)

    second = application(tmp_path, authority, Runner())
    projection = snapshot(second, "restart")
    assert (projection.epoch, projection.head) == (1, HEAD)
    second.close()


@pytest.mark.parametrize(("state", "terminal"), [("draft", False), ("closed", True), ("merged", True)])
def test_restart_disposes_seed_only_instance_after_scope_open_crash(tmp_path: Path, state: str, terminal: bool) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, runner)

    def crash_before_start(*args, **kwargs):
        raise RuntimeError("simulated crash before generation start")

    first._start_generation = crash_before_start  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="simulated crash"):
        first.activate("initial")
    first.close()

    authority.pull = replace(
        authority.pull,
        draft=state == "draft",
        closed=state in {"closed", "merged"},
        merged=state == "merged",
        state="closed" if terminal else "open",
    )
    second = application(tmp_path, authority, Runner())
    second.activate("restart")
    assert second.host is not None
    place = "terminal" if terminal else "dormant"
    assert second.host.place(place)
    second.close()


def test_restart_repairs_generation_stop_after_scope_commit(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, runner)
    first.activate("initial")
    authority.pull = replace(authority.pull, draft=True)
    assert first.host is not None
    close = first.host.close_generation

    def crash_after_close():
        close()
        raise RuntimeError("simulated crash after scope close")

    first.host.close_generation = crash_after_close  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="simulated crash"):
        first.activate("draft")
    first.close()

    second = application(tmp_path, authority, Runner())
    second.activate("restart")
    assert second.host is not None and second.host.place("dormant")
    assert second.host is not None and not second.host.place("generation_stop")
    second.close()


def test_scope_cancellation_removes_publication_from_host_unresolved_index(tmp_path: Path) -> None:
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    subject.activate("enqueue")
    assert subject.host is not None and subject.host.has_unresolved_publication()

    authority.pull = replace(authority.pull, draft=True)
    subject.activate("draft")

    assert not subject.host.has_unresolved_publication()
    subject.close()


def test_merged_is_terminal_success_without_merge_commit_identity(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    subject.activate("poll")
    authority.pull = replace(authority.pull, state="closed", closed=True, merged=True)
    subject.activate("merged")
    assert subject.host is not None
    assert subject.host.place("terminal") == ({"status": "success", "last_epoch": 1, "head": HEAD},)
    subject.close()


def test_mention_conversation_executes_explicit_mutation_once_and_clarifies_ambiguity(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    subject.activate("poll")
    common = {"actor_id": 7, "actor_login": "author", "actor_type": "User", "association": "OWNER"}
    authority.transport.comments.append({"id": 90, "body": "<!-- impetus:dashboard -->", "user": {"login": BOT}})
    comment(subject, delivery_id="status", comment_id=31, text="@hamster-dan How is this looking?", **common)
    assert runner.conversations == 1 and any(
        "Ready: every observed gate is clear" in x["body"] for x in authority.transport.comments
    )
    request = runner.requests[-1]
    assert request.comment_context["text"] == "How is this looking?"
    assert request.dashboard["head"] == HEAD
    assert request.dashboard["findings"] == []
    assert request.gates[0] == {"name": "overall", "ready": True, "blocker": ""}
    comment(subject, delivery_id="change", comment_id=32, text="@hamster-dan Please fix the finding", **common)
    assert runner.codes == 1
    comment(
        subject,
        delivery_id="ambiguous",
        comment_id=33,
        text="@hamster-dan Please fix it",
        **common,
    )
    assert runner.codes == 1
    assert any("clarify" in comment["body"] for comment in authority.transport.comments)
    subject.close()


def test_first_failure_reruns_once_then_flaky_green(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.run = replace(authority.run, conclusion="failure")
    subject = application(tmp_path, authority, runner)
    assert snapshot(subject, "poll").actions in {"failed", "waiting"}
    markers = lambda: [x for x in authority.transport.comments if "hamsterdan-rerun" in x["body"]]
    assert len(markers()) == 1
    subject.activate("same-failure")
    assert len(markers()) == 1
    authority.run = replace(authority.run, attempt=2, conclusion="success")
    assert snapshot(subject, "complete").actions == "flaky_green"
    subject.close()


def test_failed_rerun_reproduces_after_running_observation(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.run = replace(authority.run, conclusion="failure")
    subject = application(tmp_path, authority, runner)
    subject.activate("poll")
    authority.run = replace(authority.run, attempt=2, status="in_progress", conclusion=None)
    assert snapshot(subject, "running").actions == "running"
    authority.run = replace(authority.run, status="completed", conclusion="failure")
    assert snapshot(subject, "failed").actions == "reproduced" and runner.codes == 1
    subject.close()


def test_first_later_attempt_failure_still_reruns_before_repair(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.run = replace(authority.run, attempt=2, conclusion="failure")
    subject = application(tmp_path, authority, runner)
    assert snapshot(subject, "poll").actions == "waiting" and runner.codes == 0
    subject.activate("same")
    assert runner.codes == 0
    authority.run = replace(authority.run, attempt=3)
    assert snapshot(subject, "failed").actions == "reproduced" and runner.codes == 1
    subject.close()


def test_provider_failures_are_typed_inability_and_recovery(tmp_path: Path) -> None:
    authority, runner = Authority(), UnavailableRunner()
    ready(authority)
    authority.run = replace(authority.run, attempt=2, conclusion="failure")
    subject = application(tmp_path, authority, runner)
    first = snapshot(subject, "poll")
    assert first.review == "unable" and first.actions == "waiting"
    authority.run = replace(authority.run, attempt=3)
    recovered = snapshot(subject, "failed")
    control = subject.host.control  # type: ignore[union-attr]
    assert recovered.actions == "reproduced" and control is not None and not control.repair_in_flight
    assert workflow_wait(control) == "repair recovery" and runner.codes == 3
    subject.close()


def test_same_basis_reconciliation_recovers_review_with_bounded_distinct_attempts(tmp_path: Path) -> None:
    authority, runner = Authority(), RecoveringReviewRunner()
    ready(authority)
    subject = application(tmp_path, authority, runner)

    assert snapshot(subject, "attempt-1").review == "unable"
    assert snapshot(subject, "attempt-2").review == "unable"
    assert snapshot(subject, "attempt-3").review == "clear"
    assert runner.reviews == 3
    subject.activate("settled")
    assert runner.reviews == 3
    subject.close()


def test_same_basis_reconciliation_stops_after_three_unavailable_reviews(tmp_path: Path, caplog) -> None:
    authority, runner = Authority(), UnavailableRunner()
    ready(authority)
    subject = application(tmp_path, authority, runner)

    projection = {}
    for attempt in range(1, 7):
        projection = snapshot(subject, f"attempt-{attempt}")

    control = subject.host.control  # type: ignore[union-attr]
    assert runner.reviews == 3
    assert projection.review == "unable"
    assert control is not None and control.review_attempts == 3
    assert "agent activity unavailable kind=review category=protocol" in caplog.text
    assert "provider unavailable" not in caplog.text
    subject.close()


def test_restart_one_history_has_no_duplicate_agent_or_publication(tmp_path: Path) -> None:
    authority, first_runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, first_runner)
    initial = snapshot(first, "poll")
    writes = len(authority.transport.writes)
    first.close()
    second_runner = Runner()
    second = application(tmp_path, authority, second_runner)
    assert snapshot(second, "restart") == initial
    assert second_runner.reviews == 0 and len(authority.transport.writes) == writes
    second.close()


def test_terminal_activity_failure_reloads_and_resolves_in_flight_siblings(tmp_path: Path) -> None:
    authority, runner = Authority(), TerminalReviewRunner()
    ready(authority)
    subject = application(tmp_path, authority, runner)

    projection = snapshot(subject, "terminal-agent-failure")
    records = [json.loads(line) for line in (tmp_path / "state/history.jsonl").read_text().splitlines()]
    requested = {record["occurrence"] for record in records if record["record"] == "ActivityRequested"}
    terminal = {
        record["occurrence"] for record in records if record["record"] in {"ActivityCompleted", "ActivityFailed"}
    }
    failed = [record for record in records if record["record"] == "ActivityFailed"]
    firing_failed = [record for record in records if record["record"] == "FiringFailed"]

    assert subject.host is not None and projection == subject.host.snapshot
    assert requested == terminal
    assert len(failed) == len(firing_failed) == 1
    assert failed[0]["occurrence"] == firing_failed[0]["occurrence"]
    assert sum("hamsterdan:dashboard" in item["body"] for item in authority.transport.comments) == 1

    settled = (tmp_path / "state/history.jsonl").read_text()
    subject.activate("settled")
    assert (tmp_path / "state/history.jsonl").read_text() == settled
    subject.close()


def test_close_reopen_restart_preserves_pending_durable_activity_without_duplicate_effect(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.run = replace(authority.run, conclusion="failure")
    first = application(tmp_path, authority, runner)
    first.activate("poll")
    marker_count = sum("hamsterdan-rerun" in x["body"] for x in authority.transport.comments)
    history_before = (tmp_path / "state/history.jsonl").read_text()
    first.close()
    second_runner = Runner()
    second = application(tmp_path, authority, second_runner)
    second.activate("reopened")
    assert sum("hamsterdan-rerun" in x["body"] for x in authority.transport.comments) == marker_count == 1
    assert second_runner.reviews == 0 and history_before in (tmp_path / "state/history.jsonl").read_text()
    second.close()


def test_publication_requests_use_exact_durable_policy_and_operation_identity(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner, dispatch_path=tmp_path / "dispatch.sqlite3")

    subject.activate("prepare-publications")
    worker = Worker(
        LocalDispatch(tmp_path / "dispatch.sqlite3", instance="worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: subject.activity(name),
    )
    for _ in range(10):
        worker.run_available(limit=20)
        subject.settle()
        names = {
            record.activity
            for record in subject.host.engine.records  # type: ignore[union-attr]
            if isinstance(record, ActivityRequested)
        }
        if {"dashboard_publish", "readiness_publish"} <= names:
            break
    requested = [
        record
        for record in subject.host.engine.records  # type: ignore[union-attr]
        if isinstance(record, ActivityRequested) and record.activity in {"dashboard_publish", "readiness_publish"}
    ]

    assert {record.activity for record in requested} == {"dashboard_publish", "readiness_publish"}
    for record in requested:
        work = record.input.get("work", record.input.get("command"))
        assert record.policy.attempts == 3
        assert (record.policy.initial_interval, record.policy.coefficient, record.policy.max_interval) == (5, 2, 10)
        assert (record.policy.jitter, record.policy.schedule_to_close) == (0, 60)
        assert record.correlation == record.idempotency == work["operation"]
    subject.close()
    worker.close()


def test_one_local_worker_routes_instances_to_distinct_publication_providers(tmp_path: Path) -> None:
    dispatch_path = tmp_path / "dispatch.sqlite3"
    subjects: dict[str, PrReadinessApplication] = {}
    authorities: list[Authority] = []
    for label in ("one", "two"):
        authority, runner = Authority(), Runner()
        ready(authority)
        instance = f"github-{label}-pr-3"
        subject = application(
            tmp_path / label,
            authority,
            runner,
            dispatch_path=dispatch_path,
            instance_id=instance,
        )
        subject.activate("enqueue")
        subjects[instance] = subject
        authorities.append(authority)

    worker = Worker(
        LocalDispatch(dispatch_path, instance="worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: subjects[instance].activity(name),
    )
    assert worker.run_available(limit=2) == 2
    for subject in subjects.values():
        subject.settle()

    assert [len(authority.transport.writes) for authority in authorities] == [1, 1]
    for instance, subject in subjects.items():
        completed = [
            record
            for record in subject.host.engine.records  # type: ignore[union-attr]
            if record.__class__.__name__ == "ActivityCompleted"
            and str(record.transition) == "execute.dashboard_publish"
        ]
        assert len(completed) == 1
        assert subject.instance_id == instance
        subject.close()
    worker.close()


def test_frozen_worker_success_is_collected_after_application_reopen_without_duplicate_provider_call(
    tmp_path: Path,
) -> None:
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    first.activate("enqueue")
    worker = Worker(
        LocalDispatch(dispatch_path, instance="worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: first.activity(name),
    )
    assert worker.run_available(limit=20) == 1
    occurrence = next(
        record.occurrence
        for record in first.host.engine.records  # type: ignore[union-attr]
        if isinstance(record, ActivityRequested) and record.activity == "dashboard_publish"
    )
    calls = len(authority.transport.writes)
    first.close()

    second = application(tmp_path, authority, Runner(), dispatch_path=dispatch_path)
    second.settle()
    assert len(authority.transport.writes) == calls == 1
    assert any(
        record.__class__.__name__ == "ActivityCompleted" and record.occurrence == occurrence
        for record in second.host.engine.records  # type: ignore[union-attr]
    )
    second.close()
    worker.close()


def test_conversation_retry_succeeds_under_one_activity_request_and_stable_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hamsterdan.host import runtime

    monkeypatch.setattr(
        runtime,
        "_PUBLICATION_POLICY",
        ExecutionPolicy(attempts=3, initial_interval=0, coefficient=1, max_interval=0, jitter=0),
    )
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    subject.activate("enqueue")
    comment(
        subject,
        delivery_id="reply",
        comment_id=51,
        text="@hamster-dan Please fix it",
        actor_id=7,
        actor_login="author",
        actor_type="User",
        association="OWNER",
    )
    calls: list[str] = []

    def resolver(instance: str, name: str):
        implementation = subject.activity(name)

        def retry_once(invocation, *, context):
            if name != "conversation_publish":
                return implementation(invocation, context=context)
            calls.append(invocation.correlation)
            if len(calls) == 1:
                raise ActivityError("retry", kind="GitHubBoundaryError", retryable=True)
            return implementation(invocation, context=context)

        return retry_once

    worker = Worker(LocalDispatch(dispatch_path, instance="worker").worker(("publication",)), {}, resolver=resolver)
    for _ in range(10):
        worker.run_available(limit=20)
        subject.settle()
        if len(calls) == 2:
            break

    records = subject.host.engine.records  # type: ignore[union-attr]
    requested = [
        record
        for record in records
        if isinstance(record, ActivityRequested) and record.activity == "conversation_publish"
    ]
    assert len(calls) == 2 and calls[0] == calls[1]
    assert len(requested) == 1 and requested[0].idempotency == calls[0]
    assert (
        sum(
            record.__class__.__name__ == "ActivityCompleted" and record.occurrence == requested[0].occurrence
            for record in records
        )
        == 1
    )
    matching_writes = [write for write in authority.transport.writes if "clarify" in str(write[2]["body"])]
    control = subject.host.control  # type: ignore[union-attr]
    assert len(matching_writes) == 1
    assert control is not None and not control.conversation_requested and control.conversation_operation is None
    subject.close()
    worker.close()


def test_frozen_conversation_terminal_reopens_without_duplicate_provider_call(tmp_path: Path) -> None:
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    first.activate("enqueue")
    worker = Worker(
        LocalDispatch(dispatch_path, instance="worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: first.activity(name),
    )
    for _ in range(10):
        claimed = worker.run_available(limit=20)
        first.settle()
        if claimed == 0:
            break
    comment(
        first,
        delivery_id="reply",
        comment_id=55,
        text="@hamster-dan Please fix it",
        actor_id=7,
        actor_login="author",
        actor_type="User",
        association="OWNER",
    )
    requested = next(
        record
        for record in first.host.engine.records  # type: ignore[union-attr]
        if isinstance(record, ActivityRequested) and record.activity == "conversation_publish"
    )
    occurrence, operation = requested.occurrence, requested.idempotency
    assert worker.run_available(limit=20) >= 1
    calls = sum("clarify" in str(write[2]["body"]) for write in authority.transport.writes)
    assert calls == 1
    first.close()

    second = application(tmp_path, authority, Runner(), dispatch_path=dispatch_path)
    second.settle()
    records = second.host.engine.records  # type: ignore[union-attr]
    completed = [
        record for record in records if isinstance(record, ActivityCompleted) and record.occurrence == occurrence
    ]
    conversation_requests = [
        record
        for record in records
        if isinstance(record, ActivityRequested) and record.activity == "conversation_publish"
    ]
    control = second.host.control  # type: ignore[union-attr]
    assert len(completed) == 1
    assert len(conversation_requests) == 1 and conversation_requests[0].idempotency == operation
    assert control is not None and not control.conversation_requested and control.conversation_operation is None
    cleanup_worker = Worker(
        LocalDispatch(dispatch_path, instance="cleanup-worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: second.activity(name),
    )
    cleanup_worker.run_available(limit=20)
    second.settle()
    cleanup_worker.close()
    assert worker.run_available(limit=20) == 0
    assert sum("clarify" in str(write[2]["body"]) for write in authority.transport.writes) == calls
    second.close()
    worker.close()


def test_frozen_exhausted_conversation_projects_exact_terminal_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hamsterdan.host import runtime

    monkeypatch.setattr(
        runtime,
        "_PUBLICATION_POLICY",
        ExecutionPolicy(attempts=3, initial_interval=0, coefficient=1, max_interval=0, jitter=0),
    )
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    first.activate("enqueue")
    baseline_worker = Worker(
        LocalDispatch(dispatch_path, instance="baseline-worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: first.activity(name),
    )
    for _ in range(10):
        claimed = baseline_worker.run_available(limit=20)
        first.settle()
        if claimed == 0:
            break
    baseline_worker.close()
    comment(
        first,
        delivery_id="restart-exhaustion",
        comment_id=56,
        text="@hamster-dan Please fix it",
        actor_id=7,
        actor_login="author",
        actor_type="User",
        association="OWNER",
    )
    requested = next(
        record
        for record in first.host.engine.records  # type: ignore[union-attr]
        if isinstance(record, ActivityRequested) and record.activity == "conversation_publish"
    )
    occurrence, operation, request = requested.occurrence, requested.idempotency, requested.input
    calls: list[str] = []

    def resolver(instance: str, name: str):
        implementation = first.activity(name)

        def exhaust(invocation, *, context):
            if name != "conversation_publish":
                return implementation(invocation, context=context)
            calls.append(invocation.correlation)
            raise ActivityError("retry", kind="GitHubBoundaryError", retryable=True)

        return exhaust

    worker = Worker(LocalDispatch(dispatch_path, instance="worker").worker(("publication",)), {}, resolver=resolver)
    for _ in range(3):
        worker.run_available(limit=20)
    assert calls == [operation, operation, operation]
    assert not any(isinstance(record, ActivityFailed) for record in first.host.engine.records)  # type: ignore[union-attr]
    first.close()

    second = application(tmp_path, authority, Runner(), dispatch_path=dispatch_path)
    second.settle()
    records = second.host.engine.records  # type: ignore[union-attr]
    failed = [record for record in records if isinstance(record, ActivityFailed) and record.occurrence == occurrence]
    control = second.host.control  # type: ignore[union-attr]
    assert len(failed) == 1 and failed[0].occurrence == occurrence
    assert control is not None and control.conversation_capability_blocking and control.conversation_requested
    assert control.conversation_operation == operation
    assert requested.input == request
    cleanup_worker = Worker(
        LocalDispatch(dispatch_path, instance="cleanup-worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: second.activity(name),
    )
    cleanup_worker.run_available(limit=20)
    second.settle()
    cleanup_worker.close()
    assert worker.run_available(limit=20) == 0 and len(calls) == 3
    second.close()
    worker.close()


def test_conversation_exhaustion_projects_one_blocker_and_retains_exact_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hamsterdan.host import runtime

    monkeypatch.setattr(
        runtime,
        "_PUBLICATION_POLICY",
        ExecutionPolicy(attempts=3, initial_interval=0, coefficient=1, max_interval=0, jitter=0),
    )
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    subject.activate("enqueue")
    comment(
        subject,
        delivery_id="reply",
        comment_id=52,
        text="@hamster-dan Please fix it",
        actor_id=7,
        actor_login="author",
        actor_type="User",
        association="OWNER",
    )
    calls: list[str] = []

    def resolver(instance: str, name: str):
        implementation = subject.activity(name)

        def exhaust(invocation, *, context):
            if name != "conversation_publish":
                return implementation(invocation, context=context)
            calls.append(invocation.correlation)
            raise ActivityError("retry", kind="GitHubBoundaryError", retryable=True)

        return exhaust

    worker = Worker(LocalDispatch(dispatch_path, instance="worker").worker(("publication",)), {}, resolver=resolver)
    for _ in range(10):
        worker.run_available(limit=20)
        subject.settle()
        control = subject.host.control  # type: ignore[union-attr]
        if control is not None and control.conversation_capability_blocking:
            break

    records = subject.host.engine.records  # type: ignore[union-attr]
    requested = [
        record
        for record in records
        if isinstance(record, ActivityRequested) and record.activity == "conversation_publish"
    ]
    failed = [
        record
        for record in records
        if isinstance(record, ActivityFailed) and str(record.transition) == "execute.conversation_publish"
    ]
    control = subject.host.control  # type: ignore[union-attr]
    assert len(calls) == 3 and len(set(calls)) == 1
    assert len(requested) == len(failed) == 1
    assert control is not None and control.conversation_capability_blocking and control.conversation_requested
    assert control.conversation_operation == requested[0].idempotency == calls[0]
    count = len(requested)
    subject.settle()
    assert (
        sum(
            isinstance(record, ActivityRequested) and record.activity == "conversation_publish"
            for record in subject.host.engine.records  # type: ignore[union-attr]
        )
        == count
    )
    comment(
        subject,
        delivery_id="recover-reply",
        comment_id=54,
        text="@hamster-dan Retry the blocked publication",
        actor_id=7,
        actor_login="author",
        actor_type="User",
        association="OWNER",
    )
    recovered = [
        record
        for record in subject.host.engine.records  # type: ignore[union-attr]
        if isinstance(record, ActivityRequested) and record.activity == "conversation_publish"
    ]
    assert len(recovered) == 2
    assert recovered[1].occurrence != recovered[0].occurrence
    assert recovered[1].idempotency == recovered[0].idempotency
    assert recovered[1].input == recovered[0].input
    subject.close()
    worker.close()


@pytest.mark.parametrize(
    ("activity", "marker", "blocker"),
    [
        ("conversation_publish", "clarify", "conversation_capability_blocking"),
        ("dashboard_publish", "hamsterdan:dashboard", "dashboard_capability_blocking"),
        ("readiness_publish", "hamsterdan:readiness", "readiness_capability_blocking"),
    ],
)
@pytest.mark.parametrize("status", [403, 404])
def test_production_publication_capability_absence_completes_once_with_typed_blocker(
    tmp_path: Path, activity: str, marker: str, blocker: str, status: int
) -> None:
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.transport.rejection = (marker, status)
    subject = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    subject.activate("enqueue")
    if activity == "conversation_publish":
        comment(
            subject,
            delivery_id="reply",
            comment_id=53,
            text="@hamster-dan Please fix it",
            actor_id=7,
            actor_login="author",
            actor_type="User",
            association="OWNER",
        )
    worker = Worker(
        LocalDispatch(dispatch_path, instance="worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: subject.activity(name),
    )

    for _ in range(10):
        worker.run_available(limit=20)
        subject.settle()
        terminals = [
            record
            for record in subject.host.engine.records  # type: ignore[union-attr]
            if record.__class__.__name__ == "ActivityCompleted" and str(record.transition) == f"execute.{activity}"
        ]
        if terminals:
            break

    records = subject.host.engine.records  # type: ignore[union-attr]
    completed = [
        record
        for record in records
        if record.__class__.__name__ == "ActivityCompleted" and str(record.transition) == f"execute.{activity}"
    ]
    failed = [
        record
        for record in records
        if isinstance(record, ActivityFailed) and str(record.transition) == f"execute.{activity}"
    ]
    matching_writes = [write for write in authority.transport.writes if marker in str(write[2]["body"])]
    control = subject.host.control  # type: ignore[union-attr]

    assert len(completed) == 1 and failed == []
    assert completed[0].result["capability_available"] is False
    assert len(matching_writes) == 1
    assert control is not None and getattr(control, blocker)
    subject.close()
    worker.close()


@pytest.mark.parametrize(
    ("target", "activity", "marker", "state_place", "recovery_field"),
    [
        (
            "conversation",
            "conversation_publish",
            "clarify",
            "conversation_publication_state",
            "conversation_recovery",
        ),
        (
            "dashboard",
            "dashboard_publish",
            "hamsterdan:dashboard",
            "dashboard_publication_state",
            "dashboard_recovery",
        ),
        (
            "readiness",
            "readiness_publish",
            "hamsterdan:readiness",
            "readiness_publication_state",
            "readiness_recovery",
        ),
    ],
)
def test_publication_recovery_reconstructs_one_exact_owned_request_after_restart(
    tmp_path: Path,
    target: str,
    activity: str,
    marker: str,
    state_place: str,
    recovery_field: str,
) -> None:
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.transport.rejection = (marker, 403)
    first = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    first.activate("enqueue")
    if target == "conversation":
        comment(
            first,
            delivery_id="reply",
            comment_id=53,
            text="@hamster-dan Please fix it",
            actor_id=7,
            actor_login="author",
            actor_type="User",
            association="OWNER",
        )
    first_worker = Worker(
        LocalDispatch(dispatch_path, instance="first-worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: first.activity(name),
    )
    blocker = f"{target}_capability_blocking"
    for _ in range(10):
        first_worker.run_available(limit=20)
        first.settle()
        control = first.host.control  # type: ignore[union-attr]
        if control is not None and getattr(control, blocker):
            break

    original = next(
        record
        for record in first.host.engine.records  # type: ignore[union-attr]
        if isinstance(record, ActivityRequested) and record.activity == activity
    )
    original_operation = original.idempotency
    first.close()
    first_worker.close()

    class FixedRecoveryRunner(Runner):
        def converse(self, repository_url, request, *, operation, attempt, is_current=None):
            if str(request.comment_context.get("text", "")) != "Retry the blocked publication":
                return super().converse(
                    repository_url, request, operation=operation, attempt=attempt, is_current=is_current
                )
            self.conversations += 1
            self.requests.append(request)
            return ConversationResult(
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                [
                    {
                        "type": "recover_publication",
                        "arguments": {"target": target, "operation": original_operation},
                        "mutation": False,
                        "explicit": True,
                        "confidence": 1,
                    }
                ],
            )

    second = application(tmp_path, authority, FixedRecoveryRunner(), dispatch_path=dispatch_path)
    control = second.host.control  # type: ignore[union-attr]
    assert control is not None and getattr(control, blocker)
    state = second.host.place(state_place)[0]  # type: ignore[union-attr]
    retained = state[recovery_field]
    assert retained is not None and retained["operation"] == original_operation
    assert not any(
        getattr(control, f"{other}_capability_blocking")
        for other in {"conversation", "dashboard", "readiness"} - {target}
    )

    comment(
        second,
        delivery_id=f"recover-{target}",
        comment_id=54,
        text="@hamster-dan Retry the blocked publication",
        actor_id=7,
        actor_login="author",
        actor_type="User",
        association="OWNER",
    )
    selected = [
        record
        for record in second.host.engine.records  # type: ignore[union-attr]
        if isinstance(record, ActivityRequested) and record.activity == activity
    ]
    assert len(selected) == 2
    assert selected[1].occurrence != selected[0].occurrence
    assert selected[1].idempotency == selected[0].idempotency == original_operation
    assert selected[1].input == selected[0].input
    control = second.host.control  # type: ignore[union-attr]
    assert control is not None and not getattr(control, blocker)

    authority.transport.rejection = None
    second_worker = Worker(
        LocalDispatch(dispatch_path, instance="second-worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: second.activity(name),
    )
    for _ in range(10):
        second_worker.run_available(limit=20)
        second.settle()
        state = second.host.place(state_place)[0]  # type: ignore[union-attr]
        if state[f"{target}_operation"] is None:
            break
    state = second.host.place(state_place)[0]  # type: ignore[union-attr]
    assert state[f"{target}_operation"] is None
    assert state[recovery_field] is None

    comment(
        second,
        delivery_id=f"recover-{target}-stale",
        comment_id=55,
        text="@hamster-dan Retry the blocked publication",
        actor_id=7,
        actor_login="author",
        actor_type="User",
        association="OWNER",
    )
    assert (
        sum(
            isinstance(record, ActivityRequested)
            and record.activity == activity
            and record.idempotency == original_operation
            for record in second.host.engine.records  # type: ignore[union-attr]
        )
        == 2
    )
    second.close()
    second_worker.close()


@pytest.mark.parametrize(
    ("activity", "marker"),
    [
        ("conversation_publish", "clarify"),
        ("dashboard_publish", "hamsterdan:dashboard"),
        ("readiness_publish", "hamsterdan:readiness"),
    ],
)
def test_production_publication_422_projects_one_nonrecoverable_fault_without_wedging_lifecycle(
    tmp_path: Path, activity: str, marker: str
) -> None:
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.transport.rejection = (marker, 422)
    subject = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    subject.activate("enqueue")
    if activity == "conversation_publish":
        comment(
            subject,
            delivery_id="reply",
            comment_id=54,
            text="@hamster-dan Please fix it",
            actor_id=7,
            actor_login="author",
            actor_type="User",
            association="OWNER",
        )
    worker = Worker(
        LocalDispatch(dispatch_path, instance="worker").worker(("publication",)),
        {},
        resolver=lambda instance, name: subject.activity(name),
    )

    for _ in range(10):
        worker.run_available(limit=20)
        subject.settle()
        control = subject.host.control  # type: ignore[union-attr]
        target = activity.removesuffix("_publish")
        if control is not None and getattr(control, f"{target}_publication_fault"):
            break
    else:
        pytest.fail("definite publication rejection was not projected")

    records = [json.loads(line) for line in (tmp_path / "state/history.jsonl").read_text().splitlines()]
    failed = [
        record
        for record in records
        if record["record"] == "ActivityFailed" and record.get("transition") == f"execute.{activity}"
    ]
    firing_failed = [
        record
        for record in records
        if record["record"] == "FiringFailed" and record.get("transition") == f"execute.{activity}"
    ]
    matching_writes = [write for write in authority.transport.writes if marker in str(write[2]["body"])]
    assert len(failed) == len(matching_writes) == 1 and firing_failed == []
    assert failed[0]["kind"] == "ValueError" and not failed[0]["retryable"]
    assert "provider detail" not in str(failed + firing_failed)
    authority.pull = replace(authority.pull, state="closed", closed=True)
    subject.activate("closed-after-fault")
    assert subject.host is not None and subject.host.place("terminal")
    subject.close()
    worker.close()


def test_nonretryable_publication_boundary_failure_projects_typed_blocker_once(tmp_path: Path) -> None:
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    subject.activate("enqueue")

    def resolver(instance: str, name: str):
        implementation = subject.activity(name)

        def fail(invocation, *, context):
            raise ActivityError("boundary unavailable", kind="GitHubBoundaryError", retryable=False)

        return fail if name == "readiness_publish" else implementation

    worker = Worker(LocalDispatch(dispatch_path, instance="worker").worker(("publication",)), {}, resolver=resolver)
    for _ in range(10):
        assert worker.run_available(limit=20) >= 1
        subject.settle()
        if any(isinstance(record, ActivityFailed) for record in subject.host.engine.records):  # type: ignore[union-attr]
            break
    records = subject.host.engine.records  # type: ignore[union-attr]
    failures = [record for record in records if isinstance(record, ActivityFailed)]
    requests = [record for record in records if isinstance(record, ActivityRequested)]
    failed_request = next(record for record in requests if record.occurrence == failures[0].occurrence)
    work = failed_request.input["command"]
    control = subject.host.control  # type: ignore[union-attr]

    assert len(failures) == 1 and failures[0].kind == "GitHubBoundaryError"
    assert not any(isinstance(record, FiringFailed) for record in records)
    assert control is not None and control.readiness_capability_blocking
    assert control.readiness_requested
    assert (control.readiness_operation, work["operation"]) == (failed_request.idempotency, failed_request.idempotency)
    count = len(requests)
    subject.settle()
    assert sum(isinstance(record, ActivityRequested) for record in subject.host.engine.records) == count  # type: ignore[union-attr]
    subject.close()
    worker.close()


def test_wrapped_value_error_is_one_nonretryable_attempt_and_projects_fault(tmp_path: Path) -> None:
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner, dispatch_path=dispatch_path)
    subject.activate("enqueue")
    calls = 0

    def resolver(instance: str, name: str):
        implementation = subject.activity(name)

        def wrapped(invocation, *, context):
            nonlocal calls
            if name != "readiness_publish":
                return implementation(invocation, context=context)
            calls += 1
            try:
                raise ValueError("publication invariant")
            except Exception as error:
                raise ActivityError(
                    "publication invariant failed",
                    kind=type(error).__name__,
                    retryable=False,
                ) from error

        return wrapped

    worker = Worker(LocalDispatch(dispatch_path, instance="worker").worker(("publication",)), {}, resolver=resolver)
    for _ in range(10):
        worker.run_available(limit=20)
        subject.settle()
        control = subject.host.control  # type: ignore[union-attr]
        if control is not None and control.readiness_publication_fault:
            break
    else:
        pytest.fail("ValueError terminal was not projected as a publication fault")

    records = [json.loads(line) for line in (tmp_path / "state/history.jsonl").read_text().splitlines()]
    failed = [record for record in records if record["record"] == "ActivityFailed"]
    firing_failed = [record for record in records if record["record"] == "FiringFailed"]
    assert calls == 1
    assert len(failed) == 1 and firing_failed == []
    assert failed[0]["kind"] == "ValueError" and not failed[0]["retryable"]
    assert not any(
        record["record"] == "ActivityCompleted" and record.get("transition") == "execute.readiness_publish"
        for record in records
    )
    subject.close()
    worker.close()


def test_unrelated_review_activity_stays_inline_and_outside_local_publication_custody(tmp_path: Path) -> None:
    dispatch_path = tmp_path / "dispatch.sqlite3"
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner, dispatch_path=dispatch_path)

    subject.activate("mixed-dispatch")
    claimed = LocalDispatch(dispatch_path, instance="inspector").worker(("publication",)).claim()

    assert runner.reviews == 1
    assert claimed is not None and claimed.invocation.activity in {"dashboard_publish", "readiness_publish"}
    records = subject.host.engine.records  # type: ignore[union-attr]
    review_requests = [
        record for record in records if isinstance(record, ActivityRequested) and record.activity == "review"
    ]
    review_terminals = {
        record.occurrence for record in records if record.__class__.__name__ in {"ActivityCompleted", "ActivityFailed"}
    }
    assert len(review_requests) == 1 and review_requests[0].occurrence in review_terminals
    subject.close()


def test_same_head_policy_changes_reverts_and_deduplicates(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    original = authority.policy_value
    subject = application(tmp_path, authority, runner)
    subject.activate("poll")
    authority.policy_value = replace(original, strict=True, update_required=True, digest="policy-b")
    subject.activate("b")
    assert subject.host.control.policy_digest == "policy-b"  # type: ignore[union-attr]
    authority.policy_value = original
    subject.activate("a")
    assert subject.host.control.policy_digest == original.digest and runner.reviews == 3  # type: ignore[union-attr]
    writes = len(authority.transport.writes)
    subject.activate("duplicate")
    assert runner.reviews == 3 and len(authority.transport.writes) == writes
    subject.close()


def test_strict_policy_requires_base_alignment(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    subject.activate("poll")
    authority.pull = replace(authority.pull, base="d" * 40)
    non_strict = snapshot(subject, "moved")
    control = subject.host.control  # type: ignore[union-attr]
    assert non_strict.epoch == 1 and control is not None and not control.base_current and workflow_gates_ready(control)
    authority.policy_value = replace(authority.policy_value, strict=True, update_required=True, digest="strict")
    strict = snapshot(subject, "strict")
    control = subject.host.control  # type: ignore[union-attr]
    assert control is not None and not workflow_gates_ready(control) and workflow_wait(strict) == "base update"
    subject.close()


def test_real_provider_collaboration_facts_fold_into_minimal_gates(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    subject = application(tmp_path, authority, runner)

    subject.activate("draft")
    assert subject.host is None

    ready(authority)
    authority.policy_value = replace(
        authority.policy_value,
        strict=True,
        update_required=True,
        required_approvals=1,
        conversation_resolution=True,
        digest="authority-policy",
    )
    authority.review = HumanReviewSnapshot(("reviewer",), (), (), (), 0, "available")
    requested = snapshot(subject, "review-requested")
    control = subject.host.control  # type: ignore[union-attr]
    assert control is not None
    assert workflow_wait(requested) == "human review"
    assert (control.human_requested, control.human_approved, control.required_approvals) == (True, False, 1)

    authority.review = HumanReviewSnapshot((), (("reviewer", "CHANGES_REQUESTED"),), (), ("reviewer",), 1, "available")
    changes_requested = snapshot(subject, "changes-requested")
    control = subject.host.control  # type: ignore[union-attr]
    assert control is not None
    assert workflow_wait(changes_requested) == "requested changes"
    assert (control.changes_requested, control.unresolved_conversations) == (True, 1)

    authority.review = HumanReviewSnapshot((), (("reviewer", "APPROVED"),), ("reviewer",), (), 1, "available")
    approved = snapshot(subject, "approved-thread-open")
    control = subject.host.control  # type: ignore[union-attr]
    assert control is not None
    assert workflow_wait(approved) == "conversation resolution"
    assert (control.human_approved, control.distinct_reviewer_approved) == (True, True)

    authority.review = replace(authority.review, unresolved_threads=0)
    clear = snapshot(subject, "thread-resolved")
    control = subject.host.control  # type: ignore[union-attr]
    assert control is not None and workflow_gates_ready(control)
    assert workflow_wait(clear) == "terminal lifecycle"

    authority.pull = replace(authority.pull, base="d" * 40)
    stale = snapshot(subject, "base-advanced")
    assert workflow_wait(stale) == "base update"

    authority.pull = replace(authority.pull, mergeable=False, mergeable_state="dirty")
    conflicted = snapshot(subject, "conflict")
    assert workflow_wait(conflicted) == "conflict resolution"

    authority.pull = replace(authority.pull, base=BASE, mergeable=True, mergeable_state="clean")
    restored = snapshot(subject, "authority-restored")
    control = subject.host.control  # type: ignore[union-attr]
    assert control is not None and workflow_gates_ready(control)
    assert workflow_wait(restored) == "terminal lifecycle"

    authority.pull = replace(authority.pull, draft=True)
    subject.activate("draft-again")
    assert subject.host is not None and subject.host.place("dormant")
    ready(authority)
    resumed = snapshot(subject, "ready-again")
    assert resumed.epoch == 2
    subject.close()


def test_author_approval_is_excluded_case_insensitively(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    authority.pull = replace(authority.pull, author="Author")
    authority.policy_value = replace(authority.policy_value, required_approvals=1, digest="approval-policy")
    authority.review = HumanReviewSnapshot((), (("author", "APPROVED"),), ("author",), (), 0, "available")
    subject = application(tmp_path, authority, runner)

    projection = snapshot(subject, "author-approved")

    control = subject.host.control  # type: ignore[union-attr]
    assert control is not None and not control.human_approved
    assert workflow_wait(projection) == "human review"
    subject.close()


def test_reversible_human_authority_survives_restart_without_duplicate_poll_churn(tmp_path: Path) -> None:
    authority, first_runner = Authority(), Runner()
    ready(authority)
    first = application(tmp_path, authority, first_runner)
    assert workflow_wait(snapshot(first, "clean")) == "terminal lifecycle"
    authority.pull = replace(authority.pull, mergeable=False, mergeable_state="dirty")
    assert workflow_wait(snapshot(first, "conflict")) == "conflict resolution"
    first.close()

    authority.pull = replace(authority.pull, mergeable=True, mergeable_state="clean")
    second_runner = Runner()
    second = application(tmp_path, authority, second_runner)
    assert workflow_wait(snapshot(second, "restored-after-restart")) == "terminal lifecycle"
    history = (tmp_path / "state/history.jsonl").read_text()
    writes = len(authority.transport.writes)

    assert workflow_wait(snapshot(second, "duplicate-clean-poll")) == "terminal lifecycle"
    assert (tmp_path / "state/history.jsonl").read_text() == history
    assert len(authority.transport.writes) == writes
    assert second_runner.reviews == 0

    authority.pull = replace(authority.pull, mergeable=False, mergeable_state="dirty")
    assert workflow_wait(snapshot(second, "same-conflict-edge-after-restart")) == "conflict resolution"
    conflict_history = (tmp_path / "state/history.jsonl").read_text()

    assert workflow_wait(snapshot(second, "duplicate-conflict-poll")) == "conflict resolution"
    assert (tmp_path / "state/history.jsonl").read_text() == conflict_history
    second.close()


def test_state_root_refuses_rebinding(tmp_path: Path) -> None:
    authority, runner = Authority(), Runner()
    ready(authority)
    subject = application(tmp_path, authority, runner)
    subject.activate("poll")
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
        agent_settle=lambda operations: None,
        bot_login=BOT,
        public_clone_url=f"https://example.invalid/repo?x={SECRETS[0]}",
        reminder_delay=10**30,
    )
    subject.activate("poll")
    encoded_requests = json.dumps([asdict(x) for x in runner.requests])
    encoded_history = (tmp_path / "state/history.jsonl").read_text()
    assert all(secret not in encoded_requests and secret not in encoded_history for secret in SECRETS)
    subject.close()
