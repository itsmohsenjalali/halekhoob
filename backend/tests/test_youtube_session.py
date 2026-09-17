from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from library import downloader, worker
from library.youtube_session import check_public_video, youtube_cookie_file

URL = "https://www.youtube.com/watch?v=BaW_jenozKc"
HEADER = "# Netscape HTTP Cookie File\n"
COOKIE = ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tSAPISID\ttest-only-session\n"


def test_session_is_filtered_private_ephemeral_and_source_unchanged(tmp_path):
    source = tmp_path / "source.txt"
    original = HEADER + COOKIE + COOKIE.replace(".youtube.com", ".google.com")
    source.write_text(original)
    with pytest.raises(RuntimeError), youtube_cookie_file(URL, source) as name:
        copied = Path(name)
        assert copied.stat().st_mode & 0o777 == 0o600
        assert copied.read_text() == HEADER + COOKIE
        raise RuntimeError("download failed")
    assert not copied.exists()
    assert source.read_text() == original


@pytest.mark.parametrize("url", ["https://www.instagram.com/p/test/", "https://youtube.com.example/watch?v=test"])
def test_other_hosts_never_open_session(url):
    with patch.object(Path, "open", side_effect=AssertionError("secret read")):
        with youtube_cookie_file(url, "/private/cookies.txt") as name:
            assert name is None


@pytest.mark.parametrize("content", [
    "private-session-value",
    HEADER + COOKIE.replace("2000000000", "private-session-value"),
    HEADER + COOKIE.replace(".youtube.com", "youtube.com"),
    HEADER + COOKIE.replace(".youtube.com", ".google.com"),
])
def test_invalid_session_does_not_disclose_cookie_values(tmp_path, content, capsys):
    source = tmp_path / "cookies.txt"
    source.write_text(content)
    with pytest.raises(ValueError, match="^ARCHIVE_YOUTUBE_SESSION_INVALID$"):
        with youtube_cookie_file(URL, source):
            pytest.fail("invalid session accepted")
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


@pytest.mark.parametrize("availability", ["private", "needs_auth", "premium_only", "subscriber_only", None])
def test_shared_session_cannot_download_restricted_media(tmp_path, availability):
    source = tmp_path / "cookies.txt"
    source.write_text(HEADER + COOKIE)
    with patch.object(downloader, "install_network_guard"), patch("yt_dlp.YoutubeDL") as factory:
        ydl = factory.return_value.__enter__.return_value
        ydl.extract_info.return_value = {"availability": availability, "title": "restricted"}
        with pytest.raises(ValueError, match="ARCHIVE_LIMIT_AUTHENTICATED_CONTENT"):
            downloader.download(URL, tmp_path, 10000, source)
        ydl.process_ie_result.assert_not_called()


def test_age_gate_remains_blocked():
    with pytest.raises(ValueError, match="ARCHIVE_LIMIT_AUTHENTICATED_CONTENT"):
        check_public_video({"availability": "public", "age_limit": 18})


@pytest.mark.parametrize("availability", ["public", "unlisted"])
def test_publicly_accessible_media_allowed(availability):
    check_public_video({"availability": availability, "age_limit": 0})


@pytest.mark.parametrize("platform", ["youtube", "instagram"])
def test_worker_passes_only_explicit_session_path_not_application_secrets(platform, tmp_path, settings, monkeypatch):
    settings.YOUTUBE_COOKIES_FILE = "/run/secrets/youtube.cookies.txt"
    monkeypatch.setenv("YOUTUBE_COOKIES_FILE", settings.YOUTUBE_COOKIES_FILE)
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test-secret")
    video = SimpleNamespace(platform=platform, source_url=URL)
    with patch.object(worker.quota, "budget", return_value=10000), patch.object(
        worker.subprocess, "Popen", side_effect=RuntimeError("probe")
    ) as process:
        with pytest.raises(RuntimeError, match="probe"):
            worker.run_child(video, tmp_path)
    command = process.call_args.args[0]
    assert ("--youtube-cookies" in command) == (platform == "youtube")
    assert "YOUTUBE_COOKIES_FILE" not in process.call_args.kwargs["env"]
    assert "R2_SECRET_ACCESS_KEY" not in process.call_args.kwargs["env"]
