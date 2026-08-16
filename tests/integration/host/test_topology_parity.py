from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from hamsterdan.agents.protocol import (
    CodingRequest,
    CodingResult,
    ConversationRequest,
    ConversationResult,
    ReviewRequest,
    ReviewResult,
)
from hamsterdan.github_app.config import HostConfig
from hamsterdan.github_app.models import WireResponse
from hamsterdan.host.agenticus import AgentRouteStore, compose_agent
from hamsterdan.host.git_publish import GitPublishResult, GitReconciliation, HostGitPublisher
from hamsterdan.host.service import HostService
from hamsterdan.host.topology import PRODUCTION, V5, ReadinessComposition

HEAD = "a" * 40
NEW_HEAD = "c" * 40
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
CHANGE_INSTRUCTION = "Add a short usage note to README.md"
CHANGE_DIFF = """diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1,3 @@
 # Project
+
+Run `hamsterdan` to check pull-request readiness.
"""
REPAIR_DIFF = """diff --git a/src/readiness.py b/src/readiness.py
--- a/src/readiness.py
+++ b/src/readiness.py
@@ -14,6 +14,6 @@
 # Readiness must fail closed while GitHub reports unmergeable.
 def ready(mergeable, all_gates_clear):
     # Keep the provider guard attached to the ready branch.
-    if all_gates_clear:
+    if mergeable and all_gates_clear:
         return True
     return False
"""


class Clients:
    def installation(self, installation_id: int, repository_ids: list[int] | tuple[int, ...]) -> object:
        assert installation_id == 44 and tuple(repository_ids) == (31,)
        return object()

    def close(self) -> None:
        pass


def git(root: Path, *arguments: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        text=True,
        input=input_text,
    ).stdout.strip()


def repair_repository(root: Path) -> tuple[Path, Path, str, str]:
    root.mkdir(parents=True)
    remote = root / "remote.git"
    subprocess.run(("git", "init", "--bare", "-q", str(remote)), check=True)
    work = root / "work"
    subprocess.run(("git", "clone", "-q", str(remote), str(work)), check=True)
    git(work, "config", "user.name", "Parity Test")
    git(work, "config", "user.email", "parity@example.invalid")
    (work / "README.md").write_text("# Project\n")
    git(work, "add", "README.md")
    git(work, "commit", "-qm", "base")
    base = git(work, "rev-parse", "HEAD")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    source = work / "src" / "readiness.py"
    source.parent.mkdir()
    source.write_text(
        "".join(f"# Fixture context {line}\n" for line in range(1, 14))
        + "# Readiness must fail closed while GitHub reports unmergeable.\n"
        + "def ready(mergeable, all_gates_clear):\n"
        + "    # Keep the provider guard attached to the ready branch.\n"
        + "    if all_gates_clear:\n"
        + "        return True\n"
        + "    return False\n"
    )
    git(work, "add", "src/readiness.py")
    git(work, "commit", "-qm", "seed failing behavior")
    head = git(work, "rev-parse", "HEAD")
    git(work, "push", "-q", "origin", "HEAD:refs/heads/feature")
    return work, remote, base, head


class ScenarioProvider:
    def __init__(
        self,
        *,
        rerun_conclusion: str | None = None,
        head: str = HEAD,
        base: str = BASE,
        git_work: Path | None = None,
        git_remote: Path | None = None,
    ) -> None:
        self.head, self.base = head, base
        self.git_work, self.git_remote = git_work, git_remote
        self.created_git_objects: set[str] = set()
        self.cas_updates: list[dict[str, str]] = []
        self.git_boundary_events: list[dict[str, object]] = []
        self.state, self.draft, self.merged = "open", False, False
        self.mergeable, self.mergeable_state = True, "clean"
        self.rerun_conclusion = rerun_conclusion
        self.run_id = 101
        self.run_attempt = 1
        self.run_status = "completed"
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
        if method == "GET" and path == f"/repos/owner/repo/compare/{self.base}...{self.head}":
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
                            "id": self.run_id,
                            "run_attempt": self.run_attempt,
                            "head_sha": self.head,
                            "event": "pull_request",
                            "path": ".github/workflows/ci.yml",
                            "status": self.run_status,
                            "conclusion": self.run_conclusion,
                            "pull_requests": [{"number": 7}],
                        }
                    ],
                },
            )
        if (
            method == "GET"
            and path == f"/repos/owner/repo/actions/runs/{self.run_id}/attempts/{self.run_attempt}/jobs?per_page=100"
        ):
            return WireResponse(
                200,
                {
                    "total_count": 1,
                    "jobs": [
                        {
                            "id": 200 + self.run_attempt,
                            "name": "build",
                            "status": self.run_status,
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
        if method == "POST" and path.startswith("/repos/owner/repo/git/") and isinstance(body, dict):
            if self.git_work is None:
                raise AssertionError("this journey forbids Git object creation")
            self.git_boundary_events.append({"kind": "object", "path": path})
            if path.endswith("/blobs"):
                completed = subprocess.run(
                    ("git", "-C", str(self.git_work), "hash-object", "-w", "--stdin"),
                    input=base64.b64decode(str(body["content"])),
                    check=True,
                    capture_output=True,
                )
                created = completed.stdout.decode().strip()
            elif path.endswith("/trees"):
                index = self.git_work / ".git" / "parity-publication-index"
                index.unlink(missing_ok=True)
                environment = os.environ | {"GIT_INDEX_FILE": str(index)}
                subprocess.run(
                    ("git", "-C", str(self.git_work), "read-tree", str(body["base_tree"])),
                    check=True,
                    capture_output=True,
                    env=environment,
                )
                for entry in body["tree"]:
                    subprocess.run(
                        (
                            "git",
                            "-C",
                            str(self.git_work),
                            "update-index",
                            "--add",
                            "--cacheinfo",
                            f"{entry['mode']},{entry['sha']},{entry['path']}",
                        ),
                        check=True,
                        capture_output=True,
                        env=environment,
                    )
                created = subprocess.run(
                    ("git", "-C", str(self.git_work), "write-tree"),
                    check=True,
                    capture_output=True,
                    text=True,
                    env=environment,
                ).stdout.strip()
                index.unlink()
            elif path.endswith("/commits"):
                environment = os.environ | {
                    "GIT_AUTHOR_NAME": str(body["author"]["name"]),
                    "GIT_AUTHOR_EMAIL": str(body["author"]["email"]),
                    "GIT_COMMITTER_NAME": str(body["committer"]["name"]),
                    "GIT_COMMITTER_EMAIL": str(body["committer"]["email"]),
                    "GIT_AUTHOR_DATE": "2001-01-01T00:00:00Z",
                    "GIT_COMMITTER_DATE": "2001-01-01T00:00:00Z",
                }
                command = ["git", "-C", str(self.git_work), "commit-tree", str(body["tree"])]
                for parent in body["parents"]:
                    command.extend(("-p", str(parent)))
                created = subprocess.run(
                    command,
                    input=str(body["message"]),
                    check=True,
                    capture_output=True,
                    text=True,
                    env=environment,
                ).stdout.strip()
            else:
                raise AssertionError(f"unexpected Git object request: {path}")
            self.created_git_objects.add(created)
            return WireResponse(201, {"sha": created})
        if (
            method == "POST"
            and path == "/graphql"
            and isinstance(body, dict)
            and "repository(owner" in str(body.get("query"))
        ):
            assert body["variables"] == {"owner": "owner", "repository": "repo"}
            return WireResponse(200, {"data": {"repository": {"id": "R_owner_repo"}}})
        if (
            method == "POST"
            and path == "/graphql"
            and isinstance(body, dict)
            and "updateRefs" in str(body.get("query"))
        ):
            if self.git_work is None or self.git_remote is None:
                raise AssertionError("this journey forbids ref mutation")
            values = body["variables"]["input"]
            [update] = values["refUpdates"]
            assert values["repositoryId"] == "R_owner_repo"
            assert update["name"] == "refs/heads/feature" and update["force"] is False
            assert update["beforeOid"] == self.head
            assert update["afterOid"] in self.created_git_objects
            assert git(self.git_remote, "rev-parse", "refs/heads/feature") == self.head
            git(self.git_work, "push", "-q", str(self.git_remote), f"{update['afterOid']}:{update['name']}")
            self.cas_updates.append(
                {
                    "before": str(update["beforeOid"]),
                    "after": str(update["afterOid"]),
                    "client": str(values["clientMutationId"]),
                }
            )
            self.git_boundary_events.append({"kind": "cas", "before": self.head, "after": update["afterOid"]})
            self.head = str(update["afterOid"])
            self.run_id = 102
            self.run_attempt = 1
            self.run_status = "completed"
            self.run_conclusion = "success"
            return WireResponse(
                200,
                {"data": {"updateRefs": {"clientMutationId": values["clientMutationId"]}}},
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
        self.run_status = "completed"
        self.run_conclusion = self.rerun_conclusion


class ScenarioRunner:
    def __init__(
        self,
        *,
        coding_status: str | None = None,
        seeded_finding: bool = False,
        conversational_change: bool = False,
        finding_head: str | None = None,
    ) -> None:
        self.reviews: list[tuple[str, ReviewRequest, str, int]] = []
        self.review_results: list[ReviewResult] = []
        self.conversation_calls: list[tuple[str, ConversationRequest, str, int]] = []
        self.conversation_results: list[ConversationResult] = []
        self.code_calls: list[tuple[str, CodingRequest, str, int]] = []
        self.code_results: list[CodingResult] = []
        self.coding_status = coding_status
        self.seeded_finding = seeded_finding
        self.conversational_change = conversational_change
        self.finding_head = finding_head
        self.codes = 0
        self.conversations = 0

    def review(self, repository_url, request, *, operation, attempt, is_current=None):
        self.reviews.append((repository_url, request, operation, attempt))
        assert is_current is None or is_current()
        finding_open = self.seeded_finding and (self.finding_head is None or request.head == self.finding_head)
        if self.finding_head is not None:
            if finding_open:
                assert request.prior_findings == request.applied_changes == []
            else:
                [prior] = request.prior_findings
                assert all(prior[key] == value for key, value in BLOCKING_FINDING.items())
                assert request.applied_changes == BLOCKING_LINEAGE
        result = ReviewResult(
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            "blocking" if finding_open else "clear",
            [BLOCKING_FINDING] if finding_open else [],
            BLOCKING_LINEAGE
            if finding_open
            else [{"finding_id": FINDING_ID, "state": "resolved", "supersedes": None}]
            if self.seeded_finding
            else [],
        )
        self.review_results.append(result)
        return result

    def code(self, repository_url, request, *, operation, attempt, is_current=None):
        self.codes += 1
        self.code_calls.append((repository_url, request, operation, attempt))
        assert is_current is None or is_current()
        if self.coding_status is None:
            raise AssertionError("this parity journey must not invoke a coding agent")
        if self.coding_status == "changed":
            repair = request.kind == "repair"
            result = CodingResult(
                request.kind,
                request.repository,
                request.pull_request,
                request.epoch,
                request.head,
                request.base,
                request.ref,
                "changed",
                "confirmed" if repair else "not_attempted",
                REPAIR_DIFF if repair else CHANGE_DIFF,
                ["src/readiness.py"] if repair else ["README.md"],
                [{"command": "repair-check" if repair else "readme-check", "outcome": "passed"}],
                "fix: repair seeded failure" if repair else "docs: add usage note",
            )
        else:
            result = CodingResult(
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
        self.code_results.append(result)
        return result

    def converse(self, repository_url, request, *, operation, attempt, is_current=None):
        self.conversations += 1
        self.conversation_calls.append((repository_url, request, operation, attempt))
        assert is_current is None or is_current()
        if not self.conversational_change:
            raise AssertionError("this parity journey must not invoke a conversation agent")
        result = ConversationResult(
            request.repository,
            request.pull_request,
            request.epoch,
            request.head,
            request.base,
            [
                {
                    "type": "change",
                    "arguments": {"request": CHANGE_INSTRUCTION},
                    "mutation": True,
                    "explicit": True,
                    "confidence": 1.0,
                }
            ],
        )
        self.conversation_results.append(result)
        return result


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
    initial_head: str
    initial_base: str
    topology: str
    runner: ScenarioRunner
    run_attempt: int
    run_id: int
    run_conclusion: str | None
    rerun_requests: int
    git_reconciliations: tuple[dict[str, object], ...]
    git_publications: tuple[dict[str, object], ...]
    before_follow_up_comments: tuple[dict[str, object], ...]
    before_follow_up_calls: tuple[tuple[str, str], ...]
    before_follow_up_write_count: int
    follow_up_custody_before: str | None
    head_follow_up_custody_before: str | None
    head_follow_up_comments_before: tuple[dict[str, object], ...] | None
    conversation_delivery_id: str | None
    git_cas_updates: tuple[dict[str, str], ...]
    git_created_objects: tuple[str, ...]
    git_boundary_events: tuple[dict[str, object], ...]
    git_remote_head: str
    git_commit_body: str
    git_commit_parents: tuple[str, ...]
    git_repaired_content: str
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


def workflow_envelope(conclusion: str, *, head: str = HEAD) -> bytes:
    return json.dumps(
        {
            "action": "completed",
            "installation": {"id": 44, "account": {"id": 23}},
            "repository": {"id": 31, "full_name": "owner/repo"},
            "workflow_run": {
                "id": 101,
                "run_attempt": 2,
                "head_sha": head,
                "status": "completed",
                "conclusion": conclusion,
                "pull_requests": [{"number": 7}],
            },
        }
    ).encode()


def comment_envelope(comment_id: int) -> bytes:
    return json.dumps(
        {
            "action": "created",
            "installation": {"id": 44, "account": {"id": 23}},
            "repository": {"id": 31, "full_name": "owner/repo"},
            "issue": {"number": 7, "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/7"}},
            "comment": {
                "id": comment_id,
                "body": f"@hamsterdan-test {CHANGE_INSTRUCTION}",
                "author_association": "OWNER",
                "user": {"id": 701, "login": "author", "type": "User"},
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
    conversational_change: bool = False,
    agent_repair: bool = False,
) -> JourneyResult:
    assert not conversational_change or rerun_conclusion is None
    assert not agent_repair or rerun_conclusion == "failure"
    git_work = git_remote = None
    initial_base, initial_head = BASE, HEAD
    if agent_repair:
        git_work, git_remote, initial_base, initial_head = repair_repository(root / "git-world")
    provider = ScenarioProvider(
        rerun_conclusion=rerun_conclusion,
        head=initial_head,
        base=initial_base,
        git_work=git_work,
        git_remote=git_remote,
    )
    runner = ScenarioRunner(
        coding_status="changed"
        if conversational_change or agent_repair
        else "unchanged"
        if rerun_conclusion == "failure"
        else None,
        seeded_finding=seeded_finding or agent_repair,
        conversational_change=conversational_change,
        finding_head=initial_head if agent_repair else None,
    )
    monkeypatch.setattr("hamsterdan.host.service.GitHubKitTransport", lambda client: provider)
    if agent_repair:
        assert git_remote is not None
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{git_remote.as_uri()}.insteadOf")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://github.com/owner/repo.git")
        original_reconcile = HostGitPublisher.reconcile
        original_publish = HostGitPublisher.publish

        def observed_reconcile(self, **kwargs):
            reconciliation = original_reconcile(self, **kwargs)
            observed = {**kwargs, "result": asdict(reconciliation)}
            provider.git_reconciliations.append(observed)
            provider.git_boundary_events.append({"kind": "reconcile", **observed})
            return reconciliation

        def observed_publish(self, result, **kwargs):
            publication = original_publish(self, result, **kwargs)
            observed = {**kwargs, "result": asdict(result), "outcome": asdict(publication)}
            provider.git_publications.append(observed)
            provider.git_boundary_events.append({"kind": "publish", **observed})
            return publication

        monkeypatch.setattr(HostGitPublisher, "reconcile", observed_reconcile)
        monkeypatch.setattr(HostGitPublisher, "publish", observed_publish)
    elif rerun_conclusion == "failure" or conversational_change:

        def reconcile(_publisher, **kwargs):
            provider.git_reconciliations.append(dict(kwargs))
            return GitReconciliation("absent", provider.head)

        def publish(_publisher, result, **kwargs):
            provider.git_publications.append({**kwargs, "result": asdict(result)})
            if not conversational_change:
                raise AssertionError("an unchanged repair must never reach Git publication")
            assert provider.head == HEAD
            provider.head = NEW_HEAD
            provider.run_id = 102
            provider.run_attempt = 1
            provider.run_status = "in_progress"
            provider.run_conclusion = None
            return GitPublishResult(NEW_HEAD)

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
            tuple(runner.conversation_calls),
            tuple(runner.conversation_results),
            tuple(runner.code_calls),
            tuple(runner.code_results),
            runner.conversations,
            tuple(provider.git_reconciliations),
            tuple(provider.git_publications),
            tuple(provider.cas_updates),
            tuple(sorted(provider.created_git_objects)),
            tuple(provider.git_boundary_events),
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
    if agent_repair:
        assert runner.code_calls == []
    follow_up_custody_before = None
    head_follow_up_custody_before = None
    head_follow_up_comments_before = None
    conversation_delivery_id = None
    if conversational_change:
        comment_id = 501
        provider.comments.append(
            {
                "id": comment_id,
                "html_url": "https://github.com/owner/repo/pull/7#issuecomment-501",
                "body": f"@hamsterdan-test {CHANGE_INSTRUCTION}",
                "user": {"login": "author"},
            }
        )
        follow_up, follow_up_body = str(uuid.uuid4()), comment_envelope(comment_id)
        conversation_delivery_id = follow_up
        receipt = host.custody.receive(signed(follow_up_body, follow_up, "issue_comment").items(), follow_up_body)
        assert receipt.disposition == "accepted"
        follow_up_custody_before = host.custody.status(follow_up)
        pending = next(item for item in host.custody.pending() if item.delivery_id == follow_up)
        host.process(pending)
        converge()
        assert provider.head == NEW_HEAD

        head_follow_up_comments_before = tuple(dict(item) for item in provider.comments)
        head_follow_up, head_follow_up_body = str(uuid.uuid4()), envelope()
        receipt = host.custody.receive(signed(head_follow_up_body, head_follow_up).items(), head_follow_up_body)
        assert receipt.disposition == "accepted"
        head_follow_up_custody_before = host.custody.status(head_follow_up)
        pending = next(item for item in host.custody.pending() if item.delivery_id == head_follow_up)
        host.process(pending)
        converge()
    elif rerun_conclusion is not None:
        provider.complete_rerun()
        follow_up, follow_up_body = str(uuid.uuid4()), workflow_envelope(rerun_conclusion, head=initial_head)
        receipt = host.custody.receive(signed(follow_up_body, follow_up, "workflow_run").items(), follow_up_body)
        assert receipt.disposition == "accepted"
        follow_up_custody_before = host.custody.status(follow_up)
        pending = next(item for item in host.custody.pending() if item.delivery_id == follow_up)
        host.process(pending)
        converge()
        if agent_repair:
            assert provider.head != initial_head
            head_follow_up_comments_before = tuple(dict(item) for item in provider.comments)
            assert [request.head for _url, request, _operation, _attempt in runner.reviews] == [initial_head]
            [dashboard_before_head] = [
                item for item in head_follow_up_comments_before if "<!-- hamsterdan:dashboard -->" in str(item["body"])
            ]
            assert provider.head not in str(dashboard_before_head["body"])
            head_follow_up, head_follow_up_body = str(uuid.uuid4()), envelope()
            receipt = host.custody.receive(signed(head_follow_up_body, head_follow_up).items(), head_follow_up_body)
            assert receipt.disposition == "accepted"
            head_follow_up_custody_before = host.custody.status(head_follow_up)
            pending = next(item for item in host.custody.pending() if item.delivery_id == head_follow_up)
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
        initial_head,
        initial_base,
        topology.topology,
        runner,
        provider.run_attempt,
        provider.run_id,
        provider.run_conclusion,
        provider.rerun_requests,
        tuple(provider.git_reconciliations),
        tuple(provider.git_publications),
        before_follow_up_comments,
        before_follow_up_calls,
        before_follow_up_write_count,
        follow_up_custody_before,
        head_follow_up_custody_before,
        head_follow_up_comments_before,
        conversation_delivery_id,
        tuple(dict(item) for item in provider.cas_updates),
        tuple(sorted(provider.created_git_objects)),
        tuple(dict(item) for item in provider.git_boundary_events),
        "" if git_remote is None else git(git_remote, "rev-parse", "refs/heads/feature"),
        "" if git_remote is None else git(git_remote, "log", "-1", "--format=%B", provider.head),
        ()
        if git_remote is None
        else tuple(git(git_remote, "rev-list", "--parents", "-n", "1", provider.head).split()[1:]),
        "" if git_remote is None else git(git_remote, "show", f"{provider.head}:src/readiness.py"),
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


def run_conversational_change(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> JourneyResult:
    return _run_journey(root, monkeypatch, topology, rerun_conclusion=None, conversational_change=True)


def run_agent_repair(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> JourneyResult:
    return _run_journey(root, monkeypatch, topology, rerun_conclusion="failure", agent_repair=True)


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


def assert_conversational_change(result: JourneyResult) -> None:
    assert result.custody_before == result.follow_up_custody_before == result.head_follow_up_custody_before == "pending"
    assert result.custody_after == "terminal"
    assert result.custody_counts == {"terminal": 3}
    assert result.runner.conversations == len(result.runner.conversation_calls) == 1
    repository_url, conversation, conversation_operation, conversation_attempt = result.runner.conversation_calls[0]
    assert (conversation.repository, conversation.pull_request, conversation.head, conversation.base) == (
        "owner/repo",
        7,
        HEAD,
        BASE,
    )
    assert conversation.comment_context.get("text", conversation.comment_context.get("body")) == CHANGE_INSTRUCTION
    assert conversation.actor["login"] == "author"
    change_declaration = next(item for item in conversation.allowed_intents if item["type"] == "change")
    assert change_declaration["mutation"] is True and change_declaration["requires_explicit"] is True
    assert result.runner.conversation_results == [
        ConversationResult(
            "owner/repo",
            7,
            conversation.epoch,
            HEAD,
            BASE,
            [
                {
                    "type": "change",
                    "arguments": {"request": CHANGE_INSTRUCTION},
                    "mutation": True,
                    "explicit": True,
                    "confidence": 1.0,
                }
            ],
        )
    ]
    if result.topology == "v5":
        assert conversation_operation == (f"conversation:owner/repo:pr:7:delivery:{result.conversation_delivery_id}")
    else:
        assert result.topology == "production"
        assert re.fullmatch(r"conversation:[0-9a-f]{64}", conversation_operation)
    assert conversation_attempt == 1
    assert_public_clone(repository_url)

    assert result.runner.codes == len(result.runner.code_calls) == 1
    repository_url, coding, coding_operation, coding_attempt = result.runner.code_calls[0]
    assert (coding.kind, coding.repository, coding.pull_request, coding.head, coding.base) == (
        "change",
        "owner/repo",
        7,
        HEAD,
        BASE,
    )
    assert CHANGE_INSTRUCTION in json.dumps(coding.selected_work, sort_keys=True)
    assert coding.failure_evidence == [] and not coding.merge_base
    expected_v5_operation = f"push:comment:501:{HEAD}:i1"
    if result.topology == "v5":
        assert coding_operation == f"mutation:owner/repo:pr:7:{expected_v5_operation}"
    else:
        assert result.topology == "production"
        assert re.fullmatch(r"change:[0-9a-f]{64}", coding_operation)
    assert coding_attempt == 1
    assert_public_clone(repository_url)
    encoded_agent_work = json.dumps(
        {"conversation": asdict(conversation), "coding": asdict(coding)},
        sort_keys=True,
    )
    assert all(
        canary not in repository_url + encoded_agent_work
        for canary in (PRIVATE_KEY, WEBHOOK_SECRET, CLIENT_SECRET, INSTALLATION_TOKEN)
    )

    [publication] = result.git_publications
    assert publication["expected_head"] == HEAD
    assert publication["base_head"] == BASE
    assert publication["merge_base"] is False
    assert re.fullmatch(r"[0-9a-f]{64}", str(publication["payload_digest"]))
    published_result = publication["result"]
    assert isinstance(published_result, dict)
    for field in ("kind", "repository", "pull_request", "epoch", "head", "base", "ref"):
        assert published_result[field] == getattr(coding, field)
    assert published_result["status"] == "changed"
    assert published_result["changed_files"] == ["README.md"]
    assert published_result["diff"] == CHANGE_DIFF
    if result.topology == "v5":
        assert publication["operation"] == expected_v5_operation
        [reconciliation] = result.git_reconciliations
        assert reconciliation["expected_head"] == HEAD
        assert reconciliation["base_head"] == BASE
        assert reconciliation["merge_base"] is False
        assert reconciliation["operation"] == publication["operation"]
        assert reconciliation["payload_digest"] == publication["payload_digest"]
    else:
        assert result.topology == "production"
        assert publication["operation"] == coding_operation
        assert result.git_reconciliations == ()

    assert len(result.runner.reviews) == len(result.runner.review_results) == 2
    assert [request.head for _url, request, _operation, _attempt in result.runner.reviews] == [HEAD, NEW_HEAD]
    assert [request.epoch for _url, request, _operation, _attempt in result.runner.reviews] == [1, 2]
    assert [review.epoch for review in result.runner.review_results] == [1, 2]
    assert [review.status for review in result.runner.review_results] == ["clear", "clear"]
    assert all(
        url == "https://github.com/owner/repo.git" for url, _request, _operation, _attempt in result.runner.reviews
    )
    _url, new_review, _operation, _attempt = result.runner.reviews[1]
    [new_actions] = new_review.actions_evidence
    assert (
        new_actions["id"],
        new_actions["head"],
        new_actions["attempt"],
        new_actions["status"],
        new_actions["conclusion"],
    ) == (102, NEW_HEAD, 1, "in_progress", None)
    assert (result.run_id, result.run_attempt, result.run_conclusion, result.rerun_requests) == (102, 1, None, 0)
    assert result.provider_state == ("open", False, False, True, "clean", NEW_HEAD, BASE)

    human_comments = [item for item in result.comments if item["user"] == {"login": "author"}]
    bot_comments = [item for item in result.comments if item["user"] == {"login": BOT}]
    dashboard = [item for item in bot_comments if "<!-- hamsterdan:dashboard -->" in str(item["body"])]
    readiness = [item for item in bot_comments if "<!-- hamsterdan:readiness " in str(item["body"])]
    assert human_comments == [
        {
            "id": 501,
            "html_url": "https://github.com/owner/repo/pull/7#issuecomment-501",
            "body": f"@hamsterdan-test {CHANGE_INSTRUCTION}",
            "user": {"login": "author"},
        }
    ]
    assert len(dashboard) == len(readiness) == 1
    dashboard_body = str(dashboard[0]["body"])
    assert NEW_HEAD in dashboard_body
    if result.topology == "production":
        assert "Generation: `2`" in dashboard_body
        assert "Actions: **running**" in dashboard_body
        assert "actions/runs/102" in dashboard_body
    else:
        assert "checks:{'status': 'in_progress'}" in dashboard_body
    assert f"head={HEAD}" in str(readiness[0]["body"])
    assert NEW_HEAD not in str(readiness[0]["body"])
    assert not any("<!-- hamsterdan:finding " in str(item["body"]) for item in bot_comments)
    assert not any("hamsterdan-rerun" in str(item["body"]) for item in bot_comments)

    [before_dashboard] = [
        item for item in result.before_follow_up_comments if "<!-- hamsterdan:dashboard -->" in str(item["body"])
    ]
    assert dashboard[0]["id"] == before_dashboard["id"]
    assert dashboard[0]["body"] != before_dashboard["body"]
    follow_up_writes = result.provider_writes[result.before_follow_up_write_count :]
    assert any(
        method == "PATCH" and identifier == dashboard[0]["id"] and body == dashboard[0]["body"]
        for method, _path, identifier, body in follow_up_writes
    )
    assert ("GET", f"/repos/owner/repo/compare/{BASE}...{NEW_HEAD}") in result.provider_calls
    assert ("GET", "/repos/owner/repo/actions/runs/102/attempts/1/jobs?per_page=100") in result.provider_calls
    forbidden = ("/git/blobs", "/git/trees", "/git/commits", "/git/refs", "/merge", "/rerun", "updateRefs")
    assert not any(
        any(fragment in path or fragment in body for fragment in forbidden)
        for _method, path, body in result.provider_requests
    )
    assert result.comments == result.quiescent_comments
    assert len(result.runner.reviews) == result.quiescent_review_count


def assert_agent_repair(result: JourneyResult) -> None:
    initial_head, initial_base = result.initial_head, result.initial_base
    final_head = result.provider_state[5]
    assert result.custody_before == result.follow_up_custody_before == result.head_follow_up_custody_before == "pending"
    assert result.custody_after == "terminal" and result.custody_counts == {"terminal": 3}
    assert (result.run_id, result.run_attempt, result.run_conclusion, result.rerun_requests) == (102, 1, "success", 1)
    assert result.provider_state == ("open", False, False, True, "clean", final_head, initial_base)
    assert final_head not in {initial_head, initial_base}
    assert result.runner.conversations == 0 and result.runner.conversation_calls == []

    assert len(result.runner.code_calls) == len(result.runner.code_results) == result.runner.codes == 1
    repository_url, coding, coding_operation, coding_attempt = result.runner.code_calls[0]
    assert_public_clone(repository_url)
    assert (coding.kind, coding.repository, coding.pull_request, coding.epoch) == ("repair", "owner/repo", 7, 1)
    assert (coding.head, coding.base, coding_attempt) == (initial_head, initial_base, 1)
    assert coding.ref.startswith("hamsterdan/") and len(coding.failure_evidence) == 1
    [failure] = coding.failure_evidence
    assert (
        str(failure["run_id"]),
        failure["head"],
        failure["attempt"],
        failure["conclusion"],
        failure["fingerprint"],
    ) == ("101", initial_head, 2, "failure", FAILURE_FINGERPRINT)
    encoded_agent_work = repository_url + json.dumps(asdict(coding), sort_keys=True)
    assert all(
        canary not in encoded_agent_work for canary in (PRIVATE_KEY, WEBHOOK_SECRET, CLIENT_SECRET, INSTALLATION_TOKEN)
    )
    [coding_result] = result.runner.code_results
    assert coding_result == CodingResult(
        "repair",
        "owner/repo",
        7,
        1,
        initial_head,
        initial_base,
        coding.ref,
        "changed",
        "confirmed",
        REPAIR_DIFF,
        ["src/readiness.py"],
        [{"command": "repair-check", "outcome": "passed"}],
        "fix: repair seeded failure",
    )

    assert len(result.runner.reviews) == len(result.runner.review_results) == 2
    assert [(request.epoch, request.head) for _url, request, _operation, _attempt in result.runner.reviews] == [
        (1, initial_head),
        (2, final_head),
    ]
    assert all(
        url == "https://github.com/owner/repo.git" and request.base == initial_base and attempt == 1 and operation
        for url, request, operation, attempt in result.runner.reviews
    )
    first_review, repaired_review = result.runner.review_results
    assert (first_review.status, first_review.findings, first_review.lineage) == (
        "blocking",
        [BLOCKING_FINDING],
        BLOCKING_LINEAGE,
    )
    assert (repaired_review.status, repaired_review.findings, repaired_review.lineage) == (
        "clear",
        [],
        [{"finding_id": FINDING_ID, "state": "resolved", "supersedes": None}],
    )
    first_actions = result.runner.reviews[0][1].actions_evidence
    repaired_actions = result.runner.reviews[1][1].actions_evidence
    assert result.runner.reviews[0][1].prior_findings == result.runner.reviews[0][1].applied_changes == []
    [prior_finding] = result.runner.reviews[1][1].prior_findings
    assert all(prior_finding[key] == value for key, value in BLOCKING_FINDING.items())
    assert result.runner.reviews[1][1].applied_changes == BLOCKING_LINEAGE
    assert [(item["id"], item["head"], item["attempt"], item["conclusion"]) for item in first_actions] == [
        (101, initial_head, 1, "failure")
    ]
    assert [(item["id"], item["head"], item["attempt"], item["conclusion"]) for item in repaired_actions] == [
        (102, final_head, 1, "success")
    ]
    assert ("GET", "/repos/owner/repo/actions/runs/101/attempts/1/jobs?per_page=100") in result.provider_calls
    assert ("GET", "/repos/owner/repo/actions/runs/101/attempts/2/jobs?per_page=100") in result.provider_calls
    assert ("GET", "/repos/owner/repo/actions/runs/102/attempts/1/jobs?per_page=100") in result.provider_calls

    if result.topology == "v5":
        publication_operation = f"push:repair:L1:{FAILURE_FINGERPRINT}:{initial_head}:i1"
        assert coding_operation == f"mutation:owner/repo:pr:7:{publication_operation}"
    else:
        assert result.topology == "production"
        assert re.fullmatch(r"repair:[0-9a-f]{64}", coding_operation)
        publication_operation = coding_operation

    [publication] = result.git_publications
    assert publication["operation"] == publication_operation
    assert publication["expected_head"] == initial_head
    assert publication["base_head"] == initial_base and publication["merge_base"] is False
    payload_digest = str(publication["payload_digest"])
    assert re.fullmatch(r"[0-9a-f]{64}", payload_digest)
    assert publication["result"] == asdict(coding_result)
    assert publication["outcome"] == {"head": final_head, "recovered": False}
    dispositions = [item["result"]["disposition"] for item in result.git_reconciliations]
    assert dispositions[0] == "absent" and dispositions[-1] == "existing"
    assert dispositions.count("existing") == 1 and set(dispositions) == {"absent", "existing"}
    for reconciliation in result.git_reconciliations:
        assert reconciliation["operation"] == publication_operation
        assert reconciliation["payload_digest"] == payload_digest
        assert reconciliation["expected_head"] == initial_head
        assert reconciliation["base_head"] == initial_base and reconciliation["merge_base"] is False
    assert result.git_reconciliations[0]["result"]["observed_head"] == initial_head
    assert result.git_reconciliations[-1]["result"] == {
        "disposition": "existing",
        "observed_head": final_head,
        "commit": final_head,
        "parents": (initial_head,),
    }

    [cas] = result.git_cas_updates
    assert (cas["before"], cas["after"]) == (initial_head, final_head)
    expected_client = hashlib.sha256(
        json.dumps(
            {
                "repository": "owner/repo",
                "ref": "refs/heads/feature",
                "expected_head": initial_head,
                "commit": final_head,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert cas["client"] == expected_client
    assert result.git_remote_head == final_head
    assert result.git_commit_parents == (initial_head,)
    assert "if mergeable and all_gates_clear:" in result.git_repaired_content
    assert "    if all_gates_clear:" not in result.git_repaired_content
    assert result.git_commit_body == (
        "fix: repair seeded failure\n\n"
        f"Hamsterdan-Operation: {publication_operation}\n"
        f"Hamsterdan-Payload-Digest: {payload_digest}"
    )
    assert len(result.git_created_objects) == 3 and final_head in result.git_created_objects
    object_writes = [
        path
        for method, path, _body in result.provider_requests
        if method == "POST" and path.startswith("/repos/owner/repo/git/")
    ]
    assert object_writes == [
        "/repos/owner/repo/git/blobs",
        "/repos/owner/repo/git/trees",
        "/repos/owner/repo/git/commits",
    ]
    events = result.git_boundary_events
    object_events = [event["path"] for event in events if event["kind"] == "object"]
    assert object_events == object_writes
    object_indices = [index for index, event in enumerate(events) if event["kind"] == "object"]
    cas_event = next(index for index, event in enumerate(events) if event["kind"] == "cas")
    final_reconciliation = max(index for index, event in enumerate(events) if event["kind"] == "reconcile")
    publication_event = next(index for index, event in enumerate(events) if event["kind"] == "publish")
    assert events[0]["kind"] == "reconcile" and events[0]["result"]["disposition"] == "absent"
    assert 0 < object_indices[0] <= object_indices[-1] < cas_event < final_reconciliation < publication_event
    assert events[cas_event] == {"kind": "cas", "before": initial_head, "after": final_head}
    assert events[final_reconciliation]["result"]["disposition"] == "existing"
    assert publication_event == len(events) - 1
    assert (
        sum(
            "updateRefs" in body
            for method, path, body in result.provider_requests
            if method == "POST" and path == "/graphql"
        )
        == 1
    )
    assert not any("/merge" in path for _method, path, _body in result.provider_requests)

    rerun = [item for item in result.comments if "<!-- hamsterdan-rerun " in str(item["body"])]
    dashboard = [item for item in result.comments if "<!-- hamsterdan:dashboard -->" in str(item["body"])]
    readiness = [item for item in result.comments if "<!-- hamsterdan:readiness " in str(item["body"])]
    findings = [
        item for item in (*result.comments, *result.review_comments) if "<!-- hamsterdan:finding " in str(item["body"])
    ]
    assert len(rerun) == len(dashboard) == len(readiness) == len(findings) == 1
    assert f"run=101 head={initial_head}" in str(rerun[0]["body"])
    assert FINDING_ID in str(findings[0]["body"]) and initial_head in str(findings[0]["body"])
    assert final_head in str(dashboard[0]["body"])
    assert f"head={final_head}" in str(readiness[0]["body"])
    if result.topology == "production":
        assert "Generation: `2`" in str(dashboard[0]["body"])
        assert f"`{FINDING_ID}` resolved" in str(dashboard[0]["body"])
    else:
        assert f"findings:{{'blocking': 0, 'count': 0, 'head': '{final_head}'}}" in str(dashboard[0]["body"])
        assert f"review:{{'head': '{final_head}', 'status': 'clear'}}" in str(dashboard[0]["body"])
    assert result.head_follow_up_comments_before is not None
    assert not any("<!-- hamsterdan:readiness " in str(item["body"]) for item in result.head_follow_up_comments_before)
    readiness_writes = [
        body for _method, _path, _identifier, body in result.provider_writes if "<!-- hamsterdan:readiness " in body
    ]
    assert readiness_writes == [readiness[0]["body"]]
    assert all(item["user"] == {"login": BOT} for item in (*result.comments, *result.review_comments))
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


@pytest.mark.parametrize("topology", [PRODUCTION, V5], ids=["production", "v5"])
def test_conversational_change_user_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> None:
    assert_conversational_change(run_conversational_change(tmp_path / topology.topology, monkeypatch, topology))


@pytest.mark.parametrize("topology", [PRODUCTION, V5], ids=["production", "v5"])
def test_agent_repair_user_journey(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    topology: ReadinessComposition,
) -> None:
    assert_agent_repair(run_agent_repair(tmp_path / topology.topology, monkeypatch, topology))
