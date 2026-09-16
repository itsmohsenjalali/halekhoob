import pytest
from yt_dlp import YoutubeDL

from library.downloader import FORMAT_SELECTOR


@pytest.mark.parametrize("height", [None, 1920, 720])
def test_instagram_portrait_or_unknown_resolution_can_be_downloaded(height):
    info = {
        "id": "test",
        "title": "test",
        "duration": 10,
        "formats": [
            {
                "format_id": "only",
                "url": "https://example.com/video.mp4",
                "ext": "mp4",
                "vcodec": "h264",
                "acodec": "aac",
                "height": height,
                "width": 1080,
            }
        ],
    }
    with YoutubeDL({"format": FORMAT_SELECTOR, "quiet": True, "skip_download": True}) as downloader:
        selected = downloader.process_ie_result(info, download=False)
    assert selected["format_id"] == "only"
