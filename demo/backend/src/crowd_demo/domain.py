"""Các kiểu dữ liệu dùng chung giữa các module."""
from dataclasses import dataclass, field

import numpy as np

RULE_NAMES = ("overcrowd", "hot_cell", "surge", "panic", "counterflow")


@dataclass
class DensityResult:
    density: np.ndarray            # (H/4, W/4) của frame phân tích, đơn vị: người mỗi ô
    mask: np.ndarray | None        # xác suất "có người" cùng kích thước, None nếu model không có nhánh mask
    scale: float                   # chiều rộng frame phân tích / chiều rộng frame gốc


@dataclass
class DensityStats:
    total: float
    roi: float
    excluded: float
    cells: np.ndarray
    hot_cells: list[tuple[int, int]] = field(default_factory=list)
    max_cell: float = 0.0


@dataclass
class MotionStats:
    speed: float = 0.0             # px/s ở độ phân giải flow
    direction_deg: float = 0.0     # hướng chính, 0 = sang phải, 90 = xuống dưới (trục ảnh)
    entropy: float = 0.0           # 0 = cùng một hướng, 1 = hướng trải đều (hỗn loạn)
    counterflow: float = 0.0       # tỉ lệ chuyển động ngược hướng chính
    active_ratio: float = 0.0      # tỉ lệ điểm hợp lệ đang chuyển động


@dataclass
class Alert:
    rule: str
    t: float
    value: float
    threshold: float
    message: str
