"""Helpers and fixtures shared by the media tests (real ffmpeg, yt-dlp replaced by a stand-in)."""
import json
import os
import shutil
import subprocess

import pytest

from app import video_engine as ve
from app.models import Item
from app.utils import find_ffmpeg

FFMPEG = find_ffmpeg()
FFPROBE = shutil.which("ffprobe")


def needs_ffmpeg(test):
    """Marks a test 'ffmpeg' (so it can be deselected) and skips it when ffmpeg is missing."""
    test = pytest.mark.ffmpeg(test)
    return pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="ffmpeg/ffprobe not found")(test)


def ffmpeg(*args):
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *args], check=True,
                   stdin=subprocess.DEVNULL)


def probe_json(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name:stream_disposition=attached_pic:stream_tags=language"
                          ":format=bit_rate:format_tags=title,artist",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def streams_of(path):
    """({codec_type: codec_name}, {tag: value}, bit_rate) of a media file."""
    data = probe_json(path)
    return ({s["codec_type"]: s["codec_name"] for s in data["streams"]},
            {k.lower(): v for k, v in data.get("format", {}).get("tags", {}).items()},
            int(data["format"].get("bit_rate") or 0))


def has_attached_picture(path) -> bool:
    return any(s.get("disposition", {}).get("attached_pic") == 1 for s in probe_json(path)["streams"])


def fmt(url, ext, path, acodec="none", vcodec="none"):
    return {"url": url, "ext": ext, "protocol": "https", "filesize": os.path.getsize(path),
            "acodec": acodec, "vcodec": vcodec, "http_headers": {}, "_fast_headers": {}}


def new_item(url, kind, folder, **kw):
    it = Item(url, kind=kind, quality="En iyi", bitrate="192", connections=4, folder=folder)
    for k, v in kw.items():
        setattr(it, k, v)
    return it


@pytest.fixture(scope="session")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    names = ("v.mp4", "a.m4a", "o.webm", "x.mkv", "full.mp4", "cover.jpg", "cover.webp")
    v, a, o, mkv, full, jpg, webp = (str(d / n) for n in names)
    video = ["-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=15"]
    audio = ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    ffmpeg(*video, "-c:v", "libx264", "-pix_fmt", "yuv420p", v)
    ffmpeg(*audio, "-c:a", "aac", a)
    ffmpeg(*audio, "-c:a", "libopus", o)
    ffmpeg(*video, *audio, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", mkv)
    ffmpeg(*video, *audio, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", full)
    ffmpeg("-f", "lavfi", "-i", "color=c=red:s=320x240", "-frames:v", "1", jpg)
    try:
        ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=320x240", "-frames:v", "1", webp)
    except subprocess.CalledProcessError:  # this ffmpeg has no WebP encoder: reuse the JPEG
        shutil.copy(jpg, webp)
    return {"video": v, "audio": a, "opus": o, "mkv": mkv, "full": full, "jpg": jpg, "webp": webp}


@pytest.fixture
def served(server, media):
    return {k: server.add(open(p, "rb").read(), os.path.splitext(p)[1]) for k, p in media.items()}


@pytest.fixture
def stand_in(monkeypatch):
    """Make ve.resolve return a prepared info dict instead of asking yt-dlp."""
    box = {}
    monkeypatch.setattr(ve, "resolve", lambda url, kind, quality, cookies=None: box["info"])
    return box
