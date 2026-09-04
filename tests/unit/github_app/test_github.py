from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
import pytest
from githubkit import GitHub

from hamsterdan.github_app.effects import CommentPublisher, CommentRerunBroker
from hamsterdan.github_app.gateway import GitHubAuthority
from hamsterdan.github_app.models import (
    ActionsJobSnapshot,
    ActionsRunSnapshot,
    GitHubBoundaryError,
    RerunRefusedError,
    WireResponse,
)
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


def test_exact_head_workflow_selection_ignores_closed_historical_run_for_reused_head() -> None:
    fake = FakeTransport()
    path = f"/repos/owner/repo/actions/workflows/ci.yml/runs?event=pull_request&head_sha={HEAD}&per_page=20"
    fake.responses[("GET", path)] = WireResponse(
        200,
        {
            "total_count": 2,
            "workflow_runs": [
                {
                    "id": 2,
                    "head_sha": HEAD,
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
    first = f"{root}/actions/workflows/ci.yml/runs?event=pull_request&head_sha={HEAD}&per_page=20"
    second = f"{root}/actions/workflows/ci.yml/runs?event=pull_request&head_sha={HEAD}&per_page=20&page=2"
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
        {
            "id": 4,
            "html_url": "url",
            "body": "old\n\n<!-- hamsterdan:dashboard -->",
            "user": {"login": "hamsterdan[bot]"},
        },
    )
    fake.responses[("PATCH", "/repos/owner/repo/issues/comments/4")] = WireResponse(403, {"message": "denied"})
    result = publisher.dashboard("dash-2", 3, HEAD, "new")
    assert result.status == "capability_unavailable" and not result.capability_available
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

    result = publisher.immutable("readiness", "stable-operation", 1, HEAD, "Ready")

    assert not result.capability_available
    assert len([call for call in fake.calls if call[0] == "POST"]) == 1
    assert fences == ["fenced"]


@pytest.mark.parametrize("kind", ["dashboard", "readiness"])
@pytest.mark.parametrize("status", [422, 400])
def test_definite_publication_payload_rejection_is_nonretryable(kind: str, status: int) -> None:
    comments = "/repos/owner/repo/issues/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{comments}?per_page=100"] = ()
    fake.responses[("POST", comments)] = WireResponse(status, {"message": "must not escape"})
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    with pytest.raises(ValueError, match="GitHub rejected"):
        if kind == "dashboard":
            publisher.dashboard("stable-operation", 1, HEAD, "Dashboard")
        else:
            publisher.immutable("readiness", "stable-operation", 1, HEAD, "Ready")

    assert len([call for call in fake.calls if call[0] == "POST"]) == 1


@pytest.mark.parametrize("kind", ["dashboard", "readiness"])
@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_publication_status_is_boundary_failure(kind: str, status: int) -> None:
    comments = "/repos/owner/repo/issues/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{comments}?per_page=100"] = ()
    fake.responses[("POST", comments)] = WireResponse(status, {})
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    with pytest.raises(GitHubBoundaryError, match="did not prove"):
        if kind == "dashboard":
            publisher.dashboard("stable-operation", 1, HEAD, "Dashboard")
        else:
            publisher.immutable("readiness", "stable-operation", 1, HEAD, "Ready")


@pytest.mark.parametrize("body", [[], {}, {"id": None}, {"id": "not-an-id"}])
@pytest.mark.parametrize("publication", ["immutable", "dashboard_create", "dashboard_update"])
def test_expected_comment_status_with_unusable_reference_is_ambiguous(publication: str, body: object) -> None:
    comments = "/repos/owner/repo/issues/7/comments"
    marker = "<!-- hamsterdan:dashboard -->"
    fake = FakeTransport()
    existing = {
        "id": 4,
        "html_url": "url",
        "body": f"old\n\n{marker}",
        "user": {"login": "hamsterdan[bot]"},
    }
    fake.page_values[f"{comments}?per_page=100"] = () if publication != "dashboard_update" else (existing,)
    method = "PATCH" if publication == "dashboard_update" else "POST"
    path = "/repos/owner/repo/issues/comments/4" if method == "PATCH" else comments
    fake.responses[(method, path)] = WireResponse(200 if method == "PATCH" else 201, body)
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    with pytest.raises(GitHubBoundaryError, match="did not prove"):
        if publication == "immutable":
            publisher.immutable("readiness", "stable-operation", 1, HEAD, "Ready")
        else:
            publisher.dashboard("stable-operation", 1, HEAD, "new")

    assert [call[0] for call in fake.calls].count(method) == 1


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


def test_find_reports_absence_landing_and_collision_without_mutating() -> None:
    comments = "/repos/owner/repo/issues/7/comments"
    marker = CommentPublisher.marker("finding", "stable-operation", HEAD)
    fake = FakeTransport()
    fake.page_values[f"{comments}?per_page=100"] = ()
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    assert publisher.find("finding", "stable-operation", HEAD, "Finding") is None

    fake.page_values[f"{comments}?per_page=100"] = (
        {"id": 11, "html_url": "url", "body": f"Finding\n\n{marker}", "user": {"login": "hamsterdan[bot]"}},
    )
    held = publisher.find("finding", "stable-operation", HEAD, "Finding")
    assert held is not None and held.status == "existing"
    assert held.reference is not None and held.reference.id == 11
    compatible = publisher.find("finding", "stable-operation", HEAD, "Newer", compatible_bodies=("Finding",))
    assert compatible is not None and compatible.status == "existing"

    with pytest.raises(ValueError, match="different payload"):
        publisher.find("finding", "stable-operation", HEAD, "Different")

    assert not any(call[0] == "POST" for call in fake.calls)


def _no_context():
    raise AssertionError("write context must not be read for a held operation")


def test_operation_scoped_reconciliation_recovers_across_a_head_move_without_reposting() -> None:
    # A2 operation-scoped identity: a reply landed under h1 must
    # reconcile as existing when reissued under h2 (the marker embeds
    # the head) WITHOUT consulting the write context, and differing
    # content must still fail closed.
    comments = "/repos/owner/repo/issues/7/comments"
    marker = CommentPublisher.marker("conversation", "reply:c1", HEAD)
    fake = FakeTransport()
    fake.page_values[f"{comments}?per_page=100"] = (
        {"id": 12, "html_url": "url", "body": f"the answer\n\n{marker}", "user": {"login": "hamsterdan[bot]"}},
    )
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    recovered = publisher.immutable_operation("conversation", "reply:c1", "the answer", context=_no_context)
    assert recovered.status == "existing"
    assert recovered.reference is not None and recovered.reference.id == 12
    assert not any(call[0] == "POST" for call in fake.calls)

    with pytest.raises(ValueError, match="different payload"):
        publisher.immutable_operation("conversation", "reply:c1", "a different answer", context=_no_context)
    assert not any(call[0] == "POST" for call in fake.calls)


def test_operation_scoped_publication_posts_under_the_current_head_when_never_held() -> None:
    comments = "/repos/owner/repo/issues/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{comments}?per_page=100"] = ()
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 13, "html_url": "url"})
    fences: list[str] = []
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: fences.append("fenced"))

    result = publisher.immutable_operation("conversation", "reply:c1", "the answer", context=lambda: (1, HEAD))

    assert result.status == "created"
    [(_, _, posted)] = [call for call in fake.calls if call[0] == "POST"]
    assert posted["body"].endswith(CommentPublisher.marker("conversation", "reply:c1", HEAD))
    assert fences == ["fenced"]


def test_operation_scoped_reminder_reconciles_presence_only_across_a_head_move() -> None:
    # A2 presence-only reconciliation: the nudge landed under h1, so a
    # reissue reconciles WITHOUT reading claim/recipients (the body
    # legitimately drifts with addressing and the dashboard link).
    comments = "/repos/owner/repo/issues/7/comments"
    marker = CommentPublisher.marker("reminder", "reminder:t1", HEAD)
    fake = FakeTransport()
    fake.page_values[f"{comments}?per_page=100"] = (
        {"id": 14, "html_url": "url", "body": f"an OLD nudge body\n\n{marker}", "user": {"login": "hamsterdan[bot]"}},
    )
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    recovered = publisher.reminder_operation("reminder:t1", context=_no_context)

    assert recovered.status == "existing"
    assert recovered.reference is not None and recovered.reference.id == 14
    assert not any(call[0] == "POST" for call in fake.calls)
    # exactly ONE lookup: no dashboard read on the reconciliation path
    assert [call[0] for call in fake.calls] == ["PAGES"]


def test_operation_scoped_reminder_posts_under_the_current_head_when_never_held() -> None:
    comments = "/repos/owner/repo/issues/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{comments}?per_page=100"] = ()
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 15, "html_url": "url"})
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    result = publisher.reminder_operation("reminder:t1", context=lambda: (1, HEAD, "the-reviewer", "the-author"))

    assert result.status == "created"
    [(_, _, posted)] = [call for call in fake.calls if call[0] == "POST"]
    assert "@the-reviewer" in posted["body"]
    assert posted["body"].endswith(CommentPublisher.marker("reminder", "reminder:t1", HEAD))


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
            "body": "current\n\n<!-- hamsterdan:dashboard -->",
            "user": {"login": "hamsterdan[bot]"},
        },
    )
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 1, "html_url": "url"})
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)
    publisher.reminder("remind", 1, HEAD, reviewer="reviewer", author="author")
    assert "@reviewer, this PR and I have gotten to know each other quite well" in str(fake.calls[-1][2]["body"])
    assert "Please review this PR" in str(fake.calls[-1][2]["body"])
    assert "[See current readiness state.](https://github.invalid/pr/7#dashboard)" in str(fake.calls[-1][2]["body"])
    assert publisher.reviewer_assignment_available is False


def test_reminder_asks_author_to_assign_without_inventing_a_reviewer() -> None:
    fake = FakeTransport()
    comments = "/repos/owner/repo/issues/7/comments"
    fake.page_values[f"{comments}?per_page=100"] = ()
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 1, "html_url": "url"})
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    publisher.reminder("remind", 1, HEAD, reviewer=None, author="author")

    assert "@author, this PR and I have gotten to know each other quite well" in str(fake.calls[-1][2]["body"])
    assert "Please assign a reviewer" in str(fake.calls[-1][2]["body"])


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


def test_finding_publishes_native_inline_suggestion_with_related_locations() -> None:
    issues = "/repos/owner/repo/issues/7/comments"
    reviews = "/repos/owner/repo/pulls/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{reviews}?per_page=100"] = ()
    fake.page_values[f"{issues}?per_page=100"] = ()
    fake.responses[("POST", reviews)] = WireResponse(201, {"id": 8, "html_url": "inline-url"})
    fences: list[tuple] = []
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: fences.append(args))

    result = publisher.finding(
        "finding-activity:finding-id",
        3,
        HEAD,
        "Dan found one shared invariant wearing two different hats.",
        path="src/one.py",
        line=4,
        related_locations=(("src/two.py", 19),),
        suggestion="if state.is_ready:",
        authority_operation="finding-activity",
    )

    assert result.status == "created" and result.inline
    assert result.reference is not None and result.reference.url == "inline-url"
    request = next(call for call in fake.calls if call[:2] == ("POST", reviews))
    assert request[2] is not None
    assert request[2]["commit_id"] == HEAD
    assert request[2]["path"] == "src/one.py" and request[2]["line"] == 4 and request[2]["side"] == "RIGHT"
    assert f"Related locations:\n- [`src/two.py:19`](https://github.com/owner/repo/blob/{HEAD}/src/two.py#L19)" in str(
        request[2]["body"]
    )
    assert "```suggestion\nif state.is_ready:\n```" in str(request[2]["body"])
    assert fences == [("owner/repo", 7, 3, HEAD, "finding-activity")]


def test_definitive_inline_denial_falls_back_to_one_immutable_issue_comment() -> None:
    issues = "/repos/owner/repo/issues/7/comments"
    reviews = "/repos/owner/repo/pulls/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{reviews}?per_page=100"] = ()
    fake.page_values[f"{issues}?per_page=100"] = ()
    fake.responses[("POST", reviews)] = WireResponse(422, {"message": "line is not in diff"})
    fake.responses[("POST", issues)] = WireResponse(201, {"id": 9, "html_url": "issue-url"})
    fences: list[tuple] = []
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: fences.append(args))

    result = publisher.finding(
        "finding-activity:finding-id",
        3,
        HEAD,
        "Conceptual concern.",
        path="src/one.py",
        line=4,
        authority_operation="finding-activity",
    )

    assert result.status == "created" and not result.inline
    assert result.reference is not None and result.reference.url == "issue-url"
    assert len([call for call in fake.calls if call[:2] == ("POST", reviews)]) == 1
    assert len([call for call in fake.calls if call[:2] == ("POST", issues)]) == 1
    assert fences == [
        ("owner/repo", 7, 3, HEAD, "finding-activity"),
        ("owner/repo", 7, 3, HEAD, "finding-activity"),
    ]


@pytest.mark.parametrize(
    "response",
    [
        WireResponse(403, {"message": "Resource not accessible by integration"}),
        WireResponse(404, {"message": "Not Found"}),
        WireResponse(422, {"message": "Validation Failed", "errors": [{"field": "body", "code": "invalid"}]}),
        WireResponse(422, {"message": "Validation Failed", "errors": [{"field": "line", "code": "invalid"}]}),
    ],
)
def test_inline_authorization_or_payload_failure_does_not_fall_back(response: WireResponse) -> None:
    issues = "/repos/owner/repo/issues/7/comments"
    reviews = "/repos/owner/repo/pulls/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{reviews}?per_page=100"] = ()
    fake.page_values[f"{issues}?per_page=100"] = ()
    fake.responses[("POST", reviews)] = response
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    with pytest.raises(GitHubBoundaryError, match="did not prove inline") as caught:
        publisher.finding("finding-activity:finding-id", 3, HEAD, "Conceptual concern.", path="src/one.py", line=4)

    expected_class = "capability_denial" if response.status in {403, 404} else "payload_rejection"
    assert caught.value.failure_class == expected_class
    assert caught.value.provider_status == response.status
    assert "Validation Failed" not in caught.value.provider_detail
    assert not [call for call in fake.calls if call[:2] == ("POST", issues)]
    assert len([call for call in fake.calls if call[:2] == ("POST", reviews)]) == 1


def test_inline_failure_diagnostic_rejects_provider_controlled_atoms() -> None:
    issues = "/repos/owner/repo/issues/7/comments"
    reviews = "/repos/owner/repo/pulls/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{reviews}?per_page=100"] = ()
    fake.page_values[f"{issues}?per_page=100"] = ()
    fake.responses[("POST", reviews)] = WireResponse(
        422,
        {"message": "credential-bearing message", "errors": [{"field": "github_pat_secret", "code": "secret"}]},
    )
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    with pytest.raises(GitHubBoundaryError) as caught:
        publisher.finding("finding-activity:finding-id", 3, HEAD, "Conceptual concern.", path="src/one.py", line=4)

    assert caught.value.provider_detail == "unknown_field:unknown_code"
    assert "secret" not in caught.value.provider_detail


def test_ambiguous_accepted_inline_finding_recovers_without_a_second_mutation() -> None:
    issues = "/repos/owner/repo/issues/7/comments"
    reviews = "/repos/owner/repo/pulls/7/comments"

    class AcceptedInline(FakeTransport):
        def request(self, method: str, path: str, body=None) -> WireResponse:
            self.calls.append((method, path, body))
            assert method == "POST" and path == reviews and body is not None
            item = {"id": 10, "html_url": "inline-url", "body": body["body"], "user": {"login": "hamsterdan[bot]"}}
            self.page_values[f"{reviews}?per_page=100"] = (item,)
            return WireResponse(201, item)

    spent = False

    def fault(phase, repository, pull_request, kind, operation):
        nonlocal spent
        if phase == "after_call" and not spent:
            spent = True
            raise GitHubBoundaryError("qualified ambiguous outcome")

    fake = AcceptedInline()
    fake.page_values[f"{reviews}?per_page=100"] = ()
    fake.page_values[f"{issues}?per_page=100"] = ()
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None, fault)

    result = publisher.finding("finding-activity:finding-id", 3, HEAD, "Conceptual concern.", path="src/one.py", line=4)

    assert result.status == "existing" and result.inline
    assert len([call for call in fake.calls if call[:2] == ("POST", reviews)]) == 1


def test_inline_before_call_fault_retries_only_after_a_fresh_fence() -> None:
    issues = "/repos/owner/repo/issues/7/comments"
    reviews = "/repos/owner/repo/pulls/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{reviews}?per_page=100"] = ()
    fake.page_values[f"{issues}?per_page=100"] = ()
    fake.responses[("POST", reviews)] = WireResponse(201, {"id": 11, "html_url": "inline-url"})
    fences: list[tuple] = []
    spent = False

    def fault(phase, repository, pull_request, kind, operation):
        nonlocal spent
        if phase == "before_call" and not spent:
            spent = True
            raise GitHubBoundaryError("qualified pre-call failure")

    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: fences.append(args), fault)

    result = publisher.finding("finding-activity:finding-id", 3, HEAD, "Conceptual concern.", path="src/one.py", line=4)

    assert result.status == "created" and result.inline
    assert len(fences) == 2
    assert len([call for call in fake.calls if call[:2] == ("POST", reviews)]) == 1


@pytest.mark.parametrize(
    "transient",
    [
        WireResponse(403, {"message": "You have exceeded a secondary rate limit"}),
        WireResponse(422, {"message": "Validation Failed"}),
        WireResponse(429, {"message": "Too Many Requests"}),
        WireResponse(500, {"message": "Server Error"}),
    ],
)
def test_inline_transient_http_rejection_retries_after_lookup_and_a_fresh_fence(
    transient: WireResponse,
) -> None:
    issues = "/repos/owner/repo/issues/7/comments"
    reviews = "/repos/owner/repo/pulls/7/comments"

    class TransientRejection(FakeTransport):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        def request(self, method: str, path: str, body=None) -> WireResponse:
            self.calls.append((method, path, body))
            if method == "POST" and path == reviews:
                self.attempts += 1
                if self.attempts == 1:
                    return transient
                return WireResponse(201, {"id": 12, "html_url": "inline-url"})
            return super().request(method, path, body)

    fake = TransientRejection()
    fake.page_values[f"{reviews}?per_page=100"] = ()
    fake.page_values[f"{issues}?per_page=100"] = ()
    fences: list[str] = []
    delays: list[float] = []
    publisher = CommentPublisher(
        fake,
        "owner/repo",
        7,
        "hamsterdan[bot]",
        lambda *args: fences.append("fenced"),
        retry_delay=delays.append,
    )

    result = publisher.finding("finding-activity:finding-id", 3, HEAD, "Conceptual concern.", path="src/one.py", line=4)

    assert result.status == "created" and result.inline
    assert fake.attempts == 2
    assert fences == ["fenced", "fenced"]
    assert delays == [60]


def test_inline_retry_stops_when_the_fresh_second_fence_rejects_authority() -> None:
    issues = "/repos/owner/repo/issues/7/comments"
    reviews = "/repos/owner/repo/pulls/7/comments"
    fake = FakeTransport()
    fake.page_values[f"{reviews}?per_page=100"] = ()
    fake.page_values[f"{issues}?per_page=100"] = ()
    fences = 0
    spent = False

    def fence(*args):
        nonlocal fences
        fences += 1
        if fences == 2:
            raise RuntimeError("stale head")

    def fault(phase, repository, pull_request, kind, operation):
        nonlocal spent
        if phase == "before_call" and not spent:
            spent = True
            raise GitHubBoundaryError("qualified pre-call failure")

    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", fence, fault)

    with pytest.raises(RuntimeError, match="stale head"):
        publisher.finding("finding-activity:finding-id", 3, HEAD, "Conceptual concern.", path="src/one.py", line=4)

    assert fences == 2
    assert not [call for call in fake.calls if call[:2] == ("POST", reviews)]


def test_legacy_issue_finding_and_reminder_payloads_recover_exactly() -> None:
    issues = "/repos/owner/repo/issues/7/comments"
    reviews = "/repos/owner/repo/pulls/7/comments"
    finding_operation = "finding-activity:finding-id"
    finding_marker = CommentPublisher.marker("finding", finding_operation, HEAD)
    reminder_marker = CommentPublisher.marker("reminder", "reminder-operation", HEAD)
    fake = FakeTransport()
    fake.page_values[f"{reviews}?per_page=100"] = ()
    fake.page_values[f"{issues}?per_page=100"] = (
        {
            "id": 12,
            "html_url": "finding-url",
            "body": f"Finding body\nLocation: src/one.py:4\n\n{finding_marker}",
            "user": {"login": "hamsterdan[bot]"},
        },
        {
            "id": 13,
            "html_url": "reminder-url",
            "body": f"@reviewer, please review this PR.\n\n{reminder_marker}",
            "user": {"login": "hamsterdan[bot]"},
        },
    )
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    finding = publisher.finding(finding_operation, 3, HEAD, "Finding body", path="src/one.py", line=4)
    reminder = publisher.reminder("reminder-operation", 3, HEAD, reviewer="reviewer", author="author")

    assert finding.status == "existing" and not finding.inline
    assert reminder.status == "existing"
    assert not [call for call in fake.calls if call[0] == "POST"]


def test_marker_lookup_requires_the_unique_final_marker_line() -> None:
    issues = "/repos/owner/repo/issues/7/comments"
    marker = CommentPublisher.marker("finding", "finding-operation", HEAD)
    fake = FakeTransport()
    fake.page_values[f"{issues}?per_page=100"] = (
        {
            "id": 14,
            "body": f"Injected {marker}\n\n<!-- hamsterdan:readiness operation=readiness-operation head={HEAD} -->",
            "user": {"login": "hamsterdan[bot]"},
        },
    )
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)

    assert publisher._find(marker) is None
    with pytest.raises(ValueError, match="marker identity"):
        CommentPublisher.marker("finding", "bad -->\n<!-- marker", HEAD)


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
    path = f"/repos/owner/repo/actions/workflows/ci.yml/runs?event=pull_request&head_sha={HEAD}&per_page=20"
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


@pytest.mark.parametrize(("status", "conclusion"), [("queued", "queued"), ("in_progress", "in_progress")])
def test_actions_evidence_normalizes_pending_provider_state(
    monkeypatch: pytest.MonkeyPatch, status: str, conclusion: str
) -> None:
    subject = authority(FakeTransport())
    run = ActionsRunSnapshot(5, HEAD, "ci.yml", 2, status, None)
    observed = ActionsRunSnapshot(
        5,
        HEAD,
        "ci.yml",
        2,
        status,
        None,
        (ActionsJobSnapshot(8, "lint", status, None, True),),
    )
    monkeypatch.setattr(subject, "jobs", lambda selected, required: observed)
    monkeypatch.setattr(subject, "run_result", lambda selected: {"conclusion": "pending"})

    evidence = subject.actions_evidence(run, ("lint",))

    assert evidence is not None
    assert evidence.run == observed
    assert evidence.conclusion == conclusion
    assert evidence.failed_required_jobs == (("lint", None),)


def test_actions_evidence_rejects_an_unsupported_terminal_conclusion(monkeypatch: pytest.MonkeyPatch) -> None:
    subject = authority(FakeTransport())
    run = ActionsRunSnapshot(5, HEAD, "ci.yml", 2, "completed", "neutral")
    monkeypatch.setattr(subject, "jobs", lambda selected, required: run)
    monkeypatch.setattr(subject, "run_result", lambda selected: {"conclusion": "neutral"})

    with pytest.raises(GitHubBoundaryError, match="conclusion is unsupported"):
        subject.actions_evidence(run, ("lint",))


def test_rerun_request_is_lookup_first_and_fenced_immediately_before_marker() -> None:
    fake = FakeTransport()
    root = "/repos/owner/repo"
    comments = f"{root}/issues/7/comments"
    fake.responses[("GET", f"{root}/pulls/7")] = WireResponse(200, pull())
    fake.responses[("GET", f"{root}/git/ref/heads/main")] = WireResponse(200, {"object": {"sha": BASE}})
    runs = f"{root}/actions/workflows/ci.yml/runs?event=pull_request&head_sha={HEAD}&per_page=20"
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


def test_rerun_held_lookup_carries_no_currency_requirement() -> None:
    # A2 recovery reconciliation must find a landed rerun even after the
    # head moved: `held` reads ONLY the comment listing — no pull, no
    # runs, no fence — so a stale claim can never hide the landed effect.
    fake = FakeTransport()
    comments = "/repos/owner/repo/issues/7/comments"
    fake.page_values[f"{comments}?per_page=100"] = ()
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)
    broker = CommentRerunBroker(authority(fake), publisher)
    assert broker.held(5, HEAD, "retry-1") is None

    marker = "<!-- hamsterdan-rerun run=5 head=" + HEAD + " operation=retry-1 -->"
    fake.page_values[f"{comments}?per_page=100"] = (
        {"id": 9, "html_url": "url", "body": marker, "user": {"login": "hamsterdan[bot]"}},
    )
    held = broker.held(5, HEAD, "retry-1")
    assert held is not None and held.status == "existing"
    assert all(call[0] == "PAGES" and call[1].startswith(comments) for call in fake.calls)

    # marker presence alone proves the landing: a malformed provider
    # reference degrades to None instead of hiding the proven effect
    fake.page_values[f"{comments}?per_page=100"] = (
        {"html_url": "url", "body": marker, "user": {"login": "hamsterdan[bot]"}},
    )
    degraded = broker.held(5, HEAD, "retry-1")
    assert degraded is not None and degraded.status == "existing" and degraded.reference is None


def _rerun_world(fake: FakeTransport, runs: list[dict[str, Any]]) -> tuple[str, CommentRerunBroker]:
    root = "/repos/owner/repo"
    comments = f"{root}/issues/7/comments"
    fake.responses[("GET", f"{root}/pulls/7")] = WireResponse(200, pull())
    fake.responses[("GET", f"{root}/git/ref/heads/main")] = WireResponse(200, {"object": {"sha": BASE}})
    fake.responses[("GET", f"{root}/actions/workflows/ci.yml/runs?event=pull_request&head_sha={HEAD}&per_page=20")] = (
        WireResponse(200, {"total_count": len(runs), "workflow_runs": runs})
    )
    fake.page_values[f"{comments}?per_page=100"] = ()
    publisher = CommentPublisher(fake, "owner/repo", 7, "hamsterdan[bot]", lambda *args: None)
    return comments, CommentRerunBroker(authority(fake), publisher)


def _wire_run(run_id: int, attempt: int) -> dict[str, Any]:
    return {
        "id": run_id,
        "head_sha": HEAD,
        "path": ".github/workflows/ci.yml",
        "event": "pull_request",
        "pull_requests": [{"number": 7}],
        "run_attempt": attempt,
        "status": "completed",
        "conclusion": "failure",
    }


def test_rerun_issue_owns_the_final_run_read_and_the_evidence_cut() -> None:
    # The cut is the newest (run_id, attempt) in the broker's OWN final
    # read: a discriminating pair — old run with many attempts (5,9),
    # newer run's first attempt (7,1) — proves lexicographic (id,
    # attempt) ordering, not the gateway's (attempt, id) sort.
    fake = FakeTransport()
    comments, broker = _rerun_world(fake, [_wire_run(5, 9), _wire_run(7, 1)])
    fake.responses[("POST", comments)] = WireResponse(201, {"id": 9, "html_url": "url"})
    issued = broker.issue(ActionsRunSnapshot(5, HEAD, "ci.yml", 9, "completed", "failure"), epoch=3, operation="r-1")
    assert issued.result.status == "requested"
    assert (issued.cut_run_id, issued.cut_attempt) == (7, 1)


def test_rerun_issue_refusal_is_a_proven_pre_effect_movement() -> None:
    # a stale head, or an indicted run the provider no longer reports,
    # refuses BEFORE any effect: typed refusal, never a boundary error
    fake = FakeTransport()
    _comments, broker = _rerun_world(fake, [_wire_run(7, 1)])
    stale = ActionsRunSnapshot(5, "c" * 40, "ci.yml", 1, "completed", "failure")
    with pytest.raises(RerunRefusedError):
        broker.issue(stale, epoch=3, operation="r-1")
    vanished = ActionsRunSnapshot(5, HEAD, "ci.yml", 1, "completed", "failure")
    with pytest.raises(RerunRefusedError):
        broker.issue(vanished, epoch=3, operation="r-1")
    assert all(call[0] != "POST" for call in fake.calls)
    # the production wrapper still classifies every refusal the same way
    with pytest.raises(GitHubBoundaryError, match="does not belong"):
        broker.request(stale, epoch=3, operation="r-1")


def test_rerun_issue_degrades_a_malformed_201_reference_to_none() -> None:
    # the 201 PROVES the landing: a malformed reference must not turn a
    # proven effect into an activity failure
    fake = FakeTransport()
    comments, broker = _rerun_world(fake, [_wire_run(5, 1)])
    fake.responses[("POST", comments)] = WireResponse(201, {"html_url": "url"})
    issued = broker.issue(ActionsRunSnapshot(5, HEAD, "ci.yml", 1, "completed", "failure"), epoch=3, operation="r-1")
    assert issued.result.status == "requested" and issued.result.reference is None


class ThreadsTransport(FakeTransport):
    """Answers the review-threads query and records resolutions."""

    def __init__(self, threads: list[dict[str, Any]]) -> None:
        super().__init__()
        self.threads = threads
        self.resolved: list[str] = []

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> WireResponse:
        if not (method == "POST" and path == "/graphql"):
            return super().request(method, path, body)
        self.calls.append((method, path, body))
        assert body is not None
        if "resolveReviewThread" in str(body.get("query")):
            variables = body["variables"]
            assert isinstance(variables, dict)
            thread_id = str(variables["thread"])
            self.resolved.append(thread_id)
            return WireResponse(
                200, {"data": {"resolveReviewThread": {"thread": {"id": thread_id, "isResolved": True}}}}
            )
        return WireResponse(
            200,
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": self.threads,
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        }
                    }
                }
            },
        )


def _thread(thread_id: str, *, resolved: bool, viewer: bool | None, marker_head: str | None) -> dict[str, Any]:
    node: dict[str, Any] = {"id": thread_id, "isResolved": resolved}
    if viewer is not None:
        finding_body = (
            f"prose\n\n<!-- hamsterdan:finding operation=findings:{marker_head}:i1:f1 head={marker_head} -->"
            if marker_head
            else "a plain reply"
        )
        node["comments"] = {"nodes": [{"viewerDidAuthor": viewer, "body": finding_body}]}
    return node


def test_unresolved_thread_count_excludes_the_apps_own_threads() -> None:
    # ruled 2026-09-02: the Dan's-review row already carries the finding
    # signal, so the human-review count reports human threads only; a
    # thread with unreadable authorship counts as human (conservative)
    fake = ThreadsTransport(
        [
            _thread("human-open", resolved=False, viewer=False, marker_head=HEAD),
            _thread("dan-open", resolved=False, viewer=True, marker_head=HEAD),
            _thread("human-done", resolved=True, viewer=False, marker_head=HEAD),
            _thread("authorless-open", resolved=False, viewer=None, marker_head=None),
        ]
    )
    fake.responses[("GET", "/repos/owner/repo/pulls/7/requested_reviewers")] = WireResponse(200, {"users": []})
    fake.page_values["/repos/owner/repo/pulls/7/reviews?per_page=100"] = ()
    value = GitHubAuthority(fake, "owner/repo", 7, graphql=GitHubGraphQL(fake)).human_review()
    assert value.unresolved_threads == 2 and value.threads_capability == "available"


def test_stale_finding_thread_resolution_targets_only_superseded_app_threads() -> None:
    old_head = "c" * 40
    fake = ThreadsTransport(
        [
            _thread("dan-stale", resolved=False, viewer=True, marker_head=old_head),
            _thread("dan-current", resolved=False, viewer=True, marker_head=HEAD),
            _thread("human-stale", resolved=False, viewer=False, marker_head=old_head),
            _thread("dan-settled", resolved=True, viewer=True, marker_head=old_head),
            _thread("dan-reply", resolved=False, viewer=True, marker_head=None),
        ]
    )
    value = GitHubAuthority(fake, "owner/repo", 7, graphql=GitHubGraphQL(fake))
    assert value.resolve_stale_finding_threads(HEAD) == 1
    assert fake.resolved == ["dan-stale"]


def test_stale_finding_thread_resolution_without_graphql_is_inert() -> None:
    assert GitHubAuthority(FakeTransport(), "owner/repo", 7).resolve_stale_finding_threads(HEAD) == 0
