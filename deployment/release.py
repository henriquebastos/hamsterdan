#!/usr/bin/env python3
"""Build and verify one Hamsterdan OCI candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = "linux/amd64"
NODE_VERSION = "22.19.0"
PI_VERSION = "0.83.0"
PINNED_INPUTS = (
    Path("deployment/Containerfile"),
    Path("deployment/pi/package-lock.json"),
    Path("deployment/pi/package.json"),
    Path("scripts/with-runtime-secrets"),
    Path("pyproject.toml"),
    Path("uv.lock"),
)
REVISION = re.compile(r"[0-9a-f]{40}")


class ReleaseError(RuntimeError):
    """A bounded release failure that contains no credential value."""


@dataclass(frozen=True)
class Source:
    revision: str
    version: str
    source_date_epoch: int
    dirty: bool

    @property
    def tag(self) -> str:
        return f"dev-{self.revision[:12]}" if self.dirty else f"sha-{self.revision}"

    @property
    def created(self) -> str:
        return datetime.fromtimestamp(self.source_date_epoch, UTC).isoformat().replace("+00:00", "Z")


def capture(command: Sequence[str], *, cwd: Path = ROOT, environment: Mapping[str, str] | None = None) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=None if environment is None else dict(environment),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReleaseError(f"release command failed: {command[0]}") from error
    return completed.stdout.strip()


def run(
    command: Sequence[str],
    *,
    cwd: Path = ROOT,
    environment: Mapping[str, str] | None = None,
) -> None:
    try:
        subprocess.run(
            command,
            cwd=cwd,
            env=None if environment is None else dict(environment),
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReleaseError(f"release command failed: {command[0]}") from error


def project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as stream:
        value = tomllib.load(stream).get("project", {}).get("version")
    if not isinstance(value, str) or not value:
        raise ReleaseError("project version is unavailable")
    return value


def read_source(root: Path = ROOT, *, development: bool) -> Source:
    revision = capture(("git", "rev-parse", "HEAD"), cwd=root)
    status = capture(("git", "status", "--porcelain", "--untracked-files=normal"), cwd=root)
    epoch = capture(("git", "show", "-s", "--format=%ct", "HEAD"), cwd=root)
    if REVISION.fullmatch(revision) is None or not epoch.isascii() or not epoch.isdecimal():
        raise ReleaseError("source identity is malformed")
    dirty = bool(status)
    if dirty and not development:
        raise ReleaseError("a publishable candidate requires a clean commit; use --development for a local-only build")
    return Source(revision, project_version(root), int(epoch), dirty)


def container_command(environment: Mapping[str, str] | None = None) -> tuple[str, ...]:
    env = os.environ if environment is None else environment
    configured = env.get("HAMSTERDAN_CONTAINER_CLI")
    if configured:
        command = tuple(shlex.split(configured))
        if not command:
            raise ReleaseError("configured container command is empty")
        return command
    if shutil.which("docker") is None:
        raise ReleaseError("Docker with Buildx is required")
    if env.get("AMP_ORB") == "1":
        return ("sudo", "docker")
    return ("docker",)


def build_command(*, container: tuple[str, ...], image: str, metadata: Path, source: Source) -> tuple[str, ...]:
    return (
        *container,
        "buildx",
        "build",
        "--load",
        "--platform",
        PLATFORM,
        "--build-arg",
        f"SOURCE_REVISION={source.revision}",
        "--build-arg",
        f"SOURCE_VERSION={source.version}",
        "--build-arg",
        f"SOURCE_CREATED={source.created}",
        "--metadata-file",
        str(metadata),
        "--tag",
        image,
        "--file",
        "deployment/Containerfile",
        ".",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_directory(root: Path, source: Source) -> Path:
    suffix = "-dirty" if source.dirty else ""
    return root / "dist" / "deployment" / f"{source.revision}{suffix}"


def manifest_path(root: Path = ROOT) -> Path:
    return _candidate_directory(root, read_source(root, development=True)) / "release.json"


def _write_manifest(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseError("release manifest is unavailable or malformed") from error
    if not isinstance(value, dict):
        raise ReleaseError("release manifest is malformed")
    return value


def build(*, development: bool, environment: Mapping[str, str] | None = None) -> Path:
    env = dict(os.environ if environment is None else environment)
    source = read_source(ROOT, development=development)
    directory = _candidate_directory(ROOT, source)
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    metadata = directory / "build-metadata.json"
    image = f"hamsterdan:{source.tag}"
    container = container_command(env)
    run(build_command(container=container, image=image, metadata=metadata, source=source), environment=env)
    try:
        build_metadata = json.loads(metadata.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseError("Buildx did not produce valid build metadata") from error
    image_digest = build_metadata.get("containerimage.digest")
    if not isinstance(image_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None:
        raise ReleaseError("Buildx did not report a canonical image digest")
    image_id = capture((*container, "image", "inspect", "--format={{.Id}}", image))
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise ReleaseError("the loaded image identity is malformed")
    manifest: dict[str, object] = {
        "dirty": source.dirty,
        "image": image,
        "image_digest": image_digest,
        "image_id": image_id,
        "inputs": {str(path): _sha256(ROOT / path) for path in PINNED_INPUTS},
        "platform": PLATFORM,
        "source_date_epoch": source.source_date_epoch,
        "source_revision": source.revision,
        "verified": False,
        "version": source.version,
    }
    path = directory / "release.json"
    _write_manifest(path, manifest)
    return path


def verify(path: Path, *, environment: Mapping[str, str] | None = None) -> Path:
    manifest = _read_manifest(path)
    image = manifest.get("image")
    image_id = manifest.get("image_id")
    revision = manifest.get("source_revision")
    version = manifest.get("version")
    if (
        not isinstance(image, str)
        or not isinstance(image_id, str)
        or not isinstance(revision, str)
        or not isinstance(version, str)
    ):
        raise ReleaseError("release manifest identity is malformed")
    container = container_command(environment)
    observed_image_id = capture((*container, "image", "inspect", "--format={{.Id}}", image))
    if observed_image_id != image_id:
        raise ReleaseError("loaded image does not match the release manifest")
    raw_labels = capture((*container, "image", "inspect", "--format={{json .Config.Labels}}", image))
    try:
        labels = json.loads(raw_labels)
    except json.JSONDecodeError as error:
        raise ReleaseError("image labels are malformed") from error
    if not isinstance(labels, dict) or labels.get("org.opencontainers.image.revision") != revision:
        raise ReleaseError("image revision does not match the release manifest")
    if labels.get("org.opencontainers.image.version") != version:
        raise ReleaseError("image version does not match the release manifest")
    capture((*container, "run", "--rm", image, "--help"))
    node = capture(
        (
            *container,
            "run",
            "--rm",
            "--entrypoint",
            "/opt/hamsterdan/pi/node_modules/node/bin/node",
            image,
            "--version",
        )
    )
    if node != f"v{NODE_VERSION}":
        raise ReleaseError("image Node runtime does not match the qualified version")
    pi = capture(
        (
            *container,
            "run",
            "--rm",
            "--entrypoint",
            "/opt/hamsterdan/pi/node_modules/node/bin/node",
            image,
            "/opt/hamsterdan/pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js",
            "--version",
        )
    )
    if pi != PI_VERSION:
        raise ReleaseError("image Pi runtime does not match the qualified version")
    run(
        (
            *container,
            "run",
            "--rm",
            "--entrypoint",
            "/opt/hamsterdan/.venv/bin/python",
            image,
            "-c",
            f"from importlib.metadata import version; import hamsterdan; assert version('hamsterdan') == {version!r}",
        )
    )
    run((*container, "run", "--rm", "--entrypoint", "/bin/sh", image, "-c", "test -w /var/lib/hamsterdan"))
    manifest["verified"] = True
    _write_manifest(path, manifest)
    return path


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="build one local OCI candidate")
    build_parser.add_argument(
        "--development", action="store_true", help="allow a dirty, permanently unpublishable build"
    )
    verify_parser = commands.add_parser("verify", help="verify a previously built candidate")
    verify_parser.add_argument("--manifest", type=Path)
    return value


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "build":
            path = build(development=arguments.development)
        else:
            path = arguments.manifest or manifest_path()
            path = verify(path)
        display_path = path.resolve()
        if display_path.is_relative_to(ROOT):
            display_path = display_path.relative_to(ROOT)
        print(display_path)
        return 0
    except ReleaseError as error:
        print(f"release refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
