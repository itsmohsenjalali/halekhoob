import json
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from library import clerk_auth, quota
from library.accounts import provision_identity
from library.models import Account, CloudObject, Mood, Video


@pytest.fixture
def identities(settings):
    settings.CLERK_LEGACY_OWNER_EMAIL = ""
    with (
        patch.object(
            clerk_auth, "verify_token", side_effect=lambda token: {"sub": "user_" + token}
        ),
        patch.object(
            clerk_auth,
            "google_identity",
            side_effect=lambda subject, *args: {
                "email": subject + "@example.com",
                "first_name": subject,
            },
        ),
    ):
        yield


def call(client, path, method="get", data=None, identity="alice"):
    return getattr(client, method)(
        "/api/v1/" + path,
        data=json.dumps(data) if data is not None else None,
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer " + identity,
    )


@pytest.mark.django_db
def test_api_rejects_legacy_cookie_login(client, user):
    client.force_login(user)
    assert client.get("/api/v1/me/").status_code == 401


@pytest.mark.django_db
def test_independent_categories_and_duplicate_urls(client, identities):
    for identity in ["alice", "bob"]:
        assert call(client, "me/", identity=identity).status_code == 200
        category = call(client, "categories/", identity=identity).json()["items"][0]["id"]
        data = {"source_url": "https://youtu.be/BaW_jenozKc", "category_ids": [category]}
        first = call(client, "videos/", "post", data, identity)
        assert first.status_code == 201
        assert call(client, "videos/", "post", data, identity).json()["duplicate"] is True
    assert Video.objects.count() == 2
    assert Mood.objects.count() == 12
    assert set(Video.objects.values_list("owner_id", flat=True)) == set(
        get_user_model().objects.values_list("id", flat=True)
    )


@pytest.mark.django_db
def test_cross_user_endpoints_and_category_injection(client, identities):
    call(client, "me/")
    call(client, "me/", identity="bob")
    alice = get_user_model().objects.get(username="user_alice")
    category = alice.moods.first()
    video = Video.objects.create(
        owner=alice,
        source_key="youtube:test",
        source_url="https://youtu.be/BaW_jenozKc",
        status="ready",
    )
    for path in [
        f"videos/{video.pk}/",
        f"videos/{video.pk}/download/",
        f"videos/?category={category.pk}",
        f"playlist/?category={category.pk}",
    ]:
        assert call(client, path, identity="bob").status_code == 404
    assert (
        call(client, f"videos/{video.pk}/", "patch", {"favorite": True}, "bob").status_code == 404
    )
    assert call(client, f"videos/{video.pk}/", "delete", identity="bob").status_code == 404
    assert call(client, f"categories/{category.pk}/", "delete", identity="bob").status_code == 404
    assert (
        call(
            client,
            "videos/",
            "post",
            {"source_url": video.source_url, "category_ids": [category.pk]},
            "bob",
        ).status_code
        == 400
    )
    assert call(client, "videos/?state=all", identity="bob").json()["items"] == []


@pytest.mark.django_db
def test_only_storage_limits_admission(client, identities):
    call(client, "me/")
    account = Account.objects.get()
    account.storage_limit = 100
    account.save()
    category = account.user.moods.first().pk
    # More than both former five-item queue and daily limits, with <500 MB free.
    for index in range(7):
        assert call(client, "videos/", "post", {
            "source_url": f"https://instagram.com/p/ABC123{index}/", "category_ids": [category],
        }).status_code == 201
    assert call(client, "me/").json()["storage_reserved"] == 0
    assert call(client, "me/").json()["daily_used"] == 7
    account.storage_limit = 0
    account.save()
    assert call(client, "videos/", "post", {
        "source_url": "https://youtu.be/BaW_jenozKc", "category_ids": [category],
    }).status_code == 429
    assert Video.objects.count() == 7


@pytest.mark.django_db
def test_storage_accounts_retained_objects(client, identities):
    call(client, "me/")
    alice = get_user_model().objects.get(username="user_alice")
    CloudObject.objects.create(
        owner=alice, key="archive/retained", size_bytes=123, sha256="x", state="deleting"
    )
    assert call(client, "me/").json()["storage_used"] == 123
    assert call(client, "me/", identity="bob").json()["storage_used"] == 0


@pytest.mark.django_db
def test_local_download_ticket_survives_logout_but_expires(client, identities, settings):
    call(client, "me/")
    owner = get_user_model().objects.get(username="user_alice")
    video = Video.objects.create(
        owner=owner, source_key="test", status="ready", file_name="sample.mp4", title="آرامش"
    )
    (settings.MEDIA_ROOT / "sample.mp4").write_bytes(b"0123456789")
    signed = call(client, f"videos/{video.pk}/download/").json()["url"]
    response = Client().get(signed, HTTP_RANGE="bytes=2-5")
    assert response.status_code == 206
    assert b"".join(response.streaming_content) == b"2345"
    assert response["Content-Disposition"].startswith("attachment")
    with patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + 301):
        assert Client().get(signed).status_code == 404
    assert Client().get(signed + "broken").status_code == 404


@pytest.mark.django_db
def test_existing_archive_links_only_to_verified_expected_identity(user, settings):
    settings.CLERK_LEGACY_OWNER_EMAIL = "owner@example.com"
    identity = {"email": "owner@example.com", "first_name": "Owner"}
    linked = provision_identity("user_google", identity)
    assert linked.pk == user.pk and not linked.has_usable_password()
    assert linked.archive_account.clerk_id == "user_google"
    with pytest.raises(ValueError):
        provision_identity("user_attacker", identity)


@pytest.fixture
def signing_key(settings):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.CLERK_ISSUER = "https://clerk.example.com"
    settings.CLERK_AUTHORIZED_PARTIES = ["https://archive.example.com"]
    with patch.object(
        clerk_auth,
        "jwks_client",
        return_value=SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())
        ),
    ):
        yield key


def token(key, **changes):
    now = int(timezone.now().timestamp())
    payload = {
        "iss": "https://clerk.example.com",
        "azp": "https://archive.example.com",
        "sub": "user_alice",
        "sid": "sess_test",
        "iat": now,
        "nbf": now,
        "exp": now + 60,
        **changes,
    }
    return jwt.encode(payload, key, algorithm="RS256")


def test_valid_jwt_and_strict_invalid_claims(signing_key):
    assert clerk_auth.verify_token(token(signing_key))["sub"] == "user_alice"
    for changes in [
        {"iss": "https://attacker.example"},
        {"azp": "https://attacker.example"},
        {"exp": 0},
        {"nbf": 9999999999},
        {"sub": "bad"},
        {"sid": "bad"},
        {"sts": "pending"},
    ]:
        with pytest.raises(clerk_auth.AuthenticationError):
            clerk_auth.verify_token(token(signing_key, **changes))
    with pytest.raises(clerk_auth.AuthenticationError):
        clerk_auth.verify_token(jwt.encode({"sub": "user_alice"}, "bad-secret", algorithm="HS256"))


def test_google_identity_rejects_unverified_and_non_google_accounts():
    clerk_auth.google_identity.cache_clear()
    payload = {
        "id": "user_alice",
        "primary_email_address_id": "email_1",
        "email_addresses": [
            {
                "id": "email_1",
                "email_address": "alice@example.com",
                "verification": {"status": "verified"},
            }
        ],
        "external_accounts": [{"provider": "google", "email_address": "alice@example.com"}],
    }
    from io import BytesIO

    with patch.object(
        clerk_auth, "urlopen", side_effect=lambda *a, **kw: BytesIO(json.dumps(payload).encode())
    ):
        assert clerk_auth.google_identity("user_alice", 1, "secret")["email"] == "alice@example.com"
        payload["external_accounts"] = []
        with pytest.raises(clerk_auth.AuthenticationError):
            clerk_auth.google_identity("user_alice", 2, "secret")
        payload["banned"] = True
        with pytest.raises(clerk_auth.AuthenticationError):
            clerk_auth.google_identity("user_alice", 3, "secret")


@pytest.mark.django_db
def test_fair_queue_prefers_unserved_user(user):
    Video.objects.create(owner=user, source_key="first")
    Account.objects.filter(user=user).update(last_served_at=timezone.now())
    other = get_user_model().objects.create_user("other")
    second = Video.objects.create(owner=other, source_key="second")
    assert quota.next_job(Video.objects.filter(status="queued")).pk == second.pk


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_login_creates_one_account(settings):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connection

    if connection.vendor != "postgresql":
        pytest.skip("Concurrency is verified against PostgreSQL")
    barrier = Barrier(2)

    def login():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return provision_identity("user_concurrent", {"email": "concurrent@example.com"}).pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(login) for _ in range(2)]
        ids = [f.result(timeout=20) for f in futures]
    assert ids[0] == ids[1]
    assert Account.objects.filter(clerk_id="user_concurrent").count() == 1
    assert Mood.objects.filter(owner_id=ids[0]).count() == 6


def test_legacy_migration_preserves_user_archives(tmp_path):
    import os
    import subprocess
    import sys

    script = """
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
executor = MigrationExecutor(connection)
old = [('library', '0004_workerlease_video_job_token_video_storage_backend_and_more')]
executor.migrate(old)
apps = executor.loader.project_state(old).apps
User = apps.get_model('auth', 'User')
Mood = apps.get_model('library', 'Mood')
Video = apps.get_model('library', 'Video')
CloudObject = apps.get_model('library', 'CloudObject')
a = User.objects.create(username='owner')
b = User.objects.create(username='second')
mood = Mood.objects.first()
v1 = Video.objects.create(owner=a, source_key='a', storage_backend='r2', file_name='archive/old.mp4')
v2 = Video.objects.create(owner=b, source_key='b')
v1.moods.add(mood)
v2.moods.add(mood)
CloudObject.objects.create(video=v1, key='archive/old.mp4', size_bytes=42, sha256='hash', state='live')
executor = MigrationExecutor(connection)
executor.migrate(executor.loader.graph.leaf_nodes())
from library.models import Account, Mood, Video, CloudObject
for video in Video.objects.all():
    assert video.moods.count() == 1
    assert video.moods.get().owner_id == video.owner_id
assert Account.objects.count() == 2
assert Mood.objects.filter(owner_id=a.pk).count() == Mood.objects.filter(owner_id=b.pk).count()
assert CloudObject.objects.get().owner_id == a.pk
assert Video.objects.get(pk=v1.pk).file_name == 'archive/old.mp4'
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "DATA_DIR": str(tmp_path / "migration"),
            "DATABASE_URL": "",
            "MEDIA_BACKEND": "local",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
