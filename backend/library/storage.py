import fcntl
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.http import Http404


def private_path(name):
    root = Path(settings.MEDIA_ROOT).resolve()
    path = (root / name).resolve()
    if not name or not path.is_relative_to(root) or not path.is_file():
        raise Http404
    return path


@contextmanager
def archive_lock(exclusive=False):
    """Shared for normal writes; exclusive for a consistent portable export."""
    if settings.MEDIA_BACKEND == "r2":
        with transaction.atomic():
            if connection.vendor == "postgresql":
                function = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT {function}(%s)", [68421017])
            yield
        return
    with (settings.DATA_DIR / ".archive.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
