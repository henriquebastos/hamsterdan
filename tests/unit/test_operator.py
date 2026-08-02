from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from hamsterdan import operator
from hamsterdan.github_app.gateway import _derive_policy


def completed(value: object = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    stdout = value if isinstance(value, str) else json.dumps(value)
    return subprocess.CompletedProcess((), returncode, stdout, "sensitive stderr must never be emitted")


class FakeRunner:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []

    def __call__(self, command: Any, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        call = tuple(command)
        self.calls.append((call, cwd))
        key = call[2] if call[:2] == ("gh", "api") else " ".join(call)
        value = self.responses.get(key)
        if isinstance(value, subprocess.CompletedProcess):
            return value
        if value is None:
            raise AssertionError(f"unexpected command: {call}")
        return completed(value)


LEGACY = """contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.comment.author_association) &&
startsWith(github.event.comment.body, '<!-- impetus-rerun ')
marker = re.fullmatch(r\"<!-- impetus-rerun run=([1-9][0-9]*) head=x operation=x -->\", body)
"""
CURRENT = LEGACY.replace("impetus-rerun", "hamsterdan-rerun").replace(
    operator.LEGACY_BROKER_AUTHORIZATION, operator.APP_BROKER_AUTHORIZATION
)


@pytest.mark.parametrize(("value", "expected"), [(LEGACY, "legacy"), (CURRENT, "hamsterdan"), ("x", "malformed")])
def test_broker_status_requires_prefix_and_regex(value: str, expected: str) -> None:
    assert operator.broker_status(value) == expected


def test_broker_cutover_replaces_human_association_with_exact_app_bot() -> None:
    assert operator.broker_status(CURRENT) == "hamsterdan"
    assert "author_association" not in CURRENT
    assert "github.event.comment.user.type == 'Bot'" in CURRENT
    assert "github.event.comment.user.login == 'hamster-dan[bot]'" in CURRENT


def test_scenarios_are_the_fixture_closed_schema() -> None:
    clean = operator.scenario_value("clean-green")
    flake = operator.scenario_value("first-attempt-flake")
    assert set(clean) == {"schema_version", "scenario", "behavior", "review_lenses"}
    assert clean["behavior"] == {"kind": "pass"}
    assert flake["behavior"] == {
        "kind": "first_attempt_flake",
        "fingerprint": "scenario:first-attempt-flake:v1",
    }
    assert clean["review_lenses"] == ["correctness", "test-quality", "risk"]


def test_preflight_exact_inventory_and_legacy_status_pass() -> None:
    fake = FakeRunner(
        {
            "gh auth status": "",
            "/orgs/HBNetwork": {"id": operator.ORG_ID},
            f"/repos/{operator.REPOSITORY}": {
                "id": operator.REPOSITORY_ID,
                "private": False,
                "default_branch": "main",
            },
            f"/repos/{operator.REPOSITORY}/actions/workflows?per_page=100": {
                "workflows": [{"name": "ci"}, {"name": "rerun-broker"}]
            },
            f"/repos/{operator.REPOSITORY}/contents/{operator.BROKER_PATH}?ref=main": LEGACY,
        }
    )
    result = operator.preflight(fake)
    assert result["ok"] is True
    assert next(item for item in result["checks"] if item["name"] == "default_broker")["observed"] == "legacy"
    assert all("token" not in json.dumps(item).casefold() for item in result["checks"])


def test_preflight_malformed_broker_and_wrong_repository_fail() -> None:
    fake = FakeRunner(
        {
            "gh auth status": "",
            "/orgs/HBNetwork": {"id": operator.ORG_ID},
            f"/repos/{operator.REPOSITORY}": {"id": 1, "private": False, "default_branch": "main"},
            f"/repos/{operator.REPOSITORY}/actions/workflows?per_page=100": {
                "workflows": [{"name": "ci"}, {"name": "rerun-broker"}]
            },
            f"/repos/{operator.REPOSITORY}/contents/{operator.BROKER_PATH}?ref=main": "mixed",
        }
    )
    result = operator.preflight(fake)
    assert result["ok"] is False
    assert {item["name"] for item in result["checks"] if not item["pass"]} == {"repository_identity", "default_broker"}


def test_prepared_broker_is_detected_without_clone_or_mutation() -> None:
    fake = FakeRunner(
        {
            "gh pr list --repo HBNetwork/demo-pr-readiness --state open --search in:title Hamsterdan broker identity cutover --json number,url,headRefName --limit 10": [
                {"number": 9, "url": "https://github.test/pr/9", "headRefName": "hamsterdan/broker-cutover-1"}
            ]
        }
    )
    result = operator.prepare_broker(fake)
    assert result["status"] == "prepared" and result["changed"] is False
    assert len(fake.calls) == 1


def test_operator_mutation_commands_contain_no_force_merge_or_bypass() -> None:
    source = Path(operator.__file__).read_text(encoding="utf-8")
    assert '"--force"' not in source
    assert '"merge"' not in source
    assert '"--admin"' not in source
    assert "_assert_only(runner, checkout, {str(SCENARIO_PATH)})" in source
    assert "_assert_only(runner, checkout, {str(BROKER_PATH)})" in source


def inspection_runner(owner: str = operator.APP_BOT_LOGIN) -> FakeRunner:
    head = "a" * 40
    marker = f"<!-- hamsterdan-rerun run=5 head={head} operation=rerun:1 -->"
    readiness = f"<!-- hamsterdan:readiness operation=readiness:1 head={head} -->"
    return FakeRunner(
        {
            f"/repos/{operator.REPOSITORY}/pulls/7": {
                "html_url": "https://github.test/pr/7",
                "state": "open",
                "draft": False,
                "head": {"sha": head, "ref": "hamsterdan/demo"},
                "base": {"ref": "main", "repo": {"id": operator.REPOSITORY_ID}},
            },
            f"/repos/{operator.REPOSITORY}/issues/7/comments?per_page=100": [
                {
                    "id": 3,
                    "html_url": "https://github.test/comments/3",
                    "body": f"SECRET PROSE\n{marker}",
                    "user": {"login": owner},
                },
                {
                    "id": 6,
                    "html_url": "https://github.test/comments/6",
                    "body": "dashboard prose\n<!-- hamsterdan:dashboard -->",
                    "user": {"login": owner},
                },
                {
                    "id": 7,
                    "html_url": "https://github.test/comments/7",
                    "body": f"readiness prose\n{readiness}",
                    "user": {"login": owner},
                },
                {
                    "id": 4,
                    "html_url": "https://github.test/comments/4",
                    "body": "private unrelated prose",
                    "user": {"login": "human"},
                },
                {
                    "id": 5,
                    "html_url": "https://github.test/comments/5",
                    "body": f"<!-- impetus-rerun run=4 head={head} operation=old -->",
                    "user": {"login": "human"},
                },
            ],
            f"/repos/{operator.REPOSITORY}/commits/{head}": {
                "commit": {"author": {"name": "Explicit Author"}, "committer": {"name": "Explicit Committer"}},
                "author": {"login": "human"},
                "committer": {"login": operator.APP_BOT_LOGIN},
            },
            f"/repos/{operator.REPOSITORY}/actions/runs?event=pull_request&head_sha={head}&per_page=100": {
                "workflow_runs": [
                    {
                        "id": 5,
                        "name": "ci",
                        "run_attempt": 2,
                        "head_sha": head,
                        "status": "completed",
                        "conclusion": "success",
                        "html_url": "https://github.test/runs/5",
                    }
                ]
            },
            f"/repos/{operator.REPOSITORY}/actions/runs/5/attempts/2/jobs?per_page=100": {
                "jobs": [{"id": 6, "name": "unit", "status": "completed", "conclusion": "success"}]
            },
        }
    )


def test_inspection_redacts_prose_separates_attribution_and_rejects_old_identity() -> None:
    result = operator.inspect(7, inspection_runner())
    encoded = json.dumps(result)
    assert result["ok"] is False
    assert all(
        prose not in encoded
        for prose in ("SECRET PROSE", "dashboard prose", "readiness prose", "private unrelated prose")
    )
    assert result["attribution"] == {
        "commit_author": {"name": "Explicit Author"},
        "commit_committer": {"name": "Explicit Committer"},
        "authenticated_author": "human",
        "authenticated_committer": operator.APP_BOT_LOGIN,
    }
    marker_types = [item["type"] for item in result["markers"]]
    assert marker_types == ["hamsterdan-rerun", "readiness", "impetus-rerun"]
    old_check = next(item for item in result["checks"] if item["name"] == "legacy_markers_absent")
    assert old_check == {"name": "legacy_markers_absent", "pass": False, "observed": 1}
    assert next(item for item in result["checks"] if item["name"] == "dashboard_present")["pass"] is True
    assert next(item for item in result["checks"] if item["name"] == "readiness_advisory_present")["pass"] is True


def test_inspection_fails_when_human_owns_hamsterdan_marker() -> None:
    result = operator.inspect(7, inspection_runner("human"))
    assert result["ok"] is False
    ownership = next(item for item in result["checks"] if item["name"] == "hamsterdan_comment_ownership")
    assert ownership["pass"] is False


def test_inspection_accepts_complete_fresh_hamsterdan_evidence() -> None:
    fake = inspection_runner()
    comments = fake.responses[f"/repos/{operator.REPOSITORY}/issues/7/comments?per_page=100"]
    assert isinstance(comments, list)
    fake.responses[f"/repos/{operator.REPOSITORY}/issues/7/comments?per_page=100"] = comments[:-1]
    result = operator.inspect(7, fake)
    assert result["ok"] is True
    assert all(item["pass"] for item in result["checks"])


def authority_runner() -> FakeRunner:
    head, base, old_base = "a" * 40, "b" * 40, "c" * 40
    return FakeRunner(
        {
            f"/repos/{operator.REPOSITORY}/pulls/9": {
                "html_url": "https://github.test/pr/9",
                "state": "open",
                "draft": False,
                "user": {"login": "Author"},
                "head": {"sha": head, "ref": "authority/collaboration", "repo": {"id": operator.REPOSITORY_ID}},
                "base": {"sha": old_base, "ref": "authority-base", "repo": {"id": operator.REPOSITORY_ID}},
                "mergeable": True,
                "mergeable_state": "clean",
            },
            f"/repos/{operator.REPOSITORY}/git/ref/heads/authority-base": {"object": {"sha": base}},
            f"/repos/{operator.REPOSITORY}/compare/{base}...{head}": {
                "status": "behind",
                "ahead_by": 1,
                "behind_by": 1,
            },
            f"/repos/{operator.REPOSITORY}/rules/branches/authority-base?per_page=100": [
                {
                    "type": "pull_request",
                    "parameters": {
                        "required_approving_review_count": 1,
                        "required_review_thread_resolution": True,
                    },
                },
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [{"context": "unit"}],
                    },
                },
            ],
            f"/repos/{operator.REPOSITORY}/pulls/9/requested_reviewers": {
                "users": [{"login": "Reviewer"}],
                "teams": [],
            },
            f"/repos/{operator.REPOSITORY}/pulls/9/reviews?per_page=100": [
                {
                    "id": 1,
                    "submitted_at": "2026-08-02T01:00:00Z",
                    "state": "APPROVED",
                    "user": {"login": "author"},
                },
                {
                    "id": 2,
                    "submitted_at": "2026-08-02T02:00:00Z",
                    "state": "CHANGES_REQUESTED",
                    "user": {"login": "Reviewer"},
                },
            ],
            "graphql": {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewDecision": "CHANGES_REQUESTED",
                            "reviewThreads": {
                                "nodes": [{"id": "thread-1", "isResolved": False}],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            },
                        }
                    }
                }
            },
        }
    )


@pytest.mark.parametrize(
    "expected",
    ("non-draft", "strict-stale", "review-requested", "changes-requested", "unresolved-thread"),
)
def test_authority_inspection_asserts_real_provider_facts_without_prose(expected: str) -> None:
    result = operator.inspect_authority(9, expected, authority_runner())

    assert result["ok"] is True
    assert result["authority"] == {
        "draft": False,
        "head": "a" * 40,
        "base": "b" * 40,
        "base_ref": "authority-base",
        "behind_by": 1,
        "mergeable": True,
        "mergeable_state": "clean",
        "strict_base": True,
        "required_approvals": 1,
        "conversation_resolution": True,
        "requested_reviewers": ["Reviewer"],
        "requested_teams": [],
        "latest_reviews": [
            {"reviewer": "Reviewer", "state": "CHANGES_REQUESTED"},
            {"reviewer": "author", "state": "APPROVED"},
        ],
        "distinct_approvals": [],
        "changes_requested": ["Reviewer"],
        "unresolved_threads": 1,
        "review_decision": "CHANGES_REQUESTED",
    }
    assert "submitted_at" not in json.dumps(result)
    assert "thread-1" not in json.dumps(result)


def test_authority_inspection_distinguishes_approval_and_conflict() -> None:
    approved = authority_runner()
    reviews = approved.responses[f"/repos/{operator.REPOSITORY}/pulls/9/reviews?per_page=100"]
    assert isinstance(reviews, list)
    reviews[-1] = reviews[-1] | {"state": "APPROVED"}
    graphql = approved.responses["graphql"]
    assert isinstance(graphql, dict)
    graphql["data"]["repository"]["pullRequest"]["reviewDecision"] = "APPROVED"
    assert operator.inspect_authority(9, "required-approval", approved)["ok"] is True

    conflict = authority_runner()
    pull = conflict.responses[f"/repos/{operator.REPOSITORY}/pulls/9"]
    assert isinstance(pull, dict)
    conflict.responses[f"/repos/{operator.REPOSITORY}/pulls/9"] = pull | {
        "mergeable": False,
        "mergeable_state": "dirty",
    }
    assert operator.inspect_authority(9, "conflict", conflict)["ok"] is True


def test_authority_inspection_rejects_incomplete_thread_evidence() -> None:
    fake = authority_runner()
    response = fake.responses["graphql"]
    assert isinstance(response, dict)
    response["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]["hasNextPage"] = True

    with pytest.raises(operator.OperatorError, match="exceeds one bounded page"):
        operator.inspect_authority(9, "unresolved-thread", fake)


def test_authority_review_folding_preserves_dismissal_tombstone_regardless_of_order() -> None:
    approved = {
        "id": 1,
        "submitted_at": "2026-08-02T01:00:00Z",
        "state": "APPROVED",
        "user": {"login": "Reviewer"},
    }
    dismissed = approved | {"id": 2, "submitted_at": "2026-08-02T02:00:00Z", "state": "DISMISSED"}
    reapproved = approved | {"id": 3, "submitted_at": "2026-08-02T03:00:00Z"}

    assert operator._latest_reviews([approved, dismissed]) == {}
    assert operator._latest_reviews([dismissed, approved]) == {}
    assert operator._latest_reviews([dismissed, approved, reapproved]) == {"Reviewer": "APPROVED"}


def test_authority_policy_evidence_matches_production_normalization() -> None:
    fake = authority_runner()
    path = f"/repos/{operator.REPOSITORY}/rules/branches/authority-base?per_page=100"
    rules = fake.responses[path]
    assert isinstance(rules, list)

    strict, _, approvals, resolution = _derive_policy(rules)

    assert operator._authority_policy(rules) == (strict, approvals, resolution)


def test_authority_inspection_includes_team_requests_and_requires_stable_determinate_basis() -> None:
    team = authority_runner()
    requested = team.responses[f"/repos/{operator.REPOSITORY}/pulls/9/requested_reviewers"]
    assert isinstance(requested, dict)
    requested["users"] = []
    requested["teams"] = [{"slug": "maintainers"}]
    result = operator.inspect_authority(9, "review-requested", team)
    assert result["ok"] is True
    assert result["authority"]["requested_teams"] == ["maintainers"]

    indeterminate = authority_runner()
    pull = indeterminate.responses[f"/repos/{operator.REPOSITORY}/pulls/9"]
    assert isinstance(pull, dict)
    indeterminate.responses[f"/repos/{operator.REPOSITORY}/pulls/9"] = pull | {"mergeable": None}
    with pytest.raises(operator.OperatorError, match="indeterminate"):
        operator.inspect_authority(9, "strict-stale", indeterminate)


def test_authority_inspection_rejects_provider_basis_change_during_collection() -> None:
    class MovingBasis(FakeRunner):
        pull_reads = 0

        def __call__(self, command: Any, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
            call = tuple(command)
            pull_path = f"/repos/{operator.REPOSITORY}/pulls/9"
            if call[:3] == ("gh", "api", pull_path):
                self.pull_reads += 1
                value = self.responses[pull_path]
                assert isinstance(value, dict)
                if self.pull_reads > 1:
                    value = value | {"head": value["head"] | {"sha": "d" * 40}}
                return completed(value)
            return super().__call__(command, cwd)

    fake = authority_runner()
    moving = MovingBasis(fake.responses)
    with pytest.raises(operator.OperatorError, match="changed during inspection"):
        operator.inspect_authority(9, "non-draft", moving)


@pytest.mark.parametrize("collection", ("reviews", "rules"))
def test_authority_inspection_rejects_full_potentially_incomplete_pages(collection: str) -> None:
    fake = authority_runner()
    if collection == "reviews":
        path = f"/repos/{operator.REPOSITORY}/pulls/9/reviews?per_page=100"
        fake.responses[path] = [
            {
                "id": index,
                "submitted_at": f"2026-08-02T00:00:{index:02d}Z",
                "state": "APPROVED",
                "user": {"login": f"reviewer-{index}"},
            }
            for index in range(100)
        ]
        message = "review authority exceeds"
    else:
        path = f"/repos/{operator.REPOSITORY}/rules/branches/authority-base?per_page=100"
        fake.responses[path] = [{} for _ in range(100)]
        message = "policy exceeds"
    with pytest.raises(operator.OperatorError, match=message):
        operator.inspect_authority(9, "non-draft", fake)
