"""Nguồn video: file có sẵn (phát đúng FPS gốc, lặp lại) và livestream YouTube."""
import threading
import time
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from .config import VIDEO_EXTS


class SourceError(RuntimeError):
    """Lỗi mở hoặc đọc nguồn video; thông điệp hiển thị cho người dùng."""


class VideoSource(Protocol):
    fps: float
    size: tuple[int, int]
    label: str
    tz: str
    live: bool

    def read(self) -> tuple[float, np.ndarray] | None: ...
    def interrupt(self) -> None: ...   # yêu cầu read() đang chờ trả về ngay (gọi trước khi dừng luồng)
    def close(self) -> None: ...


class FileSource:
    live = False

    def __init__(self, path: str | Path, tz: str):
        self.path = Path(path)
        if self.path.suffix.lower() not in VIDEO_EXTS:
            raise SourceError(f"Định dạng {self.path.suffix} chưa được hỗ trợ.")
        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            raise SourceError(f"Không mở được video {self.path.name}.")
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if 1 <= fps <= 120 else 25.0
        self.size = (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        n = self._cap.get(cv2.CAP_PROP_FRAME_COUNT)
        self.duration_s = n / self.fps if n > 0 else 0.0
        self.label, self.tz = self.path.name, tz
        self._lock = threading.Lock()
        self._paused = False
        self._interrupted = False
        self._frame_idx = 0
        self._start = time.time()            # thời điểm ứng với frame 0 của vòng lặp đầu tiên
        self._played = 0.0                    # tổng thời gian video đã phát qua các vòng lặp
        self._next_due = time.monotonic()

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def position_s(self) -> float:
        return self._frame_idx / self.fps

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False
        self._next_due = time.monotonic()

    def seek(self, sec: float) -> None:
        with self._lock:
            sec = max(0.0, min(sec, max(self.duration_s - 1 / self.fps, 0.0)))
            # mốc thời gian tiếp tục tăng sau khi tua (như thời gian thực trôi), để chuỗi số liệu không bị đảo
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, int(sec * self.fps))
            self._played += self.position_s - int(sec * self.fps) / self.fps
            self._frame_idx = int(sec * self.fps)
            self._next_due = time.monotonic()

    def interrupt(self) -> None:
        self._interrupted = True

    def read(self) -> tuple[float, np.ndarray] | None:
        while self._paused and not self._interrupted:
            time.sleep(0.05)
        if self._interrupted:
            return None
        delay = self._next_due - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._next_due = max(self._next_due + 1 / self.fps, time.monotonic() - 1)
        with self._lock:
            ok, frame = self._cap.read()
            if not ok:                                   # hết video: phát lại từ đầu
                self._played += self.position_s
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._frame_idx = 0
                ok, frame = self._cap.read()
                if not ok:
                    raise SourceError(f"Không đọc được frame từ {self.label}.")
            t = self._start + self._played + self._frame_idx / self.fps
            self._frame_idx += 1
        return t, frame

    def close(self) -> None:
        with self._lock:
            self._cap.release()


def youtube_stream_url(url: str, max_height: int = 1080) -> tuple[str, str]:
    """(link HLS, tiêu đề) của luồng có hình cao nhất không quá max_height."""
    import yt_dlp

    def extract(verbose: bool) -> dict:
        opts = {"quiet": not verbose, "no_warnings": not verbose, "ignore_no_formats_error": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False, process=False)

    try:
        info = extract(False)
        fmts = [f for f in info.get("formats") or [] if f.get("url") and f.get("vcodec") not in (None, "none")]
        if not fmts:
            info = extract(True)
            fmts = [f for f in info.get("formats") or [] if f.get("url") and f.get("vcodec") not in (None, "none")]
    except Exception as e:  # yt-dlp ném nhiều loại lỗi khác nhau
        raise SourceError(f"Không lấy được luồng YouTube: {e}") from e
    if not fmts:
        raise SourceError("YouTube không trả luồng video nào: link sai, livestream đã kết thúc, hoặc bị chặn.")
    ok = [f for f in fmts if (f.get("height") or 0) <= max_height] or fmts
    best = max(ok, key=lambda f: ((f.get("height") or 0), "m3u8" in (f.get("protocol") or "")))
    return best["url"], info.get("title") or url


class YouTubeSource:
    """Livestream HLS. Frame đến theo từng đợt (mỗi đoạn HLS vài giây), nên mốc thời gian lấy theo
    nhịp video (n / fps) và frame được phát đều nhịp; nếu bị tụt lại quá xa (mạng chậm) thì đồng bộ lại."""

    live = True
    MAX_RECONNECT = 5
    MAX_LAG_S = 2.0

    def __init__(self, url: str, tz: str):
        self.url, self.tz = url, tz
        stream, self.label = youtube_stream_url(url)
        self._cap = self._open(stream)
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if 1 <= fps <= 120 else 30.0
        self.size = (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self._t0, self._n = time.time(), 0

    def _clock(self) -> float:
        """Mốc thời gian của frame vừa đọc, và chờ cho tới lúc phát frame đó."""
        t = self._t0 + self._n / self.fps
        self._n += 1
        now = time.time()
        if t > now:
            time.sleep(t - now)
        elif now - t > self.MAX_LAG_S:
            self._t0, self._n = now, 1
            t = now
        return t

    @staticmethod
    def _open(stream: str) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(stream)
        if not cap.isOpened():
            raise SourceError("Không mở được luồng livestream.")
        return cap

    def read(self) -> tuple[float, np.ndarray] | None:
        for attempt in range(self.MAX_RECONNECT + 1):
            ok, frame = self._cap.read()
            if ok:
                return self._clock(), frame
            if attempt == self.MAX_RECONNECT:
                break
            self._cap.release()
            time.sleep(2)
            try:
                self._cap = self._open(youtube_stream_url(self.url)[0])
            except SourceError:
                continue
        raise SourceError(f"Mất kết nối livestream sau {self.MAX_RECONNECT} lần thử lại.")

    def interrupt(self) -> None:
        """read() của livestream trả về sau tối đa một frame nên không cần làm gì thêm."""

    def close(self) -> None:
        self._cap.release()


def open_source(spec: dict) -> VideoSource:
    tz = spec.get("tz") or "UTC"
    if spec.get("kind") == "file":
        return FileSource(spec["path"], tz)
    if spec.get("kind") == "youtube":
        return YouTubeSource(spec["url"], tz)
    raise SourceError("Loại nguồn không hợp lệ.")
