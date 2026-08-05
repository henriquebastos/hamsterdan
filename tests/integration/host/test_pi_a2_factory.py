from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
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
    compose_pi_a2_runtime,
)
from petrus.agenticus.thread.continuation import Continuation
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment

from hamsterdan.agents import PiNativeRunner, ReviewRequest
from hamsterdan.host.pi_a2 import OneShotApiKeySupplier, PersistentKeyOperations

_SESSION = "11111111-1111-4111-8111-111111111111"
_READ_POLICY = PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH}), max_tool_calls=8)
_CODE_POLICY = PiA2RuntimePolicy(
    frozenset({ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH, ToolMethod.WORKSPACE_WRITE}),
    max_tool_calls=8,
    writable_roots=frozenset({"."}),
)


@dataclass
class Plan:
    text: str = "answer"
    write: bool = False
    read: str | None = None
    block: bool = False
    error: str | None = None


class Client:
    def __init__(self, plan: Plan, prior=None) -> None:
        self.plan, self.prior = plan, prior
        self.entered = threading.Event()

    def run(self, gateway, invocation, current, deadline):
        self.entered.set()
        while self.plan.block and current() and time.monotonic() < deadline:
            time.sleep(0.005)
        if self.plan.error is not None:
            raise RuntimeProtocolError(self.plan.error)
        coordinates = invocation.attachment.coordinates()
        common = {
            "version": 1,
            "episode_id": coordinates.episode_id,
            "attachment_id": coordinates.attachment_id,
            "attachment_epoch": coordinates.attachment_epoch,
            "grant_epoch": invocation.grant_epoch,
        }
        if self.plan.read is not None:
            result = gateway.submit(
                {
                    **common,
                    "call_id": "read",
                    "method": "workspace_read",
                    "params": {"path": self.plan.read},
                }
            )
            assert result.ok
        if self.plan.write:
            result = gateway.submit(
                {
                    **common,
                    "call_id": "write",
                    "method": "workspace_write",
                    "params": {"path": "output.txt", "content": "changed"},
                }
            )
            assert result.ok
        session = self.prior.session_jsonl if self.prior is not None else _session()
        body = session + json.dumps({"type": "message", "body": "next"}, separators=(",", ":")).encode() + b"\n"
        return pi._HelperResult(pi._Candidate(_SESSION, self.plan.text, body), None, "turn-completed")

    def close(self) -> bool:
        return True


class Factory:
    def __init__(self, *plans: Plan) -> None:
        self.plans = list(plans) or [Plan()]
        self.clients: list[Client] = []
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        client = Client(self.plans.pop(0), kwargs["prior"])
        self.clients.append(client)
        return client


class AttachFailure(LocalProcessEnvironment):
    def attach(self, lease, workspace_archive_bytes, input_digest):
        raise RuntimeError("synthetic attach failure")


def _session() -> bytes:
    return json.dumps({"type": "session", "version": 3, "id": _SESSION}, separators=(",", ":")).encode() + b"\n"


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
    factory: Factory,
    supplier: OneShotApiKeySupplier,
    *,
    provider: LocalProcessEnvironment | None = None,
) -> PiA2RuntimeHost:
    authority = PiA2DirectAuthority(
        ConnectionIdentity("direct", "anthropic", "synthetic", "api-key"),
        PersistentKeyOperations(root / "keys"),
        supplier,
    )
    host = compose_pi_a2_runtime(
        config=_config(root),
        authority=authority,
        provider=provider,
        client_factory=factory,
    )
    assert host.probe().disposition is ProbeDisposition.READY
    return host


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
    factory = Factory(Plan("first", write=True), Plan("second", read="output.txt"))
    host = _host(tmp_path, factory, supplier)
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
    assert factory.calls[1]["prior"].session_id == _SESSION  # type: ignore[union-attr]
    assert set(supplied) == {0}
    assert first_operation.close().verified
    assert host.close()
    assert host.close()


def test_terminal_replay_and_changed_work_conflict_use_no_authority(tmp_path: Path) -> None:
    supplier = OneShotApiKeySupplier(lambda: bytearray(b"fixture"))
    host = _host(tmp_path, Factory(), supplier)
    start = _start("stable", archive=workspace_archive(_config(tmp_path).working_directory))
    expected = host.start(start).wait(1)
    assert host.close()

    calls = 0

    def replay_supply() -> bytearray:
        nonlocal calls
        calls += 1
        return bytearray(b"unused")

    replay = compose_pi_a2_runtime(
        config=_config(tmp_path),
        authority=PiA2DirectAuthority(
            ConnectionIdentity("direct", "anthropic", "synthetic", "api-key"),
            PersistentKeyOperations(tmp_path / "replay-keys"),
            OneShotApiKeySupplier(replay_supply),
        ),
        provider=LocalProcessEnvironment(),
        client_factory=Factory(),
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
    operation_id = "pi:" + "1" * 64
    original = _host(
        tmp_path,
        Factory(Plan(output)),
        OneShotApiKeySupplier(lambda: bytearray(b"fixture")),
    )
    archive = workspace_archive(_config(tmp_path).working_directory)
    runner = PiNativeRunner(original, RunnerWorkspaces(archive))
    runner.route_operation(operation_id)
    assert runner.review("https://example.invalid/owner/repo.git", request).status == "clear"
    assert original.close()

    calls = 0

    def supply() -> bytearray:
        nonlocal calls
        calls += 1
        return bytearray(b"unused")

    replay = compose_pi_a2_runtime(
        config=_config(tmp_path),
        authority=PiA2DirectAuthority(
            ConnectionIdentity("direct", "anthropic", "synthetic", "api-key"),
            PersistentKeyOperations(tmp_path / "replay-runner-keys"),
            OneShotApiKeySupplier(supply),
        ),
    )
    replay_runner = PiNativeRunner(replay, RunnerWorkspaces(archive))
    replay_runner.route_operation(operation_id)
    assert replay_runner.review("https://example.invalid/owner/repo.git", request).status == "clear"
    assert calls == 0
    assert replay.close()


def test_cancellation_partial_rollback_and_idempotent_close(tmp_path: Path) -> None:
    host = _host(
        tmp_path / "cancel",
        Factory(Plan(block=True)),
        OneShotApiKeySupplier(lambda: bytearray(b"fixture")),
    )
    operation = host.start(_start("cancel", archive=workspace_archive(_config(tmp_path / "cancel").working_directory)))
    assert operation.cancel("host-request") is CancellationDisposition.REQUESTED
    assert operation.wait(1).outcome is TurnOutcome.CANCELLED
    assert operation.close().verified
    assert host.close() and host.close()

    failed = _host(
        tmp_path / "failure",
        Factory(),
        OneShotApiKeySupplier(lambda: bytearray(b"fixture")),
        provider=AttachFailure(),
    )
    with pytest.raises(RuntimeProtocolError, match="runtime-start-failed"):
        failed.start(_start("failed", archive=workspace_archive(_config(tmp_path / "failure").working_directory)))
    replay = failed.start(_start("failed", archive=workspace_archive(_config(tmp_path / "failure").working_directory)))
    assert replay.wait().outcome is TurnOutcome.FAILED
    assert replay.close().verified
    assert failed.close()


def test_restarted_executing_operation_is_indeterminate_without_authority(tmp_path: Path) -> None:
    config = _config(tmp_path)
    script = tmp_path / "crash.py"
    script.write_text(
        """import os
import sys
import time
from pathlib import Path
from hashlib import sha256
from petrus.agenticus.connection.custody import ConnectionIdentity
from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.runtime.pi_a2_host import PiA2DirectAuthority, PiA2RuntimeHostConfig, PiA2RuntimePolicy, PiA2RuntimeStart, compose_pi_a2_runtime
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.motus.execution.archive import workspace_archive
from hamsterdan.host.pi_a2 import PersistentKeyOperations

class Client:
    def run(self, gateway, invocation, current, deadline):
        while current() and time.monotonic() < deadline:
            time.sleep(0.01)
    def close(self):
        return True
class Factory:
    def create(self, **kwargs):
        return Client()

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
host = compose_pi_a2_runtime(config=config, authority=authority, client_factory=Factory())
host.probe()
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

    recovered = compose_pi_a2_runtime(
        config=_config(tmp_path),
        authority=PiA2DirectAuthority(
            ConnectionIdentity("direct", "anthropic", "synthetic", "api-key"),
            PersistentKeyOperations(tmp_path / "keys"),
            OneShotApiKeySupplier(supply),
        ),
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
    assert recovered.close()
