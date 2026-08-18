"""Fail-closed host composition and topology-labeled state ownership."""

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
from hamsterdan.host.application import PrReadinessApplication
from hamsterdan.host.binding import ensure_instance_binding, preflight_topology, read_instance_binding
from hamsterdan.host.topology import PRODUCTION, V5, select_readiness_composition
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


def test_selector_makes_v5_the_only_runtime_composition_and_rejects_every_unknown_value() -> None:
    assert select_readiness_composition(None) is V5
    assert select_readiness_composition("production") is V5
    assert select_readiness_composition("v5") is V5
    assert PRODUCTION.application_factory is PrReadinessApplication
    assert V5.application_factory is PrReadinessV5Application

    for malformed in ("", "V5", "legacy", "production ", "sharded-v5"):
        with pytest.raises(ValueError, match="readiness topology"):
            select_readiness_composition(malformed)


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
def test_v5_inactive_adapter_returns_exact_typed_blocked_terminal_without_provider_call(
    definition,
    work,
    expected,
) -> None:
    invocation = ActivityInvocation(definition.declaration.name, input={"work": work.dump()})

    encoded = V5.inactive_result(definition.declaration.name, invocation, definition)

    assert encoded == definition.converter.encode(expected, definition.result)


def test_new_bindings_are_explicit_and_cross_topology_reopen_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "application"
    ensure_instance_binding(root, "v5", INSTANCE, "owner/repo", 7)

    binding = read_instance_binding(root / "binding.json")
    assert binding.topology == "v5" and not binding.legacy
    assert json.loads((root / "binding.json").read_text()) == {
        "instance_id": INSTANCE,
        "pull_request": 7,
        "repository": "owner/repo",
        "topology": "v5",
    }
    with pytest.raises(RuntimeError, match="different PR Instance or topology"):
        ensure_instance_binding(root, "production", INSTANCE, "owner/repo", 7)


def test_exact_legacy_binding_is_production_only_and_migrates_atomically(tmp_path: Path) -> None:
    root = tmp_path / "application"
    root.mkdir()
    (root / "binding.json").write_text(
        json.dumps({"instance_id": INSTANCE, "repository": "owner/repo", "pull_request": 7}),
        encoding="utf-8",
    )
    (root / "history.jsonl").write_text("canonical production history", encoding="utf-8")

    with pytest.raises(RuntimeError, match="different PR Instance or topology"):
        ensure_instance_binding(root, "v5", INSTANCE, "owner/repo", 7)
    ensure_instance_binding(root, "production", INSTANCE, "owner/repo", 7)

    migrated = read_instance_binding(root / "binding.json")
    assert migrated.topology == "production" and not migrated.legacy
    assert (root / "history.jsonl").read_text() == "canonical production history"


def test_preflight_rejects_mixed_or_unknown_state_before_composition(tmp_path: Path) -> None:
    production = tmp_path / "applications/44/31/7"
    v5 = tmp_path / "applications/44/31/8"
    ensure_instance_binding(production, "production", INSTANCE, "owner/repo", 7)
    ensure_instance_binding(v5, "v5", "github:44:31:pr:8", "owner/repo", 8)
    (production / "history.jsonl").write_text("production", encoding="utf-8")
    (v5 / "history.jsonl").write_text("v5", encoding="utf-8")

    with pytest.raises(RuntimeError, match="selected readiness topology"):
        preflight_topology(tmp_path, "production")
    with pytest.raises(RuntimeError, match="selected readiness topology"):
        preflight_topology(tmp_path, "v5")


def test_preflight_rejects_unbound_history_and_symlinked_state_ancestry(tmp_path: Path) -> None:
    unbound = tmp_path / "unbound/applications/44/31/7"
    unbound.mkdir(parents=True)
    (unbound / "history.jsonl").write_text("history", encoding="utf-8")
    with pytest.raises(RuntimeError, match="binding is unreadable or malformed"):
        preflight_topology(tmp_path / "unbound", "production")

    outside = tmp_path / "outside/31/7"
    ensure_instance_binding(outside, "production", INSTANCE, "owner/repo", 7)
    (outside / "history.jsonl").write_text("history", encoding="utf-8")
    applications = tmp_path / "linked/applications"
    applications.mkdir(parents=True)
    (applications / "44").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(RuntimeError, match="state root is malformed"):
        preflight_topology(tmp_path / "linked", "production")

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "applications").symlink_to(tmp_path / "missing", target_is_directory=True)
    with pytest.raises(RuntimeError, match="application state root is malformed"):
        preflight_topology(broken, "production")

    empty_outside = tmp_path / "empty-outside"
    empty_outside.mkdir()
    empty_applications = tmp_path / "empty-linked/applications"
    empty_applications.mkdir(parents=True)
    (empty_applications / "44").symlink_to(empty_outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="state root is malformed"):
        ensure_instance_binding(empty_applications / "44/31/7", "production", INSTANCE, "owner/repo", 7)

    symlinked_history = tmp_path / "symlinked-history/applications/44/31/7"
    ensure_instance_binding(symlinked_history, "production", INSTANCE, "owner/repo", 7)
    target = tmp_path / "history-target"
    target.write_text("history", encoding="utf-8")
    (symlinked_history / "history.jsonl").symlink_to(target)
    with pytest.raises(RuntimeError, match="History is unreadable or malformed"):
        preflight_topology(tmp_path / "symlinked-history", "production")
