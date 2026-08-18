from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

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
    (workspace / "scripts").mkdir()
    (workspace / "tools" / "demo-video").mkdir(parents=True)
    binaries.mkdir()
    home.mkdir()
    shutil.copy2(ROOT / ".agents" / "setup", workspace / ".agents" / "setup")
    shutil.copy2(ROOT / "scripts" / "hamsterdan-host", workspace / "scripts" / "hamsterdan-host")
    for name in ("uv", "bun", "bunx", "ffmpeg", "ffprobe", "montage"):
        _executable(binaries / name)
    _executable(
        binaries / "npm",
        """#!/bin/sh
set -eu
while [ "$#" -gt 0 ]; do
    if [ "$1" = "--prefix" ]; then
        prefix="$2"
        shift 2
        continue
    fi
    shift
done
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
    _executable(
        binaries / "system-gh",
        """#!/bin/sh
case "$XDG_CONFIG_HOME" in
    */gh-demo-author) printf '%s\\n' author ;;
    */gh-demo-reviewer) printf '%s\\n' reviewer ;;
    *) exit 1 ;;
esac
""",
    )
    setup = workspace / ".agents" / "setup"
    setup.write_text(setup.read_text().replace("SYSTEM_GH=/usr/bin/gh", f"SYSTEM_GH={binaries / 'system-gh'}"))
    _executable(
        binaries / "gh",
        f"""#!/bin/sh
printf called > {binaries / "gh-wrapper-called"}
exit 91
""",
    )
    environment = {
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
        "GITHUB_INSTALLATION_ACCOUNT_ID": "108842540",
        "GITHUB_INSTALLATION_ACCOUNT_LOGIN": "HBNetwork",
        "GITHUB_INSTALLATION_REPOSITORIES": "1316665126:HBNetwork/demo-pr-readiness",
        "READINESS_WORKFLOW_PATH": ".github/workflows/ci.yml",
        "READINESS_REMINDER_SECONDS": "259200",
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


def _private(path: Path) -> bool:
    metadata = path.lstat()
    return stat.S_ISREG(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) == 0o600


def test_setup_materializes_complete_role_based_runtime_without_disclosure(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)

    result = _run(workspace, environment)

    assert result.returncode == 0, result.stdout
    assert not any(
        secret in result.stdout
        for secret in (AUTHOR_SECRET, REVIEWER_SECRET, APP_SECRET, WEBHOOK_SECRET, PROVIDER_SECRET, OPENAI_SECRET)
    )
    runtime = workspace / ".amp" / "runtime"
    expected = {
        "gh-demo-author/gh/hosts.yml": AUTHOR_SECRET,
        "gh-demo-reviewer/gh/hosts.yml": REVIEWER_SECRET,
        "github-app.pem": APP_SECRET,
        "webhook-secret": WEBHOOK_SECRET,
        "agent-api-key": PROVIDER_SECRET,
    }
    for relative, secret in expected.items():
        path = runtime / relative
        assert _private(path)
        assert path.read_text() == secret
    launch = runtime / "hamsterdan.env"
    assert _private(launch)
    configuration = launch.read_text()
    assert "HAMSTERDAN_GITHUB_APP_ID=4452953" in configuration
    assert "HAMSTERDAN_GITHUB_ACCOUNT_LOGIN=HBNetwork" in configuration
    assert "HAMSTERDAN_ALLOWED_REPOSITORIES=1316665126:HBNetwork/demo-pr-readiness" in configuration
    assert "HAMSTERDAN_PI_PROVIDER=anthropic" in configuration
    assert "HAMSTERDAN_PI_MODEL=claude-sonnet-4-5" in configuration
    assert "HAMSTERDAN_PI_API_KEY_FILE=" in configuration
    assert "HAMSTERDAN_READINESS_TOPOLOGY" not in configuration
    assert not any(secret in configuration for secret in expected.values())
    assert not (runtime / "gh-henriquebastos").exists()
    assert not (runtime / "gh-crisbastos").exists()


def test_setup_selects_openai_when_anthropic_is_unavailable(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    for name in ("ANTHROPIC_AGENT_API_KEY", "ANTHROPIC_API_KEY"):
        environment.pop(name)

    result = _run(workspace, environment)

    assert result.returncode == 0, result.stdout
    runtime = workspace / ".amp" / "runtime"
    assert (runtime / "agent-api-key").read_text() == OPENAI_SECRET
    configuration = (runtime / "hamsterdan.env").read_text()
    assert "HAMSTERDAN_PI_PROVIDER=openai" in configuration
    assert "HAMSTERDAN_PI_MODEL=gpt-5.6-sol" in configuration
    assert "anthropic" not in configuration


def test_setup_selects_openrouter_only_after_higher_priority_providers(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    for name in (
        "ANTHROPIC_AGENT_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_AGENT_API_KEY",
        "OPENAI_API_KEY",
    ):
        environment.pop(name)
    environment["OPENROUTER_AGENT_API_KEY"] = "openrouter-provider-canary"

    result = _run(workspace, environment)

    assert result.returncode == 0, result.stdout
    runtime = workspace / ".amp" / "runtime"
    assert (runtime / "agent-api-key").read_text() == "openrouter-provider-canary"
    configuration = (runtime / "hamsterdan.env").read_text()
    assert "HAMSTERDAN_PI_PROVIDER=openrouter" in configuration
    assert "HAMSTERDAN_PI_MODEL=anthropic/claude-sonnet-4.5" in configuration


def test_setup_role_verification_bypasses_a_path_precedence_gh_wrapper(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)

    result = _run(workspace, environment)

    assert result.returncode == 0, result.stdout
    assert not (Path(environment["PATH"].split(":", 1)[0]) / "gh-wrapper-called").exists()
    setup = (ROOT / ".agents" / "setup").read_text()
    assert "SYSTEM_GH=/usr/bin/gh" in setup
    assert '$(/usr/bin/env -i HOME="$HOME" PATH="/usr/bin:/bin"' in setup


def test_setup_removes_stale_launch_and_managed_authority_when_inputs_disappear(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    assert _run(workspace, environment).returncode == 0
    for name in (
        "GITHUB_DEMO_AUTHOR_HOSTS",
        "GITHUB_DEMO_REVIEWER_HOSTS",
        "GITHUB_APP_PRIVATE_KEY_PEM",
        "GITHUB_APP_WEBHOOK_SECRET",
        "ANTHROPIC_AGENT_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_AGENT_API_KEY",
        "OPENAI_API_KEY",
    ):
        environment.pop(name)

    result = _run(workspace, environment)

    assert result.returncode == 0, result.stdout
    runtime = workspace / ".amp" / "runtime"
    assert not (runtime / "hamsterdan.env").exists()
    assert not (runtime / "github-app.pem").exists()
    assert not (runtime / "webhook-secret").exists()
    assert not (runtime / "agent-api-key").exists()
    assert not (runtime / "anthropic-api-key").exists()
    assert not (runtime / "gh-demo-author").exists()
    assert not (runtime / "gh-demo-reviewer").exists()


def test_setup_invalidates_launch_before_external_installer_failure(tmp_path: Path) -> None:
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


def test_service_requires_an_owned_private_regular_runtime_environment() -> None:
    service = (ROOT / ".amp" / "services.yaml").read_text()

    assert "scripts/hamsterdan-host" in service
    assert "hamsterdan.env" not in service


def test_host_launcher_strips_setup_and_ambient_provider_authority(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    assert _run(workspace, environment).returncode == 0
    capture = tmp_path / "environment-names"
    binaries = Path(environment["PATH"].split(":", 1)[0])
    _executable(binaries / "uv", '#!/bin/sh\nenv | cut -d= -f1 | sort > "$CAPTURE"\n')
    environment.update(
        {
            "CAPTURE": str(capture),
            "AMP_API_KEY": "amp-canary",
            "GH_TOKEN": "gh-canary",
            "OPENAI_API_KEY": "openai-canary",
            "HAMSTERDAN_GITHUB_WORKFLOW_TOKEN": "workflow-canary",
            "HAMSTERDAN_QUALIFICATION_FAULT": "fault-canary",
        }
    )

    result = subprocess.run(
        ("scripts/hamsterdan-host",),
        cwd=workspace,
        env=environment,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    assert result.returncode == 0, result.stdout
    names = set(capture.read_text().splitlines())
    assert REQUIRED_LAUNCH_NAMES <= names
    assert "HAMSTERDAN_READINESS_TOPOLOGY" not in names
    assert "HAMSTERDAN_QUALIFICATION_FAULT" in names
    assert (
        not {
            "AMP_API_KEY",
            "ANTHROPIC_AGENT_API_KEY",
            "ANTHROPIC_API_KEY",
            "GH_TOKEN",
            "GITHUB_APP_PRIVATE_KEY_PEM",
            "GITHUB_APP_WEBHOOK_SECRET",
            "GITHUB_DEMO_AUTHOR_HOSTS",
            "GITHUB_DEMO_REVIEWER_HOSTS",
            "HAMSTERDAN_GITHUB_WORKFLOW_TOKEN",
            "OPENAI_API_KEY",
            "OPENAI_AGENT_API_KEY",
        }
        & names
    )


def test_host_launcher_refuses_a_broad_or_symlinked_environment_file(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    assert _run(workspace, environment).returncode == 0
    launch = workspace / ".amp" / "runtime" / "hamsterdan.env"
    launch.chmod(0o644)

    broad = subprocess.run(
        ("scripts/hamsterdan-host",), cwd=workspace, env=environment, check=False, capture_output=True, text=True
    )
    launch.chmod(0o600)
    target = tmp_path / "launch-target"
    launch.rename(target)
    launch.symlink_to(target)
    symlinked = subprocess.run(
        ("scripts/hamsterdan-host",), cwd=workspace, env=environment, check=False, capture_output=True, text=True
    )

    assert broad.returncode != 0
    assert symlinked.returncode != 0


def test_host_launcher_refuses_unqualified_or_redirected_pi_authority(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    assert _run(workspace, environment).returncode == 0
    launch = workspace / ".amp" / "runtime" / "hamsterdan.env"
    original = launch.read_text()
    mutations = (
        original.replace("HAMSTERDAN_PI_MODEL=claude-sonnet-4-5", "HAMSTERDAN_PI_MODEL=unqualified"),
        original.replace("/agent-api-key", "/other-api-key"),
    )

    for mutation in mutations:
        launch.write_text(mutation)
        result = subprocess.run(
            ("scripts/hamsterdan-host",),
            cwd=workspace,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
    launch.write_text(original)


def test_host_launcher_refuses_a_symlinked_runtime_ancestor_with_stale_authority(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    assert _run(workspace, environment).returncode == 0
    runtime = workspace / ".amp" / "runtime"
    stale_runtime = tmp_path / "stale-runtime"
    runtime.rename(stale_runtime)
    runtime.symlink_to(stale_runtime, target_is_directory=True)

    result = subprocess.run(
        ("scripts/hamsterdan-host",),
        cwd=workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert (stale_runtime / "hamsterdan.env").read_text()


def test_host_launcher_rejects_the_retired_parallel_topology_switch(tmp_path: Path) -> None:
    workspace, environment = _sandbox(tmp_path)
    assert _run(workspace, environment).returncode == 0
    selector = workspace / ".amp" / "runtime" / "readiness-topology"

    v5 = subprocess.run(
        ("scripts/hamsterdan-host", "topology", "v5"),
        cwd=workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    production = subprocess.run(
        ("scripts/hamsterdan-host", "topology", "production"),
        cwd=workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert v5.returncode != 0
    assert production.returncode != 0
    assert not selector.exists()


REQUIRED_LAUNCH_NAMES = {
    "HAMSTERDAN_ALLOWED_REPOSITORIES",
    "HAMSTERDAN_GITHUB_ACCOUNT_ID",
    "HAMSTERDAN_GITHUB_ACCOUNT_LOGIN",
    "HAMSTERDAN_GITHUB_APP_ID",
    "HAMSTERDAN_GITHUB_APP_SLUG",
    "HAMSTERDAN_GITHUB_CLIENT_ID",
    "HAMSTERDAN_GITHUB_PRIVATE_KEY_FILE",
    "HAMSTERDAN_GITHUB_WEBHOOK_SECRET_FILE",
    "HAMSTERDAN_PI_API_KEY_FILE",
    "HAMSTERDAN_PI_CLI_PATH",
    "HAMSTERDAN_PI_MODEL",
    "HAMSTERDAN_PI_NODE_PATH",
    "HAMSTERDAN_PI_PACKAGE_ROOT",
    "HAMSTERDAN_PI_PROVIDER",
    "HAMSTERDAN_REMINDER_SECONDS",
    "HAMSTERDAN_STATE_PATH",
    "HAMSTERDAN_WORKFLOW_PATH",
}
