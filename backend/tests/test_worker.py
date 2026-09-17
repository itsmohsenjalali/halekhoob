import json
import shutil
import socket
import subprocess
from unittest.mock import patch

import pytest
from django.utils import timezone

from library import network, worker
from library.models import Video


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "192.168.1.1",
        "::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
        "0.0.0.0",
    ],
)
def test_private_addresses_blocked(ip):
    assert not network.is_public(ip)


def test_dns_mixed_answer_blocked():
    answers = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
    ]
    with patch.object(network, "_getaddrinfo", return_value=answers), pytest.raises(OSError):
        network.public_addresses("example.test", 443)


@pytest.mark.django_db
def test_recover_interrupted_queue_cleans_only_orphans(video, settings):
    video.status, video.file_name = "downloading", ""
    video.save()
    (settings.DATA_DIR / "work" / "job-stale").mkdir()
    (settings.MEDIA_ROOT / "orphan.mp4").write_bytes(b"incomplete")
    worker.recover()
    video.refresh_from_db()
    assert video.status == "queued" and video.progress == 0
    assert not (settings.DATA_DIR / "work" / "job-stale").exists()
    assert not (settings.MEDIA_ROOT / "orphan.mp4").exists()


@pytest.mark.django_db
def test_quota_stops_before_download_and_preserves_existing(video, settings):
    video.owner.archive_account.storage_limit = 0
    video.owner.archive_account.save()
    retained = settings.MEDIA_ROOT / "retained.mp4"
    retained.write_bytes(b"original")
    with patch.object(worker, "run_child") as download:
        assert worker.process_one()
        download.assert_not_called()
    video.refresh_from_db()
    assert video.status == "failed" and video.error_code == "quota"
    assert retained.read_bytes() == b"original" and video.moods.exists()


@pytest.mark.django_db
def test_transient_retry_only_twice(video):
    with patch.object(worker, "run_child", side_effect=worker.JobError("network", "retry", True)):
        for attempt in range(1, 4):
            Video.objects.filter(pk=video.pk).update(next_attempt_at=timezone.now())
            worker.process_one()
            video.refresh_from_db()
            assert video.attempts == attempt
            assert video.status == ("queued" if attempt < 3 else "failed")
    assert video.note == "برای شروع دوباره"


@pytest.mark.django_db
def test_unavailable_not_retried(video):
    with patch.object(worker, "run_child", side_effect=worker.explain_error("Video unavailable")):
        worker.process_one()
    video.refresh_from_db()
    assert video.status == "failed" and video.attempts == 1 and video.error_code == "unavailable"


@pytest.mark.django_db
def test_complete_pipeline_with_real_ffmpeg(video, settings, tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required for media integration")
    fixture = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=320x240:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(fixture),
        ],
        check=True,
    )

    def fake_network(item, folder):
        target = folder / "source.mp4"
        shutil.copyfile(fixture, target)
        return target, {"title": "remote title", "duration": 2}

    with patch.object(worker, "run_child", side_effect=fake_network):
        worker.process_one()
    video.refresh_from_db()
    assert video.status == "ready" and video.progress == 100 and video.duration == 2
    assert video.title == "یک قدم کوچک"
    assert (settings.MEDIA_ROOT / video.file_name).is_file()
    assert (settings.MEDIA_ROOT / video.thumbnail_name).is_file()
    assert video.audio_checked and video.audio_name
    assert video.size_bytes == sum(
        (settings.MEDIA_ROOT / name).stat().st_size
        for name in [video.file_name, video.thumbnail_name, video.audio_name]
    )
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_streams",
            "-of",
            "json",
            str(settings.MEDIA_ROOT / video.file_name),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert {s["codec_name"] for s in json.loads(result.stdout)["streams"]} == {"h264", "aac"}


@pytest.mark.django_db
def test_invalid_download_not_marked_ready(video, settings):
    def broken(item, folder):
        source = folder / "source.mp4"
        source.write_bytes(b"not a real video")
        return source, {"title": "bad"}

    with patch.object(worker, "run_child", side_effect=broken):
        worker.process_one()
    video.refresh_from_db()
    assert video.status == "failed" and video.file_name == ""
    assert not list(settings.MEDIA_ROOT.iterdir())


@pytest.mark.parametrize("dimensions", ["720x1280", "101x101"])
def test_transcode_portrait_and_odd_dimensions(dimensions, tmp_path):
    source = tmp_path / "source.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={dimensions}:duration=1:rate=10",
            "-c:v",
            "ffv1",
            str(source),
        ],
        check=True,
    )
    destination, thumbnail, duration = worker.transcode(source, tmp_path)
    _, stream, _ = worker.probe(destination)
    assert stream["height"] <= 720 and stream["height"] % 2 == 0
    assert stream["codec_name"] == "h264" and stream["pix_fmt"] == "yuv420p"
    assert duration == 1 and thumbnail.is_file()


def test_long_video_duration_is_allowed():
    result = subprocess.CompletedProcess(
        [],
        0,
        stdout=json.dumps(
            {
                "format": {"duration": 1202},
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
            }
        ),
    )
    with patch.object(worker.subprocess, "run", return_value=result):
        duration, _, _ = worker.probe("source-with-no-metadata.mp4")
    assert duration == 1202


def test_real_long_video_and_audio_have_no_duration_cap(tmp_path):
    from library.audio import extract_audio, inspect_audio

    source = tmp_path / 'long-source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=16x16:r=1:d=1202',
                    '-f', 'lavfi', '-i', 'anullsrc=r=8000:cl=mono', '-t', '1202',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)], check=True)
    file, _, duration = worker.transcode(source, tmp_path, 10_000_000)
    audio = extract_audio(file, tmp_path, 10_000_000)
    assert duration == 1202
    assert float(inspect_audio(audio)['format']['duration']) > 1200
