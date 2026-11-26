"""Đồng bộ lớp phủ với hình: phát video trễ một khoảng bằng thời gian phân tích.

Frame được giữ trong hàng đợi; khi tới lượt phát thì ghép với kết quả phân tích có thời điểm gần nó nhất.
Độ trễ tự bám theo tốc độ phân tích đo được, đổi từ từ để video không giật.
"""
import threading
from collections import deque

START_DELAY_S = 3.0      # chưa có kết quả nào thì chưa phát; có kết quả đầu tiên thì vào thẳng mức trễ cần
MAX_DELAY_S = 6.0        # máy quá chậm thì chấp nhận lệch thay vì trễ vô hạn (và tốn RAM)
MARGIN_S = 0.6           # dự phòng cho những lần phân tích chậm đột xuất
GROW_RATE = 0.15         # khi tăng độ trễ, video chậm đi tối đa 15%
SHRINK_RATE = 0.03       # khi giảm, video nhanh hơn tối đa 3% (mắt không thấy)
DEADBAND_S = 0.3         # chỉ giảm độ trễ khi dư hơn ngần này
HISTORY = 20             # độ trễ lấy theo lần phân tích chậm nhất trong ngần này lần gần nhất


class OverlaySync:
    def __init__(self):
        self.delay = START_DELAY_S
        self._target = START_DELAY_S
        self._wants: deque = deque(maxlen=HISTORY)
        self._last_t: float | None = None
        self._emitted = False
        self._frames: deque = deque()
        self._layers: deque = deque(maxlen=64)
        self._lock = threading.Lock()

    def add_layers(self, t: float, layers, newest_t: float, interval: float) -> None:
        """Gọi khi phân tích xong frame thời điểm `t`; `newest_t` là frame mới nhất đã đọc lúc đó."""
        want = min(max(newest_t - t, 0.0) + interval + MARGIN_S, MAX_DELAY_S)
        with self._lock:
            self._layers.append((t, layers))
            self._wants.append(want)
            self._target = max(self._wants)
            if not self._emitted:      # chưa phát frame nào: đổi độ trễ ngay, người xem không thấy giật
                self.delay = self._target

    def push(self, t: float, frame):
        """Nhận frame mới đọc; trả (frame cần phát, lớp phủ khớp nó) hoặc None nếu chưa tới lượt."""
        with self._lock:
            dt = 0.0 if self._last_t is None else min(max(t - self._last_t, 0.0), 0.5)
            self._last_t = t
            step = self._target - self.delay
            if step > 0:
                self.delay += min(step, GROW_RATE * dt)
            elif step < -DEADBAND_S:
                self.delay -= min(-step - DEADBAND_S, SHRINK_RATE * dt)
            self._frames.append((t, frame))
            due = None
            while self._frames and self._frames[0][0] <= t - self.delay + 1e-6:
                due = self._frames.popleft()
            if due is None:
                return None
            self._emitted = True
            layers = min(self._layers, key=lambda tl: abs(tl[0] - due[0]))[1] if self._layers else None
            return due[1], layers
