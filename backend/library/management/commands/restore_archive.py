import json
import sqlite3
import tarfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from .export_archive import sha256


class Command(BaseCommand):
    help = (
        "Verify and restore an export into a NEW, empty directory. Never overwrite a live archive."
    )

    def add_arguments(self, parser):
        parser.add_argument("source")
        parser.add_argument("destination")

    def handle(self, *args, **options):
        if settings.MEDIA_BACKEND == "r2":
            raise CommandError(
                "Use export_portable/import_portable for cloud archives; prepare audio before migrating local media."
            )
        destination = Path(options["destination"]).resolve()
        if destination.exists():
            raise CommandError(
                "Destination must not exist. Stop services before switching DATA_DIR."
            )
        try:
            with tarfile.open(options["source"], "r") as archive:
                members = archive.getmembers()
                if len({m.name for m in members}) != len(members):
                    raise CommandError("Duplicate archive entries.")
                for member in members:
                    path = (destination / member.name).resolve()
                    if (
                        not member.isfile()
                        or not path.is_relative_to(destination)
                        or member.name.startswith("/")
                    ):
                        raise CommandError("Unsafe archive entry.")
                stream = archive.extractfile("manifest.json")
                manifest = json.load(stream)
                if manifest.get("version") != 1 or "archive.sqlite3" not in manifest["files"]:
                    raise CommandError("Unsupported or incomplete backup.")
                if {m.name for m in members} != set(manifest["files"]) | {"manifest.json"}:
                    raise CommandError("Archive does not match manifest.")
                destination.mkdir(parents=True, mode=0o700)
                archive.extractall(destination, filter="data")
            for name, expected in manifest["files"].items():
                if sha256(destination / name) != expected:
                    raise CommandError(f"Checksum mismatch: {name}")
            with sqlite3.connect(destination / "archive.sqlite3") as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise CommandError("Database integrity check failed.")
            (destination / "media").mkdir(exist_ok=True)
        except (tarfile.TarError, ValueError, KeyError, OSError) as exc:
            raise CommandError(f"Restore failed; do not use this destination: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Verified restore: {destination}. Keep services stopped while switching DATA_DIR."
            )
        )
