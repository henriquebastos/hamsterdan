"""Bounded human-operator tooling for the HBNetwork qualification fixture.

This module deliberately uses the operator's existing ``gh``/git credentials.
It is not imported by the host and no credential value is accepted as input.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

REPOSITORY = "HBNetwork/demo-pr-readiness"
ORG_ID = 108842540
REPOSITORY_ID = 1316665126
DEFAULT_BRANCH = "main"
WORKFLOWS = frozenset({"ci", "rerun-broker"})
APP_SLUG = "hamster-dan"
APP_BOT_LOGIN = f"{APP_SLUG}[bot]"
SCENARIO_PATH = Path(".pr-lab/scenario.json")
BROKER_PATH = Path(".github/workflows/rerun-broker.yml")
OLD_MARKER = "impetus-rerun"
NEW_MARKER = "hamsterdan-rerun"
LEGACY_BROKER_AUTHORIZATION = (
    'contains(fromJSON(\'["OWNER","MEMBER","COLLABORATOR"]\'), github.event.comment.author_association) &&'
)
APP_BROKER_AUTHORIZATION = (
    f"github.event.comment.user.type == 'Bot' &&\n      github.event.comment.user.login == '{APP_BOT_LOGIN}' &&"
)
MARKER_RE = re.compile(
    r"<!-- (?P<identity>hamsterdan-rerun|impetus-rerun) run=(?P<run>[1-9][0-9]*) "
    r"head=(?P<head>[0-9a-f]{40}) operation=(?P<operation>[A-Za-z0-9][A-Za-z0-9._:-]{0,127}) -->"
)
DASHBOARD_RE = re.compile(r"<!-- hamsterdan:dashboard -->")
IMMUTABLE_RE = re.compile(
    r"<!-- hamsterdan:(?P<kind>finding|reminder|readiness) "
    r"operation=(?P<operation>[A-Za-z0-9][A-Za-z0-9._:-]{0,127}) head=(?P<head>[0-9a-f]{40}) -->"
)
AUTHORITY_EXPECTATIONS = (
    "non-draft",
    "strict-stale",
    "conflict",
    "review-requested",
    "changes-requested",
    "required-approval",
    "unresolved-thread",
    "collaboration-clear",
)
AUTHORITY_REVIEW_FACTS = """
query($owner:String!,$repository:String!,$number:Int!) {
  repository(owner:$owner,name:$repository) {
    pullRequest(number:$number) {
      reviewDecision
      reviewThreads(first:100) {
        nodes { id isResolved }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""
Runner = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]


class OperatorError(RuntimeError):
    """A bounded operator failure safe to display."""


def command_runner(command: Sequence[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def _run(runner: Runner, command: Sequence[str], cwd: Path | None = None) -> str:
    result = runner(tuple(command), cwd)
    if result.returncode:
        # Never reproduce provider/command output: it can contain credential-bearing URLs or headers.
        raise OperatorError(f"command failed: {command[0]} {command[1] if len(command) > 1 else ''}".strip())
    return result.stdout.strip()


def _json(runner: Runner, command: Sequence[str], cwd: Path | None = None) -> Any:
    try:
        return json.loads(_run(runner, command, cwd) or "null")
    except json.JSONDecodeError:
        raise OperatorError(f"malformed JSON from {command[0]}") from None


def _api(runner: Runner, path: str) -> Any:
    return _json(runner, ("gh", "api", path))


def broker_status(text: str) -> str:
    old_prefix = "startsWith(github.event.comment.body, '<!-- impetus-rerun ')" in text
    old_regex = r"<!-- impetus-rerun run=" in text
    new_prefix = "startsWith(github.event.comment.body, '<!-- hamsterdan-rerun ')" in text
    new_regex = r"<!-- hamsterdan-rerun run=" in text
    legacy_auth = text.count(LEGACY_BROKER_AUTHORIZATION) == 1
    app_auth = text.count(APP_BROKER_AUTHORIZATION) == 1
    if old_prefix and old_regex and legacy_auth and not new_prefix and not new_regex and not app_auth:
        return "legacy"
    if new_prefix and new_regex and app_auth and not old_prefix and not old_regex and not legacy_auth:
        return "hamsterdan"
    return "malformed"


def _check(name: str, passed: bool, observed: object) -> dict[str, object]:
    return {"name": name, "pass": passed, "observed": observed}


def preflight(runner: Runner = command_runner, *, health_url: str | None = None) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    auth = runner(("gh", "auth", "status"), None)
    checks.append(_check("gh_auth", auth.returncode == 0, "authenticated" if auth.returncode == 0 else "unavailable"))
    try:
        org = _api(runner, "/orgs/HBNetwork")
        repo = _api(runner, f"/repos/{REPOSITORY}")
        workflows = _api(runner, f"/repos/{REPOSITORY}/actions/workflows?per_page=100")
        broker = _run(
            runner,
            (
                "gh",
                "api",
                f"/repos/{REPOSITORY}/contents/{BROKER_PATH}?ref={DEFAULT_BRANCH}",
                "-H",
                "Accept: application/vnd.github.raw+json",
            ),
        )
        names = {item.get("name") for item in workflows.get("workflows", []) if isinstance(item, dict)}
        checks.extend(
            (
                _check("organization_identity", org.get("id") == ORG_ID, org.get("id")),
                _check("repository_identity", repo.get("id") == REPOSITORY_ID, repo.get("id")),
                _check("repository_public", repo.get("private") is False, not bool(repo.get("private", True))),
                _check("default_branch", repo.get("default_branch") == DEFAULT_BRANCH, repo.get("default_branch")),
                _check(
                    "required_workflows", WORKFLOWS <= names, sorted(name for name in names if isinstance(name, str))
                ),
                _check("default_broker", broker_status(broker) in {"legacy", "hamsterdan"}, broker_status(broker)),
            )
        )
    except OperatorError as error:
        checks.append(_check("provider_inventory", False, str(error)))
    if health_url:
        url = health_url.rstrip("/") + "/healthz"
        result = runner(("curl", "--fail", "--silent", "--show-error", "--max-time", "10", url), None)
        healthy = False
        if result.returncode == 0:
            try:
                value = json.loads(result.stdout)
                healthy = isinstance(value, dict)
            except json.JSONDecodeError:
                pass
        checks.append(_check("app_host_health", healthy, "healthy" if healthy else "unavailable"))
    return {"command": "preflight", "ok": all(bool(item["pass"]) for item in checks), "checks": checks}


def scenario_value(scenario: str) -> dict[str, object]:
    behavior: dict[str, str] = {"kind": "pass"}
    if scenario == "first-attempt-flake":
        behavior = {"kind": "first_attempt_flake", "fingerprint": "hamsterdan:first-attempt-flake:v1"}
    elif scenario != "clean-green":
        raise OperatorError("unsupported scenario")
    return {
        "schema_version": 1,
        "scenario": scenario,
        "behavior": behavior,
        "review_lenses": ["correctness", "test-quality", "risk"],
    }


def _clone(runner: Runner, root: Path) -> Path:
    checkout = root / "demo-pr-readiness"
    _run(runner, ("git", "clone", "--origin", "origin", f"https://github.com/{REPOSITORY}.git", str(checkout)))
    _run(runner, ("git", "fetch", "origin", DEFAULT_BRANCH), checkout)
    return checkout


def _assert_only(runner: Runner, checkout: Path, admitted: set[str]) -> None:
    changed = set(_run(runner, ("git", "diff", "--name-only", "origin/main...HEAD"), checkout).splitlines())
    if changed != admitted:
        raise OperatorError(f"refusing unexpected changed paths: {sorted(changed)}")


def create(scenario: str, runner: Runner = command_runner) -> dict[str, object]:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    branch = f"hamsterdan/{scenario}-{stamp}"
    title = f"Hamsterdan demo: {scenario}"
    with tempfile.TemporaryDirectory(prefix="hamsterdan-operator-") as temporary:
        checkout = _clone(runner, Path(temporary))
        _run(runner, ("git", "switch", "--create", branch, "origin/main"), checkout)
        (checkout / SCENARIO_PATH).write_text(json.dumps(scenario_value(scenario), indent=2) + "\n", encoding="utf-8")
        _run(runner, ("python", "tools/scenario_control.py", "--attempt", "2"), checkout)
        _run(runner, ("git", "add", "--", str(SCENARIO_PATH)), checkout)
        _run(runner, ("git", "commit", "-m", title), checkout)
        _assert_only(runner, checkout, {str(SCENARIO_PATH)})
        _run(runner, ("git", "push", "--set-upstream", "origin", branch), checkout)
        _run(
            runner,
            (
                "gh",
                "pr",
                "create",
                "--repo",
                REPOSITORY,
                "--base",
                DEFAULT_BRANCH,
                "--head",
                branch,
                "--title",
                title,
                "--body",
                "Controlled Hamsterdan qualification scenario. Do not merge automatically.",
            ),
            checkout,
        )
        pr = _json(
            runner, ("gh", "pr", "view", branch, "--repo", REPOSITORY, "--json", "number,url,headRefName"), checkout
        )
        head = _run(runner, ("git", "rev-parse", "HEAD"), checkout)
    return {"command": "create", "ok": True, "number": pr["number"], "url": pr["url"], "head": head, "branch": branch}


def prepare_broker(runner: Runner = command_runner) -> dict[str, object]:
    prepared = _json(
        runner,
        (
            "gh",
            "pr",
            "list",
            "--repo",
            REPOSITORY,
            "--state",
            "open",
            "--search",
            "in:title Hamsterdan broker identity cutover",
            "--json",
            "number,url,headRefName",
            "--limit",
            "10",
        ),
    )
    matching = [item for item in prepared if str(item.get("headRefName", "")).startswith("hamsterdan/broker-cutover-")]
    if matching:
        item = matching[0]
        return {
            "command": "prepare-broker",
            "ok": True,
            "status": "prepared",
            "changed": False,
            "number": item["number"],
            "url": item["url"],
            "branch": item["headRefName"],
        }
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    branch = f"hamsterdan/broker-cutover-{stamp}"
    with tempfile.TemporaryDirectory(prefix="hamsterdan-broker-") as temporary:
        checkout = _clone(runner, Path(temporary))
        source = (checkout / BROKER_PATH).read_text(encoding="utf-8")
        state = broker_status(source)
        if state == "hamsterdan":
            return {"command": "prepare-broker", "ok": True, "status": "current", "changed": False}
        if state != "legacy" or source.count(OLD_MARKER) != 2 or source.count(LEGACY_BROKER_AUTHORIZATION) != 1:
            raise OperatorError("default broker is malformed; refusing automated preparation")
        _run(runner, ("git", "switch", "--create", branch, "origin/main"), checkout)
        target = source.replace(OLD_MARKER, NEW_MARKER).replace(LEGACY_BROKER_AUTHORIZATION, APP_BROKER_AUTHORIZATION)
        if (
            broker_status(target) != "hamsterdan"
            or target.count(NEW_MARKER) != 2
            or target.count(APP_BROKER_AUTHORIZATION) != 1
        ):
            raise OperatorError("broker transformation did not produce strict Hamsterdan grammar")
        (checkout / BROKER_PATH).write_text(target, encoding="utf-8")
        _run(runner, ("git", "add", "--", str(BROKER_PATH)), checkout)
        _run(runner, ("git", "commit", "-m", "Hamsterdan broker identity cutover"), checkout)
        _assert_only(runner, checkout, {str(BROKER_PATH)})
        _run(runner, ("git", "push", "--set-upstream", "origin", branch), checkout)
        _run(
            runner,
            (
                "gh",
                "pr",
                "create",
                "--repo",
                REPOSITORY,
                "--base",
                DEFAULT_BRANCH,
                "--head",
                branch,
                "--title",
                "Hamsterdan broker identity cutover",
                "--body",
                "Merge only after the Hamsterdan App host is ready; never run legacy and App writers together.",
            ),
            checkout,
        )
        pr = _json(
            runner, ("gh", "pr", "view", branch, "--repo", REPOSITORY, "--json", "number,url,headRefName"), checkout
        )
    return {
        "command": "prepare-broker",
        "ok": True,
        "status": "prepared",
        "changed": True,
        "number": pr["number"],
        "url": pr["url"],
        "branch": branch,
    }


def _safe_comment(comment: dict[str, Any], bot_login: str) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    body, owner = str(comment.get("body", "")), str(comment.get("user", {}).get("login", ""))
    url, identifier = comment.get("html_url"), comment.get("id")
    markers: list[dict[str, object]] = []
    kind: str | None = None
    if DASHBOARD_RE.search(body):
        kind = "dashboard"
    immutable = IMMUTABLE_RE.search(body)
    if immutable:
        kind = immutable.group("kind")
        markers.append(
            {
                "type": kind,
                "operation": immutable.group("operation"),
                "head": immutable.group("head"),
                "comment_id": identifier,
                "url": url,
                "owner": owner,
            }
        )
    for marker in MARKER_RE.finditer(body):
        marker_kind = marker.group("identity")
        markers.append(
            {
                "type": marker_kind,
                "run_id": int(marker.group("run")),
                "head": marker.group("head"),
                "operation": marker.group("operation"),
                "comment_id": identifier,
                "url": url,
                "owner": owner,
            }
        )
        if marker_kind == NEW_MARKER:
            kind = NEW_MARKER
    if kind:
        return {
            "id": identifier,
            "url": url,
            "owner": owner,
            "type": kind,
            "owned_by_app": owner.casefold() == bot_login.casefold(),
        }, markers
    return None, markers


def inspect(pr_number: int, runner: Runner = command_runner, *, bot_login: str = APP_BOT_LOGIN) -> dict[str, object]:
    if pr_number < 1:
        raise OperatorError("PR number must be positive")
    pull = _api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}")
    comments = _api(runner, f"/repos/{REPOSITORY}/issues/{pr_number}/comments?per_page=100")
    head = str(pull.get("head", {}).get("sha", ""))
    commit = _api(runner, f"/repos/{REPOSITORY}/commits/{head}")
    runs_value = _api(runner, f"/repos/{REPOSITORY}/actions/runs?event=pull_request&head_sha={head}&per_page=100")
    safe_comments: list[dict[str, object]] = []
    markers: list[dict[str, object]] = []
    for comment in comments[:100] if isinstance(comments, list) else []:
        safe, found = _safe_comment(comment, bot_login)
        if safe:
            safe_comments.append(safe)
        markers.extend(found)
    runs: list[dict[str, object]] = []
    for item in runs_value.get("workflow_runs", [])[:20]:
        attempt = int(item.get("run_attempt", 1))
        jobs_value = _api(runner, f"/repos/{REPOSITORY}/actions/runs/{item['id']}/attempts/{attempt}/jobs?per_page=100")
        runs.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "attempt": attempt,
                "head": item.get("head_sha"),
                "status": item.get("status"),
                "conclusion": item.get("conclusion"),
                "url": item.get("html_url"),
                "jobs": [
                    {
                        "id": job.get("id"),
                        "name": job.get("name"),
                        "status": job.get("status"),
                        "conclusion": job.get("conclusion"),
                    }
                    for job in jobs_value.get("jobs", [])[:100]
                ],
            }
        )
    new_markers = [item for item in markers if item["type"] == NEW_MARKER]
    old_markers = [item for item in markers if item["type"] == OLD_MARKER]
    owned = bool(safe_comments) and all(item["owned_by_app"] for item in safe_comments)
    marker_owned = all(str(item.get("owner", "")).casefold() == bot_login.casefold() for item in new_markers)
    kinds = {str(item["type"]) for item in safe_comments if item["owned_by_app"]}
    checks = [
        _check(
            "pull_identity",
            pull.get("base", {}).get("repo", {}).get("id") == REPOSITORY_ID,
            pull.get("base", {}).get("repo", {}).get("id"),
        ),
        _check("hamsterdan_comment_ownership", owned and marker_owned, bot_login),
        _check("dashboard_present", "dashboard" in kinds, "dashboard" in kinds),
        _check("readiness_advisory_present", "readiness" in kinds, "readiness" in kinds),
        _check("legacy_markers_absent", not old_markers, len(old_markers)),
        _check("workflow_heads_match", all(run["head"] == head for run in runs), head),
    ]
    authored = commit.get("commit", {})
    result = {
        "command": "inspect",
        "repository": REPOSITORY,
        "number": pr_number,
        "pull": {
            "url": pull.get("html_url"),
            "state": pull.get("state"),
            "draft": pull.get("draft"),
            "head": head,
            "head_ref": pull.get("head", {}).get("ref"),
            "base_ref": pull.get("base", {}).get("ref"),
        },
        "comments": safe_comments[:100],
        "markers": markers[:100],
        "runs": runs,
        "attribution": {
            "commit_author": authored.get("author"),
            "commit_committer": authored.get("committer"),
            "authenticated_author": commit.get("author", {}).get("login")
            if isinstance(commit.get("author"), dict)
            else None,
            "authenticated_committer": commit.get("committer", {}).get("login")
            if isinstance(commit.get("committer"), dict)
            else None,
        },
        "checks": checks,
    }
    result["ok"] = all(bool(item["pass"]) for item in checks)
    return result


def _authority_policy(rules: object) -> tuple[bool, int, bool]:
    if not isinstance(rules, list) or not all(isinstance(rule, dict) for rule in rules):
        raise OperatorError("GitHub authority policy evidence is malformed")
    if len(rules) >= 100:
        raise OperatorError("GitHub authority policy exceeds one bounded page")
    strict, approvals, resolution = False, 0, False
    for rule in cast(list[dict[str, Any]], rules):
        if rule.get("type") == "required_status_checks":
            parameters = rule.get("parameters")
            if (
                not isinstance(parameters, dict)
                or type(parameters.get("strict_required_status_checks_policy")) is not bool
                or not isinstance(parameters.get("required_status_checks"), list)
            ):
                raise OperatorError("GitHub authority policy evidence is malformed")
            strict |= parameters["strict_required_status_checks_policy"]
            for check in parameters["required_status_checks"]:
                if not isinstance(check, dict) or not isinstance(check.get("context"), str) or not check["context"]:
                    raise OperatorError("GitHub authority policy evidence is malformed")
        elif rule.get("type") == "pull_request":
            parameters = rule.get("parameters")
            count = parameters.get("required_approving_review_count") if isinstance(parameters, dict) else None
            conversations = (
                parameters.get("required_review_thread_resolution") if isinstance(parameters, dict) else None
            )
            if type(count) is not int or count < 0 or type(conversations) is not bool:
                raise OperatorError("GitHub authority policy evidence is malformed")
            approvals = max(approvals, count)
            resolution |= conversations
    return strict, approvals, resolution


def _latest_reviews(value: object) -> dict[str, str]:
    if not isinstance(value, list) or not all(isinstance(review, dict) for review in value):
        raise OperatorError("GitHub review authority evidence is malformed")
    if len(value) >= 100:
        raise OperatorError("GitHub review authority exceeds one bounded page")
    latest: dict[str, tuple[str, str, str, int]] = {}
    for review in cast(list[dict[str, Any]], value):
        user = review.get("user")
        login = user.get("login") if isinstance(user, dict) else None
        state, submitted, identifier = review.get("state"), review.get("submitted_at"), review.get("id")
        if (
            not isinstance(login, str)
            or not login
            or not isinstance(state, str)
            or not isinstance(submitted, str)
            or type(identifier) is not int
        ):
            raise OperatorError("GitHub review authority evidence is malformed")
        normalized = state.upper()
        if normalized not in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            continue
        key = login.casefold()
        if key not in latest or (submitted, identifier) > latest[key][2:]:
            latest[key] = (login, normalized, submitted, identifier)
    return {
        login: state
        for login, state, _, _ in sorted(latest.values(), key=lambda item: item[0].casefold())
        if state != "DISMISSED"
    }


def _review_facts(pr_number: int, runner: Runner) -> tuple[int, str | None]:
    owner, repository = REPOSITORY.split("/", 1)
    value = _json(
        runner,
        (
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={AUTHORITY_REVIEW_FACTS}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repository={repository}",
            "-F",
            f"number={pr_number}",
        ),
    )
    try:
        pull = value["data"]["repository"]["pullRequest"]
        decision = pull["reviewDecision"]
        threads = pull["reviewThreads"]
        nodes, page = threads["nodes"], threads["pageInfo"]
    except KeyError, TypeError:
        raise OperatorError("GitHub review-thread authority evidence is malformed") from None
    if (
        not isinstance(nodes, list)
        or not all(
            isinstance(node, dict) and isinstance(node.get("id"), str) and type(node.get("isResolved")) is bool
            for node in nodes
        )
        or not isinstance(page, dict)
        or type(page.get("hasNextPage")) is not bool
        or decision not in {None, "APPROVED", "CHANGES_REQUESTED", "REVIEW_REQUIRED"}
    ):
        raise OperatorError("GitHub review-thread authority evidence is malformed")
    if page["hasNextPage"]:
        raise OperatorError("GitHub review-thread authority exceeds one bounded page")
    return sum(not node["isResolved"] for node in nodes), decision


def inspect_authority(pr_number: int, expected: str, runner: Runner = command_runner) -> dict[str, object]:
    """Inspect real GitHub authority without copying provider objects into the Net."""
    if pr_number < 1:
        raise OperatorError("PR number must be positive")
    if expected not in AUTHORITY_EXPECTATIONS:
        raise OperatorError("unsupported authority expectation")
    pull = _api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}")
    if not isinstance(pull, dict):
        raise OperatorError("GitHub pull-request authority evidence is malformed")
    try:
        head, base_value = pull["head"], pull["base"]
        head_sha, base_ref = head["sha"], base_value["ref"]
        author = pull["user"]["login"]
        if (
            not isinstance(head_sha, str)
            or not re.fullmatch(r"[0-9a-fA-F]{40}", head_sha)
            or not isinstance(base_ref, str)
            or not base_ref
            or not isinstance(author, str)
            or not author
        ):
            raise TypeError
    except KeyError, TypeError:
        raise OperatorError("GitHub pull-request authority evidence is malformed") from None
    encoded_base = quote(base_ref, safe="")
    reference = _api(runner, f"/repos/{REPOSITORY}/git/ref/heads/{encoded_base}")
    try:
        base_sha = reference["object"]["sha"]
    except KeyError, TypeError:
        raise OperatorError("GitHub base authority evidence is malformed") from None
    if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", base_sha):
        raise OperatorError("GitHub base authority evidence is malformed")
    comparison = _api(runner, f"/repos/{REPOSITORY}/compare/{base_sha}...{head_sha}")
    behind = comparison.get("behind_by") if isinstance(comparison, dict) else None
    if type(behind) is not int or behind < 0:
        raise OperatorError("GitHub comparison authority evidence is malformed")
    strict, required, resolution = _authority_policy(
        _api(runner, f"/repos/{REPOSITORY}/rules/branches/{encoded_base}?per_page=100")
    )
    requested_value = _api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}/requested_reviewers")
    requested_users = requested_value.get("users") if isinstance(requested_value, dict) else None
    requested_teams = requested_value.get("teams") if isinstance(requested_value, dict) else None
    if (
        not isinstance(requested_users, list)
        or not all(isinstance(user, dict) for user in requested_users)
        or not isinstance(requested_teams, list)
        or not all(isinstance(team, dict) for team in requested_teams)
    ):
        raise OperatorError("GitHub requested-reviewer authority evidence is malformed")
    requested = sorted(
        str(user["login"]) for user in requested_users if isinstance(user.get("login"), str) and user["login"]
    )
    teams = sorted(str(team["slug"]) for team in requested_teams if isinstance(team.get("slug"), str) and team["slug"])
    reviews = _latest_reviews(_api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}/reviews?per_page=100"))
    approvals = sorted(
        login for login, state in reviews.items() if state == "APPROVED" and login.casefold() != author.casefold()
    )
    changes = sorted(login for login, state in reviews.items() if state == "CHANGES_REQUESTED")
    unresolved, review_decision = _review_facts(pr_number, runner)
    mergeable, mergeable_state, draft = pull.get("mergeable"), pull.get("mergeable_state"), pull.get("draft")
    if mergeable not in {True, False, None} or not isinstance(mergeable_state, str) or type(draft) is not bool:
        raise OperatorError("GitHub mergeability authority evidence is malformed")
    if mergeable is None:
        raise OperatorError("GitHub mergeability authority is indeterminate; retry inspection")
    final_pull = _api(runner, f"/repos/{REPOSITORY}/pulls/{pr_number}")
    final_reference = _api(runner, f"/repos/{REPOSITORY}/git/ref/heads/{encoded_base}")
    try:
        final_basis = (
            final_pull["head"]["sha"],
            final_pull["base"]["ref"],
            final_reference["object"]["sha"],
        )
    except KeyError, TypeError:
        raise OperatorError("GitHub final authority basis is malformed") from None
    if final_basis != (head_sha, base_ref, base_sha):
        raise OperatorError("GitHub authority changed during inspection")
    authority = {
        "draft": draft,
        "head": head_sha.lower(),
        "base": base_sha.lower(),
        "base_ref": base_ref,
        "behind_by": behind,
        "mergeable": mergeable,
        "mergeable_state": mergeable_state,
        "strict_base": strict,
        "required_approvals": required,
        "conversation_resolution": resolution,
        "requested_reviewers": requested,
        "requested_teams": teams,
        "latest_reviews": [{"reviewer": login, "state": state} for login, state in sorted(reviews.items())],
        "distinct_approvals": approvals,
        "changes_requested": changes,
        "unresolved_threads": unresolved,
        "review_decision": review_decision,
    }
    expectations = {
        "non-draft": not draft,
        "strict-stale": not draft and strict and behind > 0 and mergeable is True,
        "conflict": not draft and (mergeable is False or mergeable_state == "dirty"),
        "review-requested": bool(requested or teams),
        "changes-requested": bool(changes),
        "required-approval": required > 0 and review_decision == "APPROVED",
        "unresolved-thread": resolution and unresolved > 0,
        "collaboration-clear": (
            not requested
            and not teams
            and not changes
            and (required == 0 or review_decision == "APPROVED")
            and unresolved == 0
        ),
    }
    check = _check(expected, expectations[expected], authority)
    return {
        "command": "inspect-authority",
        "repository": REPOSITORY,
        "number": pr_number,
        "url": pull.get("html_url"),
        "expectation": expected,
        "authority": authority,
        "checks": [check],
        "ok": check["pass"],
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="python -m hamsterdan.operator")
    commands = value.add_subparsers(dest="command", required=True)
    pre = commands.add_parser("preflight")
    pre.add_argument("--health-url")
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--scenario", choices=("clean-green", "first-attempt-flake"), required=True)
    commands.add_parser("prepare-broker")
    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--pr", type=int, required=True)
    inspect_parser.add_argument("--bot-login", default=APP_BOT_LOGIN)
    authority_parser = commands.add_parser("inspect-authority")
    authority_parser.add_argument("--pr", type=int, required=True)
    authority_parser.add_argument("--expect", choices=AUTHORITY_EXPECTATIONS, required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "preflight":
            output = preflight(health_url=args.health_url)
        elif args.command == "create":
            output = create(args.scenario)
        elif args.command == "prepare-broker":
            output = prepare_broker()
        elif args.command == "inspect":
            output = inspect(args.pr, bot_login=args.bot_login)
        else:
            output = inspect_authority(args.pr, args.expect)
    except OperatorError as error:
        output = {"command": args.command, "ok": False, "error": str(error)}
    print(json.dumps(output, sort_keys=True))
    return 0 if output.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
