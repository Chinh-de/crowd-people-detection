"""Bằng chứng cho sự kiện: ảnh tại thời điểm cảnh báo và clip vài giây trước/sau."""
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

from .domain import Alert
from .storage import Store

RING_WIDTH = 640


class FrameRing:
    """Bộ đệm vòng các frame gần nhất (đã thu nhỏ), lấy mẫu tối đa `fps_cap` frame/giây."""

    def __init__(self, seconds: float, fps_cap: float = 10.0):
        self.seconds, self.fps_cap = seconds, fps_cap
        self._frames: deque[tuple[float, np.ndarray]] = deque()
        self._lock = threading.Lock()

    def push(self, t: float, frame: np.ndarray) -> None:
        with self._lock:
            if self._frames and t - self._frames[-1][0] < 1.0 / self.fps_cap - 1e-6:
                return
            h = round(frame.shape[0] * RING_WIDTH / frame.shape[1])
            small = cv2.resize(frame, (RING_WIDTH, h - h % 2), interpolation=cv2.INTER_AREA)
            self._frames.append((t, small))
            while self._frames and self._frames[0][0] < t - self.seconds:
                self._frames.popleft()

    def snapshot(self, t0: float, t1: float) -> list[tuple[float, np.ndarray]]:
        with self._lock:
            return [(t, f) for t, f in self._frames if t0 <= t <= t1]

    def nearest(self, t: float) -> tuple[float, np.ndarray] | None:
        with self._lock:
            return min(self._frames, key=lambda tf: abs(tf[0] - t)) if self._frames else None


def save_snapshot(frame: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return path


def write_clip(frames: list[np.ndarray], fps: float, path: Path) -> Path:
    """Ghi MP4 H.264 (yuv420p) để trình duyệt phát được."""
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = frames[0].shape[:2]
    writer = imageio_ffmpeg.write_frames(str(path), (w, h), fps=fps, codec="libx264", pix_fmt_in="rgb24",
                                         pix_fmt_out="yuv420p", macro_block_size=2, quality=6)
    writer.send(None)
    for f in frames:
        writer.send(np.ascontiguousarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
    writer.close()
    return path


@dataclass
class _Pending:
    event_id: int
    t: float
    name: str


class EvidenceRecorder:
    """Ghi ảnh ngay khi cảnh báo, ghi clip [t − pre, t + post] khi đã đủ frame phía sau."""

    def __init__(self, ring: FrameRing, store: Store, out_dir: Path, pre_s: float, post_s: float,
                 url_prefix: str = ""):
        self.ring, self.store, self.out_dir = ring, store, out_dir
        self.pre_s, self.post_s, self.url_prefix = pre_s, post_s, url_prefix
        self._pending: list[_Pending] = []

    def on_alert(self, alert: Alert, frame: np.ndarray, source: str) -> int:
        name = f"{int(alert.t * 1000)}_{alert.rule}"
        save_snapshot(frame, self.out_dir / f"{name}.jpg")
        event_id = self.store.add_event(alert, source, f"{self.url_prefix}{name}.jpg")
        self._pending.append(_Pending(event_id, alert.t, name))
        return event_id

    def tick(self, now: float) -> None:
        due = [p for p in self._pending if now >= p.t + self.post_s]
        for p in due:
            frames = self.ring.snapshot(p.t - self.pre_s, p.t + self.post_s)
            if len(frames) >= 2:
                fps = (len(frames) - 1) / max(frames[-1][0] - frames[0][0], 1e-3)
                write_clip([f for _, f in frames], fps, self.out_dir / f"{p.name}.mp4")
                self.store.set_clip(p.event_id, f"{self.url_prefix}{p.name}.mp4")
            self._pending.remove(p)
