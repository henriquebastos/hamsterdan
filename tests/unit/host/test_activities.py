from dataclasses import asdict, replace
from typing import ClassVar

from hamsterdan.agents import CodingResult
from hamsterdan.agents import ConversationResult as AgentConversationResult
from hamsterdan.agents import ReviewResult as AgentReviewResult
from hamsterdan.contracts.readiness import ActionsObservation, Control, ReadinessCommand, Work
from hamsterdan.github_app.models import CommentReference, GitHubBoundaryError, PublicationResult
from hamsterdan.host.activities import PrReadinessActivities, _confirmation_text, _intent_digest, activity_definitions
from hamsterdan.readiness.net import ACTIVITY_TRANSITIONS


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

    operations._fence(Work("dashboard", 2, "h", "op", payload={"base_head": "b", "policy_digest": "p"}))
    operations._fence(ReadinessCommand(3, "h2", "op2", "b2", "p2"))

    assert calls == [(2, "h", "op", "b", "p"), (3, "h2", "op2", "b2", "p2")]


def test_dashboard_projects_current_gates_instead_of_latched_announcement() -> None:
    ready = Control(
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
    dashboard = PrReadinessActivities._dashboard(asdict(ready))
    assert "Readiness: **ready**" in dashboard
    assert "Coordinating agent review: **clear**" in dashboard
    assert "Base policy: **strict / update required**" in dashboard
    assert "Observed base: `base` · Base current: True" in dashboard

    no_longer_ready = replace(ready, human_approved=False, announced=True)
    assert "Readiness: **not ready**" in PrReadinessActivities._dashboard(asdict(no_longer_ready))


def test_expected_publication_runtime_failure_becomes_typed_effect_result() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.current_fence = lambda *args: None

    class Runner:
        def code(self, repository_url, request, *, is_current=None):
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
            raise RuntimeError("provider refused the publication")

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = Work(
        "repair",
        2,
        "a" * 40,
        "repair-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "actions": {}},
    )

    result = operations.repair(work)

    assert result.kind == "repair" and result.ok is False
    assert result.operation == "repair-operation"


def test_stale_finding_publication_becomes_typed_effect_result() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.current_fence = lambda *args: (_ for _ in ()).throw(RuntimeError("stale"))
    work = Work(
        "finding",
        2,
        "a" * 40,
        "finding-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "findings": []},
    )

    result = operations.finding_publish(work)

    assert result.kind == "finding" and result.ok is False
    assert result.operation == "finding-operation"


def test_conversation_provider_failure_becomes_a_retryable_typed_result() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations._immutable = lambda *args: (_ for _ in ()).throw(GitHubBoundaryError("transient provider failure"))
    work = Work(
        "conversation",
        2,
        "a" * 40,
        "conversation-operation",
        payload={"intent": {"arguments": {"message": "Safe reply"}}},
    )

    result = operations.conversation_publish(work)

    assert result.kind == "conversation" and result.ok is False
    assert result.operation == "conversation-operation"
    assert result.capability_available is False


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
            return PublicationResult("created", CommentReference(len(self.published), f"url-{len(self.published)}"))

    operations.publisher = Publisher()
    findings = [
        {
            "id": identity,
            "title": f"Finding {identity}",
            "body": "Actionable detail",
            "evidence": "Exact evidence",
            "path": "file.py",
            "line": index,
        }
        for index, identity in enumerate(("one", "two"), 1)
    ]
    work = Work(
        "finding",
        2,
        "a" * 40,
        "finding-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "findings": findings, "lineage": []},
    )

    result = operations.finding_publish(work)

    assert result.ok and result.references == [
        {"finding_id": "one", "url": "url-1"},
        {"finding_id": "two", "url": "url-2"},
    ]
    assert len(operations.publisher.published) == 2
    assert all(item[-1]["authority_operation"] == "finding-operation" for item in operations.publisher.published)
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
    work = Work(
        "actions_rerun",
        1,
        "a" * 40,
        "rerun-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "actions": asdict(basis)},
    )

    result = operations.actions_rerun(work)

    assert result.conclusion == "canceled"
    assert result.operation == "rerun-operation"


def test_review_preserves_terminal_prior_finding_detail_for_dashboard_lineage() -> None:
    operations = object.__new__(PrReadinessActivities)
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
        def review(self, repository_url, request, *, is_current=None):
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
    work = Work(
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
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.current_fence = lambda *args: None

    class Runner:
        def converse(self, repository_url, request, *, is_current=None):
            reply = {
                "type": "reply",
                "arguments": {"message": "Duplicate"},
                "mutation": False,
                "explicit": False,
                "confidence": 1,
                "confirmation": False,
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
    work = Work(
        "conversation",
        2,
        "a" * 40,
        "conversation-operation",
        payload={
            "base_head": "b" * 40,
            "policy_digest": "policy",
            "comment": {"text": "explain the blockers", "actor_id": 1, "actor_login": "human"},
            "control": {},
        },
    )

    result = operations.conversation(work)

    assert len(result.intents) == 1
    assert result.intents[0]["kind"] == "reply"
    assert "could not interpret" in result.intents[0]["arguments"]["message"]


def test_confirmation_requires_exact_human_text_pending_arguments_and_current_fence() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    work = Work(
        "conversation",
        2,
        "a" * 40,
        payload={"base_head": "b" * 40, "policy_digest": "policy"},
    )
    item = {"type": "change", "arguments": {"request": "fix the finding"}, "confirmation": True}
    digest = _intent_digest(operations.repository, operations.pr_number, work, "change", item["arguments"])
    control = {
        "pending_intent": {"kind": "change", "arguments": item["arguments"]},
        "pending_intent_digest": digest,
    }
    exact = {"text": _confirmation_text("change", digest)}

    assert operations._confirmation_matches(item, exact, control, work)
    assert not operations._confirmation_matches(item, {"text": "please do it"}, control, work)
    assert not operations._confirmation_matches(item, {"text": _confirmation_text("change", "0" * 64)}, control, work)
    assert not operations._confirmation_matches(
        item | {"arguments": {"request": "different change"}}, exact, control, work
    )
    stale = replace(work, payload=work.payload | {"policy_digest": "new-policy"})
    assert not operations._confirmation_matches(item, exact, control, stale)
