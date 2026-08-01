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
    value.add_argument("command", choices=("serve", "validate"))
    value.add_argument("--host", default=os.getenv("HAMSTERDAN_HOST", "127.0.0.1"))
    value.add_argument("--port", type=int, default=int(os.getenv("HAMSTERDAN_PORT", "8000")))
    return value


def main() -> int:
    args = parser().parse_args()
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
        uvicorn.run(create_app(service), host=args.host, port=args.port)
        return 0
    except (ConfigurationError, RuntimeError, ValueError) as error:
        if service is not None:
            service.close()
        parser().error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
