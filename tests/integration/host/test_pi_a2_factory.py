from __future__ import annotations

import json
import subprocess
import sys
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

import pytest
from petrus.agenticus.connection.custody import ConnectionIdentity
from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.runtime import pi
from petrus.agenticus.runtime.installation import ProbeDisposition
from petrus.agenticus.runtime.operation import RuntimeProtocolError
from petrus.agenticus.runtime.pi_a2_host import (
    PiA2DirectAuthority,
    PiA2RuntimeHost,
    PiA2RuntimeHostConfig,
    PiA2RuntimePolicy,
    PiA2RuntimeStart,
    PiA2ScriptedCall,
    PiA2ScriptedTurn,
    compose_pi_a2_scripted_runtime,
)
from petrus.agenticus.thread.continuation import Continuation
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution.archive import workspace_archive

from hamsterdan.agents import AgentProtocolError, AgentResultCategory, PiNativeRunner, ReviewRequest, encode_prompt
from hamsterdan.host.pi_a2 import (
    OneShotApiKeySupplier,
    PersistentKeyOperations,
    PiA2InstallationConfig,
    compose_owned_pi_a2,
)

_READ_POLICY = PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH}), max_tool_calls=8)
_CODE_POLICY = PiA2RuntimePolicy(
    frozenset({ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH, ToolMethod.WORKSPACE_WRITE}),
    max_tool_calls=8,
    writable_roots=frozenset({"."}),
)


def _package(root: Path) -> tuple[str, str, str]:
    package = root / "package"
    (package / "dist").mkdir(parents=True, exist_ok=True)
    ai = package / "node_modules/@earendil-works/pi-ai"
    ai.mkdir(parents=True, exist_ok=True)
    (package / "dist/cli.js").write_text("fixture")
    (package / "dist/index.js").write_text("fixture")
    (package / "package.json").write_text(
        json.dumps(
            {
                "name": "@earendil-works/pi-coding-agent",
                "version": pi.PI_SDK_VERSION,
                "bin": {"pi": "dist/cli.js"},
                "main": "dist/index.js",
                "dependencies": {"@earendil-works/pi-ai": pi.PI_AI_VERSION},
            }
        )
    )
    (ai / "package.json").write_text(json.dumps({"name": "@earendil-works/pi-ai", "version": pi.PI_AI_VERSION}))
    node = root / "node"
    node.write_text(
        '#!/bin/sh\nif [ "$1" = "--version" ]; then printf "v22.19.0\\n"; '
        'else printf \'{"type":"probe","ok":true}\\n\'; fi\n'
    )
    node.chmod(0o700)
    return str(package / "dist/cli.js"), str(node), str(package)


def _config(root: Path) -> PiA2RuntimeHostConfig:
    working = root / "working"
    working.mkdir(exist_ok=True)
    (working / "input.txt").write_text("input")
    cli, node, package = _package(root)
    return PiA2RuntimeHostConfig(
        state_root=root / "state",
        working_directory=working,
        provider="anthropic",
        model="claude-sonnet-4-5",
        host_id="hamsterdan-test",
        capabilities=frozenset(ToolMethod),
        allowed_argv=frozenset({("/bin/true",)}),
        test_command=("/bin/true",),
        max_tool_calls=8,
        attachment_timeout=2,
        command_timeout=1,
        credential_ttl=1,
        wall_timeout=0.5,
        cancellation_grace=0.05,
        cli_path=cli,
        node_path=node,
        package_root=package,
    )


def _host(
    root: Path,
    script: tuple[PiA2ScriptedTurn, ...],
    supplier: OneShotApiKeySupplier,
) -> PiA2RuntimeHost:
    authority = PiA2DirectAuthority(
        ConnectionIdentity("direct", "anthropic", "synthetic", "api-key"),
        PersistentKeyOperations(root / "keys"),
        supplier,
    )
    host = compose_pi_a2_scripted_runtime(
        config=_config(root),
        authority=authority,
        script=script,
    )
    assert host.scripted_readiness().ready
    return host


def test_production_owned_composition_uses_explicit_installed_package_without_authority(tmp_path: Path) -> None:
    cli, node, package = _package(tmp_path)
    installation = PiA2InstallationConfig(
        "anthropic", "claude-sonnet-4-5", "synthetic-direct-authority", Path(cli), Path(node), Path(package)
    )

    host = compose_owned_pi_a2(tmp_path / "production", installation)
    try:
        probe = host.probe()
        assert probe.disposition is ProbeDisposition.READY
        assert probe.runtime.name == "pi.native.a2.local"
        assert not host.authority_requested
    finally:
        assert host.close()


def _start(
    name: str,
    *,
    archive: bytes,
    prompt: str = "prompt",
    continuation: Continuation | None = None,
    policy: PiA2RuntimePolicy = _CODE_POLICY,
) -> PiA2RuntimeStart:
    return PiA2RuntimeStart(
        name,
        EpisodeId(f"episode-{name}"),
        TurnId(f"turn-{name}"),
        prompt,
        archive,
        sha256(archive).hexdigest(),
        f"synthetic:{name}",
        policy,
        continuation,
    )


class RunnerWorkspace:
    def __init__(self, archive: bytes) -> None:
        self.archive = archive
        self.digest = sha256(archive).hexdigest()
        self.correlation = "synthetic:runner"
        self.policy = _READ_POLICY

    def reconcile(self, archive: bytes) -> tuple[str, list[str]]:
        return "", []


class RunnerWorkspaces:
    def __init__(self, archive: bytes) -> None:
        self.workspace = RunnerWorkspace(archive)

    @contextmanager
    def open(self, kind, repository_url, request, operation_id):
        yield self.workspace


def test_fresh_start_continuation_workspace_output_and_close(tmp_path: Path) -> None:
    supplied = bytearray(b"fixture")
    supplier = OneShotApiKeySupplier(lambda: supplied)
    host = _host(
        tmp_path,
        (
            PiA2ScriptedTurn(
                "first",
                (PiA2ScriptedCall(ToolMethod.WORKSPACE_WRITE, '{"path":"output.txt","content":"changed"}'),),
            ),
            PiA2ScriptedTurn(
                "second",
                (PiA2ScriptedCall(ToolMethod.WORKSPACE_READ, '{"path":"output.txt"}'),),
            ),
        ),
        supplier,
    )
    initial = workspace_archive(_config(tmp_path).working_directory)

    first_operation = host.start(_start("one", archive=initial))
    first = first_operation.wait(1)
    assert first.outcome is TurnOutcome.COMPLETED
    assert host.load_output(first.output_reference or "") == "first"
    assert host.load_workspace_archive("one")
    assert first.continuation_reference is not None
    continuation = Continuation(
        ContinuationId("continuation-one"),
        ThreadId("thread-one"),
        pi.PI_CONTINUATION_DESCRIPTOR,
        first.continuation_reference,
    ).claim()
    second = host.start(_start("two", archive=host.load_workspace_archive("one"), continuation=continuation)).wait(1)

    assert host.load_output(second.output_reference or "") == "second"
    assert second.continuation_reference is not None
    assert set(supplied) == {0}
    assert first_operation.close().verified
    assert host.close()
    assert host.close()


def test_terminal_replay_and_changed_work_conflict_use_no_authority(tmp_path: Path) -> None:
    supplier = OneShotApiKeySupplier(lambda: bytearray(b"fixture"))
    host = _host(tmp_path, (PiA2ScriptedTurn("answer"),), supplier)
    start = _start("stable", archive=workspace_archive(_config(tmp_path).working_directory))
    expected = host.start(start).wait(1)
    assert host.close()

    calls = 0

    def replay_supply() -> bytearray:
        nonlocal calls
        calls += 1
        return bytearray(b"unused")

    replay = compose_pi_a2_scripted_runtime(
        config=_config(tmp_path),
        authority=PiA2DirectAuthority(
            ConnectionIdentity("direct", "anthropic", "synthetic", "api-key"),
            PersistentKeyOperations(tmp_path / "replay-keys"),
            OneShotApiKeySupplier(replay_supply),
        ),
        # Terminal replay must not consume this required finite script turn.
        script=(PiA2ScriptedTurn("unused"),),
    )
    assert replay.start(start).wait() == expected
    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        replay.start(_start("stable", archive=start.workspace_archive, prompt="changed"))
    changed_workspace = tmp_path / "changed-workspace"
    changed_workspace.mkdir()
    (changed_workspace / "different.txt").write_text("different")
    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        replay.start(_start("stable", archive=workspace_archive(changed_workspace)))
    changed_correlation = PiA2RuntimeStart(
        start.operation_id,
        start.episode_id,
        start.turn_id,
        start.prompt,
        start.workspace_archive,
        start.workspace_digest,
        "synthetic:different-route",
        start.policy,
    )
    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        replay.start(changed_correlation)
    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        replay.start(_start("stable", archive=start.workspace_archive, policy=_READ_POLICY))
    assert calls == 0
    assert replay.close()


def test_agent_runner_replays_closed_operation_without_probe_or_authority(tmp_path: Path) -> None:
    request = ReviewRequest(
        "owner/repo",
        7,
        2,
        "a" * 40,
        "b" * 40,
        "diff.patch",
        review_lenses=["correctness"],
    )
    output = json.dumps(
        {
            "repository": request.repository,
            "pull_request": request.pull_request,
            "epoch": request.epoch,
            "head": request.head,
            "base": request.base,
            "status": "clear",
            "findings": [],
            "lineage": [],
        }
    )
    logical_operation = "review:replay"
    original = _host(
        tmp_path,
        (PiA2ScriptedTurn(output),),
        OneShotApiKeySupplier(lambda: bytearray(b"fixture")),
    )
    archive = workspace_archive(_config(tmp_path).working_directory)
    runner = PiNativeRunner(original, RunnerWorkspaces(archive))
    assert (
        runner.review("https://example.invalid/owner/repo.git", request, operation=logical_operation, attempt=1).status
        == "clear"
    )
    assert original.close()

    calls = 0

    def supply() -> bytearray:
        nonlocal calls
        calls += 1
        return bytearray(b"unused")

    replay = compose_pi_a2_scripted_runtime(
        config=_config(tmp_path),
        authority=PiA2DirectAuthority(
            ConnectionIdentity("direct", "anthropic", "synthetic", "api-key"),
            PersistentKeyOperations(tmp_path / "replay-runner-keys"),
            OneShotApiKeySupplier(supply),
        ),
        script=(PiA2ScriptedTurn("unused"),),
    )
    replay_runner = PiNativeRunner(replay, RunnerWorkspaces(archive))
    assert (
        replay_runner.review(
            "https://example.invalid/owner/repo.git", request, operation=logical_operation, attempt=1
        ).status
        == "clear"
    )
    assert calls == 0
    assert replay.close()


def test_agent_runner_refuses_legacy_prompt_reuse_without_new_authority_or_execution(tmp_path: Path) -> None:
    request = ReviewRequest(
        "owner/repo",
        7,
        2,
        "a" * 40,
        "b" * 40,
        "diff.patch",
        review_lenses=["correctness"],
    )
    output = json.dumps(
        {
            "repository": request.repository,
            "pull_request": request.pull_request,
            "epoch": request.epoch,
            "head": request.head,
            "base": request.base,
            "status": "clear",
            "findings": [],
            "lineage": [],
        }
    )
    calls = 0

    def supply() -> bytearray:
        nonlocal calls
        calls += 1
        return bytearray(b"fixture")

    host = _host(
        tmp_path,
        (PiA2ScriptedTurn(output), PiA2ScriptedTurn("must-not-run")),
        OneShotApiKeySupplier(supply),
    )
    archive = workspace_archive(_config(tmp_path).working_directory)
    logical_operation = "review:legacy-prompt"
    operation_id = f"pi:{sha256(f'{logical_operation}\0{1}'.encode()).hexdigest()}"
    identity = sha256(operation_id.encode()).hexdigest()
    current_payload = json.loads(encode_prompt("review", "https://example.invalid/owner/repo.git", request))
    legacy_payload = {
        key: value for key, value in current_payload.items() if key not in {"prompt_version", "response_contract"}
    }
    legacy_payload.update(
        {
            "response": "one JSON object matching the unchanged Hamsterdan result schema; no Markdown or prose",
            "schema_version": 1,
        }
    )
    legacy_prompt = json.dumps(legacy_payload, sort_keys=True, separators=(",", ":"))
    seeded = host.start(
        PiA2RuntimeStart(
            operation_id,
            EpisodeId(f"episode-{identity}"),
            TurnId(f"turn-{identity}"),
            legacy_prompt,
            archive,
            sha256(archive).hexdigest(),
            "synthetic:runner",
            _READ_POLICY,
        )
    )
    assert seeded.wait(1).outcome is TurnOutcome.COMPLETED
    assert seeded.close().verified and calls == 1

    runner = PiNativeRunner(host, RunnerWorkspaces(archive))
    with pytest.raises(AgentProtocolError) as caught:
        runner.review(
            "https://example.invalid/owner/repo.git",
            request,
            operation=logical_operation,
            attempt=1,
        )

    assert caught.value.result_category is AgentResultCategory.RUNTIME_LIFECYCLE
    assert calls == 1
    assert host.close()


def test_agent_runner_defers_its_default_deadline_to_the_finite_a2_runtime(tmp_path: Path) -> None:
    request = ReviewRequest(
        "owner/repo",
        7,
        2,
        "a" * 40,
        "b" * 40,
        "diff.patch",
        review_lenses=["correctness"],
    )
    host = _host(
        tmp_path,
        (PiA2ScriptedTurn("unused", delay_seconds=1),),
        OneShotApiKeySupplier(lambda: bytearray(b"fixture")),
    )
    archive = workspace_archive(_config(tmp_path).working_directory)
    runner = PiNativeRunner(host, RunnerWorkspaces(archive))

    with pytest.raises(AgentProtocolError) as caught:
        runner.review("https://example.invalid/owner/repo.git", request, operation="review:runtime-timeout", attempt=1)

    assert caught.value.result_category is AgentResultCategory.RUNTIME_LIFECYCLE
    assert not caught.value.timed_out
    assert host.close()


def test_cancellation_and_public_script_failure_fail_closed_with_cleanup_evidence(tmp_path: Path) -> None:
    host = _host(
        tmp_path / "cancel",
        (PiA2ScriptedTurn("unused", delay_seconds=10),),
        OneShotApiKeySupplier(lambda: bytearray(b"fixture")),
    )
    operation = host.start(_start("cancel", archive=workspace_archive(_config(tmp_path / "cancel").working_directory)))
    assert operation.cancel("host-request") is CancellationDisposition.REQUESTED
    assert operation.wait(1).outcome is TurnOutcome.CANCELLED
    assert operation.close().verified
    assert host.close() and host.close()

    # Provider attachment internals are Petrus-owned. The public scripted seam
    # preserves the application boundary: a failed turn must fail closed and
    # report unverified cleanup when the script says cleanup could not complete.
    failed = _host(
        tmp_path / "failure",
        (PiA2ScriptedTurn("", failure_code="scripted-failure", cleanup_verified=False),),
        OneShotApiKeySupplier(lambda: bytearray(b"fixture")),
    )
    replay = failed.start(_start("failed", archive=workspace_archive(_config(tmp_path / "failure").working_directory)))
    with pytest.raises(RuntimeProtocolError, match="host-cleanup-uncertain"):
        replay.wait()
    with pytest.raises(RuntimeProtocolError, match="host-cleanup-uncertain"):
        failed.close()


def test_restarted_executing_operation_is_indeterminate_without_authority(tmp_path: Path) -> None:
    config = _config(tmp_path)
    script = tmp_path / "crash.py"
    script.write_text(
        """import os
import sys
from pathlib import Path
from hashlib import sha256
from petrus.agenticus.connection.custody import ConnectionIdentity
from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.runtime.pi_a2_host import PiA2DirectAuthority, PiA2RuntimeHostConfig, PiA2RuntimePolicy, PiA2RuntimeStart, PiA2ScriptedTurn, compose_pi_a2_scripted_runtime
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.motus.execution.archive import workspace_archive
from hamsterdan.host.pi_a2 import PersistentKeyOperations

root, working, cli, node, package = map(Path, sys.argv[1:])
config = PiA2RuntimeHostConfig(
    state_root=root, working_directory=working, provider="anthropic", model="claude-sonnet-4-5",
    host_id="hamsterdan-test", capabilities=frozenset(ToolMethod),
    allowed_argv=frozenset({("/bin/true",)}), test_command=("/bin/true",), max_tool_calls=8,
    attachment_timeout=2, command_timeout=1, credential_ttl=1, wall_timeout=.5, cancellation_grace=.05,
    cli_path=str(cli), node_path=str(node), package_root=str(package),
)
authority = PiA2DirectAuthority(
    ConnectionIdentity("direct", "anthropic", "synthetic", "api-key"),
    PersistentKeyOperations(root.parent / "keys"), lambda: bytearray(b"fixture"),
)
host = compose_pi_a2_scripted_runtime(
    config=config, authority=authority, script=(PiA2ScriptedTurn("unused", delay_seconds=30),)
)
assert host.scripted_readiness().ready
archive = workspace_archive(working)
host.start(PiA2RuntimeStart(
    "crashed", EpisodeId("episode-crashed"), TurnId("turn-crashed"), "prompt",
    archive, sha256(archive).hexdigest(), "synthetic:crashed",
    PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_READ}), max_tool_calls=8),
))
os._exit(0)
"""
    )
    subprocess.run(
        (
            sys.executable,
            str(script),
            str(config.state_root),
            str(config.working_directory),
            str(config.cli_path),
            str(config.node_path),
            str(config.package_root),
        ),
        check=True,
        timeout=5,
    )

    calls = 0

    def supply() -> bytearray:
        nonlocal calls
        calls += 1
        return bytearray(b"unused")

    recovered = compose_pi_a2_scripted_runtime(
        config=_config(tmp_path),
        authority=PiA2DirectAuthority(
            ConnectionIdentity("direct", "anthropic", "synthetic", "api-key"),
            PersistentKeyOperations(tmp_path / "keys"),
            OneShotApiKeySupplier(supply),
        ),
        script=(PiA2ScriptedTurn("unused"),),
    )
    assert len(recovered.recovered_settlements) == 1
    assert recovered.recovered_settlements[0].outcome is TurnOutcome.INDETERMINATE
    with pytest.raises(RuntimeProtocolError, match="operation-indeterminate"):
        recovered.start(
            _start(
                "crashed",
                archive=workspace_archive(_config(tmp_path).working_directory),
                policy=PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_READ}), max_tool_calls=8),
            )
        )
    assert calls == 0
    # The crashed process cannot verify disposal of its executing attachment;
    # restart therefore preserves both indeterminacy and fail-closed cleanup.
    with pytest.raises(RuntimeProtocolError, match="host-cleanup-uncertain"):
        recovered.close()
