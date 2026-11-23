"""Luật phát hiện bất thường trên chuỗi số đếm và đặc trưng chuyển động.

- Mật độ: quá đông, vượt sức chứa từng vùng, ô quá dày, tăng đột ngột.
- Chuyển động: "bất thường chuyển động" dùng điểm của mô hình giai đoạn 2 đang chọn (anomaly.py);
  ngược chiều dùng tỉ lệ chuyển động ngược hướng chính.

Ngưỡng = mức nền (trung vị) + k × độ lệch bền (1,4826 × MAD), có ngưỡng sàn để cảnh vắng/đứng yên
không làm ngưỡng sát mức hiện tại. Mức nền học lúc đầu, sau đó cập nhật theo cửa sổ trượt.
Một luật phải đúng liên tục `persist_s` giây mới cảnh báo; mỗi đợt báo một lần, và giữa hai cảnh báo
cùng loại có thời gian nghỉ `cooldown_s`.
"""
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .anomaly import Reading
from .domain import RULE_NAMES, Alert, DensityStats, MotionStats

RULE_LABELS = {"overcrowd": "Quá đông", "zone_limit": "Vượt sức chứa vùng", "hot_cell": "Ô quá dày",
               "surge": "Tăng đột ngột", "panic": "Bất thường chuyển động", "counterflow": "Ngược chiều"}


@dataclass
class RuleConfig:
    k_sigma: float = 3.0              # quá đông: số độ lệch trên mức nền
    persist_s: float = 6.0            # phải đúng liên tục ngần này giây
    cooldown_s: float = 60.0          # nghỉ giữa hai cảnh báo cùng loại
    smooth: int = 3                   # làm mượt số đếm (trung vị n mẫu)
    count_margin_abs: float = 5.0     # quá đông: vượt mức nền ít nhất ngần này người...
    count_margin_rel: float = 0.3     # ...và ít nhất ngần này phần mức nền
    surge_window_s: float = 60.0
    surge_abs: float = 10.0
    surge_rel: float = 0.5
    cell_factor: float = 1.3
    min_cell_limit: float = 4.0
    panic_persist_s: float = 2.0      # hoảng loạn diễn ra nhanh (vài giây trên UMN): duy trì ngắn hơn các luật khác
    counterflow_k: float = 4.0
    min_counterflow: float = 0.3      # ngược chiều: ít nhất 30% chuyển động mới tính
    baseline_window_s: float = 900.0  # mức nền cập nhật theo 15 phút gần nhất
    count_limit: float | None = None  # sức chứa tuyệt đối do người vận hành đặt
    enabled: dict[str, bool] = field(default_factory=lambda: {r: True for r in RULE_NAMES})


REBASELINE_S = 30.0   # tính lại mức nền mỗi ngần này giây


def _robust(values) -> tuple[float, float]:
    v = np.asarray(values, float)
    med = float(np.median(v))
    return med, float(1.4826 * np.median(np.abs(v - med)))


class RuleEngine:
    def __init__(self, config: RuleConfig):
        self.config = config
        self._calib: list[tuple[float, ...]] | None = None
        self._need = 0
        self._base: dict | None = None
        self._recent: deque[tuple[float, tuple[float, ...]]] = deque()   # (t, mẫu) cho mức nền trượt
        self._rebased_at = 0.0
        self._roi = deque(maxlen=max(1, config.smooth))
        self._cell = deque(maxlen=max(1, config.smooth))
        self._history: deque[tuple[float, float]] = deque()
        self._since: dict[str, float | None] = {r: None for r in RULE_NAMES}   # luật đúng liên tục từ lúc nào
        self._reported = {r: False for r in RULE_NAMES}                      # đợt hiện tại đã báo chưa
        self._last_alert = {r: -np.inf for r in RULE_NAMES}
        self._t = 0.0
        self._panic_limit: float | None = None

    # ---------- học mức bình thường ----------
    def start_calibration(self, seconds: float, now: float, rate_hz: float) -> None:
        self._need = max(10, int(round(seconds * rate_hz)))
        self._calib = []
        self._recent.clear()

    def calibration_progress(self) -> tuple[int, int]:
        if self._calib is None:
            return (self._need, self._need) if self._base else (0, 0)
        return len(self._calib), self._need

    @property
    def learning(self) -> bool:
        return self._calib is not None

    @property
    def calibrated(self) -> bool:
        return self._base is not None

    @property
    def cell_limit(self) -> float | None:
        return None if self._base is None else self._base["cell_limit"]

    def _persist(self, rule: str) -> float:
        return self.config.panic_persist_s if rule == "panic" else self.config.persist_s

    def active(self) -> list[str]:
        """Các luật đang trong đợt cảnh báo (đã đúng liên tục đủ thời gian duy trì)."""
        return [r for r, s in self._since.items() if s is not None and self._t - s >= self._persist(r) - 1e-9]

    def thresholds(self) -> dict:
        c, b = self.config, self._base
        out = {"count_limit": c.count_limit, "overcrowd": None, "hot_cell": None,
               "panic_score": self._panic_limit, "counterflow": None}
        if b:
            out.update(overcrowd=b["count_limit"], hot_cell=b["cell_limit"], counterflow=b["counter_limit"])
        return out

    def _compute_base(self, samples) -> dict:
        c = self.config
        roi, cell, counter = (np.array(col) for col in zip(*samples))
        med, mad = _robust(roi)
        k_med, k_mad = _robust(counter)
        return {
            "count_limit": med + max(c.k_sigma * mad, c.count_margin_rel * med, c.count_margin_abs),
            "cell_limit": max(c.min_cell_limit, c.cell_factor * float(np.quantile(cell, 0.95))),
            "counter_limit": max(c.min_counterflow, k_med + c.counterflow_k * max(k_mad, 0.05)),
        }

    # ---------- cập nhật mỗi lần phân tích ----------
    def update(self, t: float, d: DensityStats, m: MotionStats, a: Reading | None = None) -> list[Alert]:
        c = self.config
        self._t = t
        self._roi.append(d.roi)
        self._cell.append(d.max_cell)
        roi = float(np.median(self._roi))
        cell = float(np.median(self._cell))
        self._history.append((t, roi))
        while self._history and self._history[0][0] < t - c.surge_window_s:
            self._history.popleft()

        sample = (d.roi, d.max_cell, m.counterflow)
        self._recent.append((t, sample))
        while self._recent and self._recent[0][0] < t - c.baseline_window_s:
            self._recent.popleft()

        learning = self._calib is not None
        if learning:
            self._calib.append(sample)
            if len(self._calib) >= self._need:
                self._base = self._compute_base(self._calib)
                self._calib, self._rebased_at = None, t
        elif self._base and t - self._rebased_at >= REBASELINE_S and len(self._recent) >= self._need:
            self._base = self._compute_base([s for _, s in self._recent])
            self._rebased_at = t

        # Đang học: chỉ áp ngưỡng sức chứa do người dùng đặt; các luật thống kê chờ học xong
        checks = self._evaluate(t, roi, cell, m, statistical=not learning)
        checks.update(self._zone_checks(d))
        if a is not None:
            self._panic_limit = a.limit
            # Không chặn theo "có người đang chuyển động": khi hoảng loạn, người chạy khỏi khung hình nên mask gần như
            # trống đúng lúc cần báo (thấy trên UMN). Số người giảm mạnh là một phần tín hiệu của mô hình.
            checks["panic"] = (a.score > a.limit, a.score, a.limit,
                               f"điểm bất thường {a.score:.3g} (ngưỡng {a.limit:.3g})")
        alerts = []
        for rule in RULE_NAMES:
            fired, value, limit, text = checks.get(rule, (False, 0.0, 0.0, ""))
            if not (fired and c.enabled.get(rule, True)):
                self._since[rule], self._reported[rule] = None, False
                continue
            if self._since[rule] is None:
                self._since[rule] = t
            if (not self._reported[rule] and t - self._since[rule] >= self._persist(rule) - 1e-9
                    and t - self._last_alert[rule] >= c.cooldown_s):
                self._reported[rule], self._last_alert[rule] = True, t
                alerts.append(Alert(rule, t, float(value), float(limit), f"{RULE_LABELS[rule]}: {text}"))
        return alerts

    def _evaluate(self, t: float, roi: float, cell: float, m: MotionStats, statistical: bool = True) -> dict:
        c = self.config
        b = self._base if statistical else None
        out = {}
        limit = c.count_limit if b is None else (
            b["count_limit"] if c.count_limit is None else min(b["count_limit"], c.count_limit))
        if limit is not None:
            out["overcrowd"] = (roi > limit, roi, limit, f"{roi:.0f} người (ngưỡng {limit:.0f})")
        if b is None:
            return out

        out["hot_cell"] = (cell > b["cell_limit"], cell, b["cell_limit"],
                           f"ô đông nhất {cell:.1f} người (ngưỡng {b['cell_limit']:.1f})")

        past = [v for ts, v in self._history if t - c.surge_window_s <= ts <= t - c.surge_window_s / 3]
        if past:
            ref = float(np.median(past))
            need = max(c.surge_abs, c.surge_rel * ref)
            out["surge"] = (roi - ref > need, roi - ref, need,
                            f"tăng {roi - ref:+.0f} người trong {c.surge_window_s:.0f} s (ngưỡng +{need:.0f})")

        moving = m.active_ratio > 0.02
        out["counterflow"] = (moving and m.counterflow > b["counter_limit"], m.counterflow, b["counter_limit"],
                              f"{m.counterflow:.0%} chuyển động ngược chiều (ngưỡng {b['counter_limit']:.0%})")
        return out

    @staticmethod
    def _zone_checks(d: DensityStats) -> dict:
        """Sức chứa từng vùng do người vận hành đặt: áp dụng ngay, không cần học mức bình thường."""
        limited = [z for z in d.zones if z.limit is not None]
        if not limited:
            return {}
        over = [z for z in limited if z.count > z.limit]
        worst = max(limited, key=lambda z: z.count - z.limit)
        text = ", ".join(f"{z.name} {z.count:.0f}/{z.limit:.0f} người" for z in over) or "trong giới hạn"
        return {"zone_limit": (bool(over), worst.count, worst.limit, text)}
