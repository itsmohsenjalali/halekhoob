"""Staff-only operations. Clerk proves identity; Django owns authorization."""

import functools
import json
import math
import time
from pathlib import Path

from django.conf import settings
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone

from . import quota
from .api import InputError, body, endpoint, error
from .models import Account, QuotaChange, Video, WorkerLease
from .storage import archive_lock


def administrator(*methods):
    def decorate(view):
        @endpoint(*methods)
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_active or not request.user.is_staff:
                return error("دسترسی مدیریت نداری.", "forbidden", 403)
            response = view(request, *args, **kwargs)
            response["Cache-Control"] = "private, no-store"
            return response

        return wrapped

    return decorate


def user_data(account):
    user = account.user
    return {
        "id": user.pk,
        "name": user.first_name or user.username,
        "email": user.email,
        "is_admin": user.is_staff,
        "is_active": user.is_active,
        "joined_at": user.date_joined.isoformat(),
        "storage_used": quota.used(user),
        "storage_limit": account.storage_limit,
        "videos": dict(
            Video.objects.filter(owner=user).values_list("status").annotate(n=Count("id"))
        ),
    }


def host_metrics():
    # The host publishes a small, explicitly filtered snapshot. Never expose
    # Docker's socket, process environment, private paths, logs or credentials.
    try:
        path = Path(settings.HOST_METRICS_FILE)
        if not settings.HOST_METRICS_FILE or path.stat().st_size > 32_000:
            return None
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            return None
        keys = (
            "timestamp",
            "cpu_percent",
            "cpu_count",
            "memory_total",
            "memory_used",
            "disk_total",
            "disk_used",
            "disk_free",
            "uptime_seconds",
            "services",
        )
        if any(
            type(data.get(key)) not in (int, float) or not math.isfinite(data[key]) or data[key] < 0
            for key in keys[:-1]
        ):
            return None
        services = data.get("services")
        if not isinstance(services, dict):
            return None
        result = {key: data[key] for key in keys[:-1]}
        result["services"] = {
            name: {
                "running": item.get("running") is True,
                "health": item.get("health")
                if item.get("health")
                in {"healthy", "unhealthy", "starting", "unknown", "unavailable"}
                else "unknown",
            }
            for name, item in services.items()
            if name in {"web", "worker", "frontend", "db", "gateway"} and isinstance(item, dict)
        }
        result["stale"] = time.time() - float(data["timestamp"]) > 90
        return result
    except (OSError, ValueError, TypeError, KeyError):
        return None


@administrator("GET")
def overview(request):
    started = time.monotonic()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    db_ms = round((time.monotonic() - started) * 1000, 1)
    lease = WorkerLease.objects.filter(name="worker").first()
    changes = QuotaChange.objects.select_related("actor", "user").order_by("-pk")[:20]
    return JsonResponse(
        {
            "host": host_metrics(),
            "database_ms": db_ms,
            "worker_online": bool(lease and lease.token and lease.expires_at > timezone.now()),
            "worker_expires_at": lease.expires_at.isoformat() if lease else None,
            "users": Account.objects.count(),
            "storage_used": quota.used(),
            "storage_allocated": Account.objects.aggregate(n=Sum("storage_limit"))["n"] or 0,
            "default_storage_limit": settings.DEFAULT_USER_STORAGE_BYTES,
            "videos": dict(
                Video.objects.values_list("status").annotate(n=Count("id")).order_by("status")
            ),
            "quota_changes": [
                {
                    "id": item.pk,
                    "actor": item.actor.email,
                    "user": item.user.email,
                    "old_limit": item.old_limit,
                    "new_limit": item.new_limit,
                    "created_at": item.created_at.isoformat(),
                }
                for item in changes
            ],
            "sampled_at": timezone.now().isoformat(),
        }
    )


@administrator("GET")
def users(request):
    search = request.GET.get("q", "").strip()[:200]
    query = (
        Account.objects.select_related("user")
        .filter(Q(user__email__icontains=search) | Q(user__first_name__icontains=search))
        .order_by("-user__date_joined", "pk")
    )
    page = Paginator(query, 20).get_page(request.GET.get("page", "1"))
    return JsonResponse(
        {
            "items": [user_data(a) for a in page],
            "count": page.paginator.count,
            "page": page.number,
            "pages": page.paginator.num_pages,
        }
    )


@administrator("PATCH")
def user_quota(request, pk):
    data = body(request)
    # No role, identity or account-status writes through this endpoint.
    limit = data.get("storage_limit")
    if (
        set(data) != {"storage_limit"}
        or type(limit) is not int
        or not 0 <= limit <= 1_000_000_000_000_000
    ):
        raise InputError("سهمیه باید یک عدد صحیح نامنفی بر حسب بایت باشد.")
    with archive_lock(exclusive=True), transaction.atomic():
        account = get_object_or_404(
            Account.objects.select_for_update().select_related("user"), user_id=pk
        )
        old = account.storage_limit
        account.storage_limit = limit
        account.save(update_fields=["storage_limit"])
        if old != limit:
            QuotaChange.objects.create(
                actor=request.user, user=account.user, old_limit=old, new_limit=limit
            )
    return JsonResponse(user_data(account))


urlpatterns = [
    path("overview/", overview),
    path("users/", users),
    path("users/<int:pk>/quota/", user_quota),
]
