import io
import json
import sqlite3
import tarfile
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from deploy import oci_backup
from deploy.oci_backup import rotation_plan
from django.core.management import call_command
from django.core.management.base import CommandError

from library.management.commands.export_archive import sha256


def backup(number, kind="backup", own=True):
    return {
        "id": str(number),
        "kind": kind,
        "volume-id": "data",
        "boot-volume-id": "boot",
        "freeform-tags": {"application": "halekhoob" if own else "other"},
        "lifecycle-state": "AVAILABLE",
        "time-created": datetime(2026, 1, number).isoformat(),
    }


def test_backup_rotation_never_exceeds_five():
    items = [backup(n) for n in range(1, 5)] + [backup(5, "boot-volume-backup")]
    removed, make_boot = rotation_plan(items, "data", "boot")
    assert [b["id"] for b in removed] == ["1"] and not make_boot
    assert len(items) - len(removed) + 1 == 5


def test_backup_never_deletes_unrelated_resources():
    with pytest.raises(RuntimeError):
        rotation_plan([backup(n, own=False) for n in range(1, 6)], "data", "boot")


def test_backup_waits_for_pending_operations():
    item = backup(1)
    item["lifecycle-state"] = "CREATING"
    with pytest.raises(RuntimeError):
        rotation_plan([item], "data", "boot")


def test_restore_checksum_and_database(tmp_path):
    source = tmp_path / "fixture"
    source.mkdir()
    database = source / "archive.sqlite3"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE video (title TEXT)")
        db.execute("INSERT INTO video VALUES ('hope')")
    media = source / "1.mp4"
    media.write_bytes(b"test-media")
    manifest = source / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "files": {"archive.sqlite3": sha256(database), "media/1.mp4": sha256(media)},
            }
        )
    )
    snapshot = tmp_path / "backup.tar"
    with tarfile.open(snapshot, "w") as archive:
        archive.add(database, arcname="archive.sqlite3")
        archive.add(media, arcname="media/1.mp4")
        archive.add(manifest, arcname="manifest.json")
    restored = tmp_path / "restored"
    call_command("restore_archive", str(snapshot), str(restored))
    assert (restored / "media/1.mp4").read_bytes() == b"test-media"
    with sqlite3.connect(restored / "archive.sqlite3") as db:
        assert db.execute("SELECT title FROM video").fetchone()[0] == "hope"
    with pytest.raises(CommandError):
        call_command("restore_archive", str(snapshot), str(restored))


def test_restore_blocks_path_traversal(tmp_path):
    snapshot = tmp_path / "evil.tar"
    with tarfile.open(snapshot, "w") as archive:
        info = tarfile.TarInfo("../outside")
        info.size = 4
        archive.addfile(info, io.BytesIO(b"evil"))
    with pytest.raises(CommandError):
        call_command("restore_archive", str(snapshot), str(tmp_path / "out"))
    assert not (tmp_path / "outside").exists()


def test_failed_cloud_snapshot_restarts_original_services(monkeypatch):
    monkeypatch.setenv("OCI_DATA_VOLUME_ID", "data")
    monkeypatch.setenv("OCI_BOOT_VOLUME_ID", "boot")
    monkeypatch.setattr(oci_backup, "ARGS", SimpleNamespace(apply=True), raising=False)

    def cloud(*args):
        if args[2] == "get":
            return {"data": {"size-in-gbs": 50}}
        raise RuntimeError("snapshot failed")

    database = MagicMock()
    database.__enter__.return_value.execute.return_value.fetchone.return_value = ("ok",)
    with (
        patch.object(oci_backup, "inventory", return_value=[]),
        patch.object(oci_backup, "cli", side_effect=cloud),
        patch.object(oci_backup.sqlite3, "connect", return_value=database),
        patch.object(
            oci_backup.subprocess, "run", return_value=SimpleNamespace(returncode=0)
        ) as run,
        pytest.raises(RuntimeError, match="snapshot failed"),
    ):
        oci_backup.apply()
    assert run.call_args_list[-1].args[0] == [
        "systemctl",
        "start",
        "motivation-worker",
        "motivation-web",
    ]
