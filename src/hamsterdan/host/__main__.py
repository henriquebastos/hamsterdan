"""Standalone host CLI."""

from __future__ import annotations

import argparse
import json
import os

import uvicorn

from hamsterdan.github_app.config import ConfigurationError, HostConfig

from .api import create_app
from .service import HostService


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        prog="python -m hamsterdan.host",
        description="Run or validate the Hamsterdan GitHub App host. Credentials are read only from configured secret files.",
    )
    value.add_argument("command", choices=("serve", "validate", "inbox", "requeue"))
    value.add_argument("--delivery", help="canonical failed GitHub delivery UUID to requeue")
    value.add_argument("--host", default=os.getenv("HAMSTERDAN_HOST", "127.0.0.1"))
    value.add_argument("--port", type=int, default=int(os.getenv("HAMSTERDAN_PORT", "8000")))
    return value


def main() -> int:
    args = parser().parse_args()
    if args.command == "requeue" and not args.delivery:
        parser().error("requeue requires --delivery")
    service: HostService | None = None
    try:
        config = HostConfig.from_environment()
        service = HostService(
            config,
            workflow_path=os.getenv("HAMSTERDAN_WORKFLOW_PATH", ".github/workflows/ci.yml"),
            reminder_delay=float(os.getenv("HAMSTERDAN_REMINDER_SECONDS", "259200")),
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
