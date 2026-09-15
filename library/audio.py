"""Create a private, audio-only AAC file from an already validated local MP4."""

import json
import subprocess

from django.conf import settings


def inspect_audio(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(result.stdout)


def extract_audio(source, folder):
    info = inspect_audio(source)
    streams = [stream for stream in info["streams"] if stream["codec_type"] == "audio"]
    if not streams:
        return None
    destination = folder / "audio.m4a"
    codecs = (
        ["-c:a", "copy"] if streams[0]["codec_name"] == "aac" else ["-c:a", "aac", "-b:a", "128k"]
    )
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            *codecs,
            "-movflags",
            "+faststart",
            "-fs",
            str(settings.MAX_VIDEO_BYTES),
            "-y",
            str(destination),
        ],
        check=True,
        capture_output=True,
        timeout=settings.DOWNLOAD_TIMEOUT,
    )
    actual = inspect_audio(destination)
    duration = float(actual["format"].get("duration", 0))
    original = float(streams[0].get("duration") or info["format"].get("duration", 0))
    if (
        not 0 < duration <= settings.MAX_VIDEO_SECONDS + 1
        or abs(duration - original) > max(2, original * 0.005)
        or destination.stat().st_size >= settings.MAX_VIDEO_BYTES
        or any(s["codec_type"] != "audio" or s["codec_name"] != "aac" for s in actual["streams"])
    ):
        raise ValueError("Audio verification failed")
    return destination
