"""Isolated child process. Never import Django settings or pass secrets into this process."""

import argparse
import json
import sys
import time
from pathlib import Path

from library.network import install_network_guard

FORMAT_SELECTOR = "bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]/b/bv*"


def emit(event, **values):
    print(json.dumps({"event": event, **values}, ensure_ascii=False), flush=True)


def download(url, output_dir, max_bytes, max_seconds):
    install_network_guard()
    import yt_dlp

    last_report = 0.0

    def hook(info):
        nonlocal last_report
        if info.get("downloaded_bytes", 0) > max_bytes:
            raise yt_dlp.utils.DownloadError("ARCHIVE_LIMIT_SIZE")
        if time.monotonic() - last_report > 1:
            total = info.get("total_bytes") or info.get("total_bytes_estimate") or 0
            progress = min(88, int(88 * info.get("downloaded_bytes", 0) / total)) if total else 0
            emit("progress", progress=progress)
            last_report = time.monotonic()

    def match_filter(info, *, incomplete=False):
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            return "ARCHIVE_LIMIT_LIVE"
        duration = info.get("duration")
        if duration and duration > max_seconds:
            return "ARCHIVE_LIMIT_DURATION"
        # Instagram's public fallback can omit duration. Download remains size/time bounded;
        # ffprobe must establish and enforce duration before the worker publishes anything.
        return None

    class QuietLogger:
        def debug(self, message):
            pass

        def warning(self, message):
            pass

        def error(self, message):
            pass

    options = {
        "paths": {"home": str(output_dir)},
        "outtmpl": "source.%(ext)s",
        # Some Instagram posts only expose a portrait/high-resolution (or unknown-height)
        # source. The worker enforces the 720px output cap after decoding it.
        "format": FORMAT_SELECTOR,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "max_filesize": max_bytes,
        "match_filter": match_filter,
        "progress_hooks": [hook],
        "logger": QuietLogger(),
        "socket_timeout": 20,
        "retries": 1,
        "fragment_retries": 1,
        "concurrent_fragment_downloads": 1,
        "continuedl": False,
        "hls_prefer_native": True,
        "fixup": "never",
        "quiet": True,
        "overwrites": True,
        "cachedir": False,
        "restrictfilenames": True,
        "js_runtimes": {"node": {}},
        "remote_components": set(),
        "proxy": "",
        "usenetrc": False,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        # Reject collections before downloading any entries (including Instagram carousels).
        info = ydl.extract_info(url, download=False)
        if not info or info.get("_type") in {"playlist", "multi_video"} or "entries" in info:
            raise ValueError("ARCHIVE_LIMIT_COLLECTION")
        reason = match_filter(info)
        if reason:
            raise ValueError(reason)
        ydl.process_ie_result(info, download=True)
        files = [
            p
            for p in Path(output_dir).glob("source.*")
            if p.suffix in {".mp4", ".mkv", ".webm", ".mov"} and ".f" not in p.stem
        ]
        if len(files) != 1:
            raise ValueError("ARCHIVE_LIMIT_NO_FILE")
        emit(
            "complete",
            file=files[0].name,
            title=str(info.get("title") or "")[:300],
            duration=info.get("duration", 0),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("output_dir")
    parser.add_argument("--max-bytes", type=int, required=True)
    parser.add_argument("--max-seconds", type=int, required=True)
    args = parser.parse_args()
    try:
        download(args.url, args.output_dir, args.max_bytes, args.max_seconds)
    except Exception as exc:
        emit("error", message=str(exc)[-2000:])
        sys.exit(1)


if __name__ == "__main__":
    main()
