from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
import pytest
from githubkit import GitHub

from hamsterdan.github_app.effects import CommentPublisher, CommentRerunBroker
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.github_app.models import ActionsRunSnapshot, GitHubBoundaryError, WireResponse
from hamsterdan.github_app.transport import GitHubGraphQL, GitHubKitTransport

HEAD = "a" * 40
BASE = "b" * 40


class FakeTransport:
    def __init__(self) -> None:
        self.responses: dict[tuple[str, str], WireResponse] = {}
        self.page_values: dict[str, tuple[dict[str, Any], ...]] = {}
        self.calls: list[tuple[str, str, Mapping[str, Any] | None]] = []

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> WireResponse:
        self.calls.append((method, path, body))
        key = (method, path)
        assert key in self.responses, key
        return self.responses[key]

    def pages(self, path: str) -> tuple[dict[str, Any], ...]:
        self.calls.append(("PAGES", path, None))
        assert path in self.page_values, path
        return self.page_values[path]


def pull() -> dict[str, Any]:
    return {
        "state": "open",
        "draft": True,
        "head": {"sha": HEAD, "ref": "topic", "repo": {"full_name": "owner/repo"}},
        "base": {"sha": BASE, "ref": "main"},
        "mergeable": True,
        "merged": False,
        "user": {"login": "author"},
    }


def authority(fake: FakeTransport) -> GitHubAuthority:
    return GitHubAuthority(fake, "owner/repo", 7)


def test_graphql_ref_update_atomically_binds_before_and_after_oids() -> None:
    class RefTransport(FakeTransport):
        def __init__(self, stale: bool = False) -> None:
            super().__init__()
            self.stale = stale

        def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> WireResponse:
            self.calls.append((method, path, body))
            assert method == "POST" and path == "/graphql" and body is not None
            if len(self.calls) == 1:
                return WireResponse(200, {"data": {"repository": {"id": "repository-node"}}})
            if self.stale:
                return WireResponse(200, {"data": {"updateRefs": None}, "errors": [{"message": "stale"}]})
            variables = body["variables"]
            assert isinstance(variables, dict)
            change = variables["input"]
            assert isinstance(change, dict)
            client_id = change["clientMutationId"]
            return WireResponse(200, {"data": {"updateRefs": {"clientMutationId": client_id}}})

    fake = RefTransport()
    GitHubGraphQL(fake).compare_and_swap_ref("owner/repo", "refs/heads/topic", HEAD, BASE)

    query, mutation = fake.calls
    assert query[2] is not None
    assert query[2] == {
        "query": query[2]["query"],
        "variables": {"owner": "owner", "repository": "repo"},
    }
    assert mutation[2] is not None
    assert "updateRefs" in mutation[2]["query"]
    variables = mutation[2]["variables"]
    assert isinstance(variables, dict)
    change = variables["input"]
    assert isinstance(change, dict)
    assert change["refUpdates"] == [
        {
            "name": "refs/heads/topic",
            "beforeOid": HEAD,
            "afterOid": BASE,
            "force": False,
        }
    ]

    with pytest.raises(GitHubBoundaryError, match="exact ref compare-and-swap"):
        GitHubGraphQL(RefTransport(stale=True)).compare_and_swap_ref("owner/repo", "refs/heads/topic", HEAD, BASE)


def test_pull_snapshot_resolves_current_base_ref_instead_of_stale_pr_base_sha() -> None:
    fake = FakeTransport()
    current_base = "c" * 40
    fake.responses[("GET", "/repos/owner/repo/pulls/7")] = WireResponse(200, pull())
    fake.responses[("GET", "/repos/owner/repo/git/ref/heads/main")] = WireResponse(
        200, {"object": {"type": "commit", "sha": current_base}}
    )

    snapshot = authority(fake).pull_request()

    assert snapshot.base == current_base
    assert snapshot.base != BASE


def test_exact_head_workflow_selection_adopts_completed_draft_run() -> None:
    fake = FakeTransport()
    path = "/repos/owner/repo/actions/workflows/ci.yml/runs?event=pull_request&per_page=100"
    fake.responses[("GET", path)] = WireResponse(
        200,
        {
            "total_count": 2,
            "workflow_runs": [
                {
                    "id": 2,
                    "head_sha": "c" * 40,
                    "path": ".github/workflows/ci.yml",
                    "run_attempt": 3,
                    "event": "pull_request",
                    "pull_requests": [],
                    "status": "completed",
                    "conclusion": "success",
                },
                {
                    "id": 1,
                    "head_sha": HEAD,
                    "path": ".github/workflows/ci.yml",
                    "run_attempt": 1,
                    "event": "pull_request",
                    "pull_requests": [{"number": 7}],
                    "status": "completed",
                    "conclusion": "success",
                },
            ],
        },
    )
    selected = authority(fake).select_run("ci.yml", HEAD)
    assert selected == ActionsRunSnapshot(1, HEAD, "ci.yml", 1, "completed", "success")


def test_object_collection_requires_complete_consistent_pagination() -> None:
    fake = FakeTransport()
    root = "/repos/owner/repo"
    first = f"{root}/actions/workflows/ci.yml/runs?event=pull_request&per_page=100"
    second = f"{root}/actions/workflows/ci.yml/runs?event=pull_request&per_page=100&page=2"
    run = {
        "id": 1,
        "head_sha": HEAD,
        "path": ".github/workflows/ci.yml",
        "run_attempt": 1,
        "event": "pull_request",
        "pull_requests": [{"number": 7}],
        "status": "completed",
        "conclusion": "success",
    }
    fake.responses[("GET", first)] = WireResponse(200, {"total_count": 1, "workflow_runs": []}, second)
    fake.responses[("GET", second)] = WireResponse(200, {"total_count": 1, "workflow_runs": [run]})
    assert authority(fake).select_run("ci.yml", HEAD).id == 1  # type: ignore[union-attr]

    fake.responses[("GET", second)] = WireResponse(200, {"total_count": 2, "workflow_runs": [run]})
    with pytest.raises(GitHubBoundaryError, match="malformed"):
        authority(fake).select_run("ci.yml", HEAD)


def test_branch_effective_rules_are_policy_authority() -> None:
    fake = FakeTransport()
    root = "/repos/owner/repo"
    fake.responses[("GET", f"{root}/rules/branches/main")] = WireResponse(
        200,
        [
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [{"context": "unit"}],
                },
            },
            {
                "type": "pull_request",
                "parameters": {"required_approving_review_count": 2, "required_review_thread_resolution": True},
            },
        ],
    )
    policy = authority(fake).policy("main")
    assert (
        policy.source,
        policy.strict,
        policy.required_checks,
        policy.required_approvals,
        policy.conversation_resolution,
    ) == ("effective_rules", True, ("unit",), 2, True)
    assert len(policy.digest) == 64


def test_review_latest_meaningful_state_and_explicit_thread_capability() -> None:
    fake = FakeTransport()
    root = "/repos/owner/repo/pulls/7"
    fake.responses[("GET", f"{root}/requested_reviewers")] = WireResponse(200, {"users": [{"login": "bob"}]})
    fake.page_values[f"{root}/reviews?per_page=100"] = (
        {"id": 1, "submitted_at": "1", "user": {"login": "alice"}, "state": "APPROVED"},
        {"id": 2, "submitted_at": "2", "user": {"login": "alice"}, "state": "CHANGES_REQUESTED"},
    )
    review = authority(fake).human_review()
    assert review.requested_reviewers == ("bob",)
    assert review.changes_requested == ("alice",)
    assert review.unresolved_threads is None and review.threads_capability == "threads_unavailable"


def test_dashboard_fences_immediately_before_create_and_does_not_append_on_patch_denial() -> None:
    fake = FakeTransport()
    comments = "/repos/owner/repo/issues/7/comments"
    fake.page_values[f"{comments}?per_page=100"] = ()
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 4, "html_url": "url", "body": "x"})
    events: list[str] = []
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: events.append("fence"))
    assert publisher.dashboard("dash-1", 3, HEAD, "body").status == "created"
    assert events == ["fence"]
    assert fake.calls[-2][0] == "PAGES" and fake.calls[-1][0] == "POST"

    fake.page_values[f"{comments}?per_page=100"] = (
        {"id": 4, "html_url": "url", "body": "old <!-- hamsterdan:dashboard -->", "user": {"login": "hamsterdan[bot]"}},
    )
    fake.responses[("PATCH", "/repos/owner/repo/issues/comments/4")] = WireResponse(403, {"message": "denied"})
    result = publisher.dashboard("dash-2", 3, HEAD, "new")
    assert result.status == "update_unavailable" and not result.capability_available
    assert not any(call[0] == "POST" for call in fake.calls[-2:])


def test_lookup_first_retry_recovers_an_uncertain_successful_comment_write() -> None:
    comments = "/repos/owner/repo/issues/7/comments"

    class UncertainWrite(FakeTransport):
        def request(self, method: str, path: str, body=None) -> WireResponse:
            if method == "POST" and path == comments:
                self.calls.append((method, path, body))
                item = {"id": 8, "html_url": "url", "body": body["body"], "user": {"login": "hamsterdan[bot]"}}
                self.page_values[f"{comments}?per_page=100"] = (item,)
                return WireResponse(500, {"message": "outcome unknown to caller"})
            return super().request(method, path, body)

    fake = UncertainWrite()
    fake.page_values[f"{comments}?per_page=100"] = ()
    fences: list[str] = []
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: fences.append("fenced"))

    recovered = publisher.immutable("finding", "stable-operation", 1, HEAD, "Finding")

    assert recovered.status == "existing"
    assert recovered.reference is not None and recovered.reference.id == 8
    assert len([call for call in fake.calls if call[0] == "POST"]) == 1
    assert fences == ["fenced"]


def test_immutable_comment_retries_once_after_proven_pre_call_failure() -> None:
    comments = "/repos/owner/repo/issues/7/comments"

    class BeforeCallFailure(FakeTransport):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        def request(self, method: str, path: str, body=None) -> WireResponse:
            self.calls.append((method, path, body))
            if method == "POST" and path == comments:
                self.attempts += 1
                if self.attempts == 1:
                    raise GitHubBoundaryError("injected before call")
                item = {"id": 9, "html_url": "url", "body": body["body"], "user": {"login": "hamsterdan[bot]"}}
                self.page_values[f"{comments}?per_page=100"] = (item,)
                return WireResponse(201, item)
            return super().request(method, path, body)

    fake = BeforeCallFailure()
    fake.page_values[f"{comments}?per_page=100"] = ()
    fences: list[str] = []
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: fences.append("fenced"))

    result = publisher.immutable("finding", "stable-operation", 1, HEAD, "Finding")

    assert result.status == "created"
    assert fake.attempts == 2
    assert [call[0] for call in fake.calls] == ["PAGES", "POST", "PAGES", "POST"]
    assert fences == ["fenced", "fenced"]


def test_after_call_fault_recovers_by_lookup_without_a_second_mutation() -> None:
    comments = "/repos/owner/repo/issues/7/comments"

    class AcceptedWrite(FakeTransport):
        def request(self, method: str, path: str, body=None) -> WireResponse:
            self.calls.append((method, path, body))
            item = {"id": 10, "html_url": "url", "body": body["body"], "user": {"login": "hamsterdan[bot]"}}
            self.page_values[f"{comments}?per_page=100"] = (item,)
            return WireResponse(201, item)

    spent = False

    def fault(phase, repository, pull_request, kind, operation):
        nonlocal spent
        if phase == "after_call" and not spent:
            spent = True
            raise GitHubBoundaryError("qualified ambiguous outcome")

    fake = AcceptedWrite()
    fake.page_values[f"{comments}?per_page=100"] = ()
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None, fault)

    result = publisher.immutable("finding", "stable-operation", 1, HEAD, "Finding")

    assert result.status == "existing"
    assert len([call for call in fake.calls if call[0] == "POST"]) == 1


def test_definitive_comment_rejection_is_looked_up_but_not_retried() -> None:
    comments = "/repos/owner/repo/issues/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{comments}?per_page=100"] = ()
    fake.responses[("POST", comments)] = WireResponse(403, {"message": "denied"})
    fences: list[str] = []
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: fences.append("fenced"))

    with pytest.raises(GitHubBoundaryError, match="did not prove"):
        publisher.immutable("finding", "stable-operation", 1, HEAD, "Finding")

    assert len([call for call in fake.calls if call[0] == "POST"]) == 1
    assert fences == ["fenced"]


def test_initial_immutable_lookup_rejects_a_stable_operation_payload_collision() -> None:
    comments = "/repos/owner/repo/issues/7/comments"
    marker = CommentPublisher.marker("finding", "stable-operation", HEAD)
    fake = FakeTransport()
    fake.page_values[f"{comments}?per_page=100"] = (
        {"id": 11, "html_url": "url", "body": f"Different\n\n{marker}", "user": {"login": "hamsterdan[bot]"}},
    )
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    with pytest.raises(ValueError, match="different payload"):
        publisher.immutable("finding", "stable-operation", 1, HEAD, "Finding")

    assert not any(call[0] == "POST" for call in fake.calls)


def test_two_unproven_comment_outcomes_stop_after_two_fenced_mutations() -> None:
    comments = "/repos/owner/repo/issues/7/comments"

    class Unproven(FakeTransport):
        def request(self, method: str, path: str, body=None) -> WireResponse:
            self.calls.append((method, path, body))
            raise GitHubBoundaryError("unproven")

    fake = Unproven()
    fake.page_values[f"{comments}?per_page=100"] = ()
    fences: list[str] = []
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: fences.append("fenced"))

    with pytest.raises(GitHubBoundaryError, match="unproven"):
        publisher.immutable("finding", "stable-operation", 1, HEAD, "Finding")

    assert len([call for call in fake.calls if call[0] == "POST"]) == 2
    assert fences == ["fenced", "fenced"]


def test_stale_recovery_fence_prevents_a_second_comment_mutation() -> None:
    comments = "/repos/owner/repo/issues/7/comments"

    class Unproven(FakeTransport):
        def request(self, method: str, path: str, body=None) -> WireResponse:
            self.calls.append((method, path, body))
            raise GitHubBoundaryError("unproven")

    fake = Unproven()
    fake.page_values[f"{comments}?per_page=100"] = ()
    fences = 0

    def fence(*args):
        nonlocal fences
        fences += 1
        if fences == 2:
            raise RuntimeError("stale authority")

    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", fence)

    with pytest.raises(RuntimeError, match="stale authority"):
        publisher.immutable("finding", "stable-operation", 1, HEAD, "Finding")

    assert len([call for call in fake.calls if call[0] == "POST"]) == 1


def test_lookup_requires_normalized_exact_bot_login_and_hamsterdan_marker() -> None:
    fake = FakeTransport()
    comments = "/repos/owner/repo/issues/7/comments"
    marker = CommentPublisher.marker("finding", "operation", HEAD)
    fake.page_values[f"{comments}?per_page=100"] = (
        {"id": 1, "body": marker, "user": {"login": "other[bot]"}},
        {
            "id": 2,
            "body": "<!-- impetus:finding operation=operation head=" + HEAD + " -->",
            "user": {"login": "hamsterdan[bot]"},
        },
        {"id": 3, "body": f"body\n\n{marker}", "user": {"login": " HamsterDan[Bot] "}},
    )
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    existing = publisher.immutable("finding", "operation", 1, HEAD, "body")

    assert marker.startswith("<!-- hamsterdan:")
    assert existing.status == "existing"
    assert existing.reference is not None and existing.reference.id == 3
    assert not any(call[0] == "POST" for call in fake.calls)


def test_legacy_marker_is_not_compatible_with_hamsterdan_publication() -> None:
    fake = FakeTransport()
    comments = "/repos/owner/repo/issues/7/comments"
    fake.page_values[f"{comments}?per_page=100"] = (
        {"id": 1, "body": "<!-- impetus:dashboard -->", "user": {"login": "hamsterdan[bot]"}},
    )
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 2, "html_url": "url"})
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    result = publisher.dashboard("dashboard", 1, HEAD, "Hamsterdan readiness")

    assert result.status == "created"
    assert "<!-- hamsterdan:dashboard -->" in str(fake.calls[-1][2]["body"])


def test_reminder_mentions_configured_reviewer_and_never_assigns() -> None:
    fake = FakeTransport()
    comments = "/repos/owner/repo/issues/7/comments"
    fake.page_values[f"{comments}?per_page=100"] = (
        {
            "id": 9,
            "html_url": "https://github.invalid/pr/7#dashboard",
            "body": "current <!-- hamsterdan:dashboard -->",
            "user": {"login": "hamsterdan[bot]"},
        },
    )
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 1, "html_url": "url"})
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)
    publisher.reminder("remind", 1, HEAD, reviewer="reviewer", author="author")
    assert "@reviewer, please review" in str(fake.calls[-1][2]["body"])
    assert "[See current readiness state.](https://github.invalid/pr/7#dashboard)" in str(fake.calls[-1][2]["body"])
    assert publisher.reviewer_assignment_available is False


def test_reminder_asks_author_to_assign_without_inventing_a_reviewer() -> None:
    fake = FakeTransport()
    comments = "/repos/owner/repo/issues/7/comments"
    fake.page_values[f"{comments}?per_page=100"] = ()
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 1, "html_url": "url"})
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    publisher.reminder("remind", 1, HEAD, reviewer=None, author="author")

    assert "@author, please assign a reviewer" in str(fake.calls[-1][2]["body"])


def test_finding_uses_distinct_publication_and_authority_operations() -> None:
    fake = FakeTransport()
    comments = "/repos/owner/repo/issues/7/comments"
    fake.page_values[f"{comments}?per_page=100"] = ()
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 1, "html_url": "url"})
    fences: list[tuple] = []
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: fences.append(args))

    publisher.finding(
        "finding-activity:finding-id",
        3,
        HEAD,
        "finding",
        authority_operation="finding-activity",
    )

    assert fences == [("owner/repo", 7, 3, HEAD, "finding-activity")]
    assert "operation=finding-activity:finding-id" in str(fake.calls[-1][2]["body"])


def test_transport_repr_does_not_claim_or_expose_credentials() -> None:
    transport = GitHubKitTransport(object())  # type: ignore[arg-type]
    assert "token" not in repr(transport).lower()
    assert "credential=<owned-by-githubkit>" in repr(transport)


def test_transport_normalizes_httpx_network_failures() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("credential-bearing-provider-error", request=request)

    transport = GitHubKitTransport(GitHub("installation-secret", transport=httpx.MockTransport(fail)))
    with pytest.raises(GitHubBoundaryError, match="without a proven outcome") as request_error:
        transport.request("GET", "/repos/owner/repo")
    with pytest.raises(GitHubBoundaryError, match="without a proven outcome") as download_error:
        transport.download("/repos/owner/repo/actions/runs/1/logs")
    assert "credential-bearing-provider-error" not in str(request_error.value)
    assert "credential-bearing-provider-error" not in str(download_error.value)


def test_policy_falls_back_only_on_effective_endpoint_404_and_rejects_malformed_evidence() -> None:
    fake = FakeTransport()
    root = "/repos/owner/repo"
    fake.responses[("GET", f"{root}/rules/branches/topic%2Fbase")] = WireResponse(404, {})
    fake.responses[("GET", f"{root}/branches/topic%2Fbase/protection")] = WireResponse(
        200,
        {
            "required_status_checks": {"strict": True, "contexts": ["unit"]},
            "required_pull_request_reviews": {"required_approving_review_count": 1},
            "required_conversation_resolution": {"enabled": True},
        },
    )
    assert authority(fake).policy("topic/base").source == "branch_protection"

    fake.responses[("GET", f"{root}/rules/branches/main")] = WireResponse(
        200,
        [{"type": "required_status_checks", "parameters": {"required_status_checks": []}}],
    )
    with pytest.raises(GitHubBoundaryError, match="status policy"):
        authority(fake).policy("main")


@pytest.mark.parametrize("field,value", [("event", "push"), ("path", ".github/workflows/other.yml")])
def test_run_evidence_rejects_wrong_event_or_workflow(field: str, value: str) -> None:
    fake = FakeTransport()
    path = "/repos/owner/repo/actions/workflows/ci.yml/runs?event=pull_request&per_page=100"
    run = {
        "id": 1,
        "head_sha": HEAD,
        "path": ".github/workflows/ci.yml",
        "event": "pull_request",
        "pull_requests": [{"number": 7}],
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
    }
    run[field] = value
    fake.responses[("GET", path)] = WireResponse(200, {"total_count": 1, "workflow_runs": [run]})
    with pytest.raises(GitHubBoundaryError, match="outside the requested PR workflow"):
        authority(fake).select_run("ci.yml", HEAD)


def test_missing_required_job_is_explicit_failure() -> None:
    fake = FakeTransport()
    run = ActionsRunSnapshot(5, HEAD, "ci.yml", 2, "completed", "success")
    fake.responses[("GET", "/repos/owner/repo/actions/runs/5/attempts/2/jobs?per_page=100")] = WireResponse(
        200,
        {
            "total_count": 1,
            "jobs": [{"id": 8, "name": "lint", "status": "completed", "conclusion": "success"}],
        },
    )
    observed = authority(fake).jobs(run, ("lint", "unit"))
    assert authority(fake).run_result(observed)["conclusion"] == "failure"
    assert tuple(job.name for job in observed.jobs if job.required) == ("lint", "unit")


def test_in_progress_run_does_not_treat_not_yet_created_required_jobs_as_failures() -> None:
    fake = FakeTransport()
    run = ActionsRunSnapshot(5, HEAD, "ci.yml", 2, "in_progress", None)
    fake.responses[("GET", "/repos/owner/repo/actions/runs/5/attempts/2/jobs?per_page=100")] = WireResponse(
        200,
        {
            "total_count": 1,
            "jobs": [{"id": 8, "name": "lint", "status": "in_progress", "conclusion": None}],
        },
    )

    observed = authority(fake).jobs(run, ("lint", "unit"))

    assert authority(fake).run_result(observed)["conclusion"] == "pending"


def test_rerun_request_is_lookup_first_and_fenced_immediately_before_marker() -> None:
    fake = FakeTransport()
    root = "/repos/owner/repo"
    comments = f"{root}/issues/7/comments"
    fake.responses[("GET", f"{root}/pulls/7")] = WireResponse(200, pull())
    fake.responses[("GET", f"{root}/git/ref/heads/main")] = WireResponse(200, {"object": {"sha": BASE}})
    runs = f"{root}/actions/workflows/ci.yml/runs?event=pull_request&per_page=100"
    fake.responses[("GET", runs)] = WireResponse(
        200,
        {
            "total_count": 1,
            "workflow_runs": [
                {
                    "id": 5,
                    "head_sha": HEAD,
                    "path": ".github/workflows/ci.yml",
                    "event": "pull_request",
                    "pull_requests": [{"number": 7}],
                    "run_attempt": 1,
                    "status": "completed",
                    "conclusion": "failure",
                }
            ],
        },
    )
    fake.page_values[f"{comments}?per_page=100"] = ()
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 9, "html_url": "url"})
    events: list[str] = []
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: events.append("fence"))
    broker = CommentRerunBroker(authority(fake), publisher)
    run = ActionsRunSnapshot(5, HEAD, "ci.yml", 1, "completed", "failure")
    assert broker.request(run, epoch=3, operation="retry-1").status == "requested"
    assert events == ["fence"] and fake.calls[-1][0] == "POST"

    marker = "<!-- hamsterdan-rerun run=5 head=" + HEAD + " operation=retry-1 -->"
    fake.page_values[f"{comments}?per_page=100"] = (
        {"id": 9, "html_url": "url", "body": marker, "user": {"login": "hamsterdan[bot]"}},
    )
    assert broker.request(run, epoch=3, operation="retry-1").status == "existing"
    assert events == ["fence"]
