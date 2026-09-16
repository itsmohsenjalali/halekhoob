"""Portable, verified account + archive export for SQLite -> PostgreSQL/R2 and backups."""

import json
import os
import shutil
import tarfile
import tempfile
import uuid
from contextlib import nullcontext
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError

from library import r2
from library.leases import Lease
from library.models import Account, CloudObject, DailyUsage, Mood, Video
from library.storage import archive_lock, private_path


class Command(BaseCommand):
    help = "Export portable .tar for cloud migration/restore. Stop the cloud worker first."

    def add_arguments(self, parser):
        parser.add_argument("destination")
        parser.add_argument(
            "--metadata-only",
            action="store_true",
            help="Cloud daily backup: references immutable R2 files instead of copying them.",
        )

    def handle(self, *args, **options):
        target = Path(options["destination"]).resolve()
        if target.exists() or target.is_relative_to(settings.DATA_DIR.resolve()):
            raise CommandError("Choose a new destination outside DATA_DIR.")
        if options["metadata_only"] and settings.MEDIA_BACKEND != "r2":
            raise CommandError("Metadata-only export requires R2.")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with (
                Lease() if settings.MEDIA_BACKEND == "r2" else nullcontext() as lease,
                tempfile.TemporaryDirectory(dir=target.parent) as directory,
            ):
                root = Path(directory)
                with archive_lock(exclusive=True):
                    videos = list(Video.objects.prefetch_related("moods"))
                    assets = []
                    for video in videos:
                        if lease:
                            lease.check()
                        if video.status == "downloading":
                            video.status, video.progress = "queued", 0
                        video.job_token = None
                        if video.status != "ready":
                            continue
                        for field, suffix, content_type in [
                            ("file_name", "mp4", "video/mp4"),
                            ("thumbnail_name", "jpg", "image/jpeg"),
                            ("audio_name", "m4a", "audio/mp4"),
                        ]:
                            name = getattr(video, field)
                            if not name:
                                continue
                            relative = f"media/{video.pk}/{field}.{suffix}"
                            path = root / relative
                            path.parent.mkdir(parents=True, exist_ok=True)
                            if video.storage_backend == "r2":
                                record = CloudObject.objects.get(
                                    key=name, video=video, state="live"
                                )
                                digest, size = record.sha256, record.size_bytes
                            else:
                                source = private_path(name)
                                if options["metadata_only"]:
                                    raise CommandError(
                                        "Migrate all ready media before metadata-only export."
                                    )
                                shutil.copyfile(source, path)
                                digest, size = r2.checksum(path), path.stat().st_size
                            assets.append(
                                {
                                    "video": video.pk,
                                    "field": field,
                                    "path": relative,
                                    "sha256": digest,
                                    "size": size,
                                    "content_type": content_type,
                                    "source_key": name if video.storage_backend == "r2" else None,
                                }
                            )
                    objects = [
                        *Group.objects.all(),
                        *get_user_model().objects.all(),
                        *Account.objects.all(),
                        *DailyUsage.objects.all(),
                        *Mood.objects.all(),
                        *videos,
                    ]
                    data = root / "database.json"
                    data.write_text(
                        serializers.serialize("json", objects, use_natural_foreign_keys=True),
                        encoding="utf-8",
                    )
                # Immutable cloud keys and the worker lease keep files stable while
                # normal web writes resume after the short metadata snapshot.
                if not options["metadata_only"]:
                    for asset in assets:
                        if asset["source_key"]:
                            lease.check()
                            r2.download(asset["source_key"], root / asset["path"], asset["sha256"])
                files = {"database.json": r2.checksum(data)}
                if not options["metadata_only"]:
                    files.update({asset["path"]: asset["sha256"] for asset in assets})
                manifest = {
                    "version": 2,
                    "id": uuid.uuid4().hex,
                    "metadata_only": options["metadata_only"],
                    "files": files,
                    "assets": assets,
                }
                (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                output = root / "export.tar"
                with tarfile.open(output, "w") as archive:
                    for name in [*files, "manifest.json"]:
                        archive.add(root / name, arcname=name, recursive=False)
                if lease:
                    lease.check()
                os.chmod(output, 0o600)
                os.replace(output, target)
        except Exception as exc:
            raise CommandError(
                f"Portable export failed ({type(exc).__name__}); no completed export was published."
            ) from exc
        self.stdout.write(f"Private portable export created: {target}")
