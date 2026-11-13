import time

import pytest

from crowd_demo import sources
from crowd_demo.sources import FileSource, SourceError, YouTubeSource, open_source


def test_file_source_paced_at_native_fps(sample_video):
    s = FileSource(sample_video, "UTC")
    s.read()
    t0 = time.monotonic()
    for _ in range(10):
        s.read()
    assert 0.8 <= time.monotonic() - t0 <= 1.4
    s.close()


def test_file_source_loops(sample_video):
    s = FileSource(sample_video, "UTC")
    ts = []
    for _ in range(40):
        s._next_due = 0                               # bỏ nhịp chờ cho test nhanh
        ts.append(s.read()[0])
    assert all(b > a for a, b in zip(ts, ts[1:]))
    s.close()


def test_seek_and_pause(sample_video):
    s = FileSource(sample_video, "UTC")
    s.seek(2.0)
    assert s.position_s == pytest.approx(2.0)
    s.pause()
    assert s.paused
    s.resume()
    s.read()
    assert s.position_s == pytest.approx(2.1)
    s.close()


def test_seek_backward_keeps_time_increasing(sample_video):
    s = FileSource(sample_video, "UTC")
    ts = []
    for _ in range(25):
        s._next_due = 0
        ts.append(s.read()[0])
    s.seek(0.5)
    s._next_due = 0
    assert s.read()[0] > ts[-1]
    s.close()


def test_file_source_reads_webm(sample_webm):
    s = open_source({"kind": "file", "path": str(sample_webm), "tz": "UTC"})
    n = 0
    for _ in range(25):
        s._next_due = 0
        _, f = s.read()
        n += f is not None
    assert n == 25 and s.size == (320, 240)
    s.close()


def test_unsupported_extension_rejected(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("x")
    with pytest.raises(SourceError):
        FileSource(p, "UTC")


def test_live_source_timestamps_follow_video_clock(monkeypatch, sample_video):
    """Luồng HLS trả frame theo đợt; mốc thời gian phải đều theo FPS và frame được phát đều nhịp."""
    monkeypatch.setattr(sources, "youtube_stream_url", lambda url, max_height=1080: (str(sample_video), "test"))
    s = YouTubeSource("https://youtube.test/live", "UTC")     # file cục bộ đọc tức thì = một đợt frame
    start = time.monotonic()
    ts = [s.read()[0] for _ in range(11)]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    assert all(g == pytest.approx(1 / s.fps, abs=1e-6) for g in gaps)
    assert time.monotonic() - start >= 0.9
    s.close()


def test_youtube_source_reports_error_on_bad_url(monkeypatch):
    def boom(url, max_height=1080):
        raise SourceError("Không lấy được luồng YouTube: link sai")
    monkeypatch.setattr(sources, "youtube_stream_url", boom)
    with pytest.raises(SourceError, match="YouTube"):
        YouTubeSource("https://www.youtube.com/watch?v=invalid", "UTC")
