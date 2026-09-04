"""Export a bounded PR runtime snapshot as filterable, payload-free JSON lines."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from pathlib import Path

from deployment import exe_access, exe_vm


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation", type=int, required=True)
    parser.add_argument("--repository", type=int, required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--layer", choices=("history", "dispatch", "inbox", "host"))
    parser.add_argument("--transition")
    args = parser.parse_args()
    if min(args.installation, args.repository, args.pr) <= 0:
        parser.error("identifiers must be positive")
    source = Path(__file__).with_name("observation.py").read_text()
    source += "\nimport datetime, urllib.request\n"
    source += "captured_at = datetime.datetime.now(datetime.timezone.utc).isoformat()\n"
    source += f'events = observe(Path("/var/lib/hamsterdan"), {args.installation}, {args.repository}, {args.pr})\n'
    source += 'with urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=10) as response:\n'
    source += "    health = json.load(response)\n"
    source += 'events.append({"layer": "host", "status": atom(health.get("status")), "scheduler_error_classes": [atom(item) for item in health.get("scheduler", {}).get("error_classes", [])]})\n'
    source += 'for event in events:\n    print(json.dumps({"captured_at": captured_at, **event}, sort_keys=True))\n'
    vm = exe_vm.wait_for_running_vm(exe_vm.DEFAULT_SPEC)
    with exe_access.temporary_access(vm.ssh_host) as access:
        result = subprocess.run(
            (
                "ssh",
                *access.ssh_options,
                "-o",
                "ServerAliveInterval=10",
                "-o",
                "ServerAliveCountMax=3",
                "-i",
                str(access.private_key),
                f"root@{access.ssh_host}",
                shlex.join(("sudo", "-n", "python3", "-")),
            ),
            input=source,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    if result.returncode:
        print(json.dumps({"ok": False, "error": "remote_observation_failed", "exit_code": result.returncode}))
        return 1
    for line in result.stdout.splitlines():
        event = json.loads(line)
        if args.layer is not None and event["layer"] != args.layer:
            continue
        if args.transition is not None and event.get("transition") != args.transition:
            continue
        print(json.dumps(event, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
