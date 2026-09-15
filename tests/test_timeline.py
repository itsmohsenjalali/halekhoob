import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from library.models import Mood, Video


@pytest.mark.django_db
def test_timeline_filters_and_pagination_preserve_scope(client_logged, user):
    hope = Mood.objects.get(name="امید")
    joy = Mood.objects.get(name="شادی")
    for index in range(10):
        video = Video.objects.create(
            owner=user,
            source_key=f"youtube:test{index}",
            platform="youtube",
            title=f"قدم {index}",
            status="ready",
            favorite=True,
        )
        video.moods.add(hope)
    unrelated = Video.objects.create(
        owner=user,
        source_key="instagram:unrelated",
        platform="instagram",
        title="قدم نامرتبط",
        status="ready",
        favorite=True,
    )
    unrelated.moods.add(joy)
    waiting = Video.objects.create(
        owner=user, source_key="instagram:pending", title="قدم در صف", favorite=True
    )
    waiting.moods.add(hope)
    url = f"/?mood={hope.pk}&q=قدم&filter=favorites"
    first = client_logged.get(url, HTTP_X_TIMELINE="fragment")
    second = client_logged.get(url + "&page=2", HTTP_X_TIMELINE="fragment")
    assert first.status_code == second.status_code == 200
    assert "<html" not in first.content.decode()
    assert first["Cache-Control"] == "private, no-store"
    ids1 = {video.pk for video in first.context["page_obj"]}
    ids2 = {video.pk for video in second.context["page_obj"]}
    assert len(ids1) == 8 and len(ids2) == 2 and not ids1 & ids2
    assert unrelated.pk not in ids1 | ids2 and waiting.pk not in ids1 | ids2
    assert first.context["mood_query"] == "q=%D9%82%D8%AF%D9%85&filter=favorites"
    assert first.content.count(b"data-feed-video") == 8
    assert b'playsinline muted loop preload="none"' in first.content
    assert b"data-feed-next" in first.content and b"data-feed-next" not in second.content


@pytest.mark.django_db
def test_fragment_auth_and_favorite_mutation(client_logged, user, video):
    anonymous = Client()
    assert anonymous.get("/", HTTP_X_TIMELINE="fragment").status_code == 302
    url = f"/videos/{video.pk}/favorite/"
    response = client_logged.post(url, HTTP_ACCEPT="application/json")
    assert response.json() == {"favorite": True}
    video.refresh_from_db()
    assert video.favorite
    other = get_user_model().objects.create_user("other-feed-user")
    anonymous.force_login(other)
    assert anonymous.post(url, HTTP_ACCEPT="application/json").status_code == 404
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(user)
    assert csrf.post(url, HTTP_ACCEPT="application/json").status_code == 403


@pytest.mark.django_db
def test_no_script_favorite_returns_to_feed_without_open_redirect(client_logged, video):
    url = f"/videos/{video.pk}/favorite/"
    response = client_logged.post(url, {"next": "/?mood=1"})
    assert response["Location"] == f"/?mood=1#post-{video.pk}"
    response = client_logged.post(url, {"next": "//evil.example/"})
    assert response["Location"] == f"/videos/{video.pk}/"
