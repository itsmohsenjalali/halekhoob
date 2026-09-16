import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts import cloud_backup
from scripts.verify_export import verify

from library.management.commands.import_portable import unpack


def test_backup_failure_restarts_original_worker_without_rotating(tmp_path):
    for index in range(5):
        (tmp_path / f"metadata-{index}.tar").write_bytes(b"previous backup")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if "run" in command:
            raise subprocess.CalledProcessError(1, command)

    with (
        patch.object(sys, "argv", ["cloud_backup.py", str(tmp_path)]),
        patch.object(subprocess, "check_output", return_value="worker\n"),
        patch.object(subprocess, "run", side_effect=run),
        pytest.raises(subprocess.CalledProcessError),
    ):
        cloud_backup.main()
    assert commands[0][-2:] == ["stop", "worker"]
    assert commands[-1][-2:] == ["start", "worker"]
    assert len(list(tmp_path.glob("*.tar"))) == 5


def test_smoke_script_refuses_cloud_database_before_initializing_django(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts/smoke_downloads.py"),
            "unused.txt",
            "--data-dir",
            str(tmp_path / "scratch"),
            "--report",
            str(tmp_path / "report.json"),
        ],
        env={**os.environ, "DATABASE_URL": "postgresql://never-connect.invalid/test"},
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "no DATABASE_URL" in result.stderr
    assert not (tmp_path / "scratch").exists()


@pytest.mark.parametrize("name", ["../escaped", "/absolute"])
def test_portable_unsafe_tar_paths_are_rejected(tmp_path, name):
    from django.core.management.base import CommandError

    source = tmp_path / "unsafe.tar"
    with tarfile.open(source, "w") as archive:
        item = tarfile.TarInfo(name)
        item.size = 1
        archive.addfile(item, io.BytesIO(b"x"))
    with pytest.raises(CommandError, match="Unsafe"):
        unpack(source, tmp_path)
    with pytest.raises(ValueError, match="Unsafe"):
        verify(source)
