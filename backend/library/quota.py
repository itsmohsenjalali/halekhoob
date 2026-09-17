"""Per-account storage admission and final publication checks."""

from django.db.models import F, Sum
from django.utils import timezone

from .accounts import ensure_account
from .models import Account, CloudObject, DailyUsage, Video


class QuotaError(Exception):
    pass


def used(owner=None):
    cloud = CloudObject.objects.all()
    local = Video.objects.filter(storage_backend="local")
    if owner is not None:
        cloud = cloud.filter(owner=owner)
        local = local.filter(owner=owner)
    return (cloud.aggregate(n=Sum("size_bytes"))["n"] or 0) + (
        local.aggregate(n=Sum("size_bytes"))["n"] or 0
    )


def reserved(owner=None, exclude=None):
    query = Video.objects.filter(status__in=["queued", "downloading"])
    if owner is not None:
        query = query.filter(owner=owner)
    if exclude is not None:
        query = query.exclude(pk=exclude)
    return query.aggregate(n=Sum("reserved_bytes"))["n"] or 0


def admit(user, exclude=None):
    """Caller holds archive_lock(exclusive=True) and a database transaction."""
    ensure_account(user)
    account = Account.objects.select_for_update().get(user=user)
    if used(user) >= account.storage_limit:
        raise QuotaError("فضای حسابت پر شده؛ برای دریافت تازه فضا آزاد کن یا از مدیر سهمیهٔ بیشتری بخواه.")
    usage, _ = DailyUsage.objects.get_or_create(owner=user, day=timezone.now().date())
    usage.downloads += 1
    usage.save(update_fields=["downloads"])
    # Sizes are unknown until extraction. The single worker budgets at execution,
    # then rechecks the current account quota atomically before publication.
    return 0


def budget(video):
    from .worker import JobError

    available = ensure_account(video.owner).storage_limit - used(video.owner)
    if available <= 0:
        raise JobError("quota", "فضای حسابت برای دریافت تازه کافی نیست.")
    return available


def ensure_publish(video, size):
    from .worker import JobError

    account = Account.objects.select_for_update().get(user=video.owner)
    if used(video.owner) + size > account.storage_limit:
        raise JobError("quota", "فضای حساب برای ذخیرهٔ خروجی کافی نیست.")


def next_job(query):
    # One worker; choose the least recently served user's next eligible job.
    return (
        query.filter(owner__is_active=True)
        .order_by(
            F("owner__archive_account__last_served_at").asc(nulls_first=True),
            "next_attempt_at",
            "pk",
        )
        .first()
    )
