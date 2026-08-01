"""The project builds only the intended Hamsterdan source package."""

from __future__ import annotations

import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).parents[1]


def test_built_artifacts_contain_no_credentials_or_runtime_state(tmp_path: Path) -> None:
    subprocess.run(
        ("uv", "build", "--out-dir", str(tmp_path)),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    archives = tuple(path for path in tmp_path.iterdir() if path.suffix in {".gz", ".whl"})
    assert {path.suffix for path in archives} >= {".whl", ".gz"}
    for archive in archives:
        if archive.suffix == ".whl":
            with zipfile.ZipFile(archive) as wheel:
                members = tuple(wheel.namelist())
        else:
            with tarfile.open(archive, "r:gz") as sdist:
                members = tuple(sdist.getnames())
        assert members
        for member in members:
            path = PurePosixPath(member)
            assert not path.is_absolute()
            assert ".." not in path.parts
            assert not any(part in {".env", ".git", ".amp", ".agents"} for part in path.parts)
            assert path.suffix not in {".key", ".pem", ".sqlite", ".sqlite3"}
