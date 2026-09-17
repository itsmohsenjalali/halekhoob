"""Optional operator-supplied YouTube session, isolated from archive files."""

import tempfile
import warnings
from contextlib import contextmanager
from http.cookiejar import LoadError, MozillaCookieJar
from pathlib import Path
from urllib.parse import urlsplit


@contextmanager
def youtube_cookie_file(url, source):
    host = (urlsplit(url).hostname or "").lower()
    if not source or host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        yield None
        return

    # Never load other sites' cookies, or let yt-dlp rewrite the mounted secret.
    try:
        with Path(source).open(encoding="utf-8") as stream:
            contents = stream.read(1_048_577)
        if len(contents) > 1_048_576 or not contents.startswith("# Netscape HTTP Cookie File"):
            raise ValueError
        rows = ["# Netscape HTTP Cookie File"]
        for line in contents.splitlines():
            if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
                continue
            fields = line.split("\t")
            if len(fields) != 7:
                raise ValueError
            domain = fields[0].removeprefix("#HttpOnly_").lower().lstrip(".")
            if domain != "youtube.com" and not domain.endswith(".youtube.com"):
                continue
            if fields[1] not in {"TRUE", "FALSE"} or fields[3] not in {"TRUE", "FALSE"}:
                raise ValueError
            if not fields[4].isdigit() or not fields[2].startswith("/") or not fields[5]:
                raise ValueError
            rows.append(line)
        if len(rows) == 1:
            raise ValueError
    except (OSError, UnicodeError, ValueError):
        # Cookie parser errors can contain credentials; expose only this fixed marker.
        raise ValueError("ARCHIVE_YOUTUBE_SESSION_INVALID") from None

    with tempfile.TemporaryDirectory(prefix="halekhoob-youtube-session-") as directory:
        target = Path(directory) / "cookies.txt"
        target.touch(mode=0o600)
        target.write_text("\n".join(rows) + "\n", encoding="utf-8")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                MozillaCookieJar().load(str(target), ignore_discard=True, ignore_expires=True)
        except (LoadError, OSError, ValueError):
            raise ValueError("ARCHIVE_YOUTUBE_SESSION_INVALID") from None
        yield str(target)


def check_public_video(info):
    # A shared operator session must not give users access to its private/paid videos.
    if info.get("availability") not in {"public", "unlisted"} or (info.get("age_limit") or 0) >= 18:
        raise ValueError("ARCHIVE_LIMIT_AUTHENTICATED_CONTENT")
