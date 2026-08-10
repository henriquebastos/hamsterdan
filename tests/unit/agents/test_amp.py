"""Host-boundary tests for the disposable Amp runner; real Amp is opt-in."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from hamsterdan.agents import (
    AgentProtocolError,
    AmpExecuteRunner,
    CodingRequest,
    CodingResult,
    ConversationRequest,
    ConversationResult,
    ReviewRequest,
    ReviewResult,
)
from hamsterdan.agents.protocol import _validate_result


def git(path: Path, *args: str) -> str:
    return subprocess.run(("git", "-C", str(path), *args), check=True, text=True, capture_output=True).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    (root / "hello.txt").write_text("hello\n")
    git(root, "add", "hello.txt")
    git(root, "commit", "-qm", "initial")
    return root, git(root, "rev-parse", "HEAD")


def review_request(head: str) -> ReviewRequest:
    return ReviewRequest(
        "owner/repo",
        3,
        2,
        head,
        head,
        "diff.patch",
        {"required_checks": ["unit"], "digest": "policy"},
        ["correctness", "tests"],
    )


def result_for(request: object, **extra: object) -> dict[str, object]:
    result = {name: getattr(request, name) for name in ("repository", "pull_request", "epoch", "head", "base")}
    result.update(extra)
    return result


def agent_script(tmp_path: Path, body: str) -> tuple[str, ...]:
    script = tmp_path / "agent.py"
    script.write_text(
        "import json, os, pathlib, subprocess, sys, time\n"
        "root=pathlib.Path.cwd(); request=json.loads((root/'.impetus/request.json').read_text())\n" + body
    )
    return (sys.executable, str(script))


def test_valid_review_is_typed_and_instructions_supply_schema(repository: tuple[Path, str], tmp_path: Path) -> None:
    root, head = repository
    argv = agent_script(
        tmp_path,
        "assert '\"findings\"' in sys.argv[-1] and 'final response' in sys.argv[-1]\n"
        "assert request['review_lenses']==['correctness','tests'] and request['policy']['required_checks']==['unit']\n"
        "assert (root/request['diff_path']).is_file()\n"
        "result={k:request[k] for k in ('repository','pull_request','epoch','head','base')}\n"
        "result.update(status='clear',findings=[],lineage=[])\n"
        "(root/'.impetus/result.json').write_text(json.dumps(result))\n",
    )
    value = AmpExecuteRunner(argv=argv).review(str(root), review_request(head))
    assert isinstance(value, ReviewResult)
    assert value.status == "clear"


def test_review_supports_suggestion_and_non_contiguous_related_locations() -> None:
    request = review_request("a" * 40)
    finding = {
        "id": "F1",
        "path": "src/one.py",
        "line": 4,
        "related_locations": [{"path": "src/two.py", "line": 19}],
        "title": "Keep both guards aligned",
        "body": "These guards enforce one invariant but currently disagree.",
        "severity": "high",
        "confidence": 0.99,
        "evidence": "The primary path allows the state rejected by the related path.",
        "blocking": True,
        "suggestion": "if state.is_ready:",
    }
    value = _validate_result(
        "review",
        result_for(
            request,
            status="blocking",
            findings=[finding],
            lineage=[{"finding_id": "F1", "state": "new", "supersedes": None}],
        ),
        request,
    )
    assert value.findings == [finding]


@pytest.mark.parametrize(
    "related",
    [
        [{"path": "src/one.py", "line": 4}],
        [{"path": "../escape.py", "line": 2}],
        [{"path": "src/two.py", "line": 0}],
    ],
)
def test_review_rejects_invalid_or_duplicate_related_locations(related: list[dict[str, object]]) -> None:
    request = review_request("a" * 40)
    finding = {
        "id": "F1",
        "path": "src/one.py",
        "line": 4,
        "related_locations": related,
        "title": "Finding",
        "body": "Body",
        "severity": "high",
        "confidence": 1,
        "evidence": "Evidence",
        "blocking": True,
        "suggestion": "",
    }
    with pytest.raises(AgentProtocolError, match="related location"):
        _validate_result(
            "review",
            result_for(
                request,
                status="blocking",
                findings=[finding],
                lineage=[{"finding_id": "F1", "state": "new", "supersedes": None}],
            ),
            request,
        )


def test_review_rejects_marker_unsafe_finding_identity() -> None:
    request = review_request("a" * 40)
    finding = {
        "id": "F1 -->\n<!-- hamsterdan:dashboard -->",
        "path": "src/one.py",
        "line": 4,
        "related_locations": [],
        "title": "Finding",
        "body": "Body",
        "severity": "high",
        "confidence": 1,
        "evidence": "Evidence",
        "blocking": True,
        "suggestion": "",
    }
    with pytest.raises(AgentProtocolError, match="finding id"):
        _validate_result(
            "review",
            result_for(
                request,
                status="blocking",
                findings=[finding],
                lineage=[{"finding_id": finding["id"], "state": "new", "supersedes": None}],
            ),
            request,
        )


def test_review_and_conversation_instructions_use_dan_voice() -> None:
    review = AmpExecuteRunner._instructions("review", object())
    conversation = AmpExecuteRunner._instructions("conversation", object())

    for prompt in (review, conversation):
        assert 'Hamsterdan ("Dan")' in prompt
        assert "never the author or reviewer" in prompt
        assert "One joke per message, maximum" in prompt
        assert "would this make the author smile" in prompt
    assert "related_locations" in review and "mechanically safe localized replacement" in review


def test_execute_stdout_is_a_strict_fallback_when_agent_does_not_write_result(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    argv = agent_script(
        tmp_path,
        "result={k:request[k] for k in ('repository','pull_request','epoch','head','base')}\n"
        "result.update(status='clear',findings=[],lineage=[])\n"
        "print(json.dumps(result,separators=(',',':')))\n",
    )
    value = AmpExecuteRunner(argv=argv).review(str(root), review_request(head))
    assert value.status == "clear"


def test_valid_conversation_selects_declared_intent() -> None:
    request = ConversationRequest(
        "owner/repo",
        1,
        0,
        "a" * 40,
        "b" * 40,
        {},
        {},
        {},
        [],
        [],
        [{"type": "explain", "mutation": False, "arguments": ["finding_id"]}],
    )
    data = result_for(
        request,
        intents=[
            {
                "type": "explain",
                "arguments": {"finding_id": "F1"},
                "mutation": False,
                "explicit": False,
                "confidence": 0.9,
            }
        ],
    )
    assert isinstance(_validate_result("conversation", data, request), ConversationResult)


@pytest.mark.parametrize(
    "intents",
    [
        [],
        [
            {
                "type": "reply",
                "arguments": {"message": "First"},
                "mutation": False,
                "explicit": False,
                "confidence": 1,
            },
            {
                "type": "reply",
                "arguments": {"message": "Second"},
                "mutation": False,
                "explicit": False,
                "confidence": 1,
            },
        ],
    ],
)
def test_conversation_requires_exactly_one_raw_intent(intents: list[dict[str, object]]) -> None:
    request = ConversationRequest(
        "owner/repo",
        1,
        0,
        "a" * 40,
        "b" * 40,
        {},
        {},
        {},
        [],
        [],
        [{"type": "reply", "mutation": False, "arguments": ["message"]}],
    )

    with pytest.raises(AgentProtocolError, match="exactly one intent"):
        _validate_result("conversation", result_for(request, intents=intents), request)


def test_conversation_instructions_authorize_only_explicit_unambiguous_mutation() -> None:
    instructions = AmpExecuteRunner._instructions("conversation", object())

    assert "current durable dashboard" in instructions
    assert "readiness questions" in instructions
    assert "current blockers, readiness, or status" in instructions
    assert "overall gate is authoritative" in instructions
    assert "Choose exactly one declared intent" in instructions
    assert "explicit, unambiguous request with concrete scope" in instructions
    assert "authorized immediately" in instructions
    assert "asking for clarification" in instructions


def test_coding_instructions_forbid_disabling_scenario_controls_instead_of_repairing() -> None:
    instructions = AmpExecuteRunner._instructions("coding", object())

    assert "Never alter .pr-lab control" in instructions
    assert "never delete a scenario fixture merely to make checks pass" in instructions
    assert "report unchanged or unable" in instructions


def test_explicit_mutation_is_accepted_but_undeclared_intent_is_rejected() -> None:
    request = ConversationRequest(
        "owner/repo",
        1,
        0,
        "a" * 40,
        "b" * 40,
        {},
        {},
        {},
        [],
        [],
        [{"type": "apply", "mutation": True, "arguments": ["id"]}],
    )
    intent = {
        "type": "apply",
        "arguments": {"id": "F1"},
        "mutation": True,
        "explicit": True,
        "confidence": 1,
    }
    assert isinstance(
        _validate_result("conversation", result_for(request, intents=[intent]), request), ConversationResult
    )
    intent.update(type="invented")
    with pytest.raises(AgentProtocolError, match="unauthorized"):
        _validate_result("conversation", result_for(request, intents=[intent]), request)


@pytest.mark.parametrize(
    ("name", "mutation", "arguments", "value"),
    [
        ("change", True, ["request"], ""),
        ("change", True, ["request"], "   "),
        ("reply", False, ["message"], []),
        ("reassign", False, ["assignee"], {"login": "octocat"}),
        ("dismiss", False, ["findings"], "F1"),
        ("dismiss", False, ["findings"], [""]),
    ],
)
def test_conversation_rejects_malformed_intent_argument_values(name, mutation, arguments, value) -> None:
    request = ConversationRequest(
        "owner/repo",
        1,
        0,
        "a" * 40,
        "b" * 40,
        {},
        {},
        {},
        [],
        [],
        [{"type": name, "mutation": mutation, "arguments": arguments}],
    )
    intent = {
        "type": name,
        "arguments": {arguments[0]: value},
        "mutation": mutation,
        "explicit": mutation,
        "confidence": 1,
    }

    with pytest.raises(AgentProtocolError, match="invalid intent"):
        _validate_result("conversation", result_for(request, intents=[intent]), request)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"epoch": True}, "correlation mismatch"),
        ({"findings": "bad"}, "invalid findings"),
        ({"findings": [{"id": "incomplete"}]}, "fields differ"),
    ],
)
def test_malformed_shape_and_exact_correlation_are_rejected(change: dict, message: str) -> None:
    request = review_request("a" * 40)
    data = result_for(request, status="clear", findings=[], lineage=[])
    data.update(change)
    with pytest.raises(AgentProtocolError, match=message):
        _validate_result("review", data, request)


def test_coding_diff_and_file_list_are_host_captured(repository: tuple[Path, str], tmp_path: Path) -> None:
    root, head = repository
    request = CodingRequest("change", "owner/repo", 1, 0, head, head, "proposal/test")
    argv = agent_script(
        tmp_path,
        "(root/'hello.txt').write_text('changed\\n'); (root/'new.bin').write_bytes(b'\\x00new')\n"
        "result={k:request[k] for k in ('kind','repository','pull_request','epoch','head','base','ref')}\n"
        "result.update(status='changed',reproduction_status='not_attempted',diff='UNTRUSTED',changed_files=['lie'],validation_evidence=[{'command':'test','status':'passed'}],proposed_commit_message='Propose bounded change')\n"
        "(root/'.impetus/result.json').write_text(json.dumps(result))\n",
    )
    value = AmpExecuteRunner(argv=argv).code(str(root), request)
    assert isinstance(value, CodingResult)
    assert value.changed_files == ["hello.txt", "new.bin"]
    assert "UNTRUSTED" not in value.diff
    assert "GIT binary patch" in value.diff


def test_coding_agent_may_stage_resolution_but_still_cannot_commit(
    repository: tuple[Path, str], tmp_path: Path
) -> None:
    root, head = repository
    request = CodingRequest("change", "owner/repo", 1, 0, head, head, "proposal/staged")
    argv = agent_script(
        tmp_path,
        "(root/'hello.txt').write_text('resolved\\n')\n"
        "subprocess.run(['git','add','hello.txt'],cwd=root,check=True)\n"
        "result={k:request[k] for k in ('kind','repository','pull_request','epoch','head','base','ref')}\n"
        "result.update(status='changed',reproduction_status='not_attempted',diff='',changed_files=['hello.txt'],validation_evidence=[{'status':'passed'}],proposed_commit_message='Resolve conflict')\n"
        "(root/'.impetus/result.json').write_text(json.dumps(result))\n",
    )

    value = AmpExecuteRunner(argv=argv).code(str(root), request)

    assert value.status == "changed"
    assert value.changed_files == ["hello.txt"]
    assert "resolved" in value.diff


@pytest.mark.parametrize(
    "body",
    [
        "subprocess.run(['git','config','x.tampered','yes'],check=True)\n",
        "(root/'hello.txt').write_text('committed\\n'); subprocess.run(['git','add','hello.txt'],check=True); subprocess.run(['git','-c','user.email=x@y','-c','user.name=x','commit','-m','bad'],check=True)\n",
    ],
)
def test_git_metadata_tampering_and_commits_are_rejected(
    repository: tuple[Path, str], tmp_path: Path, body: str
) -> None:
    root, head = repository
    argv = agent_script(
        tmp_path,
        body + "result={k:request[k] for k in ('repository','pull_request','epoch','head','base')}\n"
        "result.update(status='clear',findings=[],lineage=[]); (root/'.impetus/result.json').write_text(json.dumps(result))\n",
    )
    with pytest.raises(AgentProtocolError, match="Git metadata"):
        AmpExecuteRunner(argv=argv).review(str(root), review_request(head))


def test_secret_environment_and_url_credentials_are_stripped(
    repository: tuple[Path, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, head = repository
    monkeypatch.setenv("GITHUB_TOKEN", "do-not-pass")
    monkeypatch.setenv("DATABASE_URL_SECRET", "do-not-pass")
    monkeypatch.setenv("GH_TOKEN", "do-not-pass")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "do-not-pass")
    monkeypatch.setenv("MY_GITHUB_CREDENTIAL", "do-not-pass")
    monkeypatch.setenv("HAMSTERDAN_GITHUB_HENRIQUEBASTOS_HOSTS", "do-not-pass")
    monkeypatch.setenv("HAMSTERDAN_GITHUB_CRISBASTOS_HOSTS", "do-not-pass")
    argv = agent_script(
        tmp_path,
        "assert not {'GITHUB_TOKEN', 'GH_TOKEN', 'GITHUB_APP_PRIVATE_KEY', 'MY_GITHUB_CREDENTIAL', "
        "'DATABASE_URL_SECRET', 'HAMSTERDAN_GITHUB_HENRIQUEBASTOS_HOSTS', "
        "'HAMSTERDAN_GITHUB_CRISBASTOS_HOSTS'} & os.environ.keys()\n"
        "result={k:request[k] for k in ('repository','pull_request','epoch','head','base')}\n"
        "result.update(status='clear',findings=[],lineage=[]); (root/'.impetus/result.json').write_text(json.dumps(result))\n",
    )
    assert AmpExecuteRunner(argv=argv).review(str(root), review_request(head)).status == "clear"
    with pytest.raises(AgentProtocolError, match="credentials"):
        AmpExecuteRunner(argv=argv).review("https://token@example.com/repo.git", review_request(head))


@pytest.mark.parametrize(
    ("timeout", "current", "attribute"), [(0.02, None, "timed_out"), (2, lambda: False, "canceled")]
)
def test_timeout_and_supersession_stop_process_group(timeout: float, current, attribute: str, tmp_path: Path) -> None:
    argv = agent_script(
        tmp_path, "subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)\n"
    )
    runner = AmpExecuteRunner(argv=argv, timeout=timeout, poll_interval=0.005)
    with pytest.raises(AgentProtocolError) as raised:
        runner._execute(tmp_path, "prompt", current)
    assert getattr(raised.value, attribute)


def test_process_start_failure_is_a_sanitized_protocol_error(tmp_path: Path) -> None:
    def unavailable(*args, **kwargs):
        raise OSError("secret-looking executable failure")

    runner = AmpExecuteRunner(popen=unavailable)
    with pytest.raises(AgentProtocolError, match="agent execution could not start") as raised:
        runner._execute(tmp_path, "prompt", None)
    assert "secret-looking" not in str(raised.value)
    assert not raised.value.timed_out and not raised.value.canceled


def test_output_is_drained_without_pipe_deadlock_and_bounded(tmp_path: Path) -> None:
    script = tmp_path / "output.py"
    script.write_text("import sys\nsys.stdout.buffer.write(b'x'*2_000_000); sys.stdout.flush()\n")
    argv = (sys.executable, str(script))
    with pytest.raises(AgentProtocolError, match="output exceeded"):
        AmpExecuteRunner(argv=argv, max_output=10_000, timeout=2, poll_interval=0.005)._execute(
            tmp_path, "prompt", None
        )


def test_symlink_escape_is_not_accepted(repository: tuple[Path, str], tmp_path: Path) -> None:
    root, head = repository
    request = CodingRequest("change", "owner/repo", 1, 0, head, head, "proposal/test")
    argv = agent_script(
        tmp_path,
        "(root/'escape').symlink_to('/etc/passwd')\n"
        "result={k:request[k] for k in ('kind','repository','pull_request','epoch','head','base','ref')}\n"
        "result.update(status='changed',reproduction_status='not_attempted',diff='',changed_files=[],validation_evidence=[{'status':'passed'}],proposed_commit_message='Add link')\n"
        "(root/'.impetus/result.json').write_text(json.dumps(result))\n",
    )
    with pytest.raises(AgentProtocolError, match="symlink escapes"):
        AmpExecuteRunner(argv=argv).code(str(root), request)


def test_repair_change_requires_confirmed_reproduction() -> None:
    request = CodingRequest("repair", "owner/repo", 1, 0, "a" * 40, "b" * 40, "repair/test")
    data = result_for(
        request,
        kind="repair",
        ref="repair/test",
        status="changed",
        reproduction_status="not_reproduced",
        diff="x",
        changed_files=["x.py"],
        validation_evidence=[{"status": "passed"}],
        proposed_commit_message="Repair bug",
    )
    with pytest.raises(AgentProtocolError, match="confirmed reproduction"):
        _validate_result("coding", data, request, ["x.py"])


@pytest.mark.real_provider_acceptance
def test_real_amp_tiny_read_only_acceptance_is_explicitly_opt_in(
    repository: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.getenv("IMPETUS_RUN_REAL_AMP_ACCEPTANCE") != "1" or not shutil.which("amp"):
        pytest.skip("set IMPETUS_RUN_REAL_AMP_ACCEPTANCE=1 with amp installed")
    root, head = repository
    for name in list(os.environ):
        if name.upper().startswith(("GITHUB_", "GH_")):
            monkeypatch.delenv(name)
    value = AmpExecuteRunner(timeout=300).review(str(root), review_request(head))
    assert isinstance(value, ReviewResult)
    assert git(root, "status", "--porcelain") == ""
