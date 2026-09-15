import re
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ValidationError


def canonical_source(value):
    """Accept only individual public-platform URLs, never generic extractor inputs."""
    try:
        url = urlsplit(value.strip())
        if url.scheme != "https" or url.username or url.password or url.port not in (None, 443):
            raise ValueError
        host = (url.hostname or "").lower()
        query = parse_qs(url.query)
        if "list" in query:
            raise ValidationError("لینک پلی‌لیست پشتیبانی نمی‌شود؛ لینک خود ویدیو را وارد کن.")
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
            if host == "youtu.be":
                key = url.path.strip("/")
            elif url.path == "/watch":
                key = query.get("v", [""])[0]
            else:
                match = re.fullmatch(r"/(?:shorts|embed)/([\w-]{11})/?", url.path)
                key = match[1] if match else ""
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", key):
                raise ValueError
            return "youtube", f"youtube:{key}", f"https://www.youtube.com/watch?v={key}"
        if host in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
            match = re.fullmatch(r"/(?:reel|reels|p)/([A-Za-z0-9_-]{5,80})/?", url.path)
            if match:
                key = match[1]
                return "instagram", f"instagram:{key}", f"https://www.instagram.com/p/{key}/"
        raise ValueError
    except (ValueError, TypeError):
        raise ValidationError(
            "یک لینک HTTPS از ویدیو یا Shorts یوتیوب، پست یا Reel اینستاگرام وارد کن."
        ) from None
