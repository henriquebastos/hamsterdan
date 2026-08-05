from __future__ import annotations

import inspect
import os
import stat
from pathlib import Path

import pytest
from petrus.agenticus.connection.key import KeyContext, KeyOperationError
from petrus.agenticus.runtime.pi_a2_host import PiA2RuntimeHost

from hamsterdan.host.pi_a2 import OneShotApiKeySupplier, PersistentKeyOperations, compose_owned_pi_a2


def test_persistent_keys_authenticate_context_tamper_and_erase(tmp_path: Path) -> None:
    context = KeyContext("synthetic", 1, 1)
    sealed = PersistentKeyOperations(tmp_path / "keys").seal(context, bytearray(b"synthetic secret"))
    recreated = PersistentKeyOperations(tmp_path / "keys")
    assert recreated.open(context, sealed) == bytearray(b"synthetic secret")
    with pytest.raises(KeyOperationError):
        recreated.open(KeyContext("synthetic", 2, 1), sealed)
    with pytest.raises(KeyOperationError):
        recreated.open(context, sealed[:-1] + bytes([sealed[-1] ^ 1]))
    assert recreated.erase("synthetic").erased
    with pytest.raises(KeyOperationError):
        recreated.open(context, sealed)


def test_new_key_is_synced_before_sealing_returns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    syncs: list[str] = []
    fsync = os.fsync

    def observe(descriptor: int) -> None:
        syncs.append("directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file")
        fsync(descriptor)

    monkeypatch.setattr(os, "fsync", observe)
    PersistentKeyOperations(tmp_path / "keys").seal(KeyContext("synthetic", 1, 1), bytearray(b"synthetic"))

    assert syncs == ["file", "directory"]


def test_one_shot_supplier_transfers_mutable_buffer_once() -> None:
    source = bytearray(b"synthetic")
    calls = 0

    def load() -> bytearray:
        nonlocal calls
        calls += 1
        return source

    supplier = OneShotApiKeySupplier(load)
    assert supplier() is source
    with pytest.raises(RuntimeError, match="already spent"):
        supplier()
    assert calls == 1


def test_owned_composition_and_probe_do_not_request_authority(tmp_path: Path) -> None:
    host = compose_owned_pi_a2(tmp_path)
    try:
        assert isinstance(host, PiA2RuntimeHost)
        assert host.descriptor.identity.name == "pi.native.a2.local"
        assert host.authority.connection.profile == "api-key"
        assert not host.authority_requested
        host.probe()
        assert not host.authority_requested
    finally:
        host.close()


def test_production_composition_does_not_inject_provider_or_client_factory() -> None:
    source = inspect.getsource(compose_owned_pi_a2)
    assert "client_factory=" not in source
    assert "provider=" not in source.partition("compose_pi_a2_runtime(")[2]
    assert "compose_pi_a2_runtime(config=config, authority=authority)" in source
