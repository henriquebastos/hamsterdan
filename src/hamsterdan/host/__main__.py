"""Standalone host CLI."""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
from pathlib import Path

import uvicorn

from hamsterdan.github_app.config import ConfigurationError, HostConfig

from .api import create_app
from .service import HostService, QualificationFault

MAX_HISTORY_BYTES = 16 * 1024 * 1024
MAX_BINDING_BYTES = 4096
MAX_IDENTIFIER_BYTES = 1024


def _read_bounded_regular(path: Path, limit: int) -> bytes:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError("Instance state file is not a bounded regular file")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(descriptor)
            chunks = bytearray()
            while chunk := os.read(descriptor, min(65536, limit + 1 - len(chunks))):
                chunks.extend(chunk)
                if len(chunks) > limit:
                    raise ValueError("Instance state file is not a bounded regular file")
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        raise ValueError("Instance state cannot be inspected safely") from None
    identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    if identity != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or len(chunks) != before.st_size:
        raise ValueError("Instance state changed during inspection")
    return bytes(chunks)


def _require_real_directories(paths: tuple[Path, ...]) -> None:
    try:
        for path in paths:
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise ValueError("Instance state path is not a real directory")
    except OSError:
        raise ValueError("Instance state cannot be inspected safely") from None


def _identifier(value: object, error: str) -> str:
    if (
        not isinstance(value, str)
        or not 0 < len(value.encode()) <= MAX_IDENTIFIER_BYTES
        or not value.isascii()
        or not value.isprintable()
    ):
        raise ValueError(error)
    return value


def inspect_instance(
    state_path: Path, installation_id: int, repository_id: int, pull_request: int
) -> dict[str, object]:
    if min(installation_id, repository_id, pull_request) <= 0:
        raise ValueError("Instance identifiers must be positive")
    applications = state_path / "applications"
    installation = applications / str(installation_id)
    repository_path = installation / str(repository_id)
    root = repository_path / str(pull_request)
    _require_real_directories((state_path, applications, installation, repository_path, root))
    history = root / "history.jsonl"
    binding = root / "binding.json"
    try:
        raw = _read_bounded_regular(history, MAX_HISTORY_BYTES)
        bound = json.loads(_read_bounded_regular(binding, MAX_BINDING_BYTES).decode("utf-8"))
        records = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    except OSError, UnicodeError, json.JSONDecodeError:
        raise ValueError("Instance state cannot be inspected safely") from None
    if (
        not isinstance(bound, dict)
        or bound.get("pull_request") != pull_request
        or not records
        or not all(isinstance(record, dict) and isinstance(record.get("record"), str) for record in records)
    ):
        raise ValueError("Instance state binding or History is malformed")
    expected_instance = f"github:{installation_id}:{repository_id}:pr:{pull_request}"
    instance_id = _identifier(bound.get("instance_id"), "Instance identity is malformed")
    repository = _identifier(bound.get("repository"), "Instance repository is malformed")
    if instance_id != expected_instance:
        raise ValueError("Instance state binding does not match its selected path")
    requested: dict[int, dict[str, object]] = {}
    completed: set[int] = set()
    failed: set[int] = set()
    firing_failed: set[int] = set()
    last_instant: int | float = 0
    for record in records:
        instant = record.get("instant", 0)
        if not isinstance(instant, int | float) or isinstance(instant, bool) or not math.isfinite(instant):
            raise ValueError("Instance History instant is malformed")
        last_instant = max(last_instant, instant)
        occurrence = record.get("occurrence")
        if record["record"] == "ActivityRequested":
            if type(occurrence) is not int or occurrence <= 0:
                raise ValueError("Instance Activity identity is malformed")
            input_value = record.get("input")
            work = input_value.get("work", input_value.get("command")) if isinstance(input_value, dict) else None
            operation = work.get("operation") if isinstance(work, dict) else None
            transition = _identifier(record.get("transition"), "Activity identifiers are malformed")
            activity = _identifier(record.get("activity"), "Activity identifiers are malformed")
            operation = _identifier(operation, "Activity operation is malformed")
            requested[occurrence] = {
                "occurrence": occurrence,
                "transition": transition,
                "activity": activity,
                "operation": operation,
            }
        elif record["record"] == "ActivityCompleted" and type(occurrence) is int:
            completed.add(occurrence)
        elif record["record"] == "ActivityFailed" and type(occurrence) is int:
            failed.add(occurrence)
        elif record["record"] == "FiringFailed" and type(occurrence) is int:
            firing_failed.add(occurrence)
    unresolved = [requested[key] for key in sorted(requested.keys() - completed - failed)]
    if len(unresolved) > 1000:
        raise ValueError("Instance unresolved Activity inventory exceeds its bound")
    return {
        "command": "inspect-instance",
        "instance_id": instance_id,
        "repository": repository,
        "pull_request": pull_request,
        "record_count": len(records),
        "last_instant": last_instant,
        "activities": {
            "requested": len(requested),
            "completed": len(completed),
            "failed": len(failed),
            "firing_failed": len(firing_failed),
            "unresolved": unresolved,
        },
        "ok": True,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        prog="python -m hamsterdan.host",
        description="Run or validate the Hamsterdan GitHub App host. Credentials are read only from configured secret files.",
    )
    value.add_argument("command", choices=("serve", "validate", "inbox", "requeue", "inspect-instance"))
    value.add_argument("--delivery", help="canonical failed GitHub delivery UUID to requeue")
    value.add_argument("--installation", type=int)
    value.add_argument("--repository", type=int)
    value.add_argument("--pr", type=int)
    value.add_argument("--host", default=os.getenv("HAMSTERDAN_HOST", "127.0.0.1"))
    value.add_argument("--port", type=int, default=int(os.getenv("HAMSTERDAN_PORT", "8000")))
    return value


def main() -> int:
    args = parser().parse_args()
    if args.command == "requeue" and not args.delivery:
        parser().error("requeue requires --delivery")
    if args.command == "inspect-instance" and any(
        value is None for value in (args.installation, args.repository, args.pr)
    ):
        parser().error("inspect-instance requires --installation, --repository, and --pr")
    service: HostService | None = None
    try:
        config = HostConfig.from_environment()
        if args.command == "inspect-instance":
            print(
                json.dumps(
                    inspect_instance(config.state_path, args.installation, args.repository, args.pr), sort_keys=True
                )
            )
            return 0
        service = HostService(
            config,
            workflow_path=os.getenv("HAMSTERDAN_WORKFLOW_PATH", ".github/workflows/ci.yml"),
            reminder_delay=float(os.getenv("HAMSTERDAN_REMINDER_SECONDS", "259200")),
            qualification_fault=QualificationFault.from_environment(),
        )
        if args.command == "validate":
            print(json.dumps(service.reconcile_registration(), sort_keys=True))
            service.close()
            return 0
        if args.command == "inbox":
            print(
                json.dumps({"counts": service.custody.counts(), "failures": service.custody.failures()}, sort_keys=True)
            )
            service.close()
            return 0
        if args.command == "requeue":
            requeued = service.custody.requeue(args.delivery)
            print(json.dumps({"delivery_id": args.delivery, "requeued": requeued}, sort_keys=True))
            service.close()
            return 0 if requeued else 1
        uvicorn.run(create_app(service), host=args.host, port=args.port)
        return 0
    except (ConfigurationError, RuntimeError, ValueError) as error:
        if service is not None:
            service.close()
        parser().error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
