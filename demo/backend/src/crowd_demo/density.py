"""Đếm người theo vùng và theo ô lưới từ density map."""
import math

import numpy as np

from .domain import DensityStats, ZoneCount
from .zones import ZoneSet


def cell_sums(den: np.ndarray, cell: int) -> np.ndarray:
    """Tổng density trong từng ô cell×cell (ô cuối được đệm 0)."""
    h, w = den.shape
    H, W = math.ceil(h / cell) * cell, math.ceil(w / cell) * cell
    padded = np.pad(den, ((0, H - h), (0, W - w)))
    return padded.reshape(H // cell, cell, W // cell, cell).sum(axis=(1, 3))


def analyze_density(den: np.ndarray, zones: ZoneSet, cell: int, cell_limit: float | None) -> DensityStats:
    z = zones.masks(*den.shape)
    cells = cell_sums(np.where(z["watch"], den, 0.0), max(1, cell))
    hot = [] if cell_limit is None else [(int(r), int(c)) for r, c in zip(*np.nonzero(cells > cell_limit))]
    per_zone = [ZoneCount(zones.meta(i)["name"], float(den[m].sum()), zones.meta(i)["limit"])
                for i, m in enumerate(zones.zone_masks(*den.shape))]
    return DensityStats(total=float(den.sum()), roi=float(den[z["watch"]].sum()),
                        excluded=float(den[z["exclude"]].sum()), cells=cells,
                        hot_cells=hot, max_cell=float(cells.max()) if cells.size else 0.0, zones=per_zone)
