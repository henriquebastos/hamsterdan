"""Exact-repository and pull-request GitHub authority reads."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, cast
from urllib.parse import quote

from .models import (
    MAX_LOG_BYTES,
    ActionsEvidence,
    ActionsJobSnapshot,
    ActionsRunSnapshot,
    BinaryTransport,
    GitHubBoundaryError,
    GraphQLTransport,
    HumanReviewSnapshot,
    PullRequestSnapshot,
    RepositoryPolicy,
    Transport,
)

_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
MAX_PAGES = 20


class GitHubObjectWriteError(GitHubBoundaryError):
    """GitHub did not prove creation of an exact requested Git object."""


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _created_sha(response: object, kind: str) -> str:
    status, body = getattr(response, "status", None), getattr(response, "body", None)
    sha = body.get("sha") if isinstance(body, dict) else None
    if status != 201 or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise GitHubObjectWriteError(f"GitHub did not prove {kind} creation")
    return sha


class GitHubAuthority:
    """Reads authority for exactly one configured repository and PR."""

    def __init__(
        self, transport: Transport, repository: str, pr_number: int, *, graphql: GraphQLTransport | None = None
    ):
        owner, separator, name = repository.partition("/")
        if not separator or not owner or not name or "/" in name or pr_number <= 0:
            raise ValueError("repository and pull request must be exact")
        self.transport, self.repository, self.owner, self.name = transport, repository, owner, name
        self.pr_number, self.graphql = pr_number, graphql

    @property
    def root(self) -> str:
        return f"/repos/{self.repository}"

    def _get(self, path: str, statuses: frozenset[int] = frozenset({200})) -> object:
        response = self.transport.request("GET", path)
        if response.status not in statuses:
            raise GitHubBoundaryError(f"GitHub GET {path.split('?', 1)[0]} returned status {response.status}")
        return response.body

    def create_tree(
        self,
        *,
        base_tree: str,
        entries: Sequence[tuple[str, str, bytes | None]],
    ) -> str:
        """Create one GitHub tree from host-admitted Git entries."""

        tree: list[dict[str, object]] = []
        for path, mode, content in entries:
            sha = None
            if content is not None:
                response = self.transport.request(
                    "POST",
                    f"{self.root}/git/blobs",
                    {"content": base64.b64encode(content).decode(), "encoding": "base64"},
                )
                sha = _created_sha(response, "blob")
            tree.append({"path": path, "mode": mode, "type": "blob", "sha": sha})
        tree_response = self.transport.request("POST", f"{self.root}/git/trees", {"base_tree": base_tree, "tree": tree})
        return _created_sha(tree_response, "tree")

    def create_commit(
        self,
        *,
        tree: str,
        parents: Sequence[str],
        message: str,
        name: str,
        email: str,
    ) -> str:
        """Create one GitHub commit after the caller authorizes its proven tree."""

        commit_response = self.transport.request(
            "POST",
            f"{self.root}/git/commits",
            {
                "message": message,
                "tree": tree,
                "parents": list(parents),
                "author": {"name": name, "email": email},
                "committer": {"name": name, "email": email},
            },
        )
        return _created_sha(commit_response, "commit")

    def pull_request(self) -> PullRequestSnapshot:
        value = self._get(f"{self.root}/pulls/{self.pr_number}")
        if not isinstance(value, dict):
            raise GitHubBoundaryError("GitHub pull request evidence is malformed")
        value = cast(dict[str, Any], value)
        try:
            head, base, user = value["head"], value["base"], value["user"]
            head_repository = head.get("repo", {}).get("full_name") if isinstance(head.get("repo"), dict) else None
            sha, base_sha, head_ref, base_ref, author = (
                head["sha"],
                base["sha"],
                head["ref"],
                base["ref"],
                user["login"],
            )
            if not _SHA.fullmatch(sha) or not _SHA.fullmatch(base_sha):
                raise ValueError
            base_reference = self._get(f"{self.root}/git/ref/heads/{quote(str(base_ref), safe='')}")
            if not isinstance(base_reference, dict) or not isinstance(base_reference.get("object"), dict):
                raise TypeError
            base_reference = cast(dict[str, Any], base_reference)
            current_base = base_reference["object"].get("sha")
            if not isinstance(current_base, str) or not _SHA.fullmatch(current_base):
                raise TypeError
            state = str(value["state"])
            mergeable_state = value.get("mergeable_state", "unknown")
            url = value.get("html_url", "")
            if not isinstance(mergeable_state, str) or not isinstance(url, str) or not isinstance(head_repository, str):
                raise TypeError
            return PullRequestSnapshot(
                self.repository,
                self.pr_number,
                state,
                bool(value["draft"]),
                sha.lower(),
                current_base.lower(),
                str(head_ref),
                str(base_ref),
                value.get("mergeable"),
                bool(value.get("merged")),
                state == "closed",
                str(author),
                mergeable_state,
                url,
                head_repository,
            )
        except KeyError, TypeError, ValueError:
            raise GitHubBoundaryError("GitHub pull request evidence is malformed") from None

    def policy(self, base_ref: str) -> RepositoryPolicy:
        encoded = quote(base_ref, safe="")
        effective = self.transport.request("GET", f"{self.root}/rules/branches/{encoded}")
        if effective.status == 200:
            if not isinstance(effective.body, list) or not all(isinstance(rule, dict) for rule in effective.body):
                raise GitHubBoundaryError("GitHub effective branch policy evidence is malformed")
            rules = effective.body
            source = "effective_rules"
        elif effective.status == 404:
            protection = self.transport.request("GET", f"{self.root}/branches/{encoded}/protection")
            if protection.status == 200:
                if not isinstance(protection.body, dict):
                    raise GitHubBoundaryError("GitHub branch protection evidence is malformed")
                rules = _classic_rules(cast(Mapping[str, Any], protection.body))
                source = "branch_protection"
            elif protection.status == 404:
                rules, source = [], "none"
            else:
                raise GitHubBoundaryError("GitHub branch policy evidence is incomplete")
        else:
            raise GitHubBoundaryError("GitHub effective branch policy evidence is incomplete")
        strict, checks, approvals, conversations = _derive_policy(cast(list[Mapping[str, Any]], rules))
        canonical = {
            "strict": strict,
            "update_required": strict,
            "required_checks": sorted(checks),
            "required_approvals": approvals,
            "conversation_resolution": conversations,
            "source": source,
        }
        return RepositoryPolicy(
            strict, strict, tuple(sorted(checks)), approvals, conversations, source, _digest(canonical)
        )

    def human_review(self) -> HumanReviewSnapshot:
        requested_value = self._get(f"{self.root}/pulls/{self.pr_number}/requested_reviewers")
        if not isinstance(requested_value, dict) or not isinstance(requested_value.get("users", []), list):
            raise GitHubBoundaryError("GitHub requested-reviewer evidence is malformed")
        requested_value = cast(dict[str, Any], requested_value)
        requested_names = tuple(
            sorted(
                {
                    str(item.get("login"))
                    for item in requested_value["users"]
                    if isinstance(item, dict) and item.get("login")
                }
            )
        )
        reviews = self.transport.pages(f"{self.root}/pulls/{self.pr_number}/reviews?per_page=100")
        latest: dict[str, str] = {}
        for review in sorted(reviews, key=lambda item: (str(item.get("submitted_at", "")), int(item.get("id", 0)))):
            login = review.get("user", {}).get("login") if isinstance(review.get("user"), dict) else None
            state = str(review.get("state", "")).upper()
            if login and state in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
                if state == "DISMISSED":
                    latest.pop(str(login), None)
                else:
                    latest[str(login)] = state
        if self.graphql is None:
            unresolved, capability = None, "threads_unavailable"
        else:
            try:
                threads = self.graphql.review_threads(self.owner, self.name, self.pr_number)
            except GitHubBoundaryError:
                unresolved, capability = None, "threads_unavailable"
            else:
                unresolved = sum(not bool(thread.get("isResolved")) for thread in threads)
                capability = "available"
        items = tuple(sorted(latest.items()))
        return HumanReviewSnapshot(
            requested_names,
            items,
            tuple(name for name, state in items if state == "APPROVED"),
            tuple(name for name, state in items if state == "CHANGES_REQUESTED"),
            unresolved,
            capability,
        )

    def base_current(self, pull: PullRequestSnapshot) -> bool:
        value = self._get(f"{self.root}/compare/{pull.base}...{pull.head}")
        if not isinstance(value, dict):
            raise GitHubBoundaryError("GitHub base comparison evidence is malformed")
        status, behind = value.get("status"), value.get("behind_by")
        if status not in {"ahead", "behind", "diverged", "identical"} or type(behind) is not int or behind < 0:
            raise GitHubBoundaryError("GitHub base comparison evidence is malformed")
        return behind == 0

    def comments(self) -> tuple[dict[str, Any], ...]:
        return self.transport.pages(f"{self.root}/issues/{self.pr_number}/comments?per_page=100")

    def _object_collection(self, path: str, field: str) -> tuple[dict[str, Any], ...]:
        """Read a GitHub object-wrapped collection with bounded pagination."""
        values: list[dict[str, Any]] = []
        seen: set[str] = set()
        current: str | None = path
        total: int | None = None
        while current is not None:
            if current in seen or len(seen) >= MAX_PAGES:
                raise GitHubBoundaryError("GitHub object pagination is cyclic or exceeds its bound")
            seen.add(current)
            response = self.transport.request("GET", current)
            body = response.body
            if response.status != 200 or not isinstance(body, dict):
                raise GitHubBoundaryError("GitHub object collection is unavailable")
            page = body.get(field)
            count = body.get("total_count")
            if (
                not isinstance(page, list)
                or not all(isinstance(value, dict) for value in page)
                or type(count) is not int
                or count < 0
                or (total is not None and count != total)
            ):
                raise GitHubBoundaryError("GitHub object collection evidence is malformed")
            total = count
            values.extend(cast(list[dict[str, Any]], page))
            current = response.next_path
        if total is None or len(values) != total:
            raise GitHubBoundaryError("GitHub object collection pagination is incomplete")
        return tuple(values)

    def workflow_runs(self, workflow: str, head: str) -> tuple[ActionsRunSnapshot, ...]:
        if not _SHA.fullmatch(head):
            raise ValueError("head must be an exact commit SHA")
        path = quote(workflow, safe="")
        values = self._object_collection(
            f"{self.root}/actions/workflows/{path}/runs?event=pull_request&per_page=100",
            "workflow_runs",
        )
        # Closed historical PRs may be returned with an empty pull_requests
        # projection. They cannot authorize this exact-head operation and must
        # not make otherwise valid current evidence unavailable.
        runs = [_run(value, workflow, self.pr_number) for value in values if value.get("head_sha") == head]
        return tuple(sorted(runs, key=lambda run: (run.attempt, run.id), reverse=True))

    def select_run(self, workflow: str, head: str) -> ActionsRunSnapshot | None:
        runs = self.workflow_runs(workflow, head)
        return runs[0] if runs else None

    def jobs(self, run: ActionsRunSnapshot, required_checks: Sequence[str]) -> ActionsRunSnapshot:
        values = self._object_collection(
            f"{self.root}/actions/runs/{run.id}/attempts/{run.attempt}/jobs?per_page=100",
            "jobs",
        )
        required = set(required_checks)
        jobs = tuple(_job(value, required) for value in values)
        observed = {job.name for job in jobs}
        jobs += tuple(ActionsJobSnapshot(0, name, "completed", "failure", True) for name in sorted(required - observed))
        return ActionsRunSnapshot(run.id, run.head, run.workflow, run.attempt, run.status, run.conclusion, jobs)

    def run_result(self, run: ActionsRunSnapshot) -> dict[str, object]:
        required = tuple(job for job in run.jobs if job.required)
        conclusion = run.conclusion if run.status == "completed" else None
        if run.status == "completed" and any(job.conclusion not in {None, "success", "skipped"} for job in required):
            conclusion = "failure"
        return {
            "run_id": str(run.id),
            "head": run.head,
            "attempt": run.attempt,
            "status": run.status,
            "conclusion": conclusion or "pending",
            "required_jobs": tuple(job.name for job in required),
        }

    def actions_evidence(self, run: ActionsRunSnapshot, required_checks: Sequence[str]) -> ActionsEvidence:
        """Assess current evidence for one exact PR workflow run."""
        run = self.jobs(run, required_checks)
        raw_conclusion = self.run_result(run)["conclusion"]
        if raw_conclusion == "pending":
            conclusion = "in_progress" if run.status == "in_progress" else "queued"
        elif raw_conclusion == "success":
            conclusion = "success"
        elif raw_conclusion == "failure":
            conclusion = "failure"
        else:
            raise GitHubBoundaryError("GitHub Actions conclusion is unsupported")
        failed = tuple(
            sorted(
                ((job.name, job.conclusion) for job in run.jobs if job.required and job.conclusion != "success"),
                key=lambda item: (item[0], item[1] or ""),
            )
        )
        return ActionsEvidence(run, conclusion, failed)

    def failure_logs(self, run: ActionsRunSnapshot, binary: BinaryTransport) -> bytes:
        data = binary.download(f"{self.root}/actions/runs/{run.id}/attempts/{run.attempt}/logs", MAX_LOG_BYTES)
        if len(data) > MAX_LOG_BYTES:
            raise GitHubBoundaryError("GitHub Actions logs exceed their bound")
        return data


def _run(value: Mapping[str, Any], workflow: str, pr_number: int) -> ActionsRunSnapshot:
    expected = workflow.removeprefix(".github/workflows/")
    path = value.get("path")
    pulls = value.get("pull_requests")
    identifier, attempt = value.get("id"), value.get("run_attempt")
    head, event, status, conclusion = (
        value.get("head_sha"),
        value.get("event"),
        value.get("status"),
        value.get("conclusion"),
    )
    valid_pulls = isinstance(pulls, list) and any(
        isinstance(pull, dict) and type(pull.get("number")) is int and pull["number"] == pr_number for pull in pulls
    )
    if (
        type(identifier) is not int
        or identifier <= 0
        or type(attempt) is not int
        or attempt <= 0
        or not isinstance(head, str)
        or not _SHA.fullmatch(head)
        or event != "pull_request"
        or not isinstance(path, str)
        or path.removeprefix(".github/workflows/") != expected
        or not isinstance(status, str)
        or (conclusion is not None and not isinstance(conclusion, str))
        or not valid_pulls
    ):
        raise GitHubBoundaryError("GitHub Actions run evidence is malformed or outside the requested PR workflow")
    return ActionsRunSnapshot(identifier, head.lower(), workflow, attempt, status, conclusion)


def _job(value: Mapping[str, Any], required: set[str]) -> ActionsJobSnapshot:
    identifier, name, status, conclusion = (
        value.get("id"),
        value.get("name"),
        value.get("status"),
        value.get("conclusion"),
    )
    if (
        type(identifier) is not int
        or identifier <= 0
        or not isinstance(name, str)
        or not name
        or not isinstance(status, str)
        or (conclusion is not None and not isinstance(conclusion, str))
    ):
        raise GitHubBoundaryError("GitHub Actions job evidence is malformed")
    return ActionsJobSnapshot(identifier, name, status, conclusion, name in required)


def _classic_rules(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    checks = value.get("required_status_checks")
    review = value.get("required_pull_request_reviews")
    conversations = value.get("required_conversation_resolution")
    if checks is not None and not isinstance(checks, dict):
        raise GitHubBoundaryError("GitHub branch protection status checks are malformed")
    if review is not None and not isinstance(review, dict):
        raise GitHubBoundaryError("GitHub branch protection review policy is malformed")
    if conversations is not None and not isinstance(conversations, dict):
        raise GitHubBoundaryError("GitHub branch protection conversation policy is malformed")
    checks, review, conversations = checks or {}, review or {}, conversations or {}
    strict, contexts = checks.get("strict", False), checks.get("contexts", [])
    count, resolution = review.get("required_approving_review_count", 0), conversations.get("enabled", False)
    if (
        type(strict) is not bool
        or not isinstance(contexts, list)
        or not all(isinstance(context, str) and context for context in contexts)
        or type(count) is not int
        or count < 0
        or type(resolution) is not bool
    ):
        raise GitHubBoundaryError("GitHub branch protection policy is malformed")
    return [
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": strict,
                "required_status_checks": [{"context": context} for context in contexts],
            },
        },
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": count,
                "required_review_thread_resolution": resolution,
            },
        },
    ]


def _derive_policy(rules: Sequence[Mapping[str, Any]]) -> tuple[bool, set[str], int, bool]:
    strict, checks, approvals, conversations = False, set(), 0, False
    for rule in rules:
        if rule.get("type") == "required_status_checks":
            parameters = rule.get("parameters")
            if (
                not isinstance(parameters, dict)
                or type(parameters.get("strict_required_status_checks_policy")) is not bool
            ):
                raise GitHubBoundaryError("GitHub required status policy is malformed")
            required = parameters.get("required_status_checks")
            if not isinstance(required, list):
                raise GitHubBoundaryError("GitHub required checks are malformed")
            strict |= parameters["strict_required_status_checks_policy"]
            for check in required:
                if not isinstance(check, dict) or not isinstance(check.get("context"), str) or not check["context"]:
                    raise GitHubBoundaryError("GitHub required check is malformed")
                checks.add(check["context"])
        if rule.get("type") == "pull_request":
            parameters = rule.get("parameters")
            count = parameters.get("required_approving_review_count") if isinstance(parameters, dict) else None
            resolution = parameters.get("required_review_thread_resolution") if isinstance(parameters, dict) else None
            if type(count) is not int or count < 0 or type(resolution) is not bool:
                raise GitHubBoundaryError("GitHub pull request policy is malformed")
            approvals = max(approvals, count)
            conversations |= resolution
    return strict, checks, approvals, conversations
