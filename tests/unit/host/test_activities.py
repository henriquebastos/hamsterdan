import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import ClassVar

from hamsterdan.agents import AgentProtocolError, AmpExecuteRunner, CodingResult
from hamsterdan.agents import ConversationResult as AgentConversationResult
from hamsterdan.agents import ReviewResult as AgentReviewResult
from hamsterdan.contracts.readiness import ActionsObservation, Control, ReadinessCommand, Work
from hamsterdan.github_app.models import CommentReference, GitHubBoundaryError, PublicationResult
from hamsterdan.host.activities import PrReadinessActivities, _confirmation_text, _intent_digest, activity_definitions
from hamsterdan.host.git_publish import GitPublishError, GitPublishResult, payload_digest
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


def test_conversation_gate_projection_and_status_override_latched_lifecycle_details() -> None:
    ready = Control(
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

    gates = {gate["name"]: gate for gate in PrReadinessActivities._conversation_gates(asdict(ready))}

    assert gates["overall"] == {"name": "overall", "ready": True, "blocker": ""}
    assert gates["actions"] == {"name": "actions", "ready": True, "state": "flaky_green"}
    assert PrReadinessActivities._status(asdict(ready)) == (
        "Ready: every observed gate is clear. Clean. I'll keep one paw on the wheel."
    )


def test_expected_publication_runtime_failure_becomes_typed_effect_result(caplog) -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.agent_dispatch = lambda operation, attempt: None
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
            raise GitPublishError("provider refused the publication")

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
    assert "category=publication" in caplog.text
    assert "reason=provider refused the publication" in caplog.text


def test_coding_retries_nonchanging_agent_result_before_one_publication() -> None:
    operations = object.__new__(PrReadinessActivities)
    dispatched: list[str] = []
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.agent_dispatch = lambda operation, attempt: dispatched.append(operation)
    fences: list[tuple] = []
    operations.current_fence = lambda *args: fences.append(args)

    class Runner:
        calls = 0

        def code(self, repository_url, request, *, is_current=None):
            self.calls += 1
            changed = self.calls == 3
            return CodingResult(
                request.kind,
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                request.ref,
                "changed" if changed else "unchanged",
                "not_attempted",
                "diff" if changed else "",
                ["file.txt"] if changed else [],
                [{"check": "passed"}] if changed else [],
                "Apply requested change" if changed else "",
            )

    class Publisher:
        calls = 0

        def publish(self, *args, **kwargs):
            self.calls += 1
            return GitPublishResult("c" * 40)

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = Work(
        "change",
        2,
        "a" * 40,
        "change-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "intent": {}},
    )

    result = operations.change(work)

    assert result.ok is True
    assert operations.runner.calls == 3
    assert operations.git_publisher.calls == 1
    assert dispatched == ["change-operation"] * 3
    assert len(fences) == 4


def test_coding_stops_after_three_nonchanging_agent_results() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.agent_dispatch = lambda operation, attempt: None
    operations.current_fence = lambda *args: None

    class Runner:
        calls = 0

        def code(self, repository_url, request, *, is_current=None):
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
    work = Work(
        "change",
        2,
        "a" * 40,
        "change-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "intent": {}},
    )

    result = operations.change(work)

    assert result.ok is False
    assert operations.runner.calls == 3


def test_coding_retries_protocol_error_with_identical_request_then_publishes_once() -> None:
    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.agent_dispatch = lambda operation, attempt: None
    operations.current_fence = lambda *args: None

    class Runner:
        requests: ClassVar[list] = []

        def code(self, repository_url, request, *, is_current=None):
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
    work = Work(
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
    operations.agent_dispatch = lambda operation, attempt: None
    fences: list[tuple] = []
    operations.current_fence = lambda *args: fences.append(args)

    class Runner:
        calls = 0

        def code(self, repository_url, request, *, is_current=None):
            self.calls += 1
            raise AgentProtocolError("superseded", canceled=True)

    class Publisher:
        def publish(self, *args, **kwargs):
            raise AssertionError("canceled work must not publish")

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = Work(
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
    operations.agent_dispatch = lambda operation, attempt: None
    fence_calls = 0

    def fence(*args):
        nonlocal fence_calls
        fence_calls += 1
        if fence_calls == 2:
            raise RuntimeError("stale authority")

    operations.current_fence = fence

    class Runner:
        calls = 0

        def code(self, repository_url, request, *, is_current=None):
            self.calls += 1
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
        def publish(self, *args, **kwargs):
            raise AssertionError("stale work must not publish")

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = Work(
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


def test_stale_final_fence_after_changed_retry_prevents_publication(caplog) -> None:
    operations = object.__new__(PrReadinessActivities)
    dispatched: list[tuple[str, int]] = []
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.current = None
    operations.agent_dispatch = lambda operation, attempt: dispatched.append((operation, attempt))
    fence_calls = 0

    def fence(*args):
        nonlocal fence_calls
        fence_calls += 1
        if fence_calls == 3:
            raise RuntimeError("stale authority")

    operations.current_fence = fence

    class Runner:
        calls = 0

        def code(self, repository_url, request, *, is_current=None):
            self.calls += 1
            changed = self.calls == 2
            return CodingResult(
                request.kind,
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                request.ref,
                "changed" if changed else "unchanged",
                "not_attempted",
                "diff" if changed else "",
                ["file.txt"] if changed else [],
                [{"check": "passed"}] if changed else [],
                "Apply requested change" if changed else "",
            )

    class Publisher:
        calls = 0

        def publish(self, *args, **kwargs):
            self.calls += 1
            return GitPublishResult("c" * 40)

    operations.runner = Runner()
    operations.git_publisher = Publisher()
    work = Work(
        "change",
        2,
        "a" * 40,
        "change-operation",
        payload={"base_head": "b" * 40, "policy_digest": "policy", "intent": {}},
    )

    assert operations.change(work).ok is False
    assert operations.runner.calls == 2
    assert dispatched == [("change-operation", 1), ("change-operation", 2)]
    assert operations.git_publisher.calls == 0
    assert fence_calls == 3
    assert "coding result rejected kind=change category=stale_authority" in caplog.text


def test_confirmed_change_bridges_real_disposable_checkout_to_host_publication(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ("git", "-C", str(source), *args), check=True, text=True, capture_output=True
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    fixture = source / "fixture.txt"
    fixture.write_text("before\n")
    git("add", "fixture.txt")
    git("commit", "-qm", "requested head")
    requested_head = git("rev-parse", "HEAD")
    (source / "later.txt").write_text("default branch advanced\n")
    git("add", "later.txt")
    git("commit", "-qm", "advance source after requested head")
    advanced_head = git("rev-parse", "HEAD")

    script = tmp_path / "agent.py"
    script.write_text(
        "import json, pathlib, subprocess\n"
        "root = pathlib.Path.cwd()\n"
        "request = json.loads((root / '.impetus/request.json').read_text())\n"
        "assert request['selected_work'] == "
        + repr([{"kind": "change", "arguments": {"request": "update the tracked fixture"}}])
        + "\n"
        "observed = subprocess.run(['git', 'rev-parse', 'HEAD'], check=True, text=True, capture_output=True).stdout.strip()\n"
        "reflog = subprocess.run(['git', 'reflog', '--format=%gs'], check=True, text=True, capture_output=True).stdout\n"
        "assert observed == request['head'] and 'moving from' in reflog and request['head'] in reflog\n"
        "assert not (root / 'later.txt').exists()\n"
        "(root / 'fixture.txt').write_text('after\\n')\n"
        "result = {key: request[key] for key in ('kind','repository','pull_request','epoch','head','base','ref')}\n"
        "result.update(status='changed', reproduction_status='not_attempted', diff='CLAIMED', "
        "changed_files=['claimed.txt'], validation_evidence=[{'detached_at_request_head': True, 'head': observed}], "
        "proposed_commit_message='Update tracked fixture')\n"
        "(root / '.impetus/result.json').write_text(json.dumps(result))\n"
    )

    class Publisher:
        calls: ClassVar[list[tuple[CodingResult, dict[str, object]]]] = []

        def publish(self, result: CodingResult, **kwargs: object) -> GitPublishResult:
            self.calls.append((result, kwargs))
            return GitPublishResult("c" * 40)

    operations = object.__new__(PrReadinessActivities)
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = str(source)
    operations.runner = AmpExecuteRunner(argv=(sys.executable, str(script)))
    operations.git_publisher = Publisher()
    operations.current = None
    operations.agent_dispatch = lambda operation, attempt: None
    fences: list[tuple[object, ...]] = []
    operations.current_fence = lambda *args: fences.append(args)
    intent = {"kind": "change", "arguments": {"request": "update the tracked fixture"}}
    payload = {"base_head": requested_head, "policy_digest": "policy", "intent": intent}
    work = Work("change", 3, requested_head, "confirmed-change-operation", payload=payload)

    result = operations.change(work)

    assert result.ok and result.head == requested_head and result.provisional_head == "c" * 40
    assert result.operation == work.operation
    assert len(operations.git_publisher.calls) == 1
    coding_result, publication = operations.git_publisher.calls[0]
    assert isinstance(coding_result, CodingResult)
    assert coding_result.changed_files == ["fixture.txt"]
    assert "CLAIMED" not in coding_result.diff
    assert "-before" in coding_result.diff and "+after" in coding_result.diff
    assert coding_result.validation_evidence == [{"detached_at_request_head": True, "head": requested_head}]
    assert publication == {
        "operation": work.operation,
        "payload_digest": payload_digest(payload),
        "expected_head": requested_head,
        "base_head": requested_head,
        "merge_base": False,
    }
    assert fences and set(fences) == {(3, requested_head, work.operation, requested_head, "policy")}
    assert fixture.read_text() == "before\n"
    assert git("rev-parse", "HEAD") == advanced_head


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
    work = Work(
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
    dispatched: list[str] = []
    operations.repository = "owner/repo"
    operations.pr_number = 7
    operations.public_clone_url = "https://example.invalid/repo.git"
    operations.workflow_path = "ci.yml"
    operations.current = None
    operations.agent_dispatch = lambda operation, attempt: None
    operations.current_fence = lambda *args: None
    operations.agent_dispatch = lambda operation, attempt: dispatched.append(operation)

    class Authority:
        def comments(self):
            return ()

        def select_run(self, workflow, head):
            return None

    class Runner:
        def review(self, repository_url, request, *, is_current=None):
            assert dispatched == ["review-operation"]
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
    operations.agent_dispatch = lambda operation, attempt: dispatched.append(operation)
    operations.current_fence = lambda *args: None

    class Runner:
        def converse(self, repository_url, request, *, is_current=None):
            assert dispatched == ["conversation-operation"]
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
            "control": asdict(Control("owner/repo", 7, 2, "a" * 40, "b" * 40, False, True)),
        },
    )

    result = operations.conversation(work)

    assert dispatched == ["conversation-operation"]
    assert len(result.intents) == 1
    assert result.intents[0]["kind"] == "reply"
    assert "couldn't interpret" in result.intents[0]["arguments"]["message"]
    assert "no workflow change" in result.intents[0]["arguments"]["message"]


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
