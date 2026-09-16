from django.conf import settings
from django.db.models import Sum

from .models import Mood, Video


def archive_context(request):
    if not request.user.is_authenticated:
        return {}
    videos = Video.objects.filter(owner=request.user)
    used = videos.aggregate(n=Sum("size_bytes"))["n"] or 0
    if settings.MEDIA_BACKEND == "r2":
        from .quota import used as stored_bytes

        used = stored_bytes(request.user)
    return {
        "all_moods": Mood.objects.filter(owner=request.user),
        "storage_used": used,
        "storage_limit": settings.ARCHIVE_MAX_BYTES,
        "storage_percent": min(100, round(100 * used / settings.ARCHIVE_MAX_BYTES)),
        "ready_count": videos.filter(status=Video.Status.READY).count(),
        "queue_count": videos.filter(
            status__in=[Video.Status.QUEUED, Video.Status.DOWNLOADING]
        ).count(),
    }
