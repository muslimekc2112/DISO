"""✂ Only a part of a video: typed in the info window (start / end), remembered by the download, and
downloaded by yt-dlp as just that part (exact cuts, not the whole video first)."""
import time

import pytest

from app import jobs
from app import video_engine as ve
from app.models import Item
from app.utils import clip_text, parse_time


@pytest.mark.parametrize("text, seconds", [("1:30", 90), ("01:02:03", 3723), ("95", 95), ("1:30.5", 90.5),
                                           ("0,5", 0.5), ("  2:00 ", 120), ("", None)])
def test_a_typed_time(text, seconds):
    assert parse_time(text) == seconds


@pytest.mark.parametrize("text", ["abc", "1:75", "1:2:3:4", "-5", "1::2"])
def test_a_wrong_time(text):
    with pytest.raises(ValueError):
        parse_time(text)


def test_the_part_is_shown_and_remembered():
    assert clip_text([0, 9.5]) == "0:00–0:09" and clip_text([60, 3725]) == "1:00–1:02:05" and clip_text(None) == ""
    it = Item("https://www.youtube.com/watch?v=x", kind="video", title="Gülpembe", clip=(60, 150))
    assert it.display_name == "Gülpembe  ✂ 1:00–2:30"
    again = Item.from_dict(it.to_dict())
    assert again.clip == [60, 150] and Item.from_dict(Item("u").to_dict()).clip is None


def test_yt_dlp_is_told_to_fetch_only_the_part(tmp_path):
    it = Item("https://www.youtube.com/watch?v=x", kind="video", folder=str(tmp_path), clip=[30, 40.5])
    opts = ve.ydl_options(it)
    assert opts["force_keyframes_at_cuts"] is True
    assert list(opts["download_ranges"]({}, None)) == [{"start_time": 30.0, "end_time": 40.5}]
    assert opts["outtmpl"].endswith("%(title).150B [0.30–0.40].%(ext)s")              # no ':' in a file name
    whole = ve.ydl_options(Item("https://www.youtube.com/watch?v=x", kind="video", folder=str(tmp_path)))
    assert "download_ranges" not in whole and whole["outtmpl"].endswith("%(title).150B.%(ext)s")


def test_a_part_skips_the_fast_engine_and_the_subtitles(tmp_path, monkeypatch):
    fast = [{"url": "https://cdn/v.mp4", "protocol": "https", "ext": "mp4"}]
    monkeypatch.setattr(ve, "resolve", lambda *a, **k: {"title": "Video", "requested_formats": fast})
    monkeypatch.setattr(ve, "is_fast", lambda f: True)
    used = []
    monkeypatch.setattr(jobs, "_fast_media", lambda *a: used.append("fast") or "")
    monkeypatch.setattr(jobs, "_get_ffmpeg", lambda item, required: True)
    out = tmp_path / "Video [0.30–0.40].mp4"
    out.write_bytes(b"x")
    monkeypatch.setattr(ve, "ydl_download", lambda item: used.append(("yt-dlp", item.clip)) or str(out))
    monkeypatch.setattr(jobs, "save_subtitles", lambda *a: used.append("subtitles"))
    it = Item("https://www.youtube.com/watch?v=x", kind="video", folder=str(tmp_path), subs="Türkçe", clip=[30, 40])
    jobs.run_media(it)
    assert used == [("yt-dlp", [30, 40])] and it.final_path == str(out)           # the timings would be wrong


# ------------------------------------------------------------------------------ the info window
INFO = {"title": "A video", "uploader": "Someone", "duration": 185, "thumbnail": "",
        "qualities": [{"height": 720, "fps": 30, "codec": "avc1", "size": 60_000_000, "ext": "mp4"}],
        "audio_size": 3_000_000, "subtitles": [], "auto_subtitles": 0, "is_playlist": False, "entries": 0}


def open_info(app, monkeypatch, info=INFO):
    from app import ui
    monkeypatch.setattr(ui.ve, "fetch_info", lambda url, cookies=None: info)
    dialog = ui.InfoDialog(app, "https://www.youtube.com/watch?v=x")
    end = time.time() + 10
    while time.time() < end and not hasattr(dialog, "clip_start"):
        app.update()
        time.sleep(0.02)
    return dialog


def type_in(dialog, start, end):
    for entry, text in ((dialog.clip_start, start), (dialog.clip_end, end)):
        entry.delete(0, "end")
        entry.insert(0, text)
    dialog._show_clip()


@pytest.mark.gui
def test_empty_boxes_download_the_whole_video(app, monkeypatch):
    monkeypatch.setattr(app.manager, "start", lambda item: None)
    dialog = open_info(app, monkeypatch)
    assert dialog.clip() == (None, None) and "tamamı" in dialog.clip_note.cget("text")
    dialog._download("720p", "video")
    assert app.manager.items[-1].clip is None


@pytest.mark.gui
def test_the_buttons_download_only_the_typed_part(app, monkeypatch):
    monkeypatch.setattr(app.manager, "start", lambda item: None)
    dialog = open_info(app, monkeypatch)
    type_in(dialog, "1:00", "2:30")
    assert "1:00–2:30" in dialog.clip_note.cget("text") and "1:30" in dialog.clip_note.cget("text")
    dialog._download(None, "audio")
    it = app.manager.items[-1]
    assert it.clip == [60.0, 150.0] and it.kind == "audio" and "✂ 1:00–2:30" in app._notice
    dialog = open_info(app, monkeypatch)
    type_in(dialog, "2:00", "")                                    # no end: to the end of the video
    assert dialog.clip() == ([120.0, 185.0], None)
    dialog._download("720p", "video")
    assert app.manager.items[-1].clip == [120.0, 185.0] and len(app.manager.items) == 2   # a part is no duplicate


@pytest.mark.gui
@pytest.mark.parametrize("start, end, why", [("abc", "", "1:30"), ("2:00", "1:00", "sonra olmalı"),
                                             ("4:00", "", "sonundan sonra")])
def test_a_wrong_part_says_why_and_downloads_nothing(app, monkeypatch, start, end, why):
    monkeypatch.setattr(app.manager, "start", lambda item: None)
    dialog = open_info(app, monkeypatch)
    type_in(dialog, start, end)
    dialog._download("720p", "video")
    assert why in dialog.clip_note.cget("text") and dialog.winfo_exists() and app.manager.items == []
    dialog.destroy()


@pytest.mark.gui
def test_an_end_after_the_video_is_cut_to_its_length_and_unknown_length_needs_an_end(app, monkeypatch):
    dialog = open_info(app, monkeypatch)
    type_in(dialog, "0:10", "9:00")
    assert dialog.clip() == ([10.0, 185.0], None)
    dialog.destroy()
    dialog = open_info(app, monkeypatch, {**INFO, "duration": 0})
    type_in(dialog, "0:10", "")
    assert dialog.clip()[1] == "Bitişi de yaz (videonun uzunluğunu bilmiyorum)"
    dialog.destroy()
