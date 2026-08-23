"""Topology-labeled ownership for one durable PR Instance root."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

TopologyIdentity = Literal["production", "v5"]

_BINDING_LIMIT = 4096
_IDENTIFIER_LIMIT = 1024
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_LEGACY_FIELDS = {"instance_id", "repository", "pull_request"}
_FIELDS = {*_LEGACY_FIELDS, "topology"}


@dataclass(frozen=True)
class InstanceBinding:
    topology: TopologyIdentity
    instance_id: str
    repository: str
    pull_request: int
    legacy: bool = False

    def payload(self) -> dict[str, object]:
        return {
            "instance_id": self.instance_id,
            "pull_request": self.pull_request,
            "repository": self.repository,
            "topology": self.topology,
        }


def parse_instance_binding(value: object) -> InstanceBinding:
    if not isinstance(value, dict) or set(value) not in (_LEGACY_FIELDS, _FIELDS):
        raise ValueError("Instance state binding is malformed")
    legacy = set(value) == _LEGACY_FIELDS
    topology = "production" if legacy else value.get("topology")
    instance_id, repository, pull_request = (
        value.get("instance_id"),
        value.get("repository"),
        value.get("pull_request"),
    )
    if (
        topology not in {"production", "v5"}
        or not isinstance(instance_id, str)
        or not 0 < len(instance_id.encode()) <= _IDENTIFIER_LIMIT
        or not instance_id.isascii()
        or not instance_id.isprintable()
        or not isinstance(repository, str)
        or _REPOSITORY.fullmatch(repository) is None
        or type(pull_request) is not int
        or pull_request <= 0
    ):
        raise ValueError("Instance state binding is malformed")
    return InstanceBinding(cast(TopologyIdentity, topology), instance_id, repository, pull_request, legacy)


def read_instance_binding(path: Path) -> InstanceBinding:
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= _BINDING_LIMIT:
            raise ValueError
        value = json.loads(path.read_text(encoding="utf-8"))
        return parse_instance_binding(value)
    except OSError, UnicodeError, json.JSONDecodeError, ValueError:
        raise RuntimeError("Instance state binding is unreadable or malformed") from None


def _require_real_directory_ancestry(path: Path) -> None:
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise RuntimeError("state root is malformed") from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise RuntimeError("state root is malformed")


def _require_regular_history(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    except OSError:
        raise RuntimeError("History is unreadable or malformed") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError("History is unreadable or malformed")


def _write_binding(path: Path, binding: InstanceBinding) -> None:
    encoded = json.dumps(binding.payload(), sort_keys=True, separators=(",", ":"))
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".binding.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_instance_binding(
    root: Path,
    instance_id: str,
    repository: str,
    pull_request: int,
) -> InstanceBinding:
    expected = parse_instance_binding(
        {
            "instance_id": instance_id,
            "pull_request": pull_request,
            "repository": repository,
            "topology": "v5",
        }
    )
    _require_real_directory_ancestry(root)
    binding_path = root / "binding.json"
    if binding_path.exists() or binding_path.is_symlink():
        observed = read_instance_binding(binding_path)
        if (
            observed.topology,
            observed.instance_id,
            observed.repository,
            observed.pull_request,
        ) != ("v5", instance_id, repository, pull_request):
            raise RuntimeError("state root belongs to a different PR Instance or topology")
        _require_regular_history(root / "history.jsonl")
        return expected
    history_path = root / "history.jsonl"
    if history_path.exists() or history_path.is_symlink():
        raise RuntimeError("History has no subject binding")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write_binding(binding_path, expected)
    return expected


def preflight_v5_state(state_path: Path) -> None:
    applications = state_path / "applications"
    if not applications.exists() and not applications.is_symlink():
        return
    if applications.is_symlink() or not applications.is_dir():
        raise RuntimeError("application state root is malformed")
    try:
        for installation_path in sorted(applications.iterdir()):
            _require_real_directory_ancestry(installation_path)
            installation = int(installation_path.name)
            for repository_path in sorted(installation_path.iterdir()):
                _require_real_directory_ancestry(repository_path)
                repository_id = int(repository_path.name)
                for root in sorted(repository_path.iterdir()):
                    _require_real_directory_ancestry(root)
                    pull_request = int(root.name)
                    if min(installation, repository_id, pull_request) <= 0:
                        raise ValueError
                    binding_path, history_path = root / "binding.json", root / "history.jsonl"
                    if not (
                        binding_path.exists()
                        or binding_path.is_symlink()
                        or history_path.exists()
                        or history_path.is_symlink()
                    ):
                        continue
                    _require_regular_history(history_path)
                    binding = read_instance_binding(binding_path)
                    if binding.instance_id != f"github:{installation}:{repository_id}:pr:{pull_request}":
                        raise ValueError
                    if binding.topology != "v5" or binding.legacy:
                        raise RuntimeError("application state is not compatible with the V5 readiness topology")
    except RuntimeError:
        raise
    except OSError, ValueError:
        raise RuntimeError("application state root is malformed") from None


__all__ = [
    "InstanceBinding",
    "TopologyIdentity",
    "ensure_instance_binding",
    "parse_instance_binding",
    "preflight_v5_state",
    "read_instance_binding",
]
