#!/usr/bin/env python3
# ruff: noqa: E402
"""Run on the target server with a text file containing ten real public source URLs.

Uses a separate DATA_DIR and the real downloader. Never touches the personal library.
Produces a JSON report, including login/blocked errors, without claiming support on failure.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("links_file")
parser.add_argument("--data-dir", required=True)
parser.add_argument("--report", required=True)
args = parser.parse_args()
if os.environ.get("DATABASE_URL") or os.environ.get("MEDIA_BACKEND", "local") != "local":
    raise SystemExit(
        "This isolated smoke test requires local storage and no DATABASE_URL. "
        "Use a separate cloud test database and bucket for cloud acceptance tests."
    )
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
directory = Path(args.data_dir).resolve()
if directory.exists():
    raise SystemExit("Use a NEW isolated data directory for the smoke test.")
os.environ["DATA_DIR"] = str(directory)
os.environ.setdefault("DJANGO_DEBUG", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from library.models import Mood, Video
from library.validation import canonical_source
from library.worker import work

links = [
    line.strip()
    for line in Path(args.links_file).read_text().splitlines()
    if line.strip() and not line.startswith("#")
]
sources = [canonical_source(link) for link in links]
if len(set(s[1] for s in sources)) != 10 or {s[0] for s in sources} != {"youtube", "instagram"}:
    raise SystemExit("Supply exactly ten distinct public video URLs, covering both platforms.")
call_command("migrate", verbosity=0)
user = get_user_model().objects.create_user("smoke-test")
rows = []
for platform, key, url in sources:
    video = Video.objects.create(owner=user, platform=platform, source_key=key, source_url=url)
    video.moods.add(Mood.objects.first())
    while video.status == Video.Status.QUEUED:
        delay = (video.next_attempt_at - timezone.now()).total_seconds()
        if delay > 0:
            time.sleep(delay)
        work(once=True)
        video.refresh_from_db()
    rows.append(
        {
            "source": url,
            "status": video.status,
            "error_code": video.error_code,
            "error": video.error,
            "duration": video.duration,
            "bytes": video.size_bytes,
            "attempts": video.attempts,
        }
    )
    print(platform, video.status, video.error_code, flush=True)
passed = all(row["status"] == "ready" for row in rows)
Path(args.report).write_text(
    json.dumps({"all_passed": passed, "videos": rows}, ensure_ascii=False, indent=2)
)
sys.exit(0 if passed else 1)
