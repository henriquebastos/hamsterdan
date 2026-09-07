from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
REQUIRED = (
    "HAMSTERDAN_GITHUB_APP_ID",
    "HAMSTERDAN_GITHUB_APP_SLUG",
    "HAMSTERDAN_GITHUB_CLIENT_ID",
    "HAMSTERDAN_GITHUB_PRIVATE_KEY",
    "HAMSTERDAN_GITHUB_WEBHOOK_SECRET",
    "HAMSTERDAN_PI_API_KEY",
)
PEM = "-----BEGIN PRIVATE KEY-----\nfixture-only\n-----END PRIVATE KEY-----\n"


def launch(
    tmp_path: Path, *, missing: str | None = None, denied: bool = False, unusable_home: bool = False
) -> subprocess.CompletedProcess[str]:
    source = {
        "HAMSTERDAN_GITHUB_APP_ID": "17",
        "HAMSTERDAN_GITHUB_APP_SLUG": "hamsterdan-test",
        "HAMSTERDAN_GITHUB_CLIENT_ID": "Iv1.explicit",
        "HAMSTERDAN_GITHUB_PRIVATE_KEY": PEM,
        "HAMSTERDAN_GITHUB_WEBHOOK_SECRET": "current-webhook-secret",
        "HAMSTERDAN_PI_API_KEY": "current-api-key-canary",
    }
    if missing:
        del source[missing]
    source_path = tmp_path / "source.json"
    source_path.write_text(json.dumps(source))
    fake_op = tmp_path / "op"
    fake_op.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"required = {REQUIRED!r}\n"
        "assert all(name not in os.environ for name in required)\n"
        "assert os.environ['OP_SERVICE_ACCOUNT_TOKEN'] == 'loader-only-canary'\n"
        "assert not any(name.startswith('OP_SA_') for name in os.environ)\n"
        "assert sys.argv[1:4] == ['run', '--environment', 'a' * 26]\n"
        "config = Path(sys.argv[sys.argv.index('--config') + 1]) if '--config' in sys.argv else Path.home() / '.config/op'\n"
        "config.mkdir(parents=True, exist_ok=True)\n"
        "if os.environ.get('TEST_DENIED') == '1': sys.exit(23)\n"
        "with open(os.environ['TEST_SOURCE']) as f: os.environ.update(json.load(f))\n"
        "command = sys.argv[sys.argv.index('--') + 1:]\n"
        "os.execvpe(command[0], command, os.environ)\n"
    )
    fake_op.chmod(0o700)
    installations = tmp_path / "installations.toml"
    installations.write_text('[[accounts]]\nid=23\nlogin="owner"\nrepositories=["31:owner/repo"]\n')
    child = (
        "import os\n"
        "from hamsterdan.github_app.config import HostConfig\n"
        "from hamsterdan.host.pi_a2 import PiA2InstallationConfig\n"
        "assert not any(name.startswith(('OP_', 'GH_', 'GITHUB_', 'OPENAI_')) for name in os.environ)\n"
        "config = HostConfig.from_environment()\n"
        f"assert config._credentials() == ({PEM!r}, 'current-webhook-secret')\n"
        "installation = PiA2InstallationConfig.from_environment(os.environ)\n"
        "assert installation.direct_key == 'current-api-key-canary'\n"
        "print('current credentials accepted')\n"
    )
    environment = {
        **os.environ,
        **dict.fromkeys(REQUIRED, "stale-secret-canary"),
        "HAMSTERDAN_GITHUB_PRIVATE_KEY_FILE": "/stale/key",
        "HAMSTERDAN_PI_API_KEY_FILE": "/stale/key",
        "HAMSTERDAN_ENVIRONMENT_ID": "a" * 26,
        "HAMSTERDAN_OP_COMMAND": str(fake_op),
        "OP_SERVICE_ACCOUNT_TOKEN": "loader-only-canary",
        "OP_SA_HAMSTERDAN_OPS": "must-not-inherit",
        "OPENAI_API_KEY": "must-not-inherit",
        "GH_TOKEN": "must-not-inherit",
        "HAMSTERDAN_GITHUB_INSTALLATIONS_FILE": str(installations),
        "HAMSTERDAN_STATE_PATH": str(tmp_path / "state"),
        "HAMSTERDAN_PI_PROVIDER": "openai",
        "HAMSTERDAN_PI_MODEL": "gpt-5.6-sol",
        "HAMSTERDAN_PI_CLI_PATH": str(tmp_path / "cli"),
        "HAMSTERDAN_PI_NODE_PATH": str(tmp_path / "node"),
        "HAMSTERDAN_PI_PACKAGE_ROOT": str(tmp_path / "package"),
        "TEST_SOURCE": str(source_path),
        "TEST_DENIED": "1" if denied else "0",
    }
    environment.pop("HAMSTERDAN_OP_TOKEN_FILE", None)
    environment.pop("OP_CONFIG_DIR", None)
    environment["HOME"] = str(tmp_path / "home")
    if unusable_home:
        (tmp_path / "home").write_text("home is unavailable")
        environment["OP_CONFIG_DIR"] = str(tmp_path / "temporary-cli-config")
    return subprocess.run(
        (str(ROOT / "scripts/with-runtime-secrets"), sys.executable, "-c", child),
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def test_launcher_refreshes_multiline_values_and_excludes_bootstrap_from_application(tmp_path: Path) -> None:
    result = launch(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "current credentials accepted\n"


def test_temporary_cli_configuration_allows_start_without_a_writable_home(tmp_path: Path) -> None:
    result = launch(tmp_path, unusable_home=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "current credentials accepted\n"


@pytest.mark.parametrize("missing", REQUIRED)
def test_missing_environment_variable_cannot_fall_back_to_ambient_authority(tmp_path: Path, missing: str) -> None:
    result = launch(tmp_path, missing=missing)
    assert result.returncode != 0
    assert not result.stdout
    assert "stale-secret-canary" not in result.stderr


def test_retrieval_failure_prevents_application_start(tmp_path: Path) -> None:
    result = launch(tmp_path, denied=True)
    assert result.returncode == 23
    assert not result.stdout and not result.stderr
