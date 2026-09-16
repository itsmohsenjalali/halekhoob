import hashlib
import json
import os
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from library.models import Video
from library.storage import archive_lock, private_path


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class Command(BaseCommand):
    help = "Export a consistent database + media snapshot (keep this private; it includes account data)."

    def add_arguments(self, parser):
        parser.add_argument(
            "destination", help="New .tar outside DATA_DIR, or '-' to stream through SSH."
        )

    def handle(self, *args, **options):
        if settings.MEDIA_BACKEND == "r2":
            raise CommandError(
                "Use export_portable/import_portable for cloud archives; prepare audio before migrating local media."
            )
        streaming = options["destination"] == "-"
        destination = None if streaming else Path(options["destination"]).resolve()
        if destination and (
            destination.exists() or destination.is_relative_to(settings.DATA_DIR.resolve())
        ):
            raise CommandError("Choose a new destination outside DATA_DIR.")
        if destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
        # Worker holds a shared lock for an entire job. This waits for completion; web reads remain available.
        with (
            archive_lock(exclusive=True),
            tempfile.TemporaryDirectory(
                dir=settings.DATA_DIR if streaming else destination.parent
            ) as directory,
        ):
            temporary = Path(directory)
            database = temporary / "archive.sqlite3"
            with (
                sqlite3.connect(str(settings.DATABASES["default"]["NAME"]), uri=True) as source,
                sqlite3.connect(database) as target,
            ):
                source.backup(target)
            files = [(database, "archive.sqlite3")]
            for video in Video.objects.filter(status=Video.Status.READY):
                for name in [video.file_name, video.thumbnail_name, video.audio_name]:
                    if name:
                        files.append((private_path(name), f"media/{name}"))
            manifest = {"version": 1, "files": {name: sha256(path) for path, name in files}}
            manifest_path = temporary / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            partial = temporary / "export.tar"
            output = (
                tarfile.open(fileobj=sys.stdout.buffer, mode="w|")
                if streaming
                else tarfile.open(partial, "w")
            )
            with output as archive:
                for path, name in files:
                    archive.add(path, arcname=name, recursive=False)
                archive.add(manifest_path, arcname="manifest.json")
            if destination:
                os.chmod(partial, 0o600)
                os.replace(partial, destination)
        if destination:
            self.stdout.write(self.style.SUCCESS(f"Export written: {destination}"))
        else:
            self.stderr.write("Archive stream completed.")
