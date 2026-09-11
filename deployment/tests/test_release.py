from __future__ import annotations

import json
from pathlib import Path

import pytest

from deployment import release


def source(*, dirty: bool = False) -> release.Source:
    return release.Source(
        revision="a" * 40,
        version="0.1.0",
        source_date_epoch=1_787_577_714,
        dirty=dirty,
    )


def test_build_command_is_shared_and_requires_no_build_secret(tmp_path: Path) -> None:
    command = release.build_command(
        container=("docker",),
        image="hamsterdan:sha-aaaaaaaaaaaa",
        metadata=tmp_path / "build-metadata.json",
        source=source(),
    )

    assert command[:4] == ("docker", "buildx", "build", "--load")
    assert ("--platform", "linux/amd64") == command[command.index("--platform") : command.index("--platform") + 2]
    assert "--secret" not in command
    assert not any("PETRUS_GITHUB_TOKEN" in argument for argument in command)
    assert f"SOURCE_REVISION={'a' * 40}" in command
    assert "SOURCE_VERSION=0.1.0" in command
    assert any(argument.startswith("SOURCE_CREATED=") and argument.endswith("Z") for argument in command)
    assert str(tmp_path / "build-metadata.json") in command
    assert all("secret-canary" not in argument for argument in command)
    assert command[-3:] == ("--file", "deployment/Containerfile", ".")


def test_orb_container_command_uses_sudo_without_preserving_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release.shutil, "which", lambda _: "/usr/bin/docker")

    assert release.container_command({"AMP_ORB": "1"}) == ("sudo", "docker")


def test_dirty_source_requires_an_explicit_development_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    responses = {
        ("git", "rev-parse", "HEAD"): "b" * 40,
        ("git", "status", "--porcelain", "--untracked-files=normal"): " M src/example.py",
        ("git", "show", "-s", "--format=%ct", "HEAD"): "1787577714",
    }
    monkeypatch.setattr(release, "capture", lambda command, **_: responses[tuple(command)])
    monkeypatch.setattr(release, "project_version", lambda _: "0.1.0")

    with pytest.raises(release.ReleaseError, match="clean commit"):
        release.read_source(tmp_path, development=False)

    assert release.read_source(tmp_path, development=True).dirty is True


def test_verify_checks_the_built_image_identity_and_manifest_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_id = f"sha256:{'b' * 64}"
    path = tmp_path / "release.json"
    path.write_text(
        json.dumps(
            {
                "image": "hamsterdan:dev-aaaaaaaaaaaa",
                "image_id": image_id,
                "source_revision": "a" * 40,
                "verified": False,
                "version": "9.8.7",
            }
        )
    )
    commands: list[tuple[str, ...]] = []
    captures: list[tuple[str, ...]] = []

    def fake_capture(command: tuple[str, ...], **_: object) -> str:
        captures.append(command)
        if "--format={{json .Config.Labels}}" in command:
            return json.dumps(
                {
                    "org.opencontainers.image.revision": "a" * 40,
                    "org.opencontainers.image.version": "9.8.7",
                }
            )
        if "--format={{.Id}}" in command:
            return image_id
        if command[-1] == "--version":
            if command[-2].endswith("dist/cli.js"):
                return "0.83.0"
            return "v22.19.0"
        if command[-1] == "--help":
            return "help"
        raise AssertionError(command)

    monkeypatch.setattr(release, "container_command", lambda _: ("docker",))
    monkeypatch.setattr(release, "capture", fake_capture)
    monkeypatch.setattr(release, "run", lambda command, **_: commands.append(tuple(command)))

    release.verify(path)

    assert json.loads(path.read_text())["verified"] is True
    python_check = next(command for command in commands if "/opt/hamsterdan/.venv/bin/python" in command)
    assert "9.8.7" in python_check[-1]
    assert "0.1.0" not in python_check[-1]
    assert any(
        "/opt/hamsterdan/pi/node_modules/@earendil-works/pi-coding-agent/dist/cli.js" in command for command in captures
    )
    assert any(command[-1] == "test -w /var/lib/hamsterdan" for command in commands)


def test_verify_command_accepts_and_reports_a_repository_relative_manifest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = Path("dist/deployment/revision/release.json")
    monkeypatch.chdir(release.ROOT)
    monkeypatch.setattr(release, "verify", lambda path: path)
    monkeypatch.setattr(release.sys, "argv", ["release.py", "verify", "--manifest", str(manifest)])

    assert release.main() == 0
    assert capsys.readouterr().out == f"{manifest}\n"
