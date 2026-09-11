from __future__ import annotations

import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.linux_orb_setup,
    pytest.mark.skipif(sys.platform != "linux", reason="Orb setup requires the GNU/Linux command set"),
]

ROOT = Path(__file__).parents[2]
AUTHOR_SECRET = "author-session-canary"
REVIEWER_SECRET = "reviewer-session-canary"
APP_SECRET = "app-private-key-canary"
OPENAI_SECRET = "openai-provider-canary"
WEBHOOK_SECRET = "webhook-secret-canary"
PROVIDER_SECRET = "anthropic-provider-canary"


def _executable(path: Path, body: str = "#!/bin/sh\nexit 0\n") -> None:
    path.write_text(body)
    path.chmod(0o755)


def _sandbox(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    workspace = tmp_path / "workspace"
    binaries = tmp_path / "bin"
    home = tmp_path / "home"
    (workspace / ".agents").mkdir(parents=True)
    (workspace / ".amp").mkdir()
    (workspace / "deployment" / "config").mkdir(parents=True)
    (workspace / "deployment" / "pi").mkdir(parents=True)
    (workspace / "scripts").mkdir()
    (workspace / "tools" / "demo-video").mkdir(parents=True)
    binaries.mkdir()
    home.mkdir()
    shutil.copy2(ROOT / ".agents" / "setup", workspace / ".agents" / "setup")
    shutil.copy2(
        ROOT / "deployment" / "config" / "installations.toml",
        workspace / "deployment" / "config" / "installations.toml",
    )
    shutil.copy2(ROOT / "deployment" / "pi" / "package.json", workspace / "deployment" / "pi" / "package.json")
    shutil.copy2(
        ROOT / "deployment" / "pi" / "package-lock.json", workspace / "deployment" / "pi" / "package-lock.json"
    )
    shutil.copy2(ROOT / "scripts" / "hamsterdan-host", workspace / "scripts" / "hamsterdan-host")
    for name in ("bun", "bunx", "dot", "ffmpeg", "ffprobe", "montage", "sudo"):
        _executable(binaries / name)
    _executable(binaries / "docker")
    _executable(
        binaries / "uv",
        """#!/bin/sh
set -eu
test "$#" = 2
test "$1" = sync
test "$2" = --frozen
! env | grep '^OP_' >/dev/null
! env | grep '^PETRUS_' >/dev/null
printf used > "$UV_AUTH_BOUNDARY_MARKER"
""",
    )
    _executable(
        binaries / "npm",
        """#!/bin/sh
set -eu
test "$1" = ci
while [ "$#" -gt 0 ]; do
    if [ "$1" = "--prefix" ]; then
        prefix="$2"
        shift 2
        continue
    fi
    shift
done
test -f "$prefix/package.json"
test -f "$prefix/package-lock.json"
root="$prefix/node_modules/@earendil-works/pi-coding-agent"
mkdir -p "$root/dist" "$prefix/node_modules/node/bin"
: > "$root/dist/cli.js"
: > "$root/dist/index.js"
cat > "$root/package.json" <<'EOF'
{"name":"@earendil-works/pi-coding-agent","version":"0.83.0"}
EOF
cat > "$prefix/node_modules/node/bin/node" <<'EOF'
#!/bin/sh
exit 0
EOF
chmod 755 "$prefix/node_modules/node/bin/node"
""",
    )
    environment = {
        "TMPDIR": str(tmp_path),
        "HOME": str(home),
        "PATH": f"{binaries}:/usr/bin:/bin",
        "GITHUB_DEMO_AUTHOR_HOSTS": AUTHOR_SECRET,
        "GITHUB_DEMO_REVIEWER_HOSTS": REVIEWER_SECRET,
        "GITHUB_DEMO_AUTHOR_LOGIN": "author",
        "GITHUB_DEMO_REVIEWER_LOGIN": "reviewer",
        "GITHUB_APP_PRIVATE_KEY_PEM": APP_SECRET,
        "GITHUB_APP_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "ANTHROPIC_AGENT_API_KEY": PROVIDER_SECRET,
        "ANTHROPIC_API_KEY": "personal-provider-must-not-win",
        "OPENAI_AGENT_API_KEY": OPENAI_SECRET,
        "OPENAI_API_KEY": "personal-openai-must-not-win",
        "GITHUB_APP_ID": "4452953",
        "GITHUB_APP_SLUG": "hamster-dan",
        "GITHUB_APP_CLIENT_ID": "Iv23liKF36r9YtMkGf0m",
        "READINESS_WORKFLOW_PATH": ".github/workflows/ci.yml",
        "READINESS_REMINDER_SECONDS": "259200",
        "OP_SA_HAMSTERDAN_DEMO": "demo-reader-must-not-leak",
        "OP_SA_HAMSTERDAN_OPS": "operations-reader-must-not-leak",
        "UV_AUTH_BOUNDARY_MARKER": str(tmp_path / "uv-auth-boundary"),
    }
    return workspace, environment


def _run(workspace: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("bash", "-x", ".agents/setup"),
        cwd=workspace,
        env=environment,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def test_setup_installs_dependencies_without_build_credentials(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)

    result = _run(workspace, environment)

    assert result.returncode == 0, result.stdout
    assert Path(environment["UV_AUTH_BOUNDARY_MARKER"]).read_text() == "used"
    assert not any(
        secret in result.stdout
        for secret in (AUTHOR_SECRET, REVIEWER_SECRET, APP_SECRET, WEBHOOK_SECRET, PROVIDER_SECRET, OPENAI_SECRET)
    )
    runtime = workspace / ".amp" / "runtime"
    assert not (runtime / "gh-demo-author").exists()
    assert not (runtime / "gh-demo-reviewer").exists()
    assert not (runtime / "hamsterdan.env").exists()
    assert not (runtime / "github-app.pem").exists()
    assert not (runtime / "webhook-secret").exists()
    assert not (runtime / "agent-api-key").exists()
    assert (runtime / "state").is_dir()
    assert not (runtime / "installations.toml").exists()
    assert not (runtime / "gh-henriquebastos").exists()
    assert not (runtime / "gh-crisbastos").exists()


def test_setup_does_not_make_optional_demo_identities_a_production_prerequisite(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    for name in (
        "GITHUB_DEMO_AUTHOR_HOSTS",
        "GITHUB_DEMO_REVIEWER_HOSTS",
        "GITHUB_DEMO_AUTHOR_LOGIN",
        "GITHUB_DEMO_REVIEWER_LOGIN",
    ):
        environment.pop(name)

    result = _run(workspace, environment)

    assert result.returncode == 0, result.stdout
    runtime = workspace / ".amp" / "runtime"
    assert (runtime / "state").is_dir()
    assert not (runtime / "gh-demo-author").exists()
    assert not (runtime / "gh-demo-reviewer").exists()


def test_setup_retires_legacy_demo_identity_files(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    runtime = workspace / ".amp" / "runtime"
    for role in ("author", "reviewer"):
        identity = runtime / f"gh-demo-{role}" / "gh"
        identity.mkdir(parents=True)
        (identity / "hosts.yml").write_text(f"legacy-{role}")

    result = _run(workspace, environment)

    assert result.returncode == 0, result.stdout
    assert not (runtime / "gh-demo-author").exists()
    assert not (runtime / "gh-demo-reviewer").exists()
    assert (runtime / "state").is_dir()


def test_dependency_sync_failure_stops_setup_without_credential_artifacts(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    assert _run(workspace, environment).returncode == 0
    _executable(Path(environment["PATH"].split(":", 1)[0]) / "uv", "#!/bin/sh\nexit 17\n")

    result = _run(workspace, environment)

    assert result.returncode == 17
    assert not (workspace / ".amp" / "runtime" / "hamsterdan.env").exists()


def test_setup_refuses_symlinked_role_root_without_touching_outside_file(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    runtime = workspace / ".amp" / "runtime"
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "sentinel"
    protected.write_text("unchanged")
    runtime.mkdir(mode=0o700)
    (runtime / "gh-demo-author").symlink_to(outside, target_is_directory=True)

    result = _run(workspace, environment)

    assert result.returncode != 0
    assert protected.read_text() == "unchanged"


def test_service_uses_the_runtime_launcher() -> None:
    service = (ROOT / ".amp" / "services.yaml").read_text()

    assert "scripts/hamsterdan-host" in service
    assert "hamsterdan.env" not in service


@pytest.mark.parametrize("ambient_user", [None, "wrong-user"])
def test_setup_resolves_the_docker_account_from_effective_identity(tmp_path: Path, ambient_user: str | None) -> None:
    workspace, environment = _sandbox(tmp_path)
    if ambient_user is not None:
        environment["USER"] = ambient_user
    marker = tmp_path / "usermod-call"
    environment["TEST_USERMOD_CALL"] = str(marker)
    binaries = Path(environment["PATH"].split(":", 1)[0])
    _executable(
        binaries / "sudo",
        '#!/bin/sh\nif [ "$1" = usermod ]; then printf "%s\\n" "$*" > "$TEST_USERMOD_CALL"; fi\n',
    )
    result = _run(workspace, environment)
    assert result.returncode == 0, result.stdout
    assert marker.read_text() == f"usermod -aG docker {pwd.getpwuid(os.geteuid()).pw_name}\n"


def test_setup_keeps_locked_media_checks_without_remotion_browser_download() -> None:
    setup = (ROOT / ".agents" / "setup").read_text()

    assert "bun install --frozen-lockfile" in setup
    assert "bunx playwright install --with-deps chromium" in setup
    assert "remotion browser ensure" not in setup


def test_setup_installs_pi_from_the_release_lockfile() -> None:
    setup = (ROOT / ".agents" / "setup").read_text()

    assert "deployment/pi/package-lock.json" in setup
    assert 'npm ci --prefix "$PI_PREFIX"' in setup
    assert "npm install --prefix" not in setup
