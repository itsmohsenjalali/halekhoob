#!/usr/bin/env python3
"""Verify a streamed backup without expanding its media files (Python 3.10+)."""

import hashlib
import json
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def verify(source):
    hashes = {}
    manifest = None
    with tempfile.TemporaryDirectory() as directory:
        db_path = Path(directory) / "archive.sqlite3"
        json_path = Path(directory) / "database.json"
        with tarfile.open(source, "r|") as archive:
            for item in archive:
                name = PurePosixPath(item.name)
                if (
                    not item.isfile()
                    or name.is_absolute()
                    or ".." in name.parts
                    or item.name in hashes
                ):
                    raise ValueError("Unsafe or duplicate backup entry")
                stream = archive.extractfile(item)
                if item.name == "manifest.json":
                    if manifest is not None or item.size > 20_000_000:
                        raise ValueError("Invalid manifest")
                    manifest = json.load(stream)
                    continue
                digest = hashlib.sha256()
                database = None
                if item.name in {"archive.sqlite3", "database.json"}:
                    database = (db_path if item.name == "archive.sqlite3" else json_path).open("wb")
                try:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                        if database:
                            database.write(chunk)
                finally:
                    if database:
                        database.close()
                hashes[item.name] = digest.hexdigest()
        if not manifest or manifest.get("version") not in {1, 2} or manifest.get("files") != hashes:
            raise ValueError("Backup manifest or checksums do not match")
        if manifest["version"] == 1:
            if not db_path.exists():
                raise ValueError("Missing SQLite database")
            with sqlite3.connect(db_path) as database:
                if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Database integrity check failed")
        else:
            if not json_path.exists():
                raise ValueError("Missing portable database")
            payload = json.loads(json_path.read_text())
            if not isinstance(payload, list) or any(
                row.get("model") not in {"auth.user", "auth.group", "library.video", "library.mood", "library.account", "library.dailyusage"}
                for row in payload
            ):
                raise ValueError("Invalid portable database")
            for asset in manifest["assets"]:
                name = PurePosixPath(asset["path"])
                if name.is_absolute() or ".." in name.parts:
                    raise ValueError("Unsafe asset path")
                if manifest["metadata_only"]:
                    if not asset.get("source_key"):
                        raise ValueError("Missing cloud object reference")
                elif hashes.get(asset["path"]) != asset["sha256"]:
                    raise ValueError("Asset checksum mismatch")
    return len(hashes)


if __name__ == "__main__":
    count = verify(sys.argv[1])
    print(f"Verified {count} files and database format. External R2 references are not checked.")
