from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
AMBIENT_CREDENTIALS = {
    "AMP_API_KEY": "ambient-amp",
    "EXE_DEV_API_TOKEN": "ambient-ops",
    "GH_TOKEN": "ambient-gh",
    "GITHUB_APP_PRIVATE_KEY_PEM": "ambient-app",
    "HAMSTERDAN_GITHUB_PRIVATE_KEY": "ambient-app",
    "HAMSTERDAN_GITHUB_WEBHOOK_SECRET": "ambient-app",
    "HAMSTERDAN_PI_API_KEY": "ambient-app",
    "OPENAI_API_KEY": "ambient-openai",
    "OP_SA_HAMSTERDAN_DEMO": "ambient-demo-reader",
    "OP_SA_HAMSTERDAN_DEV": "ambient-application-reader",
    "OP_SA_HAMSTERDAN_DEV_TOOLS": "ambient-tools-reader",
    "OP_SA_HAMSTERDAN_OPS": "ambient-operations-reader",
}
CREDENTIAL_PREFIXES = ("AMP_", "EXE_DEV_", "GH_", "GITHUB_", "OPENAI_", "OPENROUTER_", "OP_", "PETRUS_")
CREDENTIAL_NAMES = {
    "HAMSTERDAN_GITHUB_PRIVATE_KEY",
    "HAMSTERDAN_GITHUB_WEBHOOK_SECRET",
    "HAMSTERDAN_PI_API_KEY",
}


def executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o700)


def tool_environment(tmp_path: Path, profile: str, bootstrap_name: str) -> dict[str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_op = fake_bin / "op"
    executable(
        fake_op,
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        f"prefixes = {CREDENTIAL_PREFIXES!r}\n"
        f"names = {CREDENTIAL_NAMES!r}\n"
        "credentials = {name: value for name, value in os.environ.items() "
        "if name.startswith(prefixes) or name in names}\n"
        "assert credentials == {'OP_SERVICE_ACCOUNT_TOKEN': 'selected-reader'}\n"
        "counter = Path(os.environ['TEST_FETCH_COUNTER'])\n"
        "counter.write_text(str(int(counter.read_text()) + 1) if counter.exists() else '1')\n"
        "if os.environ.get('TEST_DENIED') == '1': sys.exit(23)\n"
        "if sys.argv[1] == 'document':\n"
        "    assert sys.argv[2] == 'get' and '--vault' in sys.argv\n"
        "    document = sys.argv[3]\n"
        "    output = Path(sys.argv[sys.argv.index('--out-file') + 1])\n"
        "    output.write_text(document)\n"
        "    output.chmod(0o600)\n"
        "    sys.exit(0)\n"
        "assert sys.argv[1] == 'run'\n"
        "files = [arg for arg in sys.argv if arg.startswith('--env-file=')]\n"
        "if '--env-file=env-ops.tpl' in files:\n"
        "    os.environ['EXE_DEV_API_TOKEN'] = 'current-ops'\n"
        "    if '--env-file=env-provision.tpl' in files:\n"
        "        os.environ['OP_SERVICE_ACCOUNT_TOKEN_VPS'] = 'current-production-reader'\n"
        "else: raise AssertionError(files)\n"
        "command = sys.argv[sys.argv.index('--') + 1:]\n"
        "os.execvpe(command[0], command, os.environ)\n",
    )
    executable(
        fake_bin / "gh",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'case "$(cat "$XDG_CONFIG_HOME/gh/hosts.yml")" in\n'
        "  demo-author-hosts.yml) printf '%s\\n' author ;;\n"
        "  demo-reviewer-hosts.yml) printf '%s\\n' reviewer ;;\n"
        "  *) exit 19 ;;\n"
        "esac\n",
    )
    environment = {
        **os.environ,
        **AMBIENT_CREDENTIALS,
        bootstrap_name: "selected-reader",
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "HAMSTERDAN_OP_COMMAND": str(fake_op),
        "GITHUB_DEMO_AUTHOR_LOGIN": "author",
        "GITHUB_DEMO_REVIEWER_LOGIN": "reviewer",
        "TEST_FETCH_COUNTER": str(tmp_path / "fetch-count"),
        "TEST_OUTPUT": str(tmp_path / f"{profile}.json"),
        "TEST_DENIED": "0",
    }
    return environment


def child_command() -> tuple[str, ...]:
    child = (
        "import json, os, stat\n"
        "from pathlib import Path\n"
        f"prefixes = {CREDENTIAL_PREFIXES!r}\n"
        f"names = {CREDENTIAL_NAMES!r}\n"
        "result = {'credentials': {name: value for name, value in os.environ.items() "
        "if name.startswith(prefixes) or name in names}}\n"
        "root = os.environ.get('XDG_CONFIG_HOME')\n"
        "if root:\n"
        "    hosts = Path(root) / 'gh/hosts.yml'\n"
        "    result['identity_root'] = root\n"
        "    result['identity_document'] = hosts.read_text()\n"
        "    result['hosts_private'] = stat.S_IMODE(hosts.stat().st_mode) == 0o600\n"
        "Path(os.environ['TEST_OUTPUT']).write_text(json.dumps(result, sort_keys=True))\n"
    )
    return (sys.executable, "-c", child)


def run_tool(script: str, arguments: tuple[str, ...], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (str(ROOT / "scripts" / script), *arguments),
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


@pytest.mark.parametrize(
    ("script", "arguments", "bootstrap_name", "expected"),
    [
        ("ops", child_command(), "OP_SA_HAMSTERDAN_OPS", {"EXE_DEV_API_TOKEN": "current-ops"}),
        (
            "ops",
            ("--provision", *child_command()),
            "OP_SA_HAMSTERDAN_OPS",
            {"EXE_DEV_API_TOKEN": "current-ops", "OP_SERVICE_ACCOUNT_TOKEN_VPS": "current-production-reader"},
        ),
    ],
)
def test_each_tool_loader_exposes_only_its_selected_credentials(
    tmp_path: Path,
    script: str,
    arguments: tuple[str, ...],
    bootstrap_name: str,
    expected: dict[str, str],
) -> None:
    environment = tool_environment(tmp_path, script, bootstrap_name)

    result = run_tool(script, arguments, environment)

    assert result.returncode == 0, result.stderr
    observed = json.loads(Path(environment["TEST_OUTPUT"]).read_text())
    assert observed == {"credentials": expected}


@pytest.mark.parametrize(
    ("role", "expected_document"), [("author", "demo-author-hosts.yml"), ("reviewer", "demo-reviewer-hosts.yml")]
)
def test_demo_identity_exists_only_for_the_selected_command(tmp_path: Path, role: str, expected_document: str) -> None:
    environment = tool_environment(tmp_path, role, "OP_SA_HAMSTERDAN_DEMO")

    result = run_tool("demo-github", (role, *child_command()), environment)

    assert result.returncode == 0, result.stderr
    observed = json.loads(Path(environment["TEST_OUTPUT"]).read_text())
    assert observed["credentials"] == {}
    assert observed["identity_document"] == expected_document
    assert observed["hosts_private"] is True
    assert not Path(observed["identity_root"]).exists()
    assert not any(tmp_path.glob("hamsterdan-demo-identity.*"))


def test_failed_demo_retrieval_does_not_start_child_or_retain_identity(tmp_path: Path) -> None:
    environment = tool_environment(tmp_path, "denied-demo", "OP_SA_HAMSTERDAN_DEMO")
    environment["TEST_DENIED"] = "1"

    result = run_tool("demo-github", ("author", *child_command()), environment)

    assert result.returncode == 23
    assert not Path(environment["TEST_OUTPUT"]).exists()
    assert not any(tmp_path.glob("hamsterdan-demo-identity.*"))


def test_missing_demo_reader_does_not_fall_back_to_personal_cli_authentication(tmp_path: Path) -> None:
    environment = tool_environment(tmp_path, "missing-demo", "OP_SA_HAMSTERDAN_DEMO")
    environment.pop("OP_SA_HAMSTERDAN_DEMO")

    result = run_tool("demo-github", ("author", *child_command()), environment)

    assert result.returncode == 2
    assert not (tmp_path / "fetch-count").exists()
    assert not Path(environment["TEST_OUTPUT"]).exists()
