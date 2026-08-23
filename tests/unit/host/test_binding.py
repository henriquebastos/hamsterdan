"""Fail-closed V5 state ownership and inactive publication terminals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from petrus.motus.activity import ActivityInvocation, activity

from hamsterdan.contracts.readiness_v5 import (
    ABlocked,
    AnnounceReq,
    DashBlocked,
    DashReq,
    ReplyBlocked,
    ReplyReq,
)
from hamsterdan.host.binding import ensure_instance_binding, preflight_v5_state, read_instance_binding
from hamsterdan.host.v5.application import PrReadinessV5Application
from hamsterdan.readiness.net_v5.gating import VariantPayloadConverter

INSTANCE = "github:44:31:pr:7"


@activity(name="reply_gate", converter=VariantPayloadConverter())
def forbidden_reply(work: ReplyReq) -> ReplyBlocked:
    raise AssertionError(f"provider reply gate executed for {work.id}")


@activity(name="dash_gate", converter=VariantPayloadConverter())
def forbidden_dash(work: DashReq) -> DashBlocked:
    raise AssertionError(f"provider dashboard gate executed for {work.digest}")


@activity(name="announce_gate", converter=VariantPayloadConverter())
def forbidden_announce(work: AnnounceReq) -> ABlocked:
    raise AssertionError(f"provider announce gate executed for {work.op}")


@pytest.mark.parametrize(
    ("definition", "work", "expected"),
    [
        (
            forbidden_reply,
            ReplyReq(id="comment-7", text="safe reply"),
            ReplyBlocked(id="comment-7", text="safe reply"),
        ),
        (
            forbidden_dash,
            DashReq(entries=["one"], digest="d1", desired_entries=["one", "two"], desired_digest="d2"),
            DashBlocked(entries=["one"], digest="d1", desired_entries=["one", "two"], desired_digest="d2"),
        ),
        (
            forbidden_announce,
            AnnounceReq(op="ready:h1:i3", incarnation=3, head="h1", base="b1", policy="p1"),
            ABlocked(incarnation=3, head="h1", base="b1", policy="p1"),
        ),
    ],
)
def test_inactive_adapter_returns_exact_typed_blocked_terminal_without_provider_call(
    definition,
    work,
    expected,
) -> None:
    invocation = ActivityInvocation(definition.declaration.name, input={"work": work.dump()})

    encoded = PrReadinessV5Application.inactive_activity_result(definition.declaration.name, invocation, definition)

    assert encoded == definition.converter.encode(expected, definition.result)


def test_new_bindings_are_always_explicit_v5_and_identity_mismatches_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "application"
    ensure_instance_binding(root, INSTANCE, "owner/repo", 7)

    binding = read_instance_binding(root / "binding.json")
    assert binding.topology == "v5" and not binding.legacy
    assert json.loads((root / "binding.json").read_text()) == {
        "instance_id": INSTANCE,
        "pull_request": 7,
        "repository": "owner/repo",
        "topology": "v5",
    }
    with pytest.raises(RuntimeError, match="different PR Instance or topology"):
        ensure_instance_binding(root, INSTANCE, "owner/other", 7)


@pytest.mark.parametrize("explicit", [False, True], ids=["unlabeled", "production"])
def test_former_topology_binding_fails_closed_without_mutation(tmp_path: Path, explicit: bool) -> None:
    root = tmp_path / "application"
    root.mkdir()
    payload: dict[str, object] = {
        "instance_id": INSTANCE,
        "repository": "owner/repo",
        "pull_request": 7,
    }
    if explicit:
        payload["topology"] = "production"
    encoded = json.dumps(payload)
    (root / "binding.json").write_text(encoded, encoding="utf-8")
    (root / "history.jsonl").write_text("former topology history", encoding="utf-8")

    with pytest.raises(RuntimeError, match="different PR Instance or topology"):
        ensure_instance_binding(root, INSTANCE, "owner/repo", 7)

    assert (root / "binding.json").read_text(encoding="utf-8") == encoded
    assert (root / "history.jsonl").read_text(encoding="utf-8") == "former topology history"


def test_preflight_accepts_only_v5_state(tmp_path: Path) -> None:
    v5 = tmp_path / "applications/44/31/8"
    ensure_instance_binding(v5, "github:44:31:pr:8", "owner/repo", 8)
    (v5 / "history.jsonl").write_text("v5", encoding="utf-8")
    preflight_v5_state(tmp_path)

    former = tmp_path / "applications/44/31/7"
    former.mkdir()
    (former / "binding.json").write_text(
        json.dumps(
            {
                "instance_id": INSTANCE,
                "repository": "owner/repo",
                "pull_request": 7,
                "topology": "production",
            }
        ),
        encoding="utf-8",
    )
    (former / "history.jsonl").write_text("production", encoding="utf-8")

    with pytest.raises(RuntimeError, match="not compatible with the V5 readiness topology"):
        preflight_v5_state(tmp_path)


def test_preflight_rejects_unbound_history_and_symlinked_state_ancestry(tmp_path: Path) -> None:
    unbound = tmp_path / "unbound/applications/44/31/7"
    unbound.mkdir(parents=True)
    (unbound / "history.jsonl").write_text("history", encoding="utf-8")
    with pytest.raises(RuntimeError, match="binding is unreadable or malformed"):
        preflight_v5_state(tmp_path / "unbound")

    outside = tmp_path / "outside/31/7"
    ensure_instance_binding(outside, INSTANCE, "owner/repo", 7)
    (outside / "history.jsonl").write_text("history", encoding="utf-8")
    applications = tmp_path / "linked/applications"
    applications.mkdir(parents=True)
    (applications / "44").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(RuntimeError, match="state root is malformed"):
        preflight_v5_state(tmp_path / "linked")

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "applications").symlink_to(tmp_path / "missing", target_is_directory=True)
    with pytest.raises(RuntimeError, match="application state root is malformed"):
        preflight_v5_state(broken)

    empty_outside = tmp_path / "empty-outside"
    empty_outside.mkdir()
    empty_applications = tmp_path / "empty-linked/applications"
    empty_applications.mkdir(parents=True)
    (empty_applications / "44").symlink_to(empty_outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="state root is malformed"):
        ensure_instance_binding(empty_applications / "44/31/7", INSTANCE, "owner/repo", 7)

    symlinked_history = tmp_path / "symlinked-history/applications/44/31/7"
    ensure_instance_binding(symlinked_history, INSTANCE, "owner/repo", 7)
    target = tmp_path / "history-target"
    target.write_text("history", encoding="utf-8")
    (symlinked_history / "history.jsonl").symlink_to(target)
    with pytest.raises(RuntimeError, match="History is unreadable or malformed"):
        preflight_v5_state(tmp_path / "symlinked-history")
