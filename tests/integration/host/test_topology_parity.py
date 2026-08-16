from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from hamsterdan.agents.protocol import CodingRequest, CodingResult, ReviewRequest, ReviewResult
from hamsterdan.github_app.config import HostConfig
from hamsterdan.github_app.models import WireResponse
from hamsterdan.host.agenticus import AgentRouteStore, compose_agent
from hamsterdan.host.git_publish import GitReconciliation, HostGitPublisher
from hamsterdan.host.service import HostService
from hamsterdan.host.topology import PRODUCTION, V5, ReadinessComposition

HEAD = "a" * 40
BASE = "b" * 40
BOT = "hamsterdan-test[bot]"
PRIVATE_KEY = "private-key-parity-canary"
WEBHOOK_SECRET = "webhook-secret-parity-canary"
CLIENT_SECRET = "client-secret-parity-canary"
INSTALLATION_TOKEN = "ghs_installation-parity-canary"
FAILURE_FINGERPRINT = hashlib.sha256(b'[["build","failure"]]').hexdigest()
FINDING_ID = "F-mergeability-guard"
BLOCKING_FINDING = {
    "id": FINDING_ID,
    "path": "src/readiness.py",
    "line": 17,
    "related_locations": [],
    "title": "Keep the mergeability guard fail-closed",
    "body": "This path can report ready while GitHub still reports the pull request as unmergeable.",
    "severity": "high",
    "confidence": 0.99,
    "evidence": "The ready branch does not test the observed mergeability flag.",
    "blocking": True,
    "suggestion": "if mergeable and all_gates_clear:",
}
BLOCKING_LINEAGE = [{"finding_id": FINDING_ID, "state": "new", "supersedes": None}]


class Clients:
    def installation(self, installation_id: int, repository_ids: list[int] | tuple[int, ...]) -> object:
        assert installation_id == 44 and tuple(repository_ids) == (31,)
        return object()

    def close(self) -> None:
        pass


class ScenarioProvider:
    def __init__(self, *, rerun_conclusion: str | None = None) -> None:
        self.head, self.base = HEAD, BASE
        self.state, self.draft, self.merged = "open", False, False
        self.mergeable, self.mergeable_state = True, "clean"
        self.rerun_conclusion = rerun_conclusion
        self.run_attempt = 1
        self.run_conclusion = "failure" if rerun_conclusion is not None else "success"
        self.rerun_requests = 0
        self.git_reconciliations: list[dict[str, object]] = []
        self.git_publications: list[dict[str, object]] = []
        self.comments: list[dict[str, object]] = []
        self.review_comments: list[dict[str, object]] = []
        self.calls: list[tuple[str, str]] = []
        self.requests: list[tuple[str, str, str]] = []
        self.writes: list[tuple[str, str, int, str]] = []

    def pages(self, path: str) -> tuple[dict[str, object], ...]:
        self.calls.append(("PAGES", path))
        if path == "/repos/owner/repo/issues/7/comments?per_page=100":
            return tuple(self.comments)
        if path == "/repos/owner/repo/pulls/7/comments?per_page=100":
            return tuple(self.review_comments)
        if path == "/repos/owner/repo/pulls/7/reviews?per_page=100":
            return (
                {
                    "id": 301,
                    "submitted_at": "2026-08-16T00:00:00Z",
                    "state": "APPROVED",
                    "user": {"login": "reviewer"},
                },
            )
        raise AssertionError(f"unexpected provider pages request: {path}")

    def request(self, method: str, path: str, body: object | None = None) -> WireResponse:
        self.calls.append((method, path))
        self.requests.append((method, path, "" if body is None else json.dumps(body, sort_keys=True)))
        if method == "GET" and path == "/repos/owner/repo/pulls/7":
            return WireResponse(
                200,
                {
                    "state": self.state,
                    "draft": self.draft,
                    "mergeable": self.mergeable,
                    "mergeable_state": self.mergeable_state,
                    "merged": self.merged,
                    "html_url": "https://github.com/owner/repo/pull/7",
                    "user": {"login": "author"},
                    "head": {"sha": self.head, "ref": "feature", "repo": {"full_name": "owner/repo"}},
                    "base": {"sha": self.base, "ref": "main"},
                },
            )
        if method == "GET" and path == "/repos/owner/repo/git/ref/heads/main":
            return WireResponse(200, {"object": {"sha": self.base}})
        if method == "GET" and path == "/repos/owner/repo/rules/branches/main":
            return WireResponse(
                200,
                [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "strict_required_status_checks_policy": True,
                            "required_status_checks": [{"context": "build"}],
                        },
                    },
                    {
                        "type": "pull_request",
                        "parameters": {
                            "required_approving_review_count": 1,
                            "required_review_thread_resolution": True,
                        },
                    },
                ],
            )
        if method == "GET" and path == f"/repos/owner/repo/compare/{BASE}...{HEAD}":
            return WireResponse(200, {"status": "ahead", "behind_by": 0})
        if method == "GET" and path == "/repos/owner/repo/pulls/7/requested_reviewers":
            return WireResponse(200, {"users": []})
        if (
            method == "GET"
            and path
            == "/repos/owner/repo/actions/workflows/.github%2Fworkflows%2Fci.yml/runs?event=pull_request&per_page=100"
        ):
            return WireResponse(
                200,
                {
                    "total_count": 1,
                    "workflow_runs": [
                        {
                            "id": 101,
                            "run_attempt": self.run_attempt,
                            "head_sha": HEAD,
                            "event": "pull_request",
                            "path": ".github/workflows/ci.yml",
                            "status": "completed",
                            "conclusion": self.run_conclusion,
                            "pull_requests": [{"number": 7}],
                        }
                    ],
                },
            )
        if (
            method == "GET"
            and path == f"/repos/owner/repo/actions/runs/101/attempts/{self.run_attempt}/jobs?per_page=100"
        ):
            return WireResponse(
                200,
                {
                    "total_count": 1,
                    "jobs": [
                        {
                            "id": 200 + self.run_attempt,
                            "name": "build",
                            "status": "completed",
                            "conclusion": self.run_conclusion,
                        }
                    ],
                },
            )
        if (
            method == "POST"
            and path == "/graphql"
            and isinstance(body, dict)
            and "reviewThreads" in str(body.get("query"))
        ):
            return WireResponse(
                200,
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "nodes": [{"id": "thread-1", "isResolved": True}],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                }
                            }
                        }
                    }
                },
            )
        if method == "POST" and path == "/repos/owner/repo/issues/7/comments" and isinstance(body, dict):
            comment = {
                "id": len(self.comments) + 1,
                "html_url": f"https://github.com/owner/repo/pull/7#issuecomment-{len(self.comments) + 1}",
                "body": body.get("body", ""),
                "user": {"login": BOT},
            }
            self.comments.append(comment)
            self.writes.append((method, path, int(comment["id"]), str(comment["body"])))
            if "<!-- hamsterdan-rerun " in str(comment["body"]):
                self.rerun_requests += 1
            return WireResponse(201, comment)
        if method == "POST" and path == "/repos/owner/repo/pulls/7/comments" and isinstance(body, dict):
            comment = {
                "id": 1_000 + len(self.review_comments) + 1,
                "html_url": f"https://github.com/owner/repo/pull/7#discussion_r{len(self.review_comments) + 1}",
                "body": body.get("body", ""),
                "user": {"login": BOT},
                "commit_id": body.get("commit_id"),
                "path": body.get("path"),
                "line": body.get("line"),
                "side": body.get("side"),
            }
            self.review_comments.append(comment)
            self.writes.append((method, path, int(comment["id"]), str(comment["body"])))
            return WireResponse(201, comment)
        if method == "PATCH" and path.startswith("/repos/owner/repo/issues/comments/") and isinstance(body, dict):
            identifier = int(path.rsplit("/", 1)[1])
            comment = next(item for item in self.comments if item["id"] == identifier)
            comment["body"] = body.get("body", "")
            self.writes.append((method, path, identifier, str(comment["body"])))
            return WireResponse(200, comment)
        raise AssertionError(f"unexpected provider request: {method} {path} {body!r}")

    def complete_rerun(self) -> None:
        if self.rerun_conclusion is None or self.rerun_requests != 1:
            raise AssertionError("attempt 2 requires exactly one proven rerun request")
        if (self.run_attempt, self.run_conclusion) != (1, "failure"):
            raise AssertionError("only failed attempt 1 can advance to the rerun outcome")
        self.run_attempt = 2
        self.run_conclusion = self.rerun_conclusion


class ScenarioRunner:
    def __init__(self, *, coding_status: str | None = None, seeded_finding: bool = False) -> None:
        self.reviews: list[tuple[str, ReviewRequest, str, int]] = []
        self.review_results: list[ReviewResult] = []
        self.code_calls: list[tuple[str, CodingRequest, str, int]] = []
        self.coding_status = coding_status
        self.seeded_finding = seeded_finding
        self.codes = 0
        self.conversations = 0

    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        self.reviews.append((repository_url, request, operation, attempt))
        assert is_current is None or is_current()
        result = ReviewResult(
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            "blocking" if self.seeded_finding else "clear",
            [BLOCKING_FINDING] if self.seeded_finding else [],
            BLOCKING_LINEAGE if self.seeded_finding else [],
        )
        self.review_results.append(result)
        return result

    def code(self, repository_url, request, *, operation, attempt, is_current=None):
        self.codes += 1
        self.code_calls.append((repository_url, request, operation, attempt))
        assert is_current is None or is_current()
        if self.coding_status is None:
            raise AssertionError("this parity journey must not invoke a coding agent")
        return CodingResult(
            request.kind,
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            request.ref,
            self.coding_status,
            "reproduced" if request.kind == "repair" else "not_attempted",
            "",
            [],
            [],
            "",
        )

    def converse(self, *args: object, **kwargs: object) -> None:
        self.conversations += 1
        raise AssertionError("this parity journey must not invoke a conversation agent")


@dataclass(frozen=True)
class JourneyResult:
    custody_before: str | None
    custody_after: str | None
    custody_counts: dict[str, int]
    comments: tuple[dict[str, object], ...]
    review_comments: tuple[dict[str, object], ...]
    provider_calls: tuple[tuple[str, str], ...]
    provider_requests: tuple[tuple[str, str, str], ...]
    provider_writes: tuple[tuple[str, str, int, str], ...]
    provider_state: tuple[str, bool, bool, bool, str, str, str]
    topology: str
    runner: ScenarioRunner
    run_attempt: int
    run_conclusion: str
    rerun_requests: int
    git_reconciliations: tuple[dict[str, object], ...]
    git_publications: tuple[dict[str, object], ...]
    before_follow_up_comments: tuple[dict[str, object], ...]
    before_follow_up_calls: tuple[tuple[str, str], ...]
    before_follow_up_write_count: int
    follow_up_custody_before: str | None
    quiescent_comments: tuple[dict[str, object], ...]
    quiescent_review_count: int


def config(root: Path) -> HostConfig:
    return HostConfig(
        app_id=17,
        app_slug="hamsterdan-test",
        client_id=CLIENT_SECRET,
        account_id=23,
        account_login="Owner",
        allowed_repositories=frozenset({(31, "owner/repo")}),
        state_path=root,
        private_key=PRIVATE_KEY,
        webhook_secret=WEBHOOK_SECRET,
    )


def envelope() -> bytes:
    return json.dumps(
        {
            "action": "synchronize",
            "installation": {"id": 44, "account": {"id": 23}},
            "repository": {"id": 31, "full_name": "owner/repo"},
            "pull_request": {"number": 7},
        }
    ).encode()


def workflow_envelope(conclusion: str) -> bytes:
    return json.dumps(
        {
            "action": "completed",
            "installation": {"id": 44, "account": {"id": 23}},
            "repository": {"id": 31, "full_name": "owner/repo"},
            "workflow_run": {
                "id": 101,
                "run_attempt": 2,
                "head_sha": HEAD,
                "status": "completed",
                "conclusion": conclusion,
                "pull_requests": [{"number": 7}],
            },
        }
    ).encode()


def signed(body: bytes, delivery: str, event: str = "pull_request") -> dict[str, str]:
    digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        "content-type": "application/json",
        "content-length": str(len(body)),
        "x-hub-signature-256": f"sha256={digest}",
        "x-github-delivery": delivery,
        "x-github-event": event,
    }


def _run_journey(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
    *,
    rerun_conclusion: str | None,
    seeded_finding: bool = False,
) -> JourneyResult:
    provider = ScenarioProvider(rerun_conclusion=rerun_conclusion)
    runner = ScenarioRunner(
        coding_status="unchanged" if rerun_conclusion == "failure" else None,
        seeded_finding=seeded_finding,
    )
    monkeypatch.setattr("hamsterdan.host.service.GitHubKitTransport", lambda client: provider)
    if rerun_conclusion == "failure":

        def reconcile(_publisher, **kwargs):
            provider.git_reconciliations.append(dict(kwargs))
            return GitReconciliation("absent", provider.head)

        def publish(_publisher, _result, **kwargs):
            provider.git_publications.append(dict(kwargs))
            raise AssertionError("an unchanged repair must never reach Git publication")

        monkeypatch.setattr(HostGitPublisher, "reconcile", reconcile)
        monkeypatch.setattr(HostGitPublisher, "publish", publish)
    agent_composition = compose_agent()
    routes = AgentRouteStore(root / "agent-routes.sqlite3")
    routes.activate(agent_composition, root / "applications")
    host = HostService(
        config(root),
        clients=Clients(),  # type: ignore[arg-type]
        runner=runner,  # type: ignore[arg-type]
        agent_composition=agent_composition,
        agent_routes=routes,
        readiness_composition=topology,
    )
    host.registry.reconcile(44, ((31, "owner/repo"),))
    delivery, body = str(uuid.uuid4()), envelope()
    receipt = host.custody.receive(signed(body, delivery).items(), body)
    assert receipt.disposition == "accepted"
    custody_before = host.custody.status(delivery)
    host.process(host.custody.pending()[0])
    application_key = (44, 31, 7)

    def external_state() -> tuple[object, ...]:
        return (
            tuple(provider.calls),
            tuple(provider.requests),
            tuple(provider.writes),
            tuple(runner.reviews),
            tuple(runner.review_results),
            tuple(runner.code_calls),
            runner.conversations,
            tuple(provider.git_reconciliations),
            tuple(provider.git_publications),
        )

    def converge() -> None:
        for _ in range(50):
            before = external_state()
            processed = host.pump()
            application = host._apps[application_key]
            if processed == 0 and before == external_state() and not topology.has_unresolved(application):
                return
        raise AssertionError("parity journey host did not converge")

    converge()
    before_follow_up_comments = tuple(dict(item) for item in provider.comments)
    before_follow_up_calls = tuple(provider.calls)
    before_follow_up_write_count = len(provider.writes)
    follow_up_custody_before = None
    if rerun_conclusion is not None:
        provider.complete_rerun()
        follow_up, follow_up_body = str(uuid.uuid4()), workflow_envelope(rerun_conclusion)
        receipt = host.custody.receive(signed(follow_up_body, follow_up, "workflow_run").items(), follow_up_body)
        assert receipt.disposition == "accepted"
        follow_up_custody_before = host.custody.status(follow_up)
        pending = next(item for item in host.custody.pending() if item.delivery_id == follow_up)
        host.process(pending)
        converge()
    comments = tuple(dict(item) for item in provider.comments)
    application = host._apps[application_key]
    frozen = external_state()
    assert not topology.has_unresolved(application)
    assert host.pump() == 0
    assert not topology.has_unresolved(application) and external_state() == frozen
    result = JourneyResult(
        custody_before,
        host.custody.status(delivery),
        host.custody.counts(),
        comments,
        tuple(dict(item) for item in provider.review_comments),
        tuple(provider.calls),
        tuple(provider.requests),
        tuple(provider.writes),
        (
            provider.state,
            provider.draft,
            provider.merged,
            provider.mergeable,
            provider.mergeable_state,
            provider.head,
            provider.base,
        ),
        topology.topology,
        runner,
        provider.run_attempt,
        provider.run_conclusion,
        provider.rerun_requests,
        tuple(provider.git_reconciliations),
        tuple(provider.git_publications),
        before_follow_up_comments,
        before_follow_up_calls,
        before_follow_up_write_count,
        follow_up_custody_before,
        tuple(dict(item) for item in provider.comments),
        len(runner.reviews),
    )
    provider.state, provider.draft, provider.merged = "closed", True, True
    provider.mergeable, provider.mergeable_state = False, "dirty"
    provider.head, provider.base = "c" * 40, "d" * 40
    frozen = external_state()
    host.close()
    assert external_state() == frozen
    assert tuple(provider.comments) == result.quiescent_comments
    assert len(runner.reviews) == result.quiescent_review_count
    return result


def run_clean_green(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> JourneyResult:
    return _run_journey(root, monkeypatch, topology, rerun_conclusion=None)


def run_first_attempt_flake(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> JourneyResult:
    return _run_journey(root, monkeypatch, topology, rerun_conclusion="success")


def run_persistent_ci_regression(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> JourneyResult:
    return _run_journey(root, monkeypatch, topology, rerun_conclusion="failure")


def run_seeded_review_finding(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> JourneyResult:
    return _run_journey(root, monkeypatch, topology, rerun_conclusion=None, seeded_finding=True)


def assert_public_clone(repository_url: str) -> None:
    assert repository_url == "https://github.com/owner/repo.git"


def assert_clear_review(result: JourneyResult) -> None:
    assert len(result.runner.reviews) == 1
    repository_url, request, operation, attempt = result.runner.reviews[0]
    assert (request.repository, request.pull_request, request.head, request.base) == ("owner/repo", 7, HEAD, BASE)
    assert result.runner.review_results == [ReviewResult("owner/repo", 7, request.epoch, HEAD, BASE, "clear", [], [])]
    assert operation and attempt == 1
    assert_public_clone(repository_url)
    encoded_request = json.dumps(asdict(request), sort_keys=True)
    assert all(
        canary not in repository_url + encoded_request
        for canary in (PRIVATE_KEY, WEBHOOK_SECRET, CLIENT_SECRET, INSTALLATION_TOKEN)
    )


def assert_clean_green(result: JourneyResult) -> None:
    assert result.custody_before == "pending"
    assert result.custody_after == "terminal"
    assert result.custody_counts == {"terminal": 1}
    assert_clear_review(result)
    assert result.runner.codes == result.runner.conversations == 0

    dashboard = [item for item in result.comments if "<!-- hamsterdan:dashboard -->" in str(item["body"])]
    readiness = [item for item in result.comments if "<!-- hamsterdan:readiness " in str(item["body"])]
    assert len(dashboard) == len(readiness) == 1
    assert f"head={HEAD}" in str(readiness[0]["body"])
    assert "All observed gates are ready" in str(readiness[0]["body"])
    assert all(item["user"] == {"login": BOT} for item in result.comments)
    assert result.review_comments == ()
    assert not any("<!-- hamsterdan:finding " in str(item["body"]) for item in result.comments)
    assert not any("hamsterdan-rerun" in str(item["body"]) for item in result.comments)
    assert (result.run_attempt, result.run_conclusion, result.rerun_requests) == (1, "success", 0)
    assert result.provider_state == ("open", False, False, True, "clean", HEAD, BASE)

    required_evidence_calls = {
        ("GET", "/repos/owner/repo/pulls/7"),
        ("GET", "/repos/owner/repo/git/ref/heads/main"),
        ("GET", "/repos/owner/repo/rules/branches/main"),
        ("GET", f"/repos/owner/repo/compare/{BASE}...{HEAD}"),
        (
            "GET",
            "/repos/owner/repo/actions/workflows/.github%2Fworkflows%2Fci.yml/runs?event=pull_request&per_page=100",
        ),
        ("GET", "/repos/owner/repo/actions/runs/101/attempts/1/jobs?per_page=100"),
        ("GET", "/repos/owner/repo/pulls/7/requested_reviewers"),
        ("PAGES", "/repos/owner/repo/pulls/7/reviews?per_page=100"),
        ("POST", "/graphql"),
    }
    assert required_evidence_calls <= set(result.provider_calls)

    forbidden = (
        "/git/blobs",
        "/git/trees",
        "/git/commits",
        "/git/refs",
        "/merge",
        "/rerun",
        "updateRefs",
    )
    assert not any(any(fragment in path for fragment in forbidden) for _method, path in result.provider_calls)
    assert result.comments == result.quiescent_comments
    assert len(result.runner.reviews) == result.quiescent_review_count


def assert_first_attempt_flake(result: JourneyResult) -> None:
    assert result.custody_before == "pending"
    assert result.custody_after == "terminal"
    assert result.follow_up_custody_before == "pending"
    assert result.custody_counts == {"terminal": 2}
    assert (result.run_attempt, result.run_conclusion, result.rerun_requests) == (2, "success", 1)
    assert_clear_review(result)
    assert result.runner.codes == result.runner.conversations == 0

    before_reruns = [item for item in result.before_follow_up_comments if "<!-- hamsterdan-rerun " in str(item["body"])]
    before_dashboard = [
        item for item in result.before_follow_up_comments if "<!-- hamsterdan:dashboard -->" in str(item["body"])
    ]
    before_readiness = [
        item for item in result.before_follow_up_comments if "<!-- hamsterdan:readiness " in str(item["body"])
    ]
    assert len(before_reruns) == len(before_dashboard) == 1
    assert before_readiness == []
    assert ("GET", "/repos/owner/repo/actions/runs/101/attempts/1/jobs?per_page=100") in result.before_follow_up_calls
    assert not any("/attempts/2/jobs" in path for _method, path in result.before_follow_up_calls)

    reruns = [item for item in result.comments if "<!-- hamsterdan-rerun " in str(item["body"])]
    dashboard = [item for item in result.comments if "<!-- hamsterdan:dashboard -->" in str(item["body"])]
    readiness = [item for item in result.comments if "<!-- hamsterdan:readiness " in str(item["body"])]
    assert len(reruns) == len(dashboard) == len(readiness) == 1
    marker = re.fullmatch(
        rf"<!-- hamsterdan-rerun run=101 head={HEAD} operation=([^ >]+) -->",
        str(reruns[0]["body"]),
    )
    assert marker is not None and marker.group(1)
    assert f"head={HEAD}" in str(readiness[0]["body"])
    assert "All observed gates are ready" in str(readiness[0]["body"])
    assert all(item["user"] == {"login": BOT} for item in result.comments)
    assert result.review_comments == ()
    assert not any("<!-- hamsterdan:finding " in str(item["body"]) for item in result.comments)
    assert result.provider_state == ("open", False, False, True, "clean", HEAD, BASE)

    dashboard_id = int(before_dashboard[0]["id"])
    assert dashboard == [{**before_dashboard[0], "body": dashboard[0]["body"]}]
    assert dashboard[0]["body"] != before_dashboard[0]["body"]
    follow_up_writes = result.provider_writes[result.before_follow_up_write_count :]
    assert any(
        method == "PATCH" and identifier == dashboard_id and body == dashboard[0]["body"]
        for method, _path, identifier, body in follow_up_writes
    )

    rerun_writes = [
        body
        for method, _path, _identifier, body in result.provider_writes
        if method == "POST" and "<!-- hamsterdan-rerun " in body
    ]
    readiness_writes = [
        body for _method, _path, _identifier, body in result.provider_writes if "<!-- hamsterdan:readiness " in body
    ]
    assert rerun_writes == [reruns[0]["body"]]
    assert readiness_writes == [readiness[0]["body"]]
    assert not any("<!-- hamsterdan:finding " in body for _method, _path, _identifier, body in result.provider_writes)

    assert ("GET", "/repos/owner/repo/actions/runs/101/attempts/1/jobs?per_page=100") in result.provider_calls
    assert ("GET", "/repos/owner/repo/actions/runs/101/attempts/2/jobs?per_page=100") in result.provider_calls
    forbidden = ("/git/blobs", "/git/trees", "/git/commits", "/git/refs", "/merge", "updateRefs")
    assert not any(
        any(fragment in path or fragment in body for fragment in forbidden)
        for _method, path, body in result.provider_requests
    )
    assert result.comments == result.quiescent_comments
    assert len(result.runner.reviews) == result.quiescent_review_count


def assert_persistent_ci_regression(result: JourneyResult) -> None:
    assert result.custody_before == result.follow_up_custody_before == "pending"
    assert result.custody_after == "terminal"
    assert result.custody_counts == {"terminal": 2}
    assert (result.run_attempt, result.run_conclusion, result.rerun_requests) == (2, "failure", 1)
    assert_clear_review(result)
    assert result.runner.conversations == 0

    before_reruns = [item for item in result.before_follow_up_comments if "<!-- hamsterdan-rerun " in str(item["body"])]
    before_dashboard = [
        item for item in result.before_follow_up_comments if "<!-- hamsterdan:dashboard -->" in str(item["body"])
    ]
    before_readiness = [
        item for item in result.before_follow_up_comments if "<!-- hamsterdan:readiness " in str(item["body"])
    ]
    assert len(before_reruns) == len(before_dashboard) == 1
    assert before_readiness == []
    assert ("GET", "/repos/owner/repo/actions/runs/101/attempts/1/jobs?per_page=100") in result.before_follow_up_calls
    assert not any("/attempts/2/jobs" in path for _method, path in result.before_follow_up_calls)

    reruns = [item for item in result.comments if "<!-- hamsterdan-rerun " in str(item["body"])]
    dashboard = [item for item in result.comments if "<!-- hamsterdan:dashboard -->" in str(item["body"])]
    readiness = [item for item in result.comments if "<!-- hamsterdan:readiness " in str(item["body"])]
    assert len(reruns) == len(dashboard) == 1
    assert readiness == []
    marker = re.fullmatch(
        rf"<!-- hamsterdan-rerun run=101 head={HEAD} operation=([^ >]+) -->",
        str(reruns[0]["body"]),
    )
    assert marker is not None and marker.group(1)
    assert not any("<!-- hamsterdan:finding " in str(item["body"]) for item in result.comments)
    assert result.provider_state == ("open", False, False, True, "clean", HEAD, BASE)

    assert result.runner.codes == 1 and result.runner.coding_status == "unchanged"
    [(repository_url, request, operation, attempt)] = result.runner.code_calls
    assert (request.kind, request.repository, request.pull_request, request.head, request.base) == (
        "repair",
        "owner/repo",
        7,
        HEAD,
        BASE,
    )
    assert_public_clone(repository_url)
    assert operation and attempt == 1 and len(request.failure_evidence) == 1
    failure = request.failure_evidence[0]
    assert str(failure["run_id"]) == "101"
    assert failure["head"] == HEAD and failure["attempt"] == 2 and failure["conclusion"] == "failure"
    assert request.fingerprint == failure["fingerprint"] == FAILURE_FINGERPRINT
    encoded_request = json.dumps(asdict(request), sort_keys=True)
    assert all(
        canary not in repository_url + encoded_request
        for canary in (PRIVATE_KEY, WEBHOOK_SECRET, CLIENT_SECRET, INSTALLATION_TOKEN)
    )
    assert result.git_publications == ()
    if result.topology == "v5":
        [reconciliation] = result.git_reconciliations
        assert reconciliation["expected_head"] == HEAD
        assert reconciliation["base_head"] == BASE
        assert reconciliation["merge_base"] is False
        assert reconciliation["operation"] and reconciliation["payload_digest"]
    else:
        assert result.topology == "production" and result.git_reconciliations == ()

    dashboard_id = int(before_dashboard[0]["id"])
    assert dashboard[0]["id"] == dashboard_id
    assert dashboard[0]["body"] != before_dashboard[0]["body"]
    follow_up_writes = result.provider_writes[result.before_follow_up_write_count :]
    assert any(
        method == "PATCH" and identifier == dashboard_id and body == dashboard[0]["body"]
        for method, _path, identifier, body in follow_up_writes
    )
    assert not any(
        "<!-- hamsterdan:readiness " in body or "<!-- hamsterdan:finding " in body
        for _method, _path, _identifier, body in result.provider_writes
    )

    assert ("GET", "/repos/owner/repo/actions/runs/101/attempts/2/jobs?per_page=100") in result.provider_calls
    forbidden = ("/git/blobs", "/git/trees", "/git/commits", "/git/refs", "/merge", "updateRefs")
    assert not any(
        any(fragment in path or fragment in body for fragment in forbidden)
        for _method, path, body in result.provider_requests
    )
    assert result.comments == result.quiescent_comments
    assert len(result.runner.reviews) == result.quiescent_review_count


def assert_seeded_review_finding(result: JourneyResult) -> None:
    assert result.custody_before == "pending"
    assert result.custody_after == "terminal"
    assert result.custody_counts == {"terminal": 1}
    assert len(result.runner.reviews) == 1
    repository_url, request, operation, attempt = result.runner.reviews[0]
    assert (request.repository, request.pull_request, request.head, request.base) == ("owner/repo", 7, HEAD, BASE)
    assert result.runner.review_results == [
        ReviewResult(
            "owner/repo",
            7,
            request.epoch,
            HEAD,
            BASE,
            "blocking",
            [BLOCKING_FINDING],
            BLOCKING_LINEAGE,
        )
    ]
    assert operation and attempt == 1
    assert_public_clone(repository_url)
    [actions] = request.actions_evidence
    assert (actions["id"], actions["head"], actions["attempt"], actions["status"], actions["conclusion"]) == (
        101,
        HEAD,
        1,
        "completed",
        "success",
    )
    encoded_request = json.dumps(asdict(request), sort_keys=True)
    assert all(
        canary not in repository_url + encoded_request
        for canary in (PRIVATE_KEY, WEBHOOK_SECRET, CLIENT_SECRET, INSTALLATION_TOKEN)
    )
    assert result.runner.codes == result.runner.conversations == 0

    dashboard = [item for item in result.comments if "<!-- hamsterdan:dashboard -->" in str(item["body"])]
    readiness = [item for item in result.comments if "<!-- hamsterdan:readiness " in str(item["body"])]
    finding_comments = [
        item for item in (*result.comments, *result.review_comments) if "<!-- hamsterdan:finding " in str(item["body"])
    ]
    assert len(dashboard) == len(finding_comments) == 1
    assert readiness == []
    finding_body = str(finding_comments[0]["body"])
    assert all(
        text in finding_body
        for text in (
            FINDING_ID,
            str(BLOCKING_FINDING["title"]),
            str(BLOCKING_FINDING["body"]),
            str(BLOCKING_FINDING["evidence"]),
        )
    )
    marker = re.search(
        rf"<!-- hamsterdan:finding operation=([^ >]+) head={HEAD} -->",
        finding_body,
    )
    assert marker is not None and marker.group(1)
    dashboard_body = str(dashboard[0]["body"])
    assert "blocking" in dashboard_body and (FINDING_ID in dashboard_body or "'count': 1" in dashboard_body)
    assert all(item["user"] == {"login": BOT} for item in (*result.comments, *result.review_comments))
    assert (result.run_attempt, result.run_conclusion, result.rerun_requests) == (1, "success", 0)
    assert result.provider_state == ("open", False, False, True, "clean", HEAD, BASE)
    assert result.git_reconciliations == result.git_publications == ()
    assert (
        "GET",
        "/repos/owner/repo/actions/workflows/.github%2Fworkflows%2Fci.yml/runs?event=pull_request&per_page=100",
    ) in result.provider_calls
    assert ("GET", "/repos/owner/repo/actions/runs/101/attempts/1/jobs?per_page=100") in result.provider_calls

    finding_writes = [
        body for _method, _path, _identifier, body in result.provider_writes if "<!-- hamsterdan:finding " in body
    ]
    readiness_writes = [
        body for _method, _path, _identifier, body in result.provider_writes if "<!-- hamsterdan:readiness " in body
    ]
    assert finding_writes == [finding_body]
    assert readiness_writes == []
    forbidden = ("/git/blobs", "/git/trees", "/git/commits", "/git/refs", "/merge", "/rerun", "updateRefs")
    assert not any(
        any(fragment in path or fragment in body for fragment in forbidden)
        for _method, path, body in result.provider_requests
    )
    assert result.comments == result.quiescent_comments
    assert len(result.runner.reviews) == result.quiescent_review_count


@pytest.mark.parametrize("topology", [PRODUCTION, V5], ids=["production", "v5"])
def test_clean_green_user_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> None:
    assert_clean_green(run_clean_green(tmp_path / topology.topology, monkeypatch, topology))


@pytest.mark.parametrize("topology", [PRODUCTION, V5], ids=["production", "v5"])
def test_first_attempt_flake_user_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> None:
    assert_first_attempt_flake(run_first_attempt_flake(tmp_path / topology.topology, monkeypatch, topology))


@pytest.mark.parametrize("topology", [PRODUCTION, V5], ids=["production", "v5"])
def test_persistent_ci_regression_user_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> None:
    assert_persistent_ci_regression(run_persistent_ci_regression(tmp_path / topology.topology, monkeypatch, topology))


@pytest.mark.parametrize("topology", [PRODUCTION, V5], ids=["production", "v5"])
def test_seeded_review_finding_user_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> None:
    assert_seeded_review_finding(run_seeded_review_finding(tmp_path / topology.topology, monkeypatch, topology))
