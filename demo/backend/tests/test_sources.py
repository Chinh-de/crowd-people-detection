import time

import numpy as np
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


class _BurstCap:
    """Giả lập HLS: mỗi đoạn trả 10 frame tức thì rồi chờ tải đoạn tiếp theo (tốc độ trung bình đúng FPS)."""

    def __init__(self, fps=20.0, burst=10):
        self.fps, self.burst, self.i = fps, burst, 0

    def isOpened(self):
        return True

    def get(self, prop):
        import cv2
        return {cv2.CAP_PROP_FPS: self.fps, cv2.CAP_PROP_FRAME_WIDTH: 64, cv2.CAP_PROP_FRAME_HEIGHT: 48}.get(prop, 0)

    def read(self):
        if self.i and self.i % self.burst == 0:
            time.sleep(self.burst / self.fps)
        self.i += 1
        return True, np.zeros((48, 64, 3), np.uint8)

    def release(self):
        pass


def test_live_source_smooths_bursty_hls(monkeypatch):
    """Frame về theo đợt (mỗi đoạn HLS) nhưng phải được phát đều, không đứng hình giữa hai đoạn."""
    monkeypatch.setattr(sources, "youtube_stream_url", lambda url, max_height=1080: ("fake", "test"))
    monkeypatch.setattr(YouTubeSource, "_open", staticmethod(lambda stream: _BurstCap()))
    monkeypatch.setattr(YouTubeSource, "BUFFER_S", 1.0, raising=False)
    s = YouTubeSource("https://youtube.test/live", "UTC")
    s.read()                                                   # chờ đệm đầy
    stamps = []
    for _ in range(40):                                        # 2 giây = 4 đoạn HLS
        s.read()
        stamps.append(time.monotonic())
    gaps = np.diff(stamps)
    s.close()
    assert gaps.max() < 0.12, f"đứng hình {gaps.max():.2f}s"


def test_live_source_drops_frames_when_consumer_is_slow(monkeypatch):
    """Máy vẽ/nén chậm hơn FPS nguồn: bỏ frame để bám thời gian thật, không tụt dần lại phía sau."""
    monkeypatch.setattr(sources, "youtube_stream_url", lambda url, max_height=1080: ("fake", "test"))
    monkeypatch.setattr(YouTubeSource, "_open", staticmethod(lambda stream: _BurstCap()))
    monkeypatch.setattr(YouTubeSource, "BUFFER_S", 0.5)
    s = YouTubeSource("https://youtube.test/live", "UTC")
    s.read()
    for _ in range(15):                                        # đọc 10 lần/giây trong khi nguồn 20 fps
        t, _frame = s.read()
        time.sleep(0.1)
    lag = time.time() - t
    s.close()
    assert lag < 0.25, f"tụt lại {lag:.2f}s"
