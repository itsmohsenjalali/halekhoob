"""Single renewable worker; R2 publication is fenced by a database lease."""

import logging
import shutil
import signal
import tempfile
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from . import quota, r2
from .leases import Lease, LeaseBusy, LeaseLost
from .models import Account, CloudObject, Video
from .storage import archive_lock

logger = logging.getLogger(__name__)


def recover(lease):
    with archive_lock(), transaction.atomic():
        lease.check(locked=True)
        Video.objects.filter(status="downloading").exclude(job_token=lease.token).update(
            status="queued",
            job_token=None,
            progress=0,
            next_attempt_at=timezone.now(),
            error="پردازش قبلی قطع شد؛ دریافت دوباره انجام می‌شود.",
        )
    # SIGKILL cannot run TemporaryDirectory cleanup. Only remove old private
    # scratch directories after acquiring the lease; never touch media objects.
    for folder in (settings.DATA_DIR / "work").glob("job-*"):
        lease.check()
        if (
            folder.is_dir()
            and not folder.is_symlink()
            and folder.stat().st_mtime < time.time() - 86400
        ):
            shutil.rmtree(folder)


def publish(video, outputs, duration, source_title, lease):
    # UUID per attempt: a late worker cannot overwrite the current worker's files.
    attempt = uuid.uuid4().hex
    objects = []
    for path, kind, content_type in outputs:
        if path:
            key = f"{settings.R2_PREFIX}/users/{video.owner_id}/media/{video.pk}/{attempt}/{path.name}"
            with archive_lock():
                lease.check(locked=True)
                record = CloudObject.objects.create(
                    key=key, video=video, owner_id=video.owner_id, size_bytes=path.stat().st_size, sha256=r2.checksum(path)
                )
            objects.append((record, kind))
            r2.upload(path, record, content_type)
    with archive_lock(), transaction.atomic():
        lease.check(locked=True)
        current = Video.objects.select_for_update().get(
            pk=video.pk, job_token=lease.token, status="downloading"
        )
        names = {kind: record.key for record, kind in objects}
        current.file_name = names["video"]
        current.thumbnail_name = names.get("thumbnail", "")
        current.audio_name = names.get("audio", "")
        current.audio_checked = True
        current.storage_backend = "r2"
        current.size_bytes = sum(record.size_bytes for record, _ in objects)
        current.duration = duration
        current.title = current.title or source_title[:300]
        current.status, current.progress = "ready", 100
        current.reserved_bytes = 0
        current.error, current.error_code, current.job_token = "", "", None
        current.save(
            update_fields=[
                "reserved_bytes",
                "file_name",
                "thumbnail_name",
                "audio_name",
                "audio_checked",
                "storage_backend",
                "size_bytes",
                "duration",
                "title",
                "status",
                "progress",
                "error",
                "error_code",
                "job_token",
                "updated_at",
            ]
        )
        CloudObject.objects.filter(pk__in=[o.pk for o, _ in objects]).update(state="live")


def process_one(lease):
    from .audio import extract_audio
    from .worker import JobError, ensure_capacity, run_child, transcode

    with archive_lock(), transaction.atomic():
        lease.check(locked=True)
        video = quota.next_job(Video.objects.select_for_update(of=("self",)).filter(status="queued", next_attempt_at__lte=timezone.now()))
        if not video:
            return False
        quota.ensure_account(video.owner)
        Account.objects.filter(user=video.owner).update(last_served_at=timezone.now())
        video.status, video.job_token = "downloading", lease.token
        video.attempts += 1
        video.save(update_fields=["status", "job_token", "attempts", "updated_at"])
    video.check_lease = lease.check
    work = settings.DATA_DIR / "work"
    work.mkdir(parents=True, exist_ok=True)
    try:
        ensure_capacity()
        with tempfile.TemporaryDirectory(prefix=f"job-{lease.token}-", dir=work) as directory:
            folder = Path(directory)
            source, info = run_child(video, folder)
            lease.check()
            file, thumbnail, duration = transcode(source, folder)
            audio = extract_audio(file, folder)
            lease.check()
            ensure_capacity(sum(p.stat().st_size for p in [file, thumbnail, audio] if p))
            quota.ensure_publish(video, sum(p.stat().st_size for p in [file, thumbnail, audio] if p))
            publish(
                video,
                [
                    (file, "video", "video/mp4"),
                    (thumbnail, "thumbnail", "image/jpeg"),
                    (audio, "audio", "audio/mp4"),
                ],
                duration,
                info.get("title", ""),
                lease,
            )
    except LeaseLost:
        raise
    except Exception as exc:
        if isinstance(exc, r2.StorageError):
            exc = JobError("storage", "ارتباط با فضای فایل‌ها قطع شد؛ دوباره تلاش می‌کنیم.", True)
        if not isinstance(exc, JobError):
            logger.error("Video %s: processing failed (%s)", video.pk, type(exc).__name__)
            exc = JobError("internal", "پردازش فایل کامل نشد؛ دوباره تلاش کن.")
        from datetime import timedelta

        with archive_lock():
            lease.check(locked=True)
            automatic = exc.transient and video.attempts < 3
            Video.objects.filter(pk=video.pk, job_token=lease.token).update(
                status="queued" if automatic else "failed",
                progress=0,
                job_token=None,
                reserved_bytes=video.reserved_bytes if automatic else 0,
                error=str(exc),
                error_code=exc.code,
                next_attempt_at=timezone.now()
                + timedelta(seconds=30 * 2 ** min(video.attempts - 1, 6)),
            )
            r2.defer_delete(CloudObject.objects.filter(video=video, state="pending"))
    return True


def work(once=False):
    def shutdown(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    while True:
        try:
            with Lease() as lease:
                recover(lease)
                last_cleanup = 0
                while True:
                    close_old_connections()
                    lease.check()
                    if time.monotonic() - last_cleanup > 60:
                        r2.cleanup(lease.check)
                        last_cleanup = time.monotonic()
                    processed = process_one(lease)
                    if once:
                        return processed
                    if not processed:
                        time.sleep(5)
        except LeaseBusy:
            if once:
                return False
            time.sleep(10)
        except LeaseLost:
            if once:
                raise
            time.sleep(5)
