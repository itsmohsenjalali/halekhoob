import fcntl
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from library.audio import extract_audio
from library.models import Video
from library.storage import archive_lock, private_path
from library.worker import ensure_capacity


class Command(BaseCommand):
    help = (
        "Prepare audio for existing videos. Stop the download worker before running this command."
    )

    def handle(self, *args, **options):
        if settings.MEDIA_BACKEND == "r2":
            raise CommandError(
                "Use export_portable/import_portable for cloud archives; prepare audio before migrating local media."
            )
        with (settings.DATA_DIR / ".worker.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise CommandError("Stop the download worker first.") from None
            # Prevent deletion/export while files are being prepared. Video playback stays available.
            with archive_lock(exclusive=True):
                for video in Video.objects.filter(status="ready", audio_checked=False):
                    destination = None
                    try:
                        source = private_path(video.file_name)
                        ensure_capacity(source.stat().st_size)
                        with tempfile.TemporaryDirectory(dir=settings.DATA_DIR) as directory:
                            audio = extract_audio(source, Path(directory))
                            if audio:
                                size = audio.stat().st_size
                                ensure_capacity(size)
                                destination = settings.MEDIA_ROOT / f"{video.pk}.m4a"
                                os.replace(audio, destination)
                                video.audio_name = destination.name
                                video.size_bytes += size
                            video.audio_checked = True
                            with transaction.atomic():
                                video.save(
                                    update_fields=["audio_name", "audio_checked", "size_bytes"]
                                )
                        self.stdout.write(
                            f"Video {video.pk}: {'audio ready' if video.audio_name else 'no audio track'}"
                        )
                    except Exception as exc:
                        if destination:
                            destination.unlink(missing_ok=True)
                        raise CommandError(
                            f"Video {video.pk}: audio preparation failed: {exc}"
                        ) from exc
