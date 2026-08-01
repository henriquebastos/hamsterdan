from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from hamsterdan import operator


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
    assert "github.event.comment.user.login == 'hamsterdan[bot]'" in CURRENT


def test_scenarios_are_the_fixture_closed_schema() -> None:
    clean = operator.scenario_value("clean-green")
    flake = operator.scenario_value("first-attempt-flake")
    assert set(clean) == {"schema_version", "scenario", "behavior", "review_lenses"}
    assert clean["behavior"] == {"kind": "pass"}
    assert flake["behavior"] == {
        "kind": "first_attempt_flake",
        "fingerprint": "hamsterdan:first-attempt-flake:v1",
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


def inspection_runner(owner: str = "hamsterdan[bot]") -> FakeRunner:
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
                "committer": {"login": "hamsterdan[bot]"},
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
        "authenticated_committer": "hamsterdan[bot]",
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
