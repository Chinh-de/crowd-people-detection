"""Ba nhóm cảnh báo, mỗi nhóm trả lời một câu hỏi.

- Đông bao nhiêu (giai đoạn 1, không cần học):
  `zone_limit` số người vượt sức chứa người vận hành đặt cho vùng hoặc cho toàn khung;
  `surge` trong một khoảng ngắn số người tăng ít nhất `surge_abs` người và `surge_rel` lần số cũ.
- Đi sai chiều (không cần học): `counterflow` ở vùng đã đặt chiều đi cho phép, phần chuyển động đi ngược quá lớn.
- Có gì khác thường (giai đoạn 2): `panic` điểm của mô hình chuyển động bất thường (anomaly.py) vượt ngưỡng đã học.

Một luật phải đúng liên tục `persist_s` giây mới cảnh báo; mỗi đợt báo một lần, và giữa hai cảnh báo
cùng loại có thời gian nghỉ `cooldown_s`.
"""
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .anomaly import Reading
from .domain import RULE_NAMES, Alert, DensityStats, MotionStats

RULE_LABELS = {"zone_limit": "Vượt sức chứa", "surge": "Tăng đột ngột", "panic": "Bất thường chuyển động",
               "counterflow": "Đi ngược chiều"}


@dataclass
class RuleConfig:
    persist_s: float = 6.0            # phải đúng liên tục ngần này giây
    cooldown_s: float = 60.0          # nghỉ giữa hai cảnh báo cùng loại
    smooth: int = 3                   # làm mượt số đếm (trung vị n mẫu)
    surge_window_s: float = 60.0
    surge_abs: float = 10.0
    surge_rel: float = 0.5
    panic_persist_s: float = 2.0      # hoảng loạn diễn ra nhanh (vài giây trên UMN): đây là "độ nhạy" trên web
    counterflow_share: float = 0.4    # ngược chiều: báo khi phần chuyển động đi ngược lớn hơn mức này
    count_limit: float | None = None  # sức chứa toàn khung do người vận hành đặt
    enabled: dict[str, bool] = field(default_factory=lambda: {r: True for r in RULE_NAMES})


class RuleEngine:
    def __init__(self, config: RuleConfig):
        self.config = config
        self._roi = deque(maxlen=max(1, config.smooth))
        self._history: deque[tuple[float, float]] = deque()
        self._since: dict[str, float | None] = {r: None for r in RULE_NAMES}   # luật đúng liên tục từ lúc nào
        self._reported = {r: False for r in RULE_NAMES}                      # đợt hiện tại đã báo chưa
        self._last_alert = {r: -np.inf for r in RULE_NAMES}
        self._t = 0.0
        self._panic_limit: float | None = None

    def _persist(self, rule: str) -> float:
        return self.config.panic_persist_s if rule == "panic" else self.config.persist_s

    def active(self) -> list[str]:
        """Các luật đang trong đợt cảnh báo (đã đúng liên tục đủ thời gian duy trì)."""
        return [r for r, s in self._since.items() if s is not None and self._t - s >= self._persist(r) - 1e-9]

    def thresholds(self) -> dict:
        return {"count_limit": self.config.count_limit, "panic_score": self._panic_limit,
                "counterflow": self.config.counterflow_share}

    def update(self, t: float, d: DensityStats, m: MotionStats, a: Reading | None = None) -> list[Alert]:
        c = self.config
        self._t = t
        self._roi.append(d.roi)
        roi = float(np.median(self._roi))
        self._history.append((t, roi))
        while self._history and self._history[0][0] < t - c.surge_window_s:
            self._history.popleft()

        checks = {**self._capacity_check(roi, d), **self._surge_check(t, roi), **self._direction_check(d)}
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

    def _capacity_check(self, roi: float, d: DensityStats) -> dict:
        """Sức chứa do người vận hành đặt: từng vùng, và toàn khung (vùng đang theo dõi)."""
        limited = [(z.name, z.count, z.limit) for z in d.zones if z.limit is not None]
        if self.config.count_limit is not None:
            limited.append(("Toàn khung", roi, self.config.count_limit))
        if not limited:
            return {}
        over = [x for x in limited if x[1] > x[2]]
        _, count, limit = max(limited, key=lambda x: x[1] - x[2])
        text = ", ".join(f"{name} {n:.0f}/{cap:.0f} người" for name, n, cap in over) or "trong giới hạn"
        return {"zone_limit": (bool(over), count, limit, text)}

    def _surge_check(self, t: float, roi: float) -> dict:
        c = self.config
        past = [v for ts, v in self._history if t - c.surge_window_s <= ts <= t - c.surge_window_s / 3]
        if not past:
            return {}
        ref = float(np.median(past))
        need = max(c.surge_abs, c.surge_rel * ref)
        return {"surge": (roi - ref > need, roi - ref, need,
                          f"tăng từ {ref:.0f} lên {roi:.0f} người trong {c.surge_window_s:.0f} giây")}

    def _direction_check(self, d: DensityStats) -> dict:
        """Chỉ xét vùng đã đặt chiều đi và đủ chuyển động để kết luận (wrong_share khác None)."""
        judged = [z for z in d.zones if z.direction is not None and z.wrong_share is not None]
        if not judged:
            return {}
        worst = max(judged, key=lambda z: z.wrong_share)
        limit = self.config.counterflow_share
        return {"counterflow": (worst.wrong_share > limit, worst.wrong_share, limit,
                                f"{worst.name}: {worst.wrong_share:.0%} chuyển động đi ngược chiều quy định")}
