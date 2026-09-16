"""Versioned JSON API for the independent Next.js application."""

import functools
import json
from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils import timezone

from . import quota, r2
from .accounts import ensure_account
from .clerk_auth import clerk_required
from .models import CloudObject, DailyUsage, Mood, Video
from .storage import archive_lock, private_path
from .validation import canonical_source


class InputError(Exception):
    pass


def error(message, code="invalid", status=400):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def endpoint(*methods):
    def decorate(view):
        @clerk_required
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                return error("این عملیات پشتیبانی نمی‌شود.", "method", 405)
            try:
                return view(request, *args, **kwargs)
            except Http404:
                return error("مورد درخواستی پیدا نشد.", "not_found", 404)
            except quota.QuotaError as exc:
                return error(str(exc), "quota", 429)
            except (InputError, ValidationError) as exc:
                message = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
                return error(message)
            except IntegrityError:
                return error("این مورد قبلاً ثبت شده است.", "duplicate", 409)

        return wrapped

    return decorate


def body(request):
    if len(request.body) > 16_000:
        raise InputError("اطلاعات واردشده بیش از اندازه است.")
    try:
        value = json.loads(request.body or b"{}")
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeDecodeError):
        raise InputError("درخواست معتبر نیست.") from None


def text(data, key, limit, default=""):
    value = data.get(key, default)
    if not isinstance(value, str) or len(value) > limit:
        raise InputError("مقدار " + key + " معتبر نیست.")
    return value.strip()


def category_data(item):
    return {"id": item.pk, "name": item.name, "symbol": item.symbol}


def asset_url(video, kind, attachment=False):
    name = {"video": video.file_name, "audio": video.audio_name, "thumbnail": video.thumbnail_name}[
        kind
    ]
    if video.status != "ready" or not name:
        return None
    extension = {"video": "mp4", "audio": "m4a", "thumbnail": "jpg"}[kind]
    filename = video.display_title[:120].replace("/", "_").replace("\\", "_") + "." + extension
    if video.storage_backend == "r2":
        if not CloudObject.objects.filter(
            video=video, owner_id=video.owner_id, key=name, state="live"
        ).exists():
            return None
        return r2.signed_url(name, attachment_name=filename if attachment else None)
    ticket = signing.dumps(
        {"video": video.pk, "owner": video.owner_id, "kind": kind, "attachment": attachment},
        salt="private-media",
    )
    return "/api/v1/media/?ticket=" + quote(ticket)


def video_data(video):
    return {
        "id": video.pk,
        "title": video.display_title,
        "note": video.note,
        "source_url": video.source_url,
        "platform": video.platform,
        "status": video.status,
        "progress": video.progress,
        "error": video.error,
        "error_code": video.error_code,
        "favorite": video.favorite,
        "duration": video.duration,
        "size_bytes": video.size_bytes,
        "categories": [category_data(m) for m in video.moods.all()],
        "video_url": asset_url(video, "video"),
        "audio_url": asset_url(video, "audio"),
        "thumbnail_url": asset_url(video, "thumbnail"),
        "created_at": video.created_at.isoformat(),
    }


def selection(request):
    query = Video.objects.filter(owner=request.user).prefetch_related("moods")
    category = request.GET.get("category", "")
    if category:
        if not category.isdigit():
            raise InputError("دسته معتبر نیست.")
        get_object_or_404(Mood, pk=category, owner=request.user)
        query = query.filter(moods__pk=category)
    search = request.GET.get("q", "").strip()[:200]
    if search:
        query = query.filter(Q(title__icontains=search) | Q(note__icontains=search))
    mode = request.GET.get("filter", "")
    if mode == "favorites":
        query = query.filter(favorite=True)
    if mode == "pending":
        query = query.exclude(status="ready")
    elif request.GET.get("state", "ready") == "ready":
        query = query.filter(status="ready")
    return query.order_by("-favorite", "-created_at", "-pk")


def mood_ids(data, user):
    ids = data.get("category_ids", [])
    if not isinstance(ids, list) or len(ids) > 50 or any(type(i) is not int for i in ids):
        raise InputError("دسته‌ها معتبر نیستند.")
    ids = set(ids)
    if not ids or Mood.objects.filter(owner=user, pk__in=ids).count() != len(ids):
        raise InputError("حداقل یک دسته از دسته‌های خودت انتخاب کن.")
    return ids


@endpoint("GET")
def me(request):
    account = ensure_account(request.user)
    today = DailyUsage.objects.filter(owner=request.user, day=timezone.now().date()).first()
    return JsonResponse(
        {
            "name": request.user.first_name or request.user.username,
            "email": request.user.email,
            "storage_used": quota.used(request.user),
            "storage_reserved": quota.reserved(request.user),
            "storage_limit": account.storage_limit,
            "daily_used": today.downloads if today else 0,
            "daily_limit": account.daily_download_limit,
            "queue_limit": account.queue_limit,
        }
    )


@endpoint("GET", "POST")
def categories(request):
    if request.method == "GET":
        return JsonResponse(
            {"items": [category_data(m) for m in Mood.objects.filter(owner=request.user)]}
        )
    data = body(request)
    name = text(data, "name", 40)
    if not name:
        raise InputError("نام دسته را بنویس.")
    with transaction.atomic():
        ensure_account(request.user)
        from .models import Account

        Account.objects.select_for_update().get(user=request.user)
        if Mood.objects.filter(owner=request.user).count() >= 100:
            raise InputError("حداکثر ۱۰۰ دسته می‌توان ساخت.")
        item = Mood.objects.create(owner=request.user, name=name)
    return JsonResponse(category_data(item), status=201)


@endpoint("PATCH", "DELETE")
def category(request, pk):
    item = get_object_or_404(Mood, pk=pk, owner=request.user)
    if request.method == "DELETE":
        item.delete()
        return JsonResponse({"deleted": True})
    name = text(body(request), "name", 40)
    if not name:
        raise InputError("نام دسته را بنویس.")
    item.name = name
    item.save(update_fields=["name"])
    return JsonResponse(category_data(item))


@endpoint("GET", "POST")
def videos(request):
    if request.method == "GET":
        page = Paginator(selection(request), 8).get_page(request.GET.get("page", "1"))
        return JsonResponse(
            {
                "items": [video_data(v) for v in page],
                "next_page": page.next_page_number() if page.has_next() else None,
            }
        )
    data = body(request)
    platform, key, source = canonical_source(text(data, "source_url", 1000))
    with archive_lock(exclusive=True), transaction.atomic():
        existing = (
            Video.objects.filter(owner=request.user, source_key=key)
            .prefetch_related("moods")
            .first()
        )
        if existing:
            return JsonResponse({"video": video_data(existing), "duplicate": True})
        ids = mood_ids(data, request.user)
        amount = quota.admit(request.user)
        video = Video.objects.create(
            owner=request.user,
            source_key=key,
            source_url=source,
            platform=platform,
            title=text(data, "title", 300),
            note=text(data, "note", 3000),
            reserved_bytes=amount,
        )
        video.moods.set(ids)
    return JsonResponse({"video": video_data(video), "duplicate": False}, status=201)


@endpoint("GET", "PATCH", "DELETE")
def video_detail(request, pk):
    with archive_lock(), transaction.atomic():
        video = get_object_or_404(
            Video.objects.select_for_update().prefetch_related("moods"), pk=pk, owner=request.user
        )
        if request.method == "DELETE":
            if video.status == "downloading":
                return error("تا پایان دریافت این ویدیو صبر کن.", "busy", 409)
            if video.storage_backend == "r2":
                r2.defer_delete(CloudObject.objects.filter(video=video, owner=request.user))
            else:
                paths = []
                for name in (video.file_name, video.audio_name, video.thumbnail_name):
                    try:
                        paths.append(private_path(name))
                    except Http404:
                        pass
                transaction.on_commit(lambda: [p.unlink(missing_ok=True) for p in paths])
            video.delete()
            return JsonResponse({"deleted": True})
        if request.method == "PATCH":
            data = body(request)
            updates = []
            for field, limit in [("title", 300), ("note", 3000)]:
                if field in data:
                    setattr(video, field, text(data, field, limit))
                    updates.append(field)
            if "favorite" in data:
                if type(data["favorite"]) is not bool:
                    raise InputError("مقدار علاقه‌مندی معتبر نیست.")
                video.favorite = data["favorite"]
                updates.append("favorite")
            if "category_ids" in data:
                video.moods.set(mood_ids(data, request.user))
            if updates:
                video.save(update_fields=updates)
    return JsonResponse(video_data(video))


@endpoint("POST")
def retry(request, pk):
    with archive_lock(exclusive=True), transaction.atomic():
        video = get_object_or_404(Video.objects.select_for_update(), pk=pk, owner=request.user)
        if video.status != "failed":
            return error("فقط دریافت ناموفق قابل تکرار است.", "state", 409)
        video.reserved_bytes = quota.admit(request.user, exclude=video.pk)
        video.status, video.attempts, video.progress = "queued", 0, 0
        video.error, video.error_code = "", ""
        video.next_attempt_at = timezone.now()
        video.save(
            update_fields=[
                "reserved_bytes",
                "status",
                "attempts",
                "progress",
                "error",
                "error_code",
                "next_attempt_at",
            ]
        )
    return JsonResponse(video_data(video))


@endpoint("GET")
def download(request, pk):
    video = get_object_or_404(Video, pk=pk, owner=request.user, status="ready")
    kind = request.GET.get("kind", "video")
    if kind not in {"video", "audio"}:
        raise Http404
    url = asset_url(video, kind, attachment=True)
    if not url:
        raise Http404
    return JsonResponse({"url": url, "expires_in": settings.DOWNLOAD_URL_TTL})


@endpoint("GET")
def playlist(request):
    videos = selection(request).filter(status="ready").exclude(audio_name="")
    return JsonResponse({"tracks": [video_data(v) for v in videos]})


def local_media(request):
    if request.method not in {"GET", "HEAD"}:
        return error("عملیات نامعتبر است.", "method", 405)
    try:
        data = signing.loads(
            request.GET.get("ticket", ""), salt="private-media", max_age=settings.DOWNLOAD_URL_TTL
        )
        video = get_object_or_404(
            Video,
            pk=data["video"],
            owner_id=data["owner"],
            owner__is_active=True,
            storage_backend="local",
            status="ready",
        )
        request.user = video.owner
        from .views import media

        response = media.__wrapped__(request, video.pk, data["kind"])
        if data["attachment"]:
            ext = "m4a" if data["kind"] == "audio" else "mp4"
            response["Content-Disposition"] = "attachment; filename=video." + ext
        return response
    except (signing.BadSignature, ValueError, KeyError, Http404):
        return error("لینک معتبر نیست یا منقضی شده است.", "not_found", 404)


urlpatterns = [
    path("me/", me),
    path("categories/", categories),
    path("categories/<int:pk>/", category),
    path("videos/", videos),
    path("videos/<int:pk>/", video_detail),
    path("videos/<int:pk>/retry/", retry),
    path("videos/<int:pk>/download/", download),
    path("playlist/", playlist),
    path("media/", local_media),
]
