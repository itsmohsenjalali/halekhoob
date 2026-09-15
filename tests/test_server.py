import os
import subprocess
import sys
from unittest.mock import patch

import pytest
from django.db import OperationalError


@pytest.mark.django_db
def test_readiness_requires_database_and_never_exposes_error(client):
    assert client.get("/healthz/").content == b"ok"
    with patch(
        "django.db.connection.cursor", side_effect=OperationalError("private connection details")
    ):
        result = client.get("/healthz/")
    assert result.status_code == 503
    assert result.content == b"unavailable"


@pytest.mark.parametrize(
    ("changes", "valid"),
    [
        ({"APP_PUBLIC_URL": "http://127.0.0.1:8088"}, True),
        ({"APP_PUBLIC_URL": "http://203.0.113.10:8088"}, False),
        ({"APP_PUBLIC_URL": "https://example.com:8443"}, True),
        ({"DATABASE_URL": "postgresql://user:password@outside.example/db"}, False),
    ],
)
def test_production_docker_transport_settings(tmp_path, changes, valid):
    env = {
        **os.environ,
        "DJANGO_DEBUG": "0",
        "DJANGO_SECRET_KEY": "test-production-secret",
        "DATA_DIR": str(tmp_path),
        "MEDIA_BACKEND": "r2",
        "R2_ENDPOINT_URL": "https://" + "a" * 32 + ".r2.cloudflarestorage.com",
        "R2_BUCKET_NAME": "private-test",
        "R2_ACCESS_KEY_ID": "test",
        "R2_SECRET_ACCESS_KEY": "test",
        "DATABASE_URL": "postgresql://user:password@db:5432/halekhoob",
        "DATABASE_DOCKER_INTERNAL": "1",
        "APP_PUBLIC_URL": "https://example.com",
        **changes,
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """from config import settings as s
assert s.DATABASES['default']['OPTIONS']['sslmode'] == 'disable'
assert s.SESSION_COOKIE_SECURE == (not s.LOOPBACK_HTTP)
assert s.SECURE_SSL_REDIRECT == (not s.LOOPBACK_HTTP)
if ':8443' in s.PUBLIC_URL:
    assert s.SECURE_SSL_HOST == 'example.com:8443'
""",
        ],
        env=env,
        capture_output=True,
    )
    assert (result.returncode == 0) == valid
