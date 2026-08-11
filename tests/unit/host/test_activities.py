from dataclasses import replace
from typing import ClassVar

import pytest
from petrus.motus.activity import ActivityError

from hamsterdan.agents import AgentProtocolError, AgentResultCategory, CodingResult
from hamsterdan.agents import ConversationResult as AgentConversationResult
from hamsterdan.agents import ReviewResult as AgentReviewResult
from hamsterdan.contracts.readiness import (
    ActionsDiscoveryRequest,
    ActionsObservation,
    ActionsRerunRequest,
    ActionsState,
    Authority,
    ChangeRequest,
    ConversationClassificationRequest,
    ConversationObservation,
    ConversationPublicationRequest,
    ConversationPublicationState,
    DashboardPublicationRequest,
    DashboardPublicationState,
    FindingPublicationRequest,
    FindingPublicationResult,
    FindingPublicationState,
    HumanState,
    Intent,
    MutationState,
    ReadinessCommand,
    ReadinessPublicationState,
    ReadinessSnapshot,
    ReminderPublicationRequest,
    RepairRequest,
    RepairResult,
    ReviewRequest,
    ReviewState,
    project_readiness,
)
from hamsterdan.github_app.models import CommentReference, GitHubBoundaryError, PublicationResult
from hamsterdan.host.activities import PrReadinessActivities, StaleAuthorityError, activity_definitions
from hamsterdan.host.git_publish import GitPublishError, GitPublishResult, PublicationCategory
from hamsterdan.readiness.net import ACTIVITY_TRANSITIONS

REQUEST_TYPES = {
    "review": ReviewRequest,
    "actions_discovery": ActionsDiscoveryRequest,
    "actions_rerun": ActionsRerunRequest,
    "conversation": ConversationPublicationRequest,
    "change": ChangeRequest,
    "repair": RepairRequest,
    "finding": FindingPublicationRequest,
    "dashboard": DashboardPublicationRequest,
    "reminder": ReminderPublicationRequest,
}


def readiness_snapshot(repository, pr_number, epoch, head, base_head, strict_base=True, base_current=True, **changes):
    token_types = (
        Authority,
        ActionsState,
        ReviewState,
        HumanState,
        MutationState,
        FindingPublicationState,
        ConversationPublicationState,
        DashboardPublicationState,
        ReadinessPublicationState,
    )
    values = ReadinessSnapshot(
        repository, pr_number, epoch, head, base_head, strict_base, base_current, **changes
    ).dump()
    return project_readiness(
        *(
            value_type(**{name: values[name] for name in value_type.__dataclass_fields__ if name in values})
            for value_type in token_types
        )
    )


def request(kind, epoch, head, operation="", sequence=0, payload=None):
    values = dict(payload or {})
    values.setdefault("base_head", "base")
    values.setdefault("policy_digest", "policy")
    if kind == "dashboard":
        values.setdefault(
            "control",
            readiness_snapshot("repo", 1, epoch, head, values["base_head"]),
        )
    if kind == "review":
        values = {
            "strict_base": True,
            "base_current": True,
            "policy": {},
            "prior_findings": [],
            "prior_lineage": [],
            **values,
        }
    if kind == "finding":
        values.setdefault("lineage", [])
    if kind == "repair" and not values.get("actions"):
        values["actions"] = ActionsObservation(epoch, head, "", 0, "unavailable")
    if kind == "change" and not values.get("intent"):
        values["intent"] = Intent(epoch, head, "change", "digest", True, True)
    elif kind == "change" and isinstance(values.get("intent"), dict):
        intent = values["intent"]
        values["intent"] = {
            "epoch": epoch,
            "head": head,
            "digest": "digest",
            "authorized": True,
            "blocking": True,
            **intent,
        }
    if kind == "conversation" and ("comment" in values or "control" in values):
        request_type = ConversationClassificationRequest
        comment = values.get("comment", {})
        values["comment"] = ConversationObservation(
            epoch,
            head,
            True,
            str(comment.get("text", "")),
            actor_id=int(comment.get("actor_id", 0)),
            actor_login=str(comment.get("actor_login", "")),
        )
    elif kind == "conversation":
        request_type = ConversationPublicationRequest
        intent = values.get("intent", {})
        values["intent"] = (
            Intent(
                epoch,
                head,
                "reply",
                "digest",
                True,
                False,
                dict(intent.get("arguments", {})) if isinstance(intent, dict) else {},
            )
            if isinstance(intent, dict)
            else intent
        )
    else:
        request_type = REQUEST_TYPES[kind]
    for key, value_type in (("actions", ActionsObservation), ("intent", Intent), ("control", ReadinessSnapshot)):
        if key in values and isinstance(values[key], dict):
            values[key] = value_type(**values[key])
    return request_type(epoch=epoch, head=head, operation=operation, **values)


def test_activity_definitions_are_the_exact_typed_net_mapping() -> None:
    operations = object.__new__(PrReadinessActivities)
    definitions = activity_definitions(operations)

    assert set(definitions) == {path.removeprefix("execute.") for path in ACTIVITY_TRANSITIONS}
    for path, (input_type, output_type) in ACTIVITY_TRANSITIONS.items():
        definition = definitions[path.removeprefix("execute.")]
        assert tuple(definition.parameters.values()) == (input_type,)
        assert definition.result is output_type


def test_complete_fence_uses_effect_payload_and_readiness_command() -> None:
    operations = object.__new__(PrReadinessActivities)
    calls: list[tuple] = []
    operations.current_fence = lambda *values: calls.append(values)

    operations._fence(request("dashboard", 2, "h", "op", payload={"base_head": "b", "policy_digest": "p"}))
    operations._fence(ReadinessCommand(3, "h2", "op2", "b2", "p2"))

    assert calls == [(2, "h", "op", "b", "p"), (3, "h2", "op2", "b2", "p2")]


def test_readiness_replay_accepts_the_exact_legacy_voice_payload() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.current_fence = lambda *args: None
    command = ReadinessCommand(3, "a" * 40, "readiness-operation", "b" * 40, "policy")
    marker = f"<!-- hamsterdan:readiness operation={command.operation} head={command.head} -->"
    legacy = "## Hamsterdan readiness advisory\n\nAll observed gates are ready. Advisory only; Hamsterdan does not merge PRs."

    class Publisher:
        compatible: ClassVar[tuple[str, ...] | None] = None

        def marker(self, kind, operation, head):
            return marker

        def _find(self, expected_marker):
            return {"id": 1, "body": f"{legacy}\n\n{marker}", "html_url": "url"}

        def immutable(self, kind, operation, epoch, head, body, *, compatible_bodies=()):
            self.compatible = compatible_bodies
            return PublicationResult("existing", CommentReference(1, "url"))

    operations.publisher = Publisher()

    result = operations.readiness_publish(command)

    assert result.ok
    assert operations.publisher.compatible == (legacy,)


@pytest.mark.parametrize("kind", ["dashboard", "readiness"])
def test_durable_publications_classify_boundary_as_retryable_but_stale_as_typed_result(kind: str) -> None:
    operations = object.__new__(PrReadinessActivities)
    work = (
        request("dashboard", 2, "head", "operation")
        if kind == "dashboard"
        else ReadinessCommand(2, "head", "operation", "base", "policy")
    )

    def boundary(*args, **kwargs):
        raise GitHubBoundaryError("unavailable")

    operations.current_fence = lambda *args: None
    if kind == "dashboard":
        operations.publisher = type("Publisher", (), {"dashboard": boundary})()
        invoke = operations.dashboard_publish
    else:
        operations._immutable = boundary
        invoke = operations.readiness_publish

    with pytest.raises(ActivityError) as raised:
        invoke(work)
    assert raised.value.failure.retryable

    operations.current_fence = lambda *args: (_ for _ in ()).throw(StaleAuthorityError("stale"))
    if kind == "readiness":
        operations._immutable = PrReadinessActivities._immutable.__get__(operations)
    result = invoke(work)
    assert (result.epoch, result.head, result.operation, result.ok, result.capability_available) == (
        2,
        "head",
        "operation",
        False,
        True,
    )


def test_dashboard_projects_current_gates_instead_of_latched_announcement() -> None:
    ready = readiness_snapshot(
        "repo",
        7,
        1,
        "head",
        "base",
        True,
        True,
        actions="green",
        review="clear",
        findings_published=True,
        human_approved=True,
        mergeable=True,
    )
    dashboard = PrReadinessActivities._dashboard(ready.dump())
    assert "Readiness: **ready**" in dashboard
    assert "Coordinating agent review: **clear**" in dashboard
    assert "Base policy: **strict / update required**" in dashboard
    assert "Observed base: `base` · Base current: True" in dashboard

    no_longer_ready = replace(ready, human_approved=False, announced=True)
    assert "Readiness: **not ready**" in PrReadinessActivities._dashboard(no_longer_ready.dump())


def test_conversation_gate_projection_and_status_override_latched_lifecycle_details() -> None:
    ready = readiness_snapshot(
        "repo",
        7,
        1,
        "head",
        "base",
        True,
        True,
        actions="flaky_green",
        rerun_requested=True,
        review="clear",
        findings_published=True,
        human_approved=True,
        mergeable=True,
        wait="terminal lifecycle",
    )

    gates = {gate["name"]: gate for gate in PrReadinessActivities._conversation_gates(ready.dump())}

    assert gates["overall"] == {"name": "overall", "ready": True, "blocker": ""}
    assert gates["actions"] == {"name": "actions", "ready": True, "state": "flaky_green"}
    assert PrReadinessActivities._status(ready.dump()) == (
        "Ready: every observed gate is clear. Clean. I'll keep one paw on the wheel."
    )


def test_expected_publication_runtime_failure_becomes_typed_effect_result(caplog) -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.current_fence = lambda *args: None

    class Runner:
        def code(self, repository_url, request, *, operation, attempt, is_current=None):
            return CodingResult(
                request.kind,
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                request.ref,
                "changed",
                "confirmed",
                "diff",
                ["file.txt"],
                [{"check": "passed"}],
                "Conservative repair",
            )

    class Publisher:
        def publish(self, *args, **kwargs):
            raise GitPublishError(PublicationCategory.REF_CAS, "provider refused the publication")

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = request(
        "repair",
        2,
        "a" * 40,
        "repair-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "actions": {}},
    )

    result = operations.repair(work)

    assert isinstance(result, RepairResult) and result.ok is False
    assert result.operation == "repair-operation"
    assert result.publication_category == PublicationCategory.REF_CAS
    assert "category=publication" in caplog.text
    assert "reason=provider refused the publication" in caplog.text


def test_coding_unchanged_result_is_terminal_without_publication_or_retry() -> None:
    operations = object.__new__(PrReadinessActivities)
    dispatched: list[str] = []
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    fences: list[tuple] = []
    operations.current_fence = lambda *args: fences.append(args)

    class Runner:
        calls = 0

        def code(self, repository_url, request, *, operation, attempt, is_current=None):
            self.calls += 1
            dispatched.append(operation)
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

    class Publisher:
        calls = 0

        def publish(self, *args, **kwargs):
            self.calls += 1
            return GitPublishResult("c" * 40)

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = request(
        "change",
        2,
        "a" * 40,
        "change-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "intent": {}},
    )

    result = operations.change(work)

    assert result.ok is False
    assert result.agent_result_category == AgentResultCategory.UNCHANGED
    assert operations.runner.calls == 1
    assert operations.git_publisher.calls == 0
    assert dispatched == ["change-operation"]
    assert len(fences) == 1


def test_coding_unable_result_is_terminal_without_publication_or_retry() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.current_fence = lambda *args: None

    class Runner:
        calls = 0

        def code(self, repository_url, request, *, operation, attempt, is_current=None):
            self.calls += 1
            return CodingResult(
                request.kind,
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                request.ref,
                "unable",
                "not_attempted",
                "",
                [],
                [],
                "",
            )

    class Publisher:
        def publish(self, *args, **kwargs):
            raise AssertionError("nonchanging work must not publish")

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = request(
        "change",
        2,
        "a" * 40,
        "change-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "intent": {}},
    )

    result = operations.change(work)

    assert result.ok is False
    assert result.agent_result_category == AgentResultCategory.UNABLE
    assert operations.runner.calls == 1


def test_coding_retries_protocol_error_with_identical_request_then_publishes_once() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.current_fence = lambda *args: None

    class Runner:
        requests: ClassVar[list] = []

        def code(self, repository_url, request, *, operation, attempt, is_current=None):
            self.requests.append(request)
            if len(self.requests) == 1:
                raise AgentProtocolError("temporary failure")
            return CodingResult(
                request.kind,
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                request.ref,
                "changed",
                "not_attempted",
                "diff",
                ["file.txt"],
                [{"check": "passed"}],
                "Apply requested change",
            )

    class Publisher:
        calls = 0

        def publish(self, *args, **kwargs):
            self.calls += 1
            return GitPublishResult("c" * 40)

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = request(
        "change",
        2,
        "a" * 40,
        "change-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "intent": {}},
    )

    assert operations.change(work).ok is True
    assert len(operations.runner.requests) == 2
    assert operations.runner.requests[0] == operations.runner.requests[1]
    assert operations.git_publisher.calls == 1


def test_canceled_coding_attempt_does_not_retry_or_publish() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    fences: list[tuple] = []
    operations.current_fence = lambda *args: fences.append(args)

    class Runner:
        calls = 0

        def code(self, repository_url, request, *, operation, attempt, is_current=None):
            self.calls += 1
            raise AgentProtocolError("superseded", canceled=True)

    class Publisher:
        def publish(self, *args, **kwargs):
            raise AssertionError("canceled work must not publish")

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = request(
        "change",
        2,
        "a" * 40,
        "change-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "intent": {}},
    )

    assert operations.change(work).ok is False
    assert operations.runner.calls == 1
    assert len(fences) == 1


def test_stale_authority_between_coding_attempts_stops_before_retry_and_publication(caplog) -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    fence_calls = 0

    def fence(*args):
        nonlocal fence_calls
        fence_calls += 1
        if fence_calls == 2:
            raise RuntimeError("stale authority")

    operations.current_fence = fence

    class Runner:
        calls = 0

        def code(self, repository_url, request, *, operation, attempt, is_current=None):
            self.calls += 1
            raise AgentProtocolError("retryable protocol failure")

    class Publisher:
        def publish(self, *args, **kwargs):
            raise AssertionError("stale work must not publish")

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = request(
        "change",
        2,
        "a" * 40,
        "change-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "intent": {}},
    )

    assert operations.change(work).ok is False
    assert operations.runner.calls == 1
    assert fence_calls == 2
    assert "category=stale_authority attempt=2" in caplog.text


@pytest.mark.parametrize(
    ("failure", "category", "log_category"),
    [
        (RuntimeError("stale authority"), PublicationCategory.CURRENT_AUTHORITY, "stale_authority"),
        (GitHubBoundaryError("unavailable"), PublicationCategory.BOUNDARY_UNAVAILABLE, "publication_boundary"),
    ],
)
def test_final_fence_failure_retains_closed_category_before_publication(
    caplog, failure: RuntimeError, category: PublicationCategory, log_category: str
) -> None:
    operations = object.__new__(PrReadinessActivities)
    dispatched: list[tuple[str, int]] = []
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    fence_calls = 0

    def fence(*args):
        nonlocal fence_calls
        fence_calls += 1
        if fence_calls == 2:
            raise failure

    operations.current_fence = fence

    class Runner:
        calls = 0

        def code(self, repository_url, request, *, operation, attempt, is_current=None):
            self.calls += 1
            dispatched.append((operation, attempt))
            return CodingResult(
                request.kind,
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                request.ref,
                "changed",
                "not_attempted",
                "diff",
                ["file.txt"],
                [{"check": "passed"}],
                "Apply requested change",
            )

    class Publisher:
        calls = 0

        def publish(self, *args, **kwargs):
            self.calls += 1
            return GitPublishResult("c" * 40)

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = request(
        "change",
        2,
        "a" * 40,
        "change-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "intent": {}},
    )

    result = operations.change(work)
    assert result.ok is False
    assert result.publication_category == category
    assert operations.runner.calls == 1
    assert dispatched == [("change-operation", 1)]
    assert operations.git_publisher.calls == 0
    assert fence_calls == 2
    assert f"coding result rejected kind=change category={log_category}" in caplog.text


def test_stale_finding_publication_becomes_typed_effect_result() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.current_fence = lambda *args: (_ for _ in ()).throw(RuntimeError("stale"))
    work = request(
        "finding",
        2,
        "a" * 40,
        "finding-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "findings": []},
    )

    result = operations.finding_publish(work)

    assert isinstance(result, FindingPublicationResult) and result.ok is False
    assert result.operation == "finding-operation"


def test_conversation_provider_failure_becomes_a_retryable_activity_error() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations._immutable = lambda *args: (_ for _ in ()).throw(GitHubBoundaryError("transient provider failure"))
    work = request(
        "conversation",
        2,
        "a" * 40,
        "conversation-operation",
        payload={"intent": {"arguments": {"message": "Safe reply"}}},
    )

    with pytest.raises(ActivityError) as raised:
        operations.conversation_publish(work)

    assert raised.value.failure.kind == "GitHubBoundaryError"
    assert raised.value.failure.retryable is True


def test_one_coordinated_review_publishes_multiple_findings_with_one_authority_lease() -> None:
    operations = object.__new__(PrReadinessActivities)
    fences: list[tuple] = []
    operations.current_fence = lambda *args: fences.append(args)

    class Publisher:
        published: ClassVar[list[tuple]] = []

        def marker(self, kind, operation, head):
            return f"{kind}:{operation}:{head}"

        def _find(self, marker):
            return None

        def finding(self, operation, epoch, head, body, **kwargs):
            self.published.append((operation, epoch, head, body, kwargs))
            return PublicationResult(
                "created", CommentReference(len(self.published), f"url-{len(self.published)}"), inline=True
            )

    operations.publisher = Publisher()
    findings = [
        {
            "id": identity,
            "title": f"Finding {identity}",
            "body": "Actionable detail",
            "evidence": "Exact evidence",
            "path": "file.py",
            "line": index,
            "related_locations": [],
            "suggestion": "",
        }
        for index, identity in enumerate(("one", "two"), 1)
    ]
    work = request(
        "finding",
        2,
        "a" * 40,
        "finding-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "findings": findings, "lineage": []},
    )

    result = operations.finding_publish(work)

    assert result.ok and result.references == [
        {"finding_id": "one", "url": "url-1", "inline": True},
        {"finding_id": "two", "url": "url-2", "inline": True},
    ]
    assert len(operations.publisher.published) == 2
    assert all(item[-1]["authority_operation"] == "finding-operation" for item in operations.publisher.published)
    assert [(item[-1]["path"], item[-1]["line"]) for item in operations.publisher.published] == [
        ("file.py", 1),
        ("file.py", 2),
    ]
    assert fences == [(2, "a" * 40, "finding-operation", "b" * 40, "policy")]


def test_stale_actions_rerun_becomes_a_typed_canceled_observation() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.workflow_path = "ci.yml"
    operations.current_fence = lambda *args: (_ for _ in ()).throw(RuntimeError("stale"))

    class Authority:
        def workflow_runs(self, workflow, head):
            return [type("Run", (), {"id": 17, "attempt": 1})()]

    class Reruns:
        def request(self, *args, **kwargs):
            raise AssertionError("a stale rerun must not reach the provider")

    operations.authority = Authority()
    operations.reruns = Reruns()
    basis = ActionsObservation(1, "a" * 40, "17", 1, "failure")
    work = request(
        "actions_rerun",
        1,
        "a" * 40,
        "rerun-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "actions": basis.dump()},
    )

    result = operations.actions_rerun(work)

    assert result.conclusion == "canceled"
    assert result.operation == "rerun-operation"


def test_review_preserves_terminal_prior_finding_detail_for_dashboard_lineage() -> None:
    operations = object.__new__(PrReadinessActivities)
    dispatched: list[str] = []
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.workflow_path = "ci.yml"
    operations.current = None
    operations.current_fence = lambda *args: None

    class Authority:
        def comments(self):
            return ()

        def select_run(self, workflow, head):
            return None

    class Runner:
        def review(self, repository_url, request, *, operation, attempt, is_current=None):
            dispatched.append(operation)
            return AgentReviewResult(
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                "clear",
                [],
                [{"finding_id": "finding-1", "state": "resolved", "supersedes": None}],
            )

    operations.authority = Authority()
    operations.runner = Runner()
    work = request(
        "review",
        2,
        "a" * 40,
        "review-operation",
        payload={
            "base_head": "b" * 40,
            "policy_digest": "policy",
            "prior_findings": [
                {
                    "id": "finding-1",
                    "title": "Old finding",
                    "comment_url": "https://example.invalid/finding-1",
                }
            ],
        },
    )

    result = operations.review(work)

    assert result.status == "clear"
    assert dispatched == ["review-operation"]
    assert result.findings == [
        {
            "id": "finding-1",
            "title": "Old finding",
            "comment_url": "https://example.invalid/finding-1",
            "disposition": "resolved",
        }
    ]


def test_conversation_declarations_give_agents_exact_intent_arguments() -> None:
    operations = object.__new__(PrReadinessActivities)

    declarations = {item["type"]: item for item in operations._intent_declarations({})}

    assert declarations["reply"]["arguments"] == ["message"]
    assert declarations["dismiss"]["arguments"] == ["findings"]
    assert declarations["snooze"]["arguments"] == []
    assert declarations["reassign"]["arguments"] == ["assignee"]
    assert declarations["change"]["arguments"] == ["request"]
    assert declarations["update_base"]["arguments"] == ["request"]
    assert declarations["resolve_conflict"]["arguments"] == ["request"]


def test_conversation_defensively_rejects_multiple_runner_intents() -> None:
    operations = object.__new__(PrReadinessActivities)
    dispatched: list[str] = []
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.current_fence = lambda *args: None

    class Runner:
        def converse(self, repository_url, request, *, operation, attempt, is_current=None):
            dispatched.append(operation)
            reply = {
                "type": "reply",
                "arguments": {"message": "Duplicate"},
                "mutation": False,
                "explicit": False,
                "confidence": 1,
            }
            return AgentConversationResult(
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                [reply, reply],
            )

    operations.runner = Runner()
    work = request(
        "conversation",
        2,
        "a" * 40,
        "conversation-operation",
        payload={
            "base_head": "b" * 40,
            "policy_digest": "policy",
            "comment": {"text": "explain the blockers", "actor_id": 1, "actor_login": "human"},
            "control": readiness_snapshot("owner/repo", 7, 2, "a" * 40, "b" * 40, False, True).dump(),
        },
    )

    result = operations.conversation(work)

    assert dispatched == ["conversation-operation"]
    assert len(result.intents) == 1
    assert result.intents[0].kind == "reply"
    assert "couldn't interpret" in result.intents[0].arguments["message"]
    assert "no workflow change" in result.intents[0].arguments["message"]


def test_explicit_mutation_intent_is_immediately_authorized() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    work = request(
        "conversation",
        2,
        "a" * 40,
        payload={"base_head": "b" * 40, "policy_digest": "policy"},
    )
    item = {"type": "change", "arguments": {"request": "fix the finding"}}

    intent = operations._intent(item, work, {})

    assert intent.authorized is True
    assert intent.blocking is True
    assert intent.arguments == item["arguments"]


def test_identical_reply_content_from_distinct_comments_has_distinct_intent_identity() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    first = request(
        "conversation",
        2,
        "a" * 40,
        payload={"base_head": "b" * 40, "policy_digest": "policy"},
    )
    second = replace(first, operation="conversation:distinct-comment")
    item = {"type": "reply", "arguments": {"message": "Same reply"}}

    first_intent = operations._intent(item, first, {})
    second_intent = operations._intent(item, second, {})

    assert first_intent.arguments == second_intent.arguments
    assert first_intent.digest != second_intent.digest
