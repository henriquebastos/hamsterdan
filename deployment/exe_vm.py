#!/usr/bin/env python3
"""Select or explicitly create Hamsterdan's owned exe.dev VM."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, cast

API_URL = "https://exe.dev/exec"
GIB = 1024**3
NAME = re.compile(r"[a-z][a-z0-9-]{0,62}")


class ExeError(RuntimeError):
    """A bounded exe.dev failure that contains no credential value."""


@dataclass(frozen=True)
class VmSpec:
    name: str
    ownership_tag: str
    cpus: int
    memory_gib: int
    disk_gib: int
    image: str

    def __post_init__(self) -> None:
        if NAME.fullmatch(self.name) is None or NAME.fullmatch(self.ownership_tag) is None:
            raise ValueError("exe.dev VM names and tags must be lowercase DNS labels")

    @property
    def create_command(self) -> str:
        return (
            f"new --name={self.name} --cpu={self.cpus} --memory={self.memory_gib}GB --disk={self.disk_gib}GB "
            f"--tag={self.ownership_tag} --no-email"
        )


DEFAULT_SPEC = VmSpec(
    name="hamsterdan-prod",
    ownership_tag="hamsterdan",
    cpus=2,
    memory_gib=4,
    disk_gib=20,
    image="boldsoftware/exeuntu",
)


def _integer(value: Mapping[str, Any], key: str) -> int:
    observed = value.get(key)
    if isinstance(observed, bool) or not isinstance(observed, int):
        raise ExeError(f"exe.dev inventory field {key} is malformed")
    return observed


def _string(value: Mapping[str, Any], key: str, *, empty: bool = False) -> str:
    observed = value.get(key)
    if not isinstance(observed, str) or (not observed and not empty):
        raise ExeError(f"exe.dev inventory field {key} is malformed")
    return observed


@dataclass(frozen=True)
class Vm:
    name: str
    status: str
    tags: tuple[str, ...]
    cpus: int
    memory_bytes: int
    disk_bytes: int
    image: str
    ssh_host: str

    @classmethod
    def from_api(cls, value: object) -> Vm:
        if not isinstance(value, dict):
            raise ExeError("exe.dev inventory contains a malformed VM")
        fields = cast(dict[str, Any], value)
        raw_tags = fields.get("tags")
        if not isinstance(raw_tags, list) or not all(isinstance(tag, str) for tag in raw_tags):
            raise ExeError("exe.dev inventory field tags is malformed")
        tags = cast(list[str], raw_tags)
        return cls(
            name=_string(fields, "vm_name"),
            status=_string(fields, "status"),
            tags=tuple(tags),
            cpus=_integer(fields, "allocated_cpus"),
            memory_bytes=_integer(fields, "memory_capacity_bytes"),
            disk_bytes=_integer(fields, "disk_capacity_bytes"),
            image=_string(fields, "image"),
            ssh_host=_string(fields, "ssh_host", empty=True),
        )


def api_call(command: str, *, environment: Mapping[str, str] | None = None) -> object:
    env = os.environ if environment is None else environment
    token = env.get("EXE_DEV_API_TOKEN")
    if not token:
        raise ExeError("EXE_DEV_API_TOKEN is required")
    request = urllib.request.Request(
        API_URL,
        data=command.encode(),
        headers={"Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read(1024).decode(errors="replace").strip().replace(token, "[redacted]")
        suffix = f": {detail}" if detail else ""
        raise ExeError(f"exe.dev API rejected {command.split()[0]} with HTTP {error.code}{suffix}") from error
    except (OSError, TimeoutError, json.JSONDecodeError) as error:
        raise ExeError(f"exe.dev API request failed for {command.split()[0]}") from error


def list_vms() -> tuple[Vm, ...]:
    response = api_call("ls --l")
    if not isinstance(response, dict):
        raise ExeError("exe.dev inventory response is malformed")
    inventory = cast(dict[str, Any], response).get("vms")
    if not isinstance(inventory, list):
        raise ExeError("exe.dev inventory response is malformed")
    return tuple(Vm.from_api(value) for value in cast(list[object], inventory))


def _assert_owned_shape(vm: Vm, spec: VmSpec) -> Vm:
    if spec.ownership_tag not in vm.tags:
        raise ExeError(f"VM {spec.name} does not carry the {spec.ownership_tag!r} ownership tag")
    if vm.cpus != spec.cpus:
        raise ExeError(f"VM {spec.name} has an unexpected CPU allocation")
    if vm.memory_bytes != spec.memory_gib * GIB:
        raise ExeError(f"VM {spec.name} has an unexpected memory allocation")
    if vm.disk_bytes != spec.disk_gib * GIB:
        raise ExeError(f"VM {spec.name} has an unexpected disk allocation")
    if vm.image != spec.image:
        raise ExeError(f"VM {spec.name} has an unexpected base image")
    expected_host = f"{spec.name}.exe.xyz"
    if vm.ssh_host and vm.ssh_host != expected_host:
        raise ExeError(f"VM {spec.name} has an unexpected SSH endpoint")
    return vm


def find_owned_vm(spec: VmSpec) -> Vm | None:
    matches = [vm for vm in list_vms() if vm.name == spec.name]
    if not matches:
        return None
    if len(matches) != 1:
        raise ExeError(f"exe.dev returned more than one VM named {spec.name}")
    return _assert_owned_shape(matches[0], spec)


def ensure_vm(spec: VmSpec, *, confirm_create: str | None) -> Vm:
    existing = find_owned_vm(spec)
    if existing is not None:
        return existing
    if confirm_create != spec.name:
        raise ExeError(f"creating {spec.name} requires --confirm-create {spec.name}")
    creation_error: ExeError | None = None
    try:
        api_call(spec.create_command)
    except ExeError as error:
        creation_error = error
    observed = find_owned_vm(spec)
    if observed is not None:
        return observed
    if creation_error is not None:
        raise creation_error
    raise ExeError(f"exe.dev did not return the newly created VM {spec.name}")


def wait_for_running_vm(
    spec: VmSpec,
    *,
    timeout: float = 180,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Vm:
    deadline = clock() + timeout
    while clock() < deadline:
        observed = find_owned_vm(spec)
        if observed is not None and observed.status == "running" and observed.ssh_host:
            return observed
        sleep(2)
    raise ExeError(f"VM {spec.name} did not become ready within {timeout:g} seconds")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show the bounded exe.dev inventory")
    ensure = commands.add_parser("ensure", help="reuse or explicitly create the owned VM")
    ensure.add_argument("--confirm-create")
    return value


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "list":
            result: object = [asdict(vm) for vm in list_vms()]
        else:
            result = asdict(ensure_vm(DEFAULT_SPEC, confirm_create=arguments.confirm_create))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ExeError as error:
        print(f"exe.dev refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
