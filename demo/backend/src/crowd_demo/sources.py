"""Nguồn video: file có sẵn (phát đúng FPS gốc, lặp lại) và livestream YouTube."""
import threading
import time
from collections import deque
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
        self._next_due: float | None = None    # đặt ở lần đọc đầu, để lúc mới mở không bị tính là trễ

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
        if self._next_due is None:
            self._next_due = time.monotonic()
        delay = self._next_due - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        with self._lock:
            # đọc không kịp FPS gốc: bỏ frame quá hạn (tối đa 1 giây) để video vẫn đúng tốc độ, không chậm rồi chạy dồn
            late = min(int((time.monotonic() - self._next_due) * self.fps), int(self.fps))
            skipped = 0
            while skipped < late and self._cap.grab():
                skipped += 1
            self._frame_idx += skipped
            self._next_due = max(self._next_due + (skipped + 1) / self.fps, time.monotonic() - 1 / self.fps)
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
    """Livestream HLS. Frame đến theo từng đợt (mỗi đoạn HLS vài giây), nên một luồng riêng giải mã frame vào
    bộ đệm, còn read() phát frame đều nhịp FPS với độ trễ cố định BUFFER_S (jitter buffer). Nếu bộ đệm cạn
    (mạng chậm) thì chờ đệm lại rồi đồng bộ nhịp phát; mất kết nối thì tự kết nối lại."""

    live = True
    MAX_RECONNECT = 5
    BUFFER_S = 3.0           # độ trễ phát so với lúc nhận, đủ che khoảng trống giữa hai đoạn HLS
    MAX_BUFFER_S = 15.0      # đệm quá dài (máy xử lý chậm) thì bỏ frame cũ nhất

    def __init__(self, url: str, tz: str):
        self.url, self.tz = url, tz
        stream, self.label = youtube_stream_url(url)
        self._cap = self._open(stream)
        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if 1 <= fps <= 120 else 30.0
        self.size = (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        self._buf: deque[np.ndarray] = deque(maxlen=max(1, int(self.MAX_BUFFER_S * self.fps)))
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._error: str | None = None
        self._t0: float | None = None     # mốc phát frame số 0 của nhịp hiện tại
        self._n = 0
        self._pump = threading.Thread(target=self._pump_loop, name="hls-pump", daemon=True)
        self._pump.start()

    @staticmethod
    def _open(stream: str) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(stream)
        if not cap.isOpened():
            raise SourceError("Không mở được luồng livestream.")
        return cap

    def _pump_loop(self) -> None:
        """Giải mã liên tục vào bộ đệm; tự kết nối lại khi mất luồng."""
        fails = 0
        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if ok:
                fails = 0
                with self._cond:
                    self._buf.append(frame)
                    self._cond.notify_all()
                continue
            fails += 1
            if fails > self.MAX_RECONNECT:
                with self._cond:
                    self._error = f"Mất kết nối livestream sau {self.MAX_RECONNECT} lần thử lại."
                    self._cond.notify_all()
                return
            self._cap.release()
            if self._stop.wait(2):
                return
            try:
                self._cap = self._open(youtube_stream_url(self.url)[0])
            except SourceError:
                continue

    def _wait_for(self, n_frames: int) -> bool:
        """Chờ tới khi bộ đệm có ít nhất n_frames frame; False nếu bị dừng hoặc luồng đã hỏng."""
        with self._cond:
            while len(self._buf) < n_frames:
                if self._stop.is_set():
                    return False
                if self._error:
                    if self._buf:
                        return True
                    raise SourceError(self._error)
                self._cond.wait(0.2)
        return True

    def read(self) -> tuple[float, np.ndarray] | None:
        if self._t0 is None or not self._buf:
            # Lúc bắt đầu hoặc khi đệm cạn: đệm lại BUFFER_S rồi bắt đầu nhịp phát mới
            if not self._wait_for(max(1, int(self.BUFFER_S * self.fps))):
                return None
            self._t0, self._n = time.time(), 0
        due = int((time.time() - self._t0) * self.fps)   # frame lẽ ra đang được phát lúc này
        skip = max(0, due - self._n)                    # người đọc (vẽ, nén) chậm hơn FPS: bỏ frame quá hạn
        t = self._t0 + (self._n + skip) / self.fps
        delay = t - time.time()
        if delay > 0 and self._stop.wait(delay):
            return None
        with self._cond:
            skip = min(skip, len(self._buf) - 1)
            if skip < 0:
                return None              # đệm cạn đúng lúc phát: lần read() sau sẽ đệm lại
            for _ in range(skip):
                self._buf.popleft()
            self._n += skip
            t = self._t0 + self._n / self.fps    # đệm ít hơn số frame cần bỏ thì mốc lùi lại tương ứng
            frame = self._buf.popleft()
        self._n += 1
        return t, frame

    def interrupt(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()

    def close(self) -> None:
        self.interrupt()
        self._pump.join(timeout=5)
        self._cap.release()


def open_source(spec: dict) -> VideoSource:
    tz = spec.get("tz") or "UTC"
    if spec.get("kind") == "file":
        return FileSource(spec["path"], tz)
    if spec.get("kind") == "youtube":
        return YouTubeSource(spec["url"], tz)
    raise SourceError("Loại nguồn không hợp lệ.")
