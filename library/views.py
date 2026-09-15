import hashlib
import re
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AddForm, MoodForm, VideoForm
from .models import CloudObject, LoginThrottle, Mood, Video
from .storage import archive_lock, private_path


def health(request):
    """Minimal readiness signal; never returns database or credential details."""
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return HttpResponse("unavailable", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")


class PrivateLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        # Never trust client-supplied X-Forwarded-For. Nginx sets X-Real-IP on the private socket.
        address = request.META.get("HTTP_X_REAL_IP", request.META.get("REMOTE_ADDR", "unknown"))
        key = hashlib.sha256(address.encode()).hexdigest()
        with transaction.atomic():
            now = timezone.now()
            LoginThrottle.objects.filter(started_at__lt=now - timedelta(days=1)).delete()
            LoginThrottle.objects.get_or_create(key=key)
            throttle = LoginThrottle.objects.select_for_update().get(key=key)
            if now - throttle.started_at >= timedelta(minutes=15):
                throttle.failures = 0
                throttle.started_at = now
            if throttle.failures >= 5:
                form = self.get_form()
                form.add_error(None, "تلاش‌های ورود زیاد شده؛ ۱۵ دقیقه دیگر دوباره امتحان کن.")
                return self.render_to_response(self.get_context_data(form=form), status=429)
            # Count before checking credentials so concurrent attempts cannot bypass the limit.
            throttle.failures += 1
            throttle.save()
        response = super().post(request, *args, **kwargs)
        if response.status_code == 302:
            LoginThrottle.objects.filter(key=key).delete()
        return response


def owned(request, pk, lock=False):
    query = Video.objects.select_for_update() if lock else Video.objects
    return get_object_or_404(query.prefetch_related("moods"), pk=pk, owner=request.user)


def filtered_videos(request, home_page):
    videos = Video.objects.filter(owner=request.user).prefetch_related("moods")
    selected = None
    if request.GET.get("mood", "").isdigit():
        selected = get_object_or_404(Mood, pk=request.GET["mood"])
        videos = videos.filter(moods=selected)
    query = request.GET.get("q", "").strip()[:200]
    if query:
        videos = videos.filter(Q(title__icontains=query) | Q(note__icontains=query))
    mode = request.GET.get("filter", "")
    if mode == "favorites":
        videos = videos.filter(favorite=True)
    elif mode == "pending":
        videos = videos.exclude(status=Video.Status.READY)
    if home_page and mode != "pending":
        videos = videos.filter(status=Video.Status.READY)
    return videos.order_by("-favorite", "-created_at", "-pk").distinct(), selected, query, mode


def listing(request, home_page):
    videos, selected, query, mode = filtered_videos(request, home_page)
    page = Paginator(videos, 8).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    mood_params = params.copy()
    mood_params.pop("mood", None)
    return render(
        request,
        "library/timeline.html"
        if request.headers.get("X-Timeline") == "fragment"
        else "library/list.html",
        {
            "home_page": home_page,
            "page_obj": page,
            "selected_mood": selected,
            "query": query,
            "filter_mode": mode,
            "page_query": params.urlencode(),
            "mood_query": mood_params.urlencode(),
            "feed_base": request.path,
            "feed_return": request.get_full_path(),
            "playlist_url": reverse("audio_playlist") + "?" + params.urlencode(),
        },
    )


@login_required
def audio_playlist(request):
    videos, selected, query, mode = filtered_videos(request, True)
    videos = videos.filter(status=Video.Status.READY)
    tracks = [
        {
            "id": video.pk,
            "title": video.display_title,
            "duration": video.duration,
            "url": reverse("media", args=[video.pk, "audio"]),
            "artwork": reverse("media", args=[video.pk, "thumbnail"])
            if video.thumbnail_name
            else "",
        }
        for video in videos
        if video.audio_name
    ]
    label = selected.name if selected else ("دوست‌داشتنی‌ها" if mode == "favorites" else "همهٔ حس‌ها")
    if query:
        label += f" · {query}"
    return JsonResponse(
        {
            "label": label,
            "tracks": tracks,
            "pending": sum(not video.audio_checked for video in videos),
            "silent": sum(video.audio_checked and not video.audio_name for video in videos),
        }
    )


@login_required
def home(request):
    return listing(request, True)


@login_required
def archive(request):
    return listing(request, False)


@login_required
def add(request):
    form = AddForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        platform, key, url = form.source
        with archive_lock():
            try:
                with transaction.atomic():
                    video, created = Video.objects.get_or_create(
                        source_key=key,
                        defaults={
                            "owner": request.user,
                            "source_url": url,
                            "platform": platform,
                            "title": form.cleaned_data["title"],
                            "note": form.cleaned_data["note"],
                        },
                    )
                    if video.owner_id != request.user.pk:
                        raise Http404
                    if created:
                        form.save_moods(video)
            except IntegrityError:
                video = get_object_or_404(Video, source_key=key, owner=request.user)
                created = False
        messages.success(
            request,
            "ویدیو به صف اضافه شد؛ می‌توانی این صفحه را ببندی."
            if created
            else "این ویدیو قبلاً در آرشیوت ثبت شده است.",
        )
        return redirect("detail", pk=video.pk)
    return render(request, "library/form.html", {"form": form, "adding": True})


@login_required
def detail(request, pk):
    return render(request, "library/detail.html", {"video": owned(request, pk)})


@login_required
def edit(request, pk):
    video = owned(request, pk)
    form = VideoForm(request.POST or None, instance=video)
    if request.method == "POST" and form.is_valid():
        with archive_lock(), transaction.atomic():
            # Update only user-controlled fields; never overwrite worker status from a stale form.
            Video.objects.filter(pk=pk, owner=request.user).update(
                title=form.cleaned_data["title"], note=form.cleaned_data["note"]
            )
            form.save_moods(video)
        messages.success(request, "تغییرات ذخیره شد.")
        return redirect("detail", pk=pk)
    return render(request, "library/form.html", {"form": form, "video": video})


@login_required
@require_POST
def favorite(request, pk):
    with archive_lock(), transaction.atomic():
        video = owned(request, pk, lock=True)
        video.favorite = not video.favorite
        video.save(update_fields=["favorite"])
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"favorite": video.favorite})
    if request.POST.get("next", "").split("?", 1)[0] in {reverse("home"), reverse("archive")}:
        return redirect(request.POST["next"] + f"#post-{pk}")
    return redirect("detail", pk=pk)


@login_required
@require_POST
def retry(request, pk):
    with archive_lock(), transaction.atomic():
        video = owned(request, pk, lock=True)
        if video.status == Video.Status.FAILED:
            Video.objects.filter(pk=pk).update(
                status=Video.Status.QUEUED,
                attempts=0,
                progress=0,
                error="",
                error_code="",
                next_attempt_at=timezone.now(),
            )
            messages.success(request, "ویدیو دوباره به صف اضافه شد.")
    return redirect("detail", pk=pk)


@login_required
def delete(request, pk):
    video = owned(request, pk)
    if request.method == "POST":
        with archive_lock(), transaction.atomic():
            video = owned(request, pk, lock=True)
            if video.status == Video.Status.DOWNLOADING:
                messages.error(
                    request, "دانلود هنوز در حال انجام است؛ پس از پایان می‌توانی ویدیو را حذف کنی."
                )
                return redirect("detail", pk=pk)
            if video.storage_backend == "r2":
                from .r2 import defer_delete

                defer_delete(CloudObject.objects.filter(video=video))
                video.delete()
                messages.success(request, "ویدیو حذف شد؛ فایل‌ها پس از دورهٔ نگهداری پاک می‌شوند.")
                return redirect("archive")
            files = []
            for name in [video.file_name, video.thumbnail_name, video.audio_name]:
                if name:
                    try:
                        files.append(private_path(name))
                    except Http404:
                        pass
            video.delete()
            # Commit the database first. A failed commit must not leave a ready record
            # pointing to deleted media; an interrupted cleanup is handled by recover().
            transaction.on_commit(lambda: [path.unlink(missing_ok=True) for path in files])
        messages.success(request, "ویدیو از آرشیو حذف شد.")
        return redirect("archive")
    return render(request, "library/delete.html", {"video": video})


@login_required
def moods(request):
    instance = (
        get_object_or_404(Mood, pk=request.GET["edit"])
        if request.GET.get("edit", "").isdigit()
        else None
    )
    form = MoodForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        with archive_lock():
            form.save()
        messages.success(request, "حس ذخیره شد.")
        return redirect("moods")
    return render(request, "library/moods.html", {"form": form, "editing_mood": instance})


@login_required
def status(request, pk):
    video = owned(request, pk)
    return JsonResponse(
        {
            "status": video.status,
            "label": video.get_status_display(),
            "progress": video.progress,
            "error": video.error,
            "error_code": video.error_code,
        }
    )


def file_chunks(path, start, length):
    with path.open("rb") as source:
        source.seek(start)
        while length > 0:
            chunk = source.read(min(64 * 1024, length))
            if not chunk:
                break
            length -= len(chunk)
            yield chunk


@login_required
def media(request, pk, kind):
    video = owned(request, pk)
    if video.status != Video.Status.READY or kind not in {"video", "thumbnail", "audio"}:
        raise Http404
    names = {"video": video.file_name, "thumbnail": video.thumbnail_name, "audio": video.audio_name}
    if video.storage_backend == "r2":
        from .r2 import StorageError, signed_url

        if (
            not names[kind]
            or not CloudObject.objects.filter(video=video, key=names[kind], state="live").exists()
        ):
            raise Http404
        try:
            response = redirect(signed_url(names[kind], request.method))
        except StorageError:
            raise Http404 from None
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response
    path = private_path(names[kind])
    content_type = {"video": "video/mp4", "thumbnail": "image/jpeg", "audio": "audio/mp4"}[kind]
    size = path.stat().st_size
    range_header = request.headers.get("Range", "")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not match or len(range_header) > 100 or not any(match.groups()) or size == 0:
            return HttpResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
        left, right = match.groups()
        start = int(left) if left else max(0, size - int(right))
        end = min(size - 1, int(right)) if left and right else size - 1
        if start >= size or end < start:
            return HttpResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
        length = end - start + 1
        response = StreamingHttpResponse(
            [] if request.method == "HEAD" else file_chunks(path, start, length),
            status=206,
            content_type=content_type,
        )
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Content-Length"] = str(length)
    elif request.method == "HEAD":
        response = HttpResponse(content_type=content_type, headers={"Content-Length": str(size)})
    else:
        response = FileResponse(path.open("rb"), content_type=content_type)
    response["Accept-Ranges"] = "bytes"
    response["Content-Disposition"] = "inline"
    return response
