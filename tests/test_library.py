import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client

from library.models import Mood, Video
from library.validation import canonical_source


@pytest.mark.parametrize(
    "url",
    [
        "http://www.youtube.com/watch?v=BaW_jenozKc",
        "https://youtube.com.evil.test/watch?v=BaW_jenozKc",
        "https://127.0.0.1/video",
        "https://youtube.com@evil.test/watch?v=BaW_jenozKc",
        "https://youtube.com:8080/watch?v=BaW_jenozKc",
        "https://www.youtube.com/playlist?list=123",
        "https://www.youtube.com/watch?v=BaW_jenozKc&list=PL123",
        "https://www.instagram.com/someone/",
        "file:///etc/passwd",
        "--exec=touch /tmp/bad",
        "https://www.instagram.com/stories/test/123/",
    ],
)
def test_unsafe_or_unsupported_links_rejected(url):
    with pytest.raises(ValidationError):
        canonical_source(url)


def test_link_normalization():
    assert canonical_source("https://youtu.be/BaW_jenozKc?si=hello") == canonical_source(
        "https://www.youtube.com/shorts/BaW_jenozKc"
    )
    assert canonical_source("https://www.instagram.com/reel/ABC1234/?igsh=x") == canonical_source(
        "https://instagram.com/p/ABC1234/"
    )


@pytest.mark.django_db
def test_add_and_duplicate_preserves_original(client_logged):
    mood = Mood.objects.get(name="امید")
    data = {"source_url": "https://youtu.be/BaW_jenozKc", "moods": [mood.pk], "note": "یادداشت من"}
    response = client_logged.post("/add/", data)
    assert response.status_code == 302
    item = Video.objects.get()
    assert item.status == "queued" and item.moods.filter(pk=mood.pk).exists()
    data.update(source_url="https://youtube.com/shorts/BaW_jenozKc", note="overwrite")
    client_logged.post("/add/", data)
    item.refresh_from_db()
    assert Video.objects.count() == 1 and item.note == "یادداشت من"


@pytest.mark.django_db
def test_new_mood_and_required_selection(client_logged):
    data = {"source_url": "https://youtu.be/BaW_jenozKc"}
    assert client_logged.post("/add/", data).status_code == 200
    assert Video.objects.count() == 0
    data["new_mood"] = "تمرکز"
    assert client_logged.post("/add/", data).status_code == 302
    assert Video.objects.get().moods.get().name == "تمرکز"


@pytest.mark.django_db
def test_authentication_and_owner_isolation(client, client_logged, video, settings):
    paths = [
        "/",
        "/archive/",
        "/add/",
        "/moods/",
        f"/videos/{video.pk}/",
        f"/api/videos/{video.pk}/status/",
        f"/videos/{video.pk}/media/video/",
    ]
    anonymous = Client()
    for path in paths:
        response = anonymous.get(path)
        assert response.status_code == 302
        assert response["Cache-Control"] == "private, no-store"
    assert anonymous.get("/media/1.mp4").status_code == 404
    other = get_user_model().objects.create_user("other", password="other-long-password")
    client.force_login(other)
    assert client.get(f"/videos/{video.pk}/").status_code == 404
    assert client.get(f"/api/videos/{video.pk}/status/").status_code == 404


@pytest.mark.django_db
def test_search_mood_and_favorite_order(client_logged, video, user):
    video.status = "ready"
    video.save()
    favored = Video.objects.create(
        owner=user,
        source_key="instagram:ABC1234",
        source_url="https://instagram.com/p/ABC1234/",
        platform="instagram",
        title="آرام باش",
        favorite=True,
        status="ready",
    )
    response = client_logged.get("/")
    assert list(response.context["page_obj"])[0] == favored
    assert list(client_logged.get("/archive/?q=دوباره").context["page_obj"]) == [video]
    assert list(client_logged.get(f"/?mood={video.moods.first().pk}").context["page_obj"]) == [
        video
    ]
    assert list(client_logged.get("/archive/?filter=favorites").context["page_obj"]) == [favored]


@pytest.mark.django_db
def test_edit_preserves_job_fields_and_retry(client_logged, video):
    video.status, video.attempts = "failed", 3
    video.error = "خطا"
    video.save()
    client_logged.post(
        f"/videos/{video.pk}/edit/",
        {"title": "نام تازه", "note": "متن تازه", "moods": [video.moods.first().pk]},
    )
    video.refresh_from_db()
    assert video.title == "نام تازه" and video.status == "failed"
    client_logged.post(f"/videos/{video.pk}/retry/")
    video.refresh_from_db()
    assert video.status == "queued" and video.attempts == 0 and video.error == ""
    assert client_logged.get(f"/videos/{video.pk}/retry/").status_code == 405


@pytest.mark.django_db
def test_delete_refuses_active_download_and_removes_saved_files(
    client_logged, video, settings, django_capture_on_commit_callbacks
):
    video.status = "downloading"
    video.save()
    with django_capture_on_commit_callbacks(execute=True):
        client_logged.post(f"/videos/{video.pk}/delete/")
    assert Video.objects.filter(pk=video.pk).exists()
    video.status, video.file_name = "ready", "1.mp4"
    video.save()
    path = settings.MEDIA_ROOT / "1.mp4"
    path.write_bytes(b"test")
    with django_capture_on_commit_callbacks(execute=True):
        client_logged.post(f"/videos/{video.pk}/delete/")
    assert not path.exists() and not Video.objects.filter(pk=video.pk).exists()


@pytest.mark.django_db
def test_mutations_require_csrf(user, video):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.post(f"/videos/{video.pk}/favorite/").status_code == 403


@pytest.mark.django_db
def test_login_throttled(client, user):
    for _ in range(5):
        assert client.post("/login/", {"username": "owner", "password": "wrong"}).status_code == 200
    assert client.post("/login/", {"username": "owner", "password": "wrong"}).status_code == 429


@pytest.mark.django_db
def test_no_open_registration_or_admin(client):
    assert client.get("/register/").status_code == 404
    assert client.get("/admin/").status_code == 404


@pytest.mark.django_db
def test_range_streaming_and_private_file_paths(client_logged, video, settings):
    video.status, video.file_name = "ready", "1.mp4"
    video.save()
    (settings.MEDIA_ROOT / "1.mp4").write_bytes(b"0123456789")
    url = f"/videos/{video.pk}/media/video/"
    response = client_logged.get(url, HTTP_RANGE="bytes=2-5")
    assert response.status_code == 206 and response["Content-Range"] == "bytes 2-5/10"
    assert b"".join(response.streaming_content) == b"2345"
    response = client_logged.get(url, HTTP_RANGE="bytes=-3")
    assert b"".join(response.streaming_content) == b"789"
    assert client_logged.head(url)["Content-Length"] == "10"
    for value in ["bytes=90-", "bytes=5-3", "bytes=0-1,3-4", "bytes=-0", "bytes=-", "nope"]:
        assert client_logged.get(url, HTTP_RANGE=value).status_code == 416
    assert b"".join(client_logged.get(url).streaming_content) == b"0123456789"
    video.file_name = "../outside.mp4"
    video.save()
    (settings.DATA_DIR / "outside.mp4").write_bytes(b"secret")
    assert client_logged.get(url).status_code == 404
