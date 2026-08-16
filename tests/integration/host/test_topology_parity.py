from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hamsterdan.agents.protocol import ReviewRequest, ReviewResult
from hamsterdan.github_app.config import HostConfig
from hamsterdan.github_app.models import WireResponse
from hamsterdan.host.agenticus import AgentRouteStore, compose_agent
from hamsterdan.host.service import HostService
from hamsterdan.host.topology import PRODUCTION, V5, ReadinessComposition

HEAD = "a" * 40
BASE = "b" * 40
BOT = "hamsterdan-test[bot]"
PRIVATE_KEY = "private-key-parity-canary"
WEBHOOK_SECRET = "webhook-secret-parity-canary"
CLIENT_SECRET = "client-secret-parity-canary"
INSTALLATION_TOKEN = "ghs_installation-parity-canary"


class Clients:
    def installation(self, installation_id: int, repository_ids: list[int] | tuple[int, ...]) -> object:
        assert installation_id == 44 and tuple(repository_ids) == (31,)
        return object()

    def close(self) -> None:
        pass


class CleanGreenProvider:
    def __init__(self) -> None:
        self.head, self.base = HEAD, BASE
        self.state, self.draft, self.merged = "open", False, False
        self.mergeable, self.mergeable_state = True, "clean"
        self.comments: list[dict[str, object]] = []
        self.review_comments: list[dict[str, object]] = []
        self.calls: list[tuple[str, str]] = []

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
                            "run_attempt": 1,
                            "head_sha": HEAD,
                            "event": "pull_request",
                            "path": ".github/workflows/ci.yml",
                            "status": "completed",
                            "conclusion": "success",
                            "pull_requests": [{"number": 7}],
                        }
                    ],
                },
            )
        if method == "GET" and path == "/repos/owner/repo/actions/runs/101/attempts/1/jobs?per_page=100":
            return WireResponse(
                200,
                {
                    "total_count": 1,
                    "jobs": [{"id": 201, "name": "build", "status": "completed", "conclusion": "success"}],
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
            return WireResponse(201, comment)
        if method == "PATCH" and path.startswith("/repos/owner/repo/issues/comments/") and isinstance(body, dict):
            identifier = int(path.rsplit("/", 1)[1])
            comment = next(item for item in self.comments if item["id"] == identifier)
            comment["body"] = body.get("body", "")
            return WireResponse(200, comment)
        raise AssertionError(f"unexpected provider request: {method} {path} {body!r}")


class CleanGreenRunner:
    def __init__(self) -> None:
        self.reviews: list[tuple[str, ReviewRequest, str, int]] = []
        self.review_results: list[ReviewResult] = []
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
            "clear",
            [],
            [],
        )
        self.review_results.append(result)
        return result

    def code(self, *args: object, **kwargs: object) -> None:
        self.codes += 1
        raise AssertionError("clean-green must not invoke a coding agent")

    def converse(self, *args: object, **kwargs: object) -> None:
        self.conversations += 1
        raise AssertionError("clean-green must not invoke a conversation agent")


@dataclass(frozen=True)
class CleanGreenResult:
    custody_before: str | None
    custody_after: str | None
    custody_counts: dict[str, int]
    comments: tuple[dict[str, object], ...]
    review_comments: tuple[dict[str, object], ...]
    provider_calls: tuple[tuple[str, str], ...]
    provider_state: tuple[str, bool, bool, bool, str, str, str]
    runner: CleanGreenRunner
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


def signed(body: bytes, delivery: str) -> dict[str, str]:
    digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        "content-type": "application/json",
        "content-length": str(len(body)),
        "x-hub-signature-256": f"sha256={digest}",
        "x-github-delivery": delivery,
        "x-github-event": "pull_request",
    }


def run_clean_green(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> CleanGreenResult:
    provider = CleanGreenProvider()
    runner = CleanGreenRunner()
    monkeypatch.setattr("hamsterdan.host.service.GitHubKitTransport", lambda client: provider)
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
    for _ in range(50):
        comments_before = tuple(dict(item) for item in provider.comments)
        reviews_before = len(runner.reviews)
        processed = host.pump()
        if processed == 0 and comments_before == tuple(provider.comments) and reviews_before == len(runner.reviews):
            break
    else:
        raise AssertionError("clean-green host did not converge")
    comments = tuple(dict(item) for item in provider.comments)
    assert host.pump() == 0
    result = CleanGreenResult(
        custody_before,
        host.custody.status(delivery),
        host.custody.counts(),
        comments,
        tuple(dict(item) for item in provider.review_comments),
        tuple(provider.calls),
        (
            provider.state,
            provider.draft,
            provider.merged,
            provider.mergeable,
            provider.mergeable_state,
            provider.head,
            provider.base,
        ),
        runner,
        tuple(dict(item) for item in provider.comments),
        len(runner.reviews),
    )
    provider.state, provider.draft, provider.merged = "closed", True, True
    provider.mergeable, provider.mergeable_state = False, "dirty"
    provider.head, provider.base = "c" * 40, "d" * 40
    host.close()
    assert tuple(provider.comments) == result.quiescent_comments
    assert len(runner.reviews) == result.quiescent_review_count
    return result


def assert_clean_green(result: CleanGreenResult) -> None:
    assert result.custody_before == "pending"
    assert result.custody_after == "terminal"
    assert result.custody_counts == {"terminal": 1}
    assert len(result.runner.reviews) == 1
    repository_url, request, operation, attempt = result.runner.reviews[0]
    assert (request.repository, request.pull_request, request.head, request.base) == ("owner/repo", 7, HEAD, BASE)
    assert result.runner.review_results == [ReviewResult("owner/repo", 7, request.epoch, HEAD, BASE, "clear", [], [])]
    assert operation and attempt == 1
    parsed = urlsplit(repository_url)
    assert (parsed.scheme, parsed.netloc, parsed.path, parsed.username, parsed.query) == (
        "https",
        "github.com",
        "/owner/repo.git",
        None,
        "",
    )
    encoded_request = json.dumps(asdict(request), sort_keys=True)
    assert all(
        canary not in repository_url + encoded_request
        for canary in (PRIVATE_KEY, WEBHOOK_SECRET, CLIENT_SECRET, INSTALLATION_TOKEN)
    )
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


@pytest.mark.parametrize("topology", [PRODUCTION, V5], ids=["production", "v5"])
def test_clean_green_user_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> None:
    assert_clean_green(run_clean_green(tmp_path / topology.topology, monkeypatch, topology))
