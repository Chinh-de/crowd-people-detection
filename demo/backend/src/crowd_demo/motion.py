"""Chuyển động của đám đông bằng optical flow Farneback (OpenCV, không cần model)."""
import cv2
import numpy as np

from .domain import MotionStats

N_BINS = 16              # số ngăn hướng (la bàn 16 hướng) để tính entropy
COUNTER_ANGLE = 120.0    # lệch hơn góc này so với hướng đang xét = ngược chiều
MIN_MOVING_PX = 40       # vùng có ít điểm ảnh flow chuyển động hơn mức này thì không kết luận (nhiễu)


def compute_flow(prev_bgr: np.ndarray, cur_bgr: np.ndarray, width: int) -> np.ndarray:
    """Trường vector (h, w, 2) giữa hai frame, tính trên ảnh xám thu nhỏ về `width`."""
    h = round(prev_bgr.shape[0] * width / prev_bgr.shape[1])
    a = cv2.cvtColor(cv2.resize(prev_bgr, (width, h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(cv2.resize(cur_bgr, (width, h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    return cv2.calcOpticalFlowFarneback(a, b, None, pyr_scale=0.5, levels=3, winsize=15,
                                        iterations=3, poly_n=5, poly_sigma=1.2, flags=0)


def flow_features(flow: np.ndarray, valid: np.ndarray | None, dt: float, min_mag: float = 0.5) -> MotionStats:
    """Đặc trưng chuyển động trên các điểm hợp lệ (có người, trong vùng giám sát) đang di chuyển."""
    dx, dy = flow[..., 0], flow[..., 1]
    mag = np.hypot(dx, dy)
    valid = np.ones(mag.shape, bool) if valid is None else valid
    moving = valid & (mag >= min_mag)
    n_valid = int(valid.sum())
    if not moving.any():
        return MotionStats()

    m, vx, vy = mag[moving], dx[moving], dy[moving]
    main = np.arctan2(vy.sum(), vx.sum())                         # hướng của tổng vector
    angles = np.arctan2(vy, vx)

    hist, _ = np.histogram(angles, bins=N_BINS, range=(-np.pi, np.pi), weights=m)
    p = hist / hist.sum()
    p = p[p > 0]
    entropy = float(-(p * np.log(p)).sum() / np.log(N_BINS))

    diff = np.degrees(np.abs(np.angle(np.exp(1j * (angles - main)))))
    counterflow = float(m[diff > COUNTER_ANGLE].sum() / m.sum())

    return MotionStats(speed=float(m.mean() / max(dt, 1e-6)), direction_deg=float(np.degrees(main)),
                       entropy=entropy, counterflow=counterflow,
                       active_ratio=float(moving.sum() / max(n_valid, 1)))


def wrong_way(flow: np.ndarray, area: np.ndarray, allowed_deg: float,
              min_mag: float = 0.5) -> tuple[float | None, np.ndarray]:
    """Phần chuyển động (theo độ lớn) trong `area` đi ngược chiều cho phép, và mask các điểm đi ngược.

    `allowed_deg`: 0 = sang phải, 90 = xuống dưới (trục ảnh). Trả None nếu quá ít chuyển động để xét.
    """
    dx, dy = flow[..., 0], flow[..., 1]
    mag = np.hypot(dx, dy)
    moving = area & (mag >= min_mag)
    if moving.sum() < MIN_MOVING_PX:
        return None, np.zeros(area.shape, bool)
    diff = np.abs(np.angle(np.exp(1j * (np.arctan2(dy, dx) - np.radians(allowed_deg)))))
    wrong = moving & (diff > np.radians(COUNTER_ANGLE))
    return float(mag[wrong].sum() / mag[moving].sum()), wrong
