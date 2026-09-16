"""Atomic per-account admission and conservative storage reservations."""

from django.conf import settings
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
    queue = Video.objects.filter(owner=user, status__in=["queued", "downloading"])
    if exclude is not None:
        queue = queue.exclude(pk=exclude)
    if queue.count() >= account.queue_limit:
        raise QuotaError("صف دریافتت پر است؛ منتظر پایان ویدیوهای قبلی بمان.")
    usage, _ = DailyUsage.objects.get_or_create(owner=user, day=timezone.now().date())
    if usage.downloads >= account.daily_download_limit:
        raise QuotaError("به سقف دریافت روزانه رسیده‌ای؛ فردا دوباره تلاش کن.")
    amount = settings.MAX_VIDEO_BYTES + settings.MAX_VIDEO_SECONDS * 20_000 + 1_000_000
    if used(user) + reserved(user, exclude) + amount > account.storage_limit:
        raise QuotaError("فضای آزاد حسابت برای دریافت یک ویدیوی جدید کافی نیست.")
    if used() + reserved(exclude=exclude) + amount > settings.ARCHIVE_MAX_BYTES:
        raise QuotaError("ظرفیت دریافت سرور تکمیل شده؛ بعداً دوباره تلاش کن.")
    usage.downloads += 1
    usage.save(update_fields=["downloads"])
    return amount


def ensure_publish(video, size):
    from .worker import JobError

    account = ensure_account(video.owner)
    if used(video.owner) + reserved(video.owner, video.pk) + size > account.storage_limit:
        raise JobError("quota", "فضای حساب برای ذخیرهٔ خروجی کافی نیست.")
    if used() + reserved(exclude=video.pk) + size > settings.ARCHIVE_MAX_BYTES:
        raise JobError("quota", "ظرفیت کلی آرشیو برای این خروجی کافی نیست.")


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
