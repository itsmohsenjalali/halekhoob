import fcntl
import json
import logging
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import quota
from .audio import extract_audio
from .models import Account, Video
from .storage import archive_lock

logger = logging.getLogger(__name__)


class JobError(Exception):
    def __init__(self, code, message, transient=False):
        super().__init__(message)
        self.code, self.transient = code, transient


def explain_error(raw):
    text = raw.lower()
    if "archive_youtube_session_invalid" in text:
        return JobError("source_session", "نشست دانلود یوتیوب نیاز به بررسی مدیر دارد؛ لینک و دسته‌ها حفظ شده‌اند.")
    if "archive_limit_authenticated_content" in text:
        return JobError("login_required", "فقط ویدیوهای عمومی بدون محدودیت ورود، سن یا اشتراک قابل دریافت هستند.")
    # A public video can trigger a source-side verification gate for this server.
    # Do not mislabel it as private content or retry the verification in a loop.
    if any(marker in text for marker in ["not a bot", "confirm you’re not", "confirm you're not", "unusual traffic"]):
        source = "یوتیوب" if "youtube" in text else "منبع ویدیو"
        return JobError(
            "source_verification",
            f"{source} دریافت از این سرور را متوقف کرده و تأیید انسانی می‌خواهد. "
            "این خطا به حجم یا مدت ویدیو مربوط نیست؛ ورود دوباره به حال‌خوب هم آن را برطرف نمی‌کند. "
            "لینک و دسته‌ها حفظ شده‌اند؛ پس از رفع محدودیت منبع می‌توان دوباره تلاش کرد.",
        )
    if "archive_limit_size" in text or "larger than max" in text or "max-filesize" in text:
        return JobError("size", "حجم ویدیو از فضای باقی‌ماندهٔ حسابت بیشتر است.")
    if "archive_limit_collection" in text or "archive_limit_live" in text:
        return JobError(
            "unsupported",
            "فقط لینک یک ویدیوی منتشرشده پشتیبانی می‌شود؛ پخش زنده یا مجموعه قابل دریافت نیست.",
        )
    if any(
        s in text
        for s in [
            "sign in",
            "login",
            "log in",
            "cookies",
            "private video",
            "confirm you're",
            "age-restricted",
        ]
    ):
        return JobError(
            "login_required",
            "منبع برای این ویدیو درخواست ورود کرده است؛ نسخهٔ اول فقط ویدیوهای بدون نیاز به ورود را دریافت می‌کند.",
        )
    if any(
        s in text
        for s in ["removed", "unavailable", "not available", "404", "copyright", "does not exist"]
    ):
        return JobError("unavailable", "ویدیو در منبع در دسترس نیست؛ لینک اصلی را بررسی کن.")
    if any(
        s in text
        for s in [
            "timed out",
            "timeout",
            "429",
            "502",
            "503",
            "connection",
            "network",
            "temporary",
            "resolve",
        ]
    ):
        return JobError(
            "network", "ارتباط با منبع قطع یا محدود شد؛ دانلود دوباره امتحان می‌شود.", True
        )
    if "403" in text or "forbidden" in text:
        return JobError("blocked", "منبع دانلود از این سرور را نپذیرفت؛ بعداً دوباره امتحان کن.")
    return JobError(
        "extractor",
        "دانلود کامل نشد؛ لینک را بررسی کن. ممکن است ابزار دانلود نیاز به به‌روزرسانی داشته باشد.",
    )


def used_bytes():
    if settings.MEDIA_BACKEND == "r2":
        from .r2 import stored_bytes

        return stored_bytes()
    return Video.objects.aggregate(n=Sum("size_bytes"))["n"] or 0


def ensure_capacity(required=None):
    required = 0 if required is None else required
    if shutil.disk_usage(settings.DATA_DIR).free < settings.MIN_FREE_BYTES + required * 3:
        raise JobError(
            "disk", "فضای آزاد سرور برای دانلود و پردازش کافی نیست؛ فایل‌های قبلی حفظ شده‌اند."
        )


def terminate(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def run_child(video, folder):
    max_bytes = quota.budget(video)
    events_path = folder / "events.jsonl"
    command = [
        sys.executable,
        "-m",
        "library.downloader",
        video.source_url,
        str(folder),
        "--max-bytes",
        str(max_bytes),
    ]
    if video.platform == "youtube" and settings.YOUTUBE_COOKIES_FILE:
        command.extend(["--youtube-cookies", settings.YOUTUBE_COOKIES_FILE])
    # Only the explicitly configured YouTube session is allowed; never inherit
    # app credentials, proxies, browser profiles or arbitrary Python config.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "SSL_CERT_FILE") if key in os.environ}
    env["PYTHONUNBUFFERED"] = "1"
    started = time.monotonic()
    cursor = 0
    result = None
    error = ""
    with events_path.open("w") as output:
        process = subprocess.Popen(
            command,
            cwd=settings.BASE_DIR,
            env=env,
            stdout=output,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            while True:
                time.sleep(0.25)
                if hasattr(video, "check_lease"):
                    video.check_lease()
                if time.monotonic() - started > settings.DOWNLOAD_TIMEOUT:
                    raise JobError(
                        "network", "زمان دریافت ویدیو تمام شد؛ دوباره تلاش می‌کنیم.", True
                    )
                total = sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
                if total > max_bytes * 2 + 1_000_000:
                    raise explain_error("ARCHIVE_LIMIT_SIZE")
                if shutil.disk_usage(folder).free < settings.MIN_FREE_BYTES:
                    raise JobError("disk", "فضای آزاد سرور کافی نیست؛ فایل‌های قبلی حفظ شده‌اند.")
                with events_path.open() as events:
                    events.seek(cursor)
                    for line in events:
                        if not line.endswith("\n"):
                            break
                        cursor += len(line.encode())
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if event.get("event") == "progress":
                            Video.objects.filter(pk=video.pk, job_token=video.job_token).update(
                                progress=max(0, min(88, int(event.get("progress", 0))))
                            )
                        elif event.get("event") == "complete":
                            result = event
                        elif event.get("event") == "error":
                            error = event.get("message", "")
                if process.poll() is not None:
                    break
            if process.returncode or result is None:
                raise explain_error(error)
            source = (folder / result["file"]).resolve()
            if source.parent != folder.resolve() or not source.is_file():
                raise JobError("file", "فایل دانلودشده معتبر نیست.")
            if source.stat().st_size > max_bytes:
                raise explain_error("ARCHIVE_LIMIT_SIZE")
            return source, result
        finally:
            terminate(process)


def probe(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        info = json.loads(result.stdout)
        duration = float(info["format"].get("duration", 0))
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Invalid duration")
        return duration, video, info["streams"]
    except (subprocess.SubprocessError, ValueError, KeyError, StopIteration):
        raise JobError("file", "فایل ویدیویی سالم دریافت نشد؛ دوباره تلاش کن.") from None


def processing_budget(folder, requested):
    # FFmpeg's -fs is approximate. Leave the disk reserve plus a packet margin.
    available = shutil.disk_usage(folder).free - settings.MIN_FREE_BYTES - 1_000_000
    if available <= 0:
        raise JobError("disk", "فضای آزاد سرور برای پردازش کافی نیست.")
    if requested <= 0:
        raise explain_error("ARCHIVE_LIMIT_SIZE")
    return min(requested, available)


def transcode(source, folder, max_bytes=None):
    max_bytes = settings.DEFAULT_USER_STORAGE_BYTES if max_bytes is None else max_bytes
    requested = max_bytes
    max_bytes = processing_budget(folder, max_bytes)
    duration, stream, streams = probe(source)
    destination = folder / "video.mp4"
    compatible = (
        stream.get("codec_name") == "h264"
        and stream.get("pix_fmt") == "yuv420p"
        and all(s.get("codec_name") == "aac" for s in streams if s.get("codec_type") == "audio")
        and stream.get("height", 0) <= 720
    )
    codecs = (
        ["-c", "copy"]
        if compatible
        else [
            "-vf",
            "scale=w=-2:h='trunc(min(720,ih)/2)*2'",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-threads",
            "2",
        ]
    )
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        *codecs,
        "-movflags",
        "+faststart",
        "-fs",
        str(max_bytes),
        "-y",
        str(destination),
    ]
    try:
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=settings.DOWNLOAD_TIMEOUT,
        )
        actual_duration, actual_video, _ = probe(destination)
        if (
            abs(actual_duration - duration) > max(2, duration * 0.005)
            or destination.stat().st_size >= max_bytes
        ):
            if max_bytes < requested:
                raise JobError("disk", "فضای آزاد سرور برای پردازش کامل کافی نیست.")
            raise explain_error("ARCHIVE_LIMIT_SIZE")
        if actual_video.get("codec_name") != "h264" or actual_video.get("height", 0) > 720:
            raise JobError("file", "فایل برای پخش در مرورگر آماده نشد.")
        thumbnail = folder / "thumbnail.jpg"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-ss",
                str(min(1, duration / 2)),
                "-i",
                str(destination),
                "-frames:v",
                "1",
                "-vf",
                "scale=640:-2",
                "-y",
                str(thumbnail),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=30,
        )
        return destination, thumbnail, round(actual_duration)
    except subprocess.SubprocessError:
        raise JobError("processing", "پردازش ویدیو کامل نشد؛ دوباره تلاش کن.") from None


def recover():
    # Called only after acquiring the single-worker OS lock; no live worker can own these jobs.
    Video.objects.filter(status=Video.Status.DOWNLOADING).update(
        status=Video.Status.QUEUED,
        progress=0,
        next_attempt_at=timezone.now(),
        error="دانلود قبلی قطع شد؛ دوباره از ابتدا دریافت می‌شود.",
    )
    work = settings.DATA_DIR / "work"
    work.mkdir(exist_ok=True)
    for path in work.glob("job-*"):
        if path.is_dir():
            shutil.rmtree(path)
    referenced = (
        set(Video.objects.exclude(file_name="").values_list("file_name", flat=True))
        | set(Video.objects.exclude(thumbnail_name="").values_list("thumbnail_name", flat=True))
        | set(Video.objects.exclude(audio_name="").values_list("audio_name", flat=True))
    )
    for path in settings.MEDIA_ROOT.glob("*.*"):
        if path.name not in referenced:
            path.unlink()


def process_one():
    with archive_lock():
        with transaction.atomic():
            video = quota.next_job(Video.objects.filter(status=Video.Status.QUEUED, next_attempt_at__lte=timezone.now()))
            if not video:
                return False
            quota.ensure_account(video.owner)
            Account.objects.filter(user=video.owner).update(last_served_at=timezone.now())
            video.status = Video.Status.DOWNLOADING
            video.attempts += 1
            video.error = ""
            video.save(update_fields=["status", "attempts", "error", "updated_at"])
        published = []
        try:
            max_bytes = quota.budget(video)
            ensure_capacity()
            with tempfile.TemporaryDirectory(
                prefix="job-", dir=settings.DATA_DIR / "work"
            ) as directory:
                source, info = run_child(video, Path(directory))
                Video.objects.filter(pk=video.pk).update(progress=90)
                file, thumbnail, duration = transcode(source, Path(directory), max_bytes)
                audio = extract_audio(file, Path(directory), max_bytes - file.stat().st_size - thumbnail.stat().st_size)
                size = (
                    file.stat().st_size
                    + thumbnail.stat().st_size
                    + (audio.stat().st_size if audio else 0)
                )
                ensure_capacity(size)
                with transaction.atomic():
                    quota.ensure_publish(video, size)
                file_name, thumb_name = f"{video.pk}.mp4", f"{video.pk}.jpg"
                audio_name = f"{video.pk}.m4a" if audio else ""
                outputs = [(file, file_name), (thumbnail, thumb_name)]
                if audio:
                    outputs.append((audio, audio_name))
                for origin, name in outputs:
                    destination = settings.MEDIA_ROOT / name
                    os.replace(origin, destination)
                    published.append(destination)
                with transaction.atomic():
                    current = Video.objects.get(pk=video.pk)
                    current.status = Video.Status.READY
                    current.progress = 100
                    current.reserved_bytes = 0
                    current.title = current.title or info.get("title", "")[:300]
                    current.file_name, current.thumbnail_name = file_name, thumb_name
                    current.audio_name, current.audio_checked = audio_name, True
                    current.duration, current.size_bytes = duration, size
                    current.error, current.error_code = "", ""
                    current.save(
                        update_fields=[
                            "reserved_bytes",
                            "status",
                            "progress",
                            "title",
                            "file_name",
                            "thumbnail_name",
                            "audio_name",
                            "audio_checked",
                            "duration",
                            "size_bytes",
                            "error",
                            "error_code",
                            "updated_at",
                        ]
                    )
            logger.info("Video %s ready", video.pk)
        except Exception as exc:
            for path in published:
                path.unlink(missing_ok=True)
            if not isinstance(exc, JobError):
                logger.exception("Video %s worker failure", video.pk)
                exc = JobError("internal", "دانلود به دلیل خطای داخلی متوقف شد؛ دوباره تلاش کن.")
            automatic = exc.transient and video.attempts < 3
            message = str(exc)
            if exc.transient and not automatic:
                message = "پس از سه تلاش، ارتباط با منبع برقرار نشد؛ بعداً دوباره تلاش کن."
            Video.objects.filter(pk=video.pk).update(
                status=Video.Status.QUEUED if automatic else Video.Status.FAILED,
                progress=0,
                reserved_bytes=video.reserved_bytes if automatic else 0,
                error=message,
                error_code=exc.code,
                next_attempt_at=timezone.now() + timedelta(seconds=30 * 2 ** (video.attempts - 1)),
            )
            logger.warning("Video %s: %s (attempt %s)", video.pk, exc.code, video.attempts)
        return True


def work(once=False):
    if settings.MEDIA_BACKEND == "r2":
        from .cloud_worker import work as cloud_work

        return cloud_work(once=once)
    with (settings.DATA_DIR / ".worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A download worker is already running.") from None
        with archive_lock():
            recover()
        while True:
            processed = process_one()
            if once:
                return processed
            if not processed:
                time.sleep(2)
