import os

os.environ.setdefault("DJANGO_DEBUG", "1")
os.environ.setdefault("LEGACY_UI_ENABLED", "1")

import pytest
from django.contrib.auth import get_user_model

from library.models import Mood, Video


@pytest.fixture(autouse=True)
def isolated_storage(settings, tmp_path):
    settings.LEGACY_UI_ENABLED = True
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir()
    settings.MEDIA_ROOT = settings.DATA_DIR / "media"
    settings.MEDIA_ROOT.mkdir()
    (settings.DATA_DIR / "work").mkdir()
    settings.MIN_FREE_BYTES = 0
    settings.MAX_VIDEO_BYTES = 5_000_000
    settings.SECURE_SSL_REDIRECT = False
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user("owner", password="personal-long-pass-296!")


@pytest.fixture
def client_logged(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def video(user):
    item = Video.objects.create(
        owner=user,
        source_url="https://www.youtube.com/watch?v=BaW_jenozKc",
        source_key="youtube:BaW_jenozKc",
        platform="youtube",
        title="یک قدم کوچک",
        note="برای شروع دوباره",
    )
    item.moods.add(Mood.objects.get(name="امید"))
    return item
