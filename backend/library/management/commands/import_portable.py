import json
import re
import tarfile
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from library import r2
from library.leases import Lease
from library.models import CloudObject, Mood, Video
from library.storage import archive_lock


def unpack(source, root):
    with tarfile.open(source, "r") as archive:
        members = archive.getmembers()
        if len({m.name for m in members}) != len(members):
            raise CommandError("Duplicate archive entries.")
        for member in members:
            if (
                not member.isfile()
                or member.name.startswith("/")
                or not (root / member.name).resolve().is_relative_to(root)
            ):
                raise CommandError("Unsafe archive entry.")
        manifest = json.load(archive.extractfile("manifest.json"))
        if manifest.get("version") != 2 or not re.fullmatch(
            r"[a-f0-9]{32}", manifest.get("id", "")
        ):
            raise CommandError("Not a portable version-2 archive.")
        if set(manifest["files"]) | {"manifest.json"} != {m.name for m in members}:
            raise CommandError("Archive does not match manifest.")
        archive.extractall(root, filter="data")
    for name, digest in manifest["files"].items():
        if r2.checksum(root / name) != digest:
            raise CommandError("Checksum mismatch.")
    if "database.json" not in manifest["files"]:
        raise CommandError("Missing database.")
    payload = json.loads((root / "database.json").read_text())
    if any(
        row["model"] not in {"auth.user", "auth.group", "library.mood", "library.video", "library.account", "library.dailyusage", "library.quotachange"}
        for row in payload
    ):
        raise CommandError("Unexpected model in backup.")
    videos = {row["pk"]: row for row in payload if row["model"] == "library.video"}
    seen = set()
    for asset in manifest["assets"]:
        pair = (asset["video"], asset["field"])
        if (
            pair in seen
            or asset["video"] not in videos
            or asset["field"] not in {"file_name", "audio_name", "thumbnail_name"}
        ):
            raise CommandError("Invalid asset mapping.")
        seen.add(pair)
        if (
            not manifest["metadata_only"]
            and manifest["files"].get(asset["path"]) != asset["sha256"]
        ):
            raise CommandError("Asset checksum missing from manifest.")
        if not (root / asset["path"]).resolve().is_relative_to(root):
            raise CommandError("Invalid asset path.")
    for pk, row in videos.items():
        if row["fields"]["status"] == "ready":
            if not row["fields"].get("file_name"):
                raise CommandError("Ready video has no media file.")
            for field in ["file_name", "thumbnail_name", "audio_name"]:
                if row["fields"].get(field) and (pk, field) not in seen:
                    raise CommandError("Ready video is missing an asset.")
    return manifest


class Command(BaseCommand):
    help = "Import a verified portable backup into a migrated, empty PostgreSQL/R2 installation."

    def add_arguments(self, parser):
        parser.add_argument("source")

    def handle(self, *args, **options):
        if settings.MEDIA_BACKEND != "r2":
            raise CommandError("Set MEDIA_BACKEND=r2 for cloud import.")
        if Video.objects.exists() or get_user_model().objects.exists():
            raise CommandError(
                "Target database must have no accounts or videos. Never overwrite a live archive."
            )
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=settings.DATA_DIR) as directory:
            root = Path(directory).resolve()
            try:
                manifest = unpack(options["source"], root)
                with Lease() as lease:
                    mapping = []
                    for asset in manifest["assets"]:
                        lease.check()
                        if manifest["metadata_only"]:
                            key = r2.valid_key(asset["source_key"])
                            head = r2.client().head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
                            if (
                                head["ContentLength"] != asset["size"]
                                or head.get("Metadata", {}).get("sha256") != asset["sha256"]
                            ):
                                raise CommandError(
                                    "Referenced R2 object is missing or differs from backup."
                                )
                        else:
                            path = root / asset["path"]
                            if path.stat().st_size != asset["size"]:
                                raise CommandError("Asset size mismatch.")
                            key = f"{settings.R2_PREFIX}/media/{asset['video']}/{manifest['id']}/{path.name}"
                        with archive_lock():
                            lease.check(locked=True)
                            record, created = CloudObject.objects.get_or_create(
                                key=key,
                                defaults={"size_bytes": asset["size"], "sha256": asset["sha256"]},
                            )
                        if record.sha256 != asset["sha256"] or record.size_bytes != asset["size"]:
                            raise CommandError("Conflicting object key.")
                        if not manifest["metadata_only"]:
                            r2.upload(path, record, asset["content_type"])
                        mapping.append((asset, record))
                    with archive_lock(exclusive=True), transaction.atomic():
                        lease.check(locked=True)
                        if Video.objects.exists() or get_user_model().objects.exists():
                            raise CommandError("Target database is no longer empty.")
                        # Seed moods are recreated from the backup with original IDs.
                        Mood.objects.all().delete()
                        payload = json.loads((root / "database.json").read_text())
                        # Account count caps were removed; accept backups from earlier releases.
                        for row in payload:
                            if row['model'] == 'library.account':
                                row['fields'].pop('daily_download_limit', None)
                                row['fields'].pop('queue_limit', None)
                            if row['model'] == 'library.video':
                                row['fields']['reserved_bytes'] = 0
                        # Older backups have global moods. Assign/clone them to each video owner.
                        users = [row for row in payload if row['model'] == 'auth.user']
                        next_id = max([row['pk'] for row in payload if row['model'] == 'library.mood'] or [0]) + 1
                        for mood in list(payload):
                            if mood['model'] != 'library.mood' or 'owner' in mood['fields']:
                                continue
                            original = mood['pk']
                            for index, user in enumerate(users):
                                if index == 0:
                                    mood['fields']['owner'] = [user['fields']['username']]
                                else:
                                    clone = {**mood, 'pk': next_id, 'fields': {**mood['fields'], 'owner': [user['fields']['username']]}}
                                    payload.append(clone)
                                    for row in payload:
                                        if row['model'] == 'library.video' and row['fields']['owner'] == [user['fields']['username']]:
                                            row['fields']['moods'] = [next_id if i == original else i for i in row['fields']['moods']]
                                    next_id += 1
                        (root / 'database.json').write_text(json.dumps(payload))
                        call_command("loaddata", str(root / "database.json"), verbosity=0)
                        for user in get_user_model().objects.all():
                            from library.models import Account
                            Account.objects.get_or_create(user=user)
                        for asset, record in mapping:
                            Video.objects.filter(pk=asset["video"]).update(
                                **{
                                    asset["field"]: record.key,
                                    "storage_backend": "r2",
                                    "job_token": None,
                                }
                            )
                            record.video_id, record.state, record.delete_after = (
                                asset["video"],
                                "live",
                                None,
                            )
                            record.owner_id = Video.objects.get(pk=asset["video"]).owner_id
                            record.save(update_fields=["video", "owner", "state", "delete_after"])
                        Video.objects.filter(status="downloading").update(
                            status="queued", job_token=None, progress=0
                        )
                        for video in Video.objects.filter(status="ready"):
                            size = sum(
                                asset["size"] for asset, _ in mapping if asset["video"] == video.pk
                            )
                            Video.objects.filter(pk=video.pk).update(size_bytes=size)
            except CommandError:
                raise
            except Exception as exc:
                raise CommandError(
                    f"Import failed ({type(exc).__name__}); fix the cause and retry the same backup."
                ) from exc
        self.stdout.write("Cloud import verified and committed. Original archive was not changed.")
