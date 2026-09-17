import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction

from library import quota, worker
from library.models import CloudObject, QuotaChange, Video
from tests.test_api import call, identities  # noqa: F401


@pytest.mark.django_db
@pytest.mark.usefixtures("identities")
def test_admin_endpoints_require_staff_and_reject_role_injection(client):
    call(client, "me/")
    user = get_user_model().objects.get(username="user_alice")
    for path in ["admin/overview/", "admin/users/"]:
        assert client.get("/api/v1/" + path).status_code == 401
        assert call(client, path).status_code == 403
    assert (
        call(client, f"admin/users/{user.pk}/quota/", "patch", {"storage_limit": 0}).status_code
        == 403
    )
    user.is_staff = True
    user.save()
    assert call(client, "me/").json()["is_admin"] is True
    for value in [-1, True, "12", 1.5, 10**16, None]:
        assert (
            call(
                client, f"admin/users/{user.pk}/quota/", "patch", {"storage_limit": value}
            ).status_code
            == 400
        )
    assert (
        call(
            client, f"admin/users/{user.pk}/quota/", "patch", {"storage_limit": 0, "is_staff": True}
        ).status_code
        == 400
    )
    response = call(client, "admin/overview/")
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    assert call(client, "admin/users/?q=missing").json()["count"] == 0
    user.is_staff = False
    user.save()
    assert call(client, "admin/users/").status_code == 403


@pytest.mark.django_db
@pytest.mark.usefixtures("identities")
def test_admin_quota_change_preserves_media_and_records_actor(client):
    call(client, "me/")
    call(client, "me/", identity="bob")
    admin = get_user_model().objects.get(username="user_alice")
    admin.is_staff = True
    admin.save()
    target = get_user_model().objects.get(username="user_bob")
    video = Video.objects.create(owner=target, source_key="kept", status="ready", size_bytes=200)
    queued = Video.objects.create(owner=target, source_key="next", status="queued")
    original = target.archive_account.storage_limit
    response = call(client, f"admin/users/{target.pk}/quota/", "patch", {"storage_limit": 100})
    assert response.status_code == 200 and response.json()["storage_used"] == 200
    video.refresh_from_db()
    assert video.status == "ready" and video.size_bytes == 200
    with pytest.raises(worker.JobError), transaction.atomic():
        quota.ensure_publish(queued, 1)
    record = QuotaChange.objects.get()
    assert (record.actor_id, record.user_id, record.old_limit, record.new_limit) == (
        admin.pk,
        target.pk,
        original,
        100,
    )
    assert (
        call(
            client, f"admin/users/{target.pk}/quota/", "patch", {"storage_limit": 1000}
        ).status_code
        == 200
    )
    with transaction.atomic():
        quota.ensure_publish(queued, 800)
    assert call(client, "admin/users/?q=user_bob").json()["items"][0]["storage_limit"] == 1000


@pytest.mark.django_db
@pytest.mark.usefixtures("identities")
def test_monitoring_snapshot_whitelists_and_flags_stale(client, settings, tmp_path):
    call(client, "me/")
    get_user_model().objects.update(is_staff=True)
    path = tmp_path / "metrics.json"
    settings.HOST_METRICS_FILE = str(path)
    path.write_text(
        json.dumps(
            {
                "timestamp": 1,
                "cpu_percent": 12,
                "cpu_count": 2,
                "memory_total": 100,
                "memory_used": 50,
                "disk_total": 100,
                "disk_used": 50,
                "disk_free": 50,
                "uptime_seconds": 10,
                "services": {},
                "secret": "do-not-expose",
            }
        )
    )
    host = call(client, "admin/overview/").json()["host"]
    assert host["stale"] is True and "secret" not in host
    path.write_text("broken")
    assert call(client, "admin/overview/").json()["host"] is None


@pytest.mark.django_db
@pytest.mark.usefixtures("identities")
def test_budget_is_remaining_user_space_without_global_or_fixed_file_cap(video, settings):
    settings.ARCHIVE_MAX_BYTES = 1
    account = video.owner.archive_account
    account.storage_limit = 3_000_000_000
    account.save()
    CloudObject.objects.create(owner=video.owner, key="old", size_bytes=250_000_000, sha256="x")
    assert quota.budget(video) == 2_750_000_000
    with transaction.atomic():
        quota.ensure_publish(video, 2_750_000_000)
        with pytest.raises(worker.JobError):
            quota.ensure_publish(video, 2_750_000_001)


def test_invalid_duration_still_rejected():
    for duration in [0, -1, "NaN", "Infinity"]:
        payload = {"format": {"duration": duration}, "streams": [{"codec_type": "video"}]}
        with patch.object(
            worker.subprocess,
            "run",
            return_value=type("Result", (), {"stdout": json.dumps(payload)})(),
        ):
            with pytest.raises(worker.JobError):
                worker.probe("bad.mp4")
