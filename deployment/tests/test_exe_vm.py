from __future__ import annotations

from dataclasses import replace

import pytest

from deployment import exe_vm

TEST_SPEC = replace(exe_vm.DEFAULT_SPEC, name="example-vm")


def vm_payload(*, tags: list[str] | None = None) -> dict[str, object]:
    return {
        "allocated_cpus": 2,
        "disk_capacity_bytes": 20 * 1024**3,
        "image": "boldsoftware/exeuntu",
        "memory_capacity_bytes": 4 * 1024**3,
        "ssh_host": "example-vm.exe.xyz",
        "status": "running",
        "tags": ["hamsterdan"] if tags is None else tags,
        "vm_name": "example-vm",
    }


def test_ensure_reuses_only_the_exact_owned_vm(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[str] = []

    def fake_call(command: str) -> object:
        commands.append(command)
        return {"vms": [vm_payload()]}

    monkeypatch.setattr(exe_vm, "api_call", fake_call)

    observed = exe_vm.ensure_vm(TEST_SPEC, confirm_create=None)

    assert observed.name == "example-vm"
    assert observed.ssh_host == "example-vm.exe.xyz"
    assert commands == ["ls --l"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("tags", ["another-project"], "ownership tag"),
        ("allocated_cpus", 4, "CPU allocation"),
        ("memory_capacity_bytes", 2 * 1024**3, "memory allocation"),
        ("disk_capacity_bytes", 10 * 1024**3, "disk allocation"),
    ],
)
def test_ensure_refuses_same_name_with_a_different_ownership_or_shape(
    field: str,
    value: object,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = vm_payload()
    payload[field] = value
    monkeypatch.setattr(exe_vm, "api_call", lambda _: {"vms": [payload]})

    with pytest.raises(exe_vm.ExeError, match=message):
        exe_vm.ensure_vm(TEST_SPEC, confirm_create=None)


def test_creation_requires_exact_confirmation_and_rereads_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[str] = []
    responses: list[object] = [{"vms": []}, {"vm_name": "example-vm"}, {"vms": [vm_payload()]}]

    def fake_call(command: str) -> object:
        commands.append(command)
        return responses.pop(0)

    monkeypatch.setattr(exe_vm, "api_call", fake_call)

    with pytest.raises(exe_vm.ExeError, match="--confirm-create example-vm"):
        exe_vm.ensure_vm(TEST_SPEC, confirm_create=None)
    assert commands == ["ls --l"]

    commands.clear()
    responses[:] = [{"vms": []}, {"vm_name": "example-vm"}, {"vms": [vm_payload()]}]
    observed = exe_vm.ensure_vm(TEST_SPEC, confirm_create="example-vm")

    assert observed.name == "example-vm"
    assert commands == [
        "ls --l",
        ("new --name=example-vm --cpu=2 --memory=4GB --disk=20GB --tag=hamsterdan --no-email"),
        "ls --l",
    ]


def test_creation_rereads_after_an_ambiguous_api_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    responses: list[object | Exception] = [
        {"vms": []},
        exe_vm.ExeError("exe.dev API request failed"),
        {"vms": [vm_payload()]},
    ]

    def fake_call(_: str) -> object:
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(exe_vm, "api_call", fake_call)

    assert exe_vm.ensure_vm(TEST_SPEC, confirm_create="example-vm").name == "example-vm"


def test_wait_for_running_vm_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def fake_find(_: exe_vm.VmSpec) -> exe_vm.Vm:
        nonlocal calls
        calls += 1
        payload = vm_payload()
        payload["status"] = "creating"
        return exe_vm.Vm.from_api(payload)

    clock_values = iter((0.0, 0.0, 4.0, 6.0))
    monkeypatch.setattr(exe_vm, "find_owned_vm", fake_find)

    with pytest.raises(exe_vm.ExeError, match="did not become ready"):
        exe_vm.wait_for_running_vm(
            TEST_SPEC,
            timeout=5,
            sleep=lambda _: None,
            clock=lambda: next(clock_values),
        )

    assert calls == 2
