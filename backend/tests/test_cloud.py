import io
import shutil
import subprocess
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.utils import timezone
from moto import mock_aws
from scripts.verify_export import verify

from library import cloud_worker, r2, worker
from library.leases import Lease, LeaseBusy, LeaseLost
from library.models import CloudObject, Video, WorkerLease


@pytest.fixture
def store(settings):
    settings.MEDIA_BACKEND = "r2"
    settings.R2_BUCKET_NAME = "private-test"
    settings.R2_PREFIX = "archive"
    settings.R2_ACCESS_KEY_ID = "testing"
    settings.R2_SECRET_ACCESS_KEY = "testing"
    settings.R2_ENDPOINT_URL = "https://" + "a" * 32 + ".r2.cloudflarestorage.com"
    with mock_aws():
        client = boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
        client.create_bucket(Bucket=settings.R2_BUCKET_NAME)
        with patch.object(r2, "client", return_value=client):
            yield client


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=160x120:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path


def download_fixture(source):
    def run(video, folder):
        target = folder / "source.mp4"
        shutil.copyfile(source, target)
        return target, {"title": "test", "duration": 1}

    return run


@pytest.mark.django_db
def test_cloud_pipeline_private_redirect_and_durable_delete(
    store, source, video, client_logged, settings
):
    with Lease() as lease, patch.object(worker, "run_child", side_effect=download_fixture(source)):
        assert cloud_worker.process_one(lease)
    video.refresh_from_db()
    assert video.status == "ready" and video.storage_backend == "r2" and video.audio_name
    assert CloudObject.objects.filter(video=video, state="live").count() == 3
    assert video.size_bytes == sum(CloudObject.objects.values_list("size_bytes", flat=True))
    assert not list(settings.MEDIA_ROOT.iterdir())
    url = f"/videos/{video.pk}/media/audio/"
    response = client_logged.get(url, HTTP_RANGE="bytes=0-3")
    assert response.status_code == 302
    assert video.audio_name in response["Location"]
    assert response["Cache-Control"] == "private, no-store"
    assert settings.R2_ENDPOINT_URL in response["Content-Security-Policy"]
    assert not hasattr(response, "streaming_content")
    # The actual S3 protocol supports byte-range delivery directly.
    partial = store.get_object(
        Bucket=settings.R2_BUCKET_NAME, Key=video.audio_name, Range="bytes=0-3"
    )
    assert partial["ResponseMetadata"]["HTTPStatusCode"] == 206 and len(partial["Body"].read()) == 4
    assert Client().get(url).status_code == 302
    other = Client()
    other.force_login(get_user_model().objects.create_user("foreign"))
    assert other.get(url).status_code == 404
    assert client_logged.post(f"/videos/{video.pk}/delete/").status_code == 302
    assert not Video.objects.filter(pk=video.pk).exists()
    assert CloudObject.objects.filter(state="deleting").count() == 3
    assert all(obj.delete_after <= timezone.now() for obj in CloudObject.objects.all())
    r2.cleanup()
    assert not CloudObject.objects.exists()
    assert r2.stored_bytes() == 0
    assert store.list_objects_v2(Bucket=settings.R2_BUCKET_NAME).get("KeyCount", 0) == 0


@pytest.mark.django_db
def test_failed_upload_retry_uses_new_keys_and_preserves_journal(store, source, video):
    original = r2.upload
    calls = 0

    def interrupted(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise r2.StorageError("network")
        original(*args)

    with Lease() as lease, patch.object(worker, "run_child", side_effect=download_fixture(source)):
        with patch.object(r2, "upload", side_effect=interrupted):
            cloud_worker.process_one(lease)
        video.refresh_from_db()
        assert video.status == "queued" and video.error_code == "storage" and not video.file_name
        old_keys = set(CloudObject.objects.values_list("key", flat=True))
        assert len(old_keys) == 2 and CloudObject.objects.filter(state="deleting").count() == 2
        Video.objects.filter(pk=video.pk).update(next_attempt_at=timezone.now())
        cloud_worker.process_one(lease)
        video.refresh_from_db()
        assert video.status == "ready" and video.file_name not in old_keys
        assert CloudObject.objects.filter(key__in=old_keys).count() == 2


@pytest.mark.django_db
def test_expired_lease_is_fenced_and_recovers_only_after_takeover(store, video, tmp_path):
    first = Lease().acquire()
    Video.objects.filter(pk=video.pk).update(status="downloading", job_token=first.token)
    with pytest.raises(LeaseBusy):
        Lease().acquire()
    WorkerLease.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    second = Lease().acquire()
    cloud_worker.recover(second)
    video.refresh_from_db()
    assert video.status == "queued"
    path = tmp_path / "old.mp4"
    path.write_bytes(b"stale")
    with pytest.raises(LeaseLost):
        cloud_worker.publish(video, [(path, "video", "video/mp4")], 1, "old", first)
    assert not CloudObject.objects.exists()
    second.renew()
    with pytest.raises(LeaseLost):
        first.renew()


@pytest.mark.django_db
def test_delete_failure_retries_and_ready_objects_are_never_removed(store, video, settings):
    key = "archive/media/retained.mp4"
    video.status, video.file_name = "ready", key
    video.save()
    record = CloudObject.objects.create(
        key=key,
        video=video,
        size_bytes=4,
        sha256="abc",
        state="deleting",
        delete_after=timezone.now(),
    )
    with patch.object(store, "delete_object") as delete:
        r2.cleanup()
        delete.assert_not_called()
    video.delete()
    with patch.object(store, "delete_object", side_effect=RuntimeError("network")):
        r2.cleanup()
    record.refresh_from_db()
    assert record.attempts == 1 and record.error == "delete_failed"


@pytest.mark.django_db
def test_cloud_quota_includes_retained_objects(store, video, settings):
    CloudObject.objects.create(owner=video.owner, key="archive/old", size_bytes=100, sha256="abc", state="deleting")
    video.owner.archive_account.storage_limit = 100
    video.owner.archive_account.save()
    with Lease() as lease, patch.object(worker, "run_child") as run:
        cloud_worker.process_one(lease)
        run.assert_not_called()
    video.refresh_from_db()
    assert video.status == "failed" and video.error_code == "quota"


def test_real_r2_signature_is_scoped_and_has_no_range_in_signature(settings):
    settings.R2_ENDPOINT_URL = "https://" + "a" * 32 + ".r2.cloudflarestorage.com"
    settings.R2_BUCKET_NAME = "private"
    settings.R2_ACCESS_KEY_ID, settings.R2_SECRET_ACCESS_KEY = "example", "test-secret"
    url = r2.signed_url("archive/media/1/audio.m4a")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.hostname.endswith(".r2.cloudflarestorage.com")
    assert query["X-Amz-SignedHeaders"] == ["host"]
    assert query["X-Amz-Expires"] == ["3600"]
    assert "test-secret" not in url
    attachment = parse_qs(urlparse(r2.signed_url("archive/media/1/audio.m4a", attachment_name="آرامش.m4a")).query)
    assert attachment["X-Amz-Expires"] == ["300"]
    assert attachment["response-content-disposition"][0].startswith("attachment;")
    assert "filename*=UTF-8" in attachment["response-content-disposition"][0]
    with pytest.raises(r2.StorageError):
        r2.signed_url("archive/../secret")


@pytest.mark.django_db(transaction=True)
def test_portable_local_to_r2_and_cloud_backup_restore(store, source, video, settings, tmp_path):
    # Start with the existing local format, keeping the original media intact.
    settings.MEDIA_BACKEND = "local"
    video.status, video.file_name = "ready", "original.mp4"
    video.size_bytes = source.stat().st_size
    video.save()
    from library.models import QuotaChange

    QuotaChange.objects.create(actor=video.owner, user=video.owner, old_limit=1000, new_limit=2000)
    original = settings.MEDIA_ROOT / "original.mp4"
    shutil.copyfile(source, original)
    output = tmp_path / "migration.tar"
    call_command("export_portable", str(output), stdout=io.StringIO())
    assert verify(output) == 2
    video.delete()
    QuotaChange.objects.all().delete()
    get_user_model().objects.all().delete()
    settings.MEDIA_BACKEND = "r2"
    call_command("import_portable", str(output), stdout=io.StringIO())
    assert QuotaChange.objects.get().new_limit == 2000
    restored = Video.objects.get()
    assert restored.storage_backend == "r2" and restored.note == "برای شروع دوباره"
    assert restored.moods.get().name == "امید"
    assert get_user_model().objects.get().check_password("personal-long-pass-296!")
    assert original.read_bytes() == source.read_bytes()
    with pytest.raises(CommandError):
        call_command("import_portable", str(output))
    backup = tmp_path / "cloud.tar"
    call_command("export_portable", str(backup), stdout=io.StringIO())
    meta = tmp_path / "metadata.tar"
    call_command("export_portable", str(meta), metadata_only=True, stdout=io.StringIO())
    assert verify(backup) == 2
    assert verify(meta) == 1
    Video.objects.all().delete()
    QuotaChange.objects.all().delete()
    get_user_model().objects.all().delete()
    CloudObject.objects.all().delete()
    call_command("import_portable", str(meta), stdout=io.StringIO())
    assert Video.objects.get().file_name == restored.file_name
    Video.objects.all().delete()
    QuotaChange.objects.all().delete()
    get_user_model().objects.all().delete()
    CloudObject.objects.all().delete()
    call_command("import_portable", str(backup), stdout=io.StringIO())
    assert Video.objects.get().file_name != restored.file_name


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_workers_only_one_acquires():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connection

    if connection.vendor != "postgresql":
        pytest.skip("Run with DATABASE_URL for PostgreSQL concurrency verification")
    barrier = Barrier(2)

    def claim():
        close_old_connections()
        try:
            barrier.wait()
            try:
                return str(Lease().acquire().token)
            except LeaseBusy:
                return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(result is not None for result in results) == 1


@pytest.mark.django_db
def test_quota_reduced_during_upload_prevents_publication(store, source, video):
    upload = r2.upload

    def reduce_after_upload(*args, **kwargs):
        result = upload(*args, **kwargs)
        account = video.owner.archive_account
        account.storage_limit = 0
        account.save()
        return result

    with Lease() as lease, patch.object(worker, "run_child", side_effect=download_fixture(source)), patch.object(r2, "upload", side_effect=reduce_after_upload):
        cloud_worker.process_one(lease)
    video.refresh_from_db()
    assert video.status == "failed" and video.error_code == "quota"
    assert video.file_name == "" and not CloudObject.objects.filter(state="live").exists()
    assert CloudObject.objects.filter(video=video, state="deleting").count() == 3


def test_deletion_runner_cleans_while_download_thread_is_busy():
    import threading
    from types import SimpleNamespace

    cleaned = threading.Event()
    lease = SimpleNamespace(check=lambda: None)
    with patch.object(cloud_worker, "close_old_connections"), patch.object(
        r2, "cleanup", side_effect=lambda check: (check(), cleaned.set())
    ):
        with cloud_worker.deletion_runner(lease):
            # Main worker may be blocked waiting for a video; deletion runs anyway.
            assert cleaned.wait(3)
    assert not any(t.name == "r2-deletions" for t in threading.enumerate())


def test_deletion_runner_stops_when_worker_loses_lease():
    from types import SimpleNamespace

    def lost():
        raise LeaseLost("test")

    with patch.object(cloud_worker, "close_old_connections"), patch.object(r2, "cleanup") as cleanup:
        with cloud_worker.deletion_runner(SimpleNamespace(check=lost)):
            pass
        cleanup.assert_not_called()
