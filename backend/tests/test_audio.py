import io
import subprocess
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from library.audio import extract_audio, inspect_audio
from library.models import Mood, Video
from library.worker import recover


@pytest.mark.django_db
def test_playlist_includes_entire_filtered_queue_and_is_private(client_logged, user):
    hope = Mood.objects.get(name="امید")
    expected = []
    for i in range(11):
        video = Video.objects.create(
            owner=user,
            source_key=f"audio:{i}",
            title=f"قدم {i}",
            status="ready",
            audio_checked=True,
            audio_name=f"{i}.m4a",
            favorite=True,
        )
        video.moods.add(hope)
        expected.append(video.pk)
    Video.objects.create(owner=user, source_key="unrelated", status="ready", audio_name="other.m4a")
    other = get_user_model().objects.create_user("audio-other")
    foreign = Video.objects.create(
        owner=other,
        source_key="foreign",
        status="ready",
        title="قدم",
        audio_name="private.m4a",
        favorite=True,
    )
    foreign.moods.add(hope)
    response = client_logged.get(
        f"/api/audio-playlist/?mood={hope.pk}&q=قدم&filter=favorites&page=2"
    )
    assert response.status_code == 200
    assert [track["id"] for track in response.json()["tracks"]] == expected[::-1]
    assert response["Cache-Control"] == "private, no-store"
    assert Client().get("/api/audio-playlist/").status_code == 302
    assert client_logged.get("/api/audio-playlist/?filter=pending").json()["tracks"] == []


@pytest.mark.django_db
def test_audio_range_auth_deletion_and_recovery(
    client_logged, video, settings, django_capture_on_commit_callbacks
):
    video.status, video.audio_checked, video.audio_name = "ready", True, "private.m4a"
    video.save()
    path = settings.MEDIA_ROOT / video.audio_name
    path.write_bytes(b"0123456789")
    url = f"/videos/{video.pk}/media/audio/"
    assert Client().get(url).status_code == 302
    other_client = Client()
    other_client.force_login(get_user_model().objects.create_user("not-owner"))
    assert other_client.get(url).status_code == 404
    response = client_logged.get(url, HTTP_RANGE="bytes=2-5")
    assert response.status_code == 206 and response["Content-Type"] == "audio/mp4"
    assert b"".join(response.streaming_content) == b"2345"
    recover()
    assert path.exists()
    with django_capture_on_commit_callbacks(execute=True):
        assert client_logged.post(f"/videos/{video.pk}/delete/").status_code == 302
    assert not path.exists()


@pytest.mark.django_db
def test_silent_and_pending_are_reported_separately(client_logged, video, user):
    video.status, video.audio_checked = "ready", True
    video.save()
    Video.objects.create(owner=user, source_key="pending-audio", status="ready")
    result = client_logged.get("/api/audio-playlist/").json()
    assert result["tracks"] == [] and result["pending"] == result["silent"] == 1


@pytest.fixture
def audio_source(tmp_path):
    source = tmp_path / "input.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=s=160x120:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=1",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
    )
    return source


def test_extract_is_audio_only_and_silent_video_is_supported(audio_source, tmp_path):
    audio = extract_audio(audio_source, tmp_path)
    assert {(s["codec_type"], s["codec_name"]) for s in inspect_audio(audio)["streams"]} == {
        ("audio", "aac")
    }
    silent = tmp_path / "silent.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(audio_source), "-an", "-c:v", "copy", str(silent)],
        check=True,
    )
    assert extract_audio(silent, tmp_path) is None


@pytest.mark.django_db
def test_backfill_is_idempotent_and_accounts_for_space(video, settings, audio_source):
    video.status, video.file_name = "ready", "original.mp4"
    original = audio_source.read_bytes()
    (settings.MEDIA_ROOT / video.file_name).write_bytes(original)
    video.size_bytes = len(original)
    video.save()
    call_command("prepare_audio", stdout=io.StringIO())
    video.refresh_from_db()
    assert video.audio_checked and video.audio_name
    size = len(original) + (settings.MEDIA_ROOT / video.audio_name).stat().st_size
    assert video.size_bytes == size
    with patch("library.management.commands.prepare_audio.extract_audio") as extract:
        call_command("prepare_audio", stdout=io.StringIO())
        extract.assert_not_called()
    video.refresh_from_db()
    assert video.size_bytes == size


@pytest.mark.django_db
def test_backfill_quota_preserves_original(video, settings, audio_source):
    video.status, video.file_name = "ready", "original.mp4"
    original = audio_source.read_bytes()
    (settings.MEDIA_ROOT / video.file_name).write_bytes(original)
    video.size_bytes = len(original)
    video.save()
    settings.ARCHIVE_MAX_BYTES = len(original)
    with pytest.raises(CommandError):
        call_command("prepare_audio")
    video.refresh_from_db()
    assert not video.audio_checked and not video.audio_name
    assert (settings.MEDIA_ROOT / video.file_name).read_bytes() == original
