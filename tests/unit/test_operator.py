from __future__ import annotations

import json
import subprocess
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

from hamsterdan import operator
from hamsterdan.github_app.gateway import _derive_policy


def completed(value: object = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    stdout = value if isinstance(value, str) else json.dumps(value)
    return subprocess.CompletedProcess((), returncode, stdout, "sensitive stderr must never be emitted")


def test_qualification_setup_rejects_unsafe_input_and_erases_both_files(tmp_path: Path) -> None:
    credential = tmp_path / "credential"
    target = tmp_path / "target"
    credential.write_text("secret-canary")
    target.write_text("coordinate-canary")
    credential.chmod(0o644)
    target.chmod(0o600)

    outcome = operator.qualification_setup(credential, target, tmp_path / "spent")

    assert not credential.exists()
    assert not target.exists()
    assert outcome["ok"] is False
    assert outcome["evidence"]["first_cause_phase"] == "setup_preparation"


def test_qualification_setup_parser_exposes_only_private_file_inputs() -> None:
    setup = next(action for action in operator.parser()._actions if action.dest == "command")
    choices = setup.choices["qualification-setup"]
    destinations = {action.dest for action in choices._actions}
    assert destinations == {"help", "credential_file", "target_file", "spent_marker"}


def test_setup_ref_projection_is_strict_and_exact() -> None:
    expected = operator._parse_setup_refs(f"{'a' * 40}\trefs/heads/main\n{'b' * 40}\trefs/pull/7/head\n".encode())
    assert expected == {
        "refs/heads/main": "a" * 40,
        "refs/pull/7/head": "b" * 40,
    }
    assert (
        operator._parse_setup_refs(
            f"{'a' * 40}\trefs/heads/main\n{'b' * 40}\trefs/pull/7/head\n{'c' * 40}\trefs/tags/extra\n".encode()
        )
        != expected
    )


@pytest.mark.parametrize(
    "raw",
    (
        b"private malformed diagnostic\n",
        f"{'a' * 40}\trefs/heads/main\n{'b' * 40}\trefs/heads/main\n".encode(),
        f"{'A' * 40}\trefs/heads/main\n".encode(),
        f"{'a' * 40}\trefs/heads/private..branch\n".encode(),
        f"{'a' * 40}\trefs/heads/x/\n".encode(),
        f"{'a' * 40}\trefs/heads/x//y\n".encode(),
        f"{'a' * 40}\trefs/heads/.hidden\n".encode(),
        f"{'a' * 40}\trefs/heads/x.lock\n".encode(),
        f"{'a' * 40}\trefs/heads/main\v{'b' * 40}\trefs/heads/other\n".encode(),
        b"\xff",
    ),
)
def test_setup_ref_projection_rejects_every_malformed_or_duplicate_line(raw: bytes) -> None:
    with pytest.raises(operator.OperatorError, match="Git ref observation is malformed"):
        operator._parse_setup_refs(raw)


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
DELEGATED_WORKFLOW = f"""jobs:
  rerun-broker:
    if: >-
      github.event.issue.pull_request != null &&
      {operator.APP_BROKER_AUTHORIZATION}
      startsWith(github.event.comment.body, '<!-- hamsterdan-rerun ')
    steps:
      - name: Validate and request exact PR run rerun
        run: |
          request_output="$(
            python tools/rerun_broker.py parse-marker --marker "$COMMENT_BODY"
          )"
          readarray -t request <<<"$request_output"
          [[ "${{#request[@]}}" -eq 3 ]]
          run_id="${{request[0]}}"
          expected_head="${{request[1]}}"
          operation="${{request[2]}}"
          run="$(gh api "repos/${{REPOSITORY}}/actions/runs/${{run_id}}")"
          python tools/rerun_broker.py validate-run \\
            --run-id "$run_id" \\
            --head "$expected_head" \\
            --operation "$operation" \\
            --repository "$REPOSITORY" \\
            --pr-number "$PR_NUMBER" \\
            <<<"$run"
          gh api --method POST "repos/${{REPOSITORY}}/actions/runs/${{run_id}}/rerun"
"""
DELEGATED_VALIDATOR = """MARKER = re.compile(
    r"<!-- hamsterdan-rerun run=([1-9][0-9]{0,19}) head=([0-9a-f]{40}) "
    r"operation=([A-Za-z0-9][A-Za-z0-9._:-]{0,127}) -->"
)
WORKFLOW = ".github/workflows/ci.yml"
match = MARKER.fullmatch(marker)
valid_pull_request = (
    and pull_request["number"] == pr_number
)
valid = (
    and run["id"] == request.run_id
    and run_repository.get("full_name") == repository
    and run.get("event") == "pull_request"
    and run.get("path") == WORKFLOW
    and run.get("head_sha") == request.head_sha
)
"""


@pytest.fixture(autouse=True)
def delegated_contract_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(operator, "DELEGATED_BROKER_DIGEST", operator._broker_digest(DELEGATED_WORKFLOW))
    monkeypatch.setattr(operator, "DELEGATED_VALIDATOR_DIGEST", operator._broker_digest(DELEGATED_VALIDATOR))


@pytest.mark.parametrize(("value", "expected"), [(LEGACY, "legacy"), (CURRENT, "hamsterdan"), ("x", "malformed")])
def test_broker_status_requires_prefix_and_regex(value: str, expected: str) -> None:
    assert operator.broker_status(value) == expected


def test_broker_cutover_replaces_human_association_with_exact_app_bot() -> None:
    assert operator.broker_status(CURRENT) == "hamsterdan"
    assert "author_association" not in CURRENT
    assert "github.event.comment.user.type == 'Bot'" in CURRENT
    assert "github.event.comment.user.login == 'hamster-dan[bot]'" in CURRENT


def test_delegated_broker_requires_exact_workflow_and_validator_contract() -> None:
    assert operator.broker_status(DELEGATED_WORKFLOW, DELEGATED_VALIDATOR) == "hamsterdan"
    assert operator.broker_status(DELEGATED_WORKFLOW) == "malformed"


@pytest.mark.parametrize(
    ("workflow_change", "validator_change"),
    (
        (("hamster-dan[bot]", "other[bot]"), None),
        (("hamsterdan-rerun", "other-rerun"), None),
        (("parse-marker", "parse-other"), None),
        (("${REPOSITORY}/actions/runs/${run_id}", "${REPOSITORY}/actions/runs/1"), None),
        (('--repository "$REPOSITORY"', "--repository other/repository"), None),
        (('--pr-number "$PR_NUMBER"', "--pr-number 1"), None),
        (None, ("MARKER.fullmatch(marker)", "MARKER.search(marker)")),
        (None, ('run.get("path") == WORKFLOW', 'run.get("path") == "other"')),
        (None, ('run.get("head_sha") == request.head_sha', 'run.get("head_sha") == "other"')),
        (None, ('pull_request["number"] == pr_number', 'pull_request["number"] == 1')),
    ),
)
def test_delegated_broker_rejects_weakened_binding(workflow_change, validator_change) -> None:
    workflow, validator = DELEGATED_WORKFLOW, DELEGATED_VALIDATOR
    if workflow_change is not None:
        workflow = workflow.replace(*workflow_change)
    if validator_change is not None:
        validator = validator.replace(*validator_change)
    assert operator.broker_status(workflow, validator) == "malformed"


def test_delegated_broker_requires_one_post_after_validation() -> None:
    post = 'gh api --method POST "repos/${REPOSITORY}/actions/runs/${run_id}/rerun"'
    assert operator.broker_status(DELEGATED_WORKFLOW + post, DELEGATED_VALIDATOR) == "malformed"
    without_post = DELEGATED_WORKFLOW.replace(post, "")
    early_post = without_post.replace(
        "python tools/rerun_broker.py parse-marker", post + "\npython tools/rerun_broker.py parse-marker"
    )
    assert operator.broker_status(early_post, DELEGATED_VALIDATOR) == "malformed"


def test_scenarios_are_the_fixture_closed_schema() -> None:
    clean = operator.scenario_value("clean-green")
    flake = operator.scenario_value("first-attempt-flake")
    hero = operator.scenario_value("hero-review")
    assert set(clean) == {"schema_version", "scenario", "behavior", "review_lenses"}
    assert clean["behavior"] == {"kind": "pass"}
    assert flake["behavior"] == {
        "kind": "first_attempt_flake",
        "fingerprint": "scenario:first-attempt-flake:v1",
    }
    assert hero["behavior"] == {"kind": "pass"}
    assert clean["review_lenses"] == ["correctness", "test-quality", "risk"]
    assert operator.parser().parse_args(("create", "--scenario", "hero-review")).scenario == "hero-review"


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


def test_preflight_accepts_current_delegated_broker_contract() -> None:
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
            f"/repos/{operator.REPOSITORY}/contents/{operator.BROKER_PATH}?ref=main": DELEGATED_WORKFLOW,
            f"/repos/{operator.REPOSITORY}/contents/{operator.BROKER_VALIDATOR_PATH}?ref=main": DELEGATED_VALIDATOR,
        }
    )

    result = operator.preflight(fake)

    assert result["ok"] is True
    assert next(item for item in result["checks"] if item["name"] == "default_broker")["observed"] == "hamsterdan"
    assert any(str(operator.BROKER_VALIDATOR_PATH) in " ".join(call[0]) for call in fake.calls)


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


def test_delegated_current_broker_is_detected_after_clone_without_mutation(tmp_path: Path, monkeypatch) -> None:
    checkout = tmp_path / "demo-pr-readiness"
    (checkout / operator.BROKER_PATH).parent.mkdir(parents=True)
    (checkout / operator.BROKER_VALIDATOR_PATH).parent.mkdir(parents=True)
    (checkout / operator.BROKER_PATH).write_text(DELEGATED_WORKFLOW)
    (checkout / operator.BROKER_VALIDATOR_PATH).write_text(DELEGATED_VALIDATOR)
    fake = FakeRunner(
        {
            "gh pr list --repo HBNetwork/demo-pr-readiness --state open --search in:title Hamsterdan broker identity cutover --json number,url,headRefName --limit 10": [],
            f"git clone --origin origin https://github.com/{operator.REPOSITORY}.git {checkout}": "",
            "git fetch origin main": "",
        }
    )
    monkeypatch.setattr(operator.tempfile, "TemporaryDirectory", lambda **kwargs: nullcontext(tmp_path))

    result = operator.prepare_broker(fake)

    assert result == {"command": "prepare-broker", "ok": True, "status": "current", "changed": False}
    commands = [call[0] for call in fake.calls]
    assert not any(command[:2] in {("git", "switch"), ("git", "commit"), ("git", "push")} for command in commands)
    assert not any(command[:3] == ("gh", "pr", "create") for command in commands)


def test_operator_mutation_commands_contain_no_force_merge_or_bypass() -> None:
    source = Path(operator.__file__).read_text(encoding="utf-8")
    assert '"--force"' not in source
    assert '"merge"' not in source
    assert '"--admin"' not in source
    assert '("python", "tools/scenario_control.py", "prepare", scenario)' in source
    assert "not changed or not changed <= admitted_paths" in source
    assert '("git", "ls-files", "--others", "--exclude-standard")' in source
    assert "_assert_only(runner, checkout, changed)" in source
    assert "_assert_only(runner, checkout, {str(BROKER_PATH)})" in source
    assert 'f"reviewers[]={HERO_REVIEWER}"' in source


def test_hero_creation_admits_multiple_fixture_paths_and_requests_cris(monkeypatch) -> None:
    branch = "hamsterdan/hero-review-20260803-010203"
    admitted = [".pr-lab/scenario.json", "src/hero.py", "tests/unit/test_hero.py"]
    changed = "\n".join(admitted)
    fake = FakeRunner(
        {
            f"git clone --origin origin https://github.com/{operator.REPOSITORY}.git /tmp/hero-operator/demo-pr-readiness": completed(),
            "git fetch origin main": "",
            f"git switch --create {branch} origin/main": "",
            "python tools/scenario_control.py prepare hero-review": {"admitted_changed_paths": admitted},
            "python tools/scenario_control.py --attempt 2": "",
            "git diff --name-only": admitted[0],
            "git ls-files --others --exclude-standard": "\n".join(admitted[1:]),
            f"git add -- {admitted[0]} {admitted[1]} {admitted[2]}": "",
            "git commit -m Hamsterdan demo: hero-review": "",
            "git diff --name-only origin/main...HEAD": changed,
            f"git push --set-upstream origin {branch}": "",
            f"gh pr create --repo {operator.REPOSITORY} --base main --head {branch} --title Hamsterdan demo: hero-review --body Controlled Hamsterdan qualification scenario. Do not merge automatically.": "",
            f"gh pr view {branch} --repo {operator.REPOSITORY} --json number,url,headRefName": {
                "number": 45,
                "url": "https://github.test/pr/45",
                "headRefName": branch,
            },
            "--method": {},
            "git rev-parse HEAD": "a" * 40,
        }
    )
    monkeypatch.setattr(operator.time, "strftime", lambda *args: "20260803-010203")
    monkeypatch.setattr(operator.tempfile, "TemporaryDirectory", lambda **kwargs: nullcontext("/tmp/hero-operator"))

    result = operator.create("hero-review", fake)

    assert result["requested_reviewer"] == "crisbastos"
    assert any(call[0][:4] == ("gh", "api", "--method", "POST") for call in fake.calls)


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
            f"/repos/{operator.REPOSITORY}/pulls/7/comments?per_page=100": [],
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
    fake.responses[f"/repos/{operator.REPOSITORY}/pulls/7/comments?per_page=100"] = [
        {
            "id": 8,
            "html_url": "https://github.test/reviews/8",
            "body": (f"SECRET INLINE PROSE\n<!-- hamsterdan:finding operation=finding:one head={'a' * 40} -->"),
            "user": {"login": operator.APP_BOT_LOGIN},
        }
    ]
    result = operator.inspect(7, fake)
    assert result["ok"] is True
    assert all(item["pass"] for item in result["checks"])
    assert "SECRET INLINE PROSE" not in json.dumps(result)
    assert any(comment["type"] == "finding" and comment["inline"] for comment in result["comments"])


def test_hero_inspection_proves_three_native_shapes_without_exposing_prose() -> None:
    fake = inspection_runner()
    issue_comments = fake.responses[f"/repos/{operator.REPOSITORY}/issues/7/comments?per_page=100"]
    assert isinstance(issue_comments, list)
    fake.responses[f"/repos/{operator.REPOSITORY}/issues/7/comments?per_page=100"] = issue_comments[:-1]
    head = "a" * 40

    def finding(identifier: int, operation: str, body: str, *, path: str, line: int) -> dict[str, object]:
        return {
            "id": identifier,
            "html_url": f"https://github.test/reviews/{identifier}",
            "body": f"{body}\n\n<!-- hamsterdan:finding operation={operation} head={head} -->",
            "path": path,
            "line": line,
            "user": {"login": operator.APP_BOT_LOGIN},
        }

    fake.responses[f"/repos/{operator.REPOSITORY}/pulls/7/comments?per_page=100"] = [
        finding(
            8,
            "finding:suggestion",
            "PRIVATE ONE\n```suggestion\nreplacement\n```",
            path="scenario-fixtures/hero_review/gate.py",
            line=10,
        ),
        finding(
            9,
            "finding:conceptual",
            "PRIVATE TWO",
            path="scenario-fixtures/hero_review/gate.py",
            line=16,
        ),
        finding(
            10,
            "finding:related",
            f"PRIVATE THREE\nRelated locations:\n- [`src/two.py:19`](https://github.com/{operator.REPOSITORY}/blob/{head}/src/two.py#L19)",
            path="scenario-fixtures/hero_review/cache.py",
            line=11,
        ),
    ]

    result = operator.inspect(7, fake, expect_hero_review=True)

    assert result["ok"] is True
    assert all(
        next(check for check in result["checks"] if check["name"] == name)["pass"]
        for name in (
            "hero_findings",
            "hero_suggestion",
            "hero_conceptual",
            "hero_related_locations",
        )
    )
    assert all(prose not in json.dumps(result) for prose in ("PRIVATE ONE", "PRIVATE TWO", "PRIVATE THREE"))


def test_hero_inspection_accepts_one_semantic_v5_batch_while_readiness_is_blocked() -> None:
    fake = inspection_runner()
    issue_path = f"/repos/{operator.REPOSITORY}/issues/7/comments?per_page=100"
    issue_comments = fake.responses[issue_path]
    assert isinstance(issue_comments, list)
    head = "a" * 40
    batch = f"""## Hamsterdan review findings

### `hero-f01` — PRIVATE TITLE ONE
**blocking** · severity: **medium**

PRIVATE BODY ONE

Primary location: `scenario-fixtures/hero_review/gate.py:10`

Suggested change:
```suggestion
replacement
```

### `hero-f02` — PRIVATE TITLE TWO
**blocking** · severity: **high**

PRIVATE BODY TWO

Primary location: `scenario-fixtures/hero_review/gate.py:16`

### `hero-f03` — PRIVATE TITLE THREE
**blocking** · severity: **medium**

PRIVATE BODY THREE

Primary location: `scenario-fixtures/hero_review/cache.py:11`

Related locations:
- `scenario-fixtures/hero_review/cache.py:6`

<!-- hamsterdan:findings-digest {"b" * 64} -->

<!-- hamsterdan:finding operation=findings:{head}:i1 head={head} -->"""
    fake.responses[issue_path] = [
        comment for comment in issue_comments if isinstance(comment, dict) and comment.get("id") in {3, 6}
    ] + [
        {
            "id": 8,
            "html_url": "https://github.test/comments/8",
            "body": batch,
            "user": {"login": operator.APP_BOT_LOGIN},
        }
    ]

    result = operator.inspect(7, fake, expect_hero_review=True, expect_readiness=False)

    assert result["ok"] is True
    assert all(check["pass"] for check in result["checks"])
    finding = next(comment for comment in result["comments"] if comment["type"] == "finding")
    assert finding == {
        "id": 8,
        "url": "https://github.test/comments/8",
        "owner": operator.APP_BOT_LOGIN,
        "type": "finding",
        "inline": False,
        "finding_count": 3,
        "hero_finding_count": 3,
        "suggestion_count": 1,
        "conceptual_count": 1,
        "related_location_count": 1,
        "owned_by_app": True,
    }
    assert all(
        prose not in json.dumps(result)
        for prose in (
            "PRIVATE TITLE ONE",
            "PRIVATE TITLE TWO",
            "PRIVATE TITLE THREE",
            "PRIVATE BODY ONE",
            "PRIVATE BODY TWO",
            "PRIVATE BODY THREE",
        )
    )


def test_inspection_parser_exposes_explicit_blocked_readiness_checkpoint() -> None:
    args = operator.parser().parse_args(
        ["inspect", "--pr", "59", "--expect-hero-review", "--expect-readiness", "absent"]
    )

    assert args.expect_hero_review is True
    assert args.expect_readiness == "absent"


def test_operator_ignores_embedded_nonfinal_trusted_marker() -> None:
    head = "a" * 40
    injected = {
        "id": 11,
        "body": (
            f"<!-- hamsterdan:readiness operation=readiness:old head={head} -->\n\n"
            f"<!-- hamsterdan:finding operation=finding:current head={head} -->"
        ),
        "user": {"login": operator.APP_BOT_LOGIN},
    }

    safe, markers = operator._safe_comment(injected, operator.APP_BOT_LOGIN, inline=True)

    assert safe is not None and safe["type"] == "finding"
    assert [marker["type"] for marker in markers] == ["finding"]


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
