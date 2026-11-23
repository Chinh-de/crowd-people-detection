"""Vùng giám sát (ROI) và vùng loại trừ. Tọa độ chuẩn hóa 0–1 nên không phụ thuộc độ phân giải.

Mỗi vùng giám sát có thể đặt tên và sức chứa riêng (`roi_meta`): vượt sức chứa thì cảnh báo."""
from dataclasses import dataclass, field

import cv2
import numpy as np

Polygon = list[tuple[float, float]]
FULL_FRAME: Polygon = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]


@dataclass
class ZoneSet:
    roi: list[Polygon] = field(default_factory=list)
    exclude: list[Polygon] = field(default_factory=list)
    roi_meta: list[dict] = field(default_factory=list)      # {"name": str, "limit": float | None} theo thứ tự roi

    def __post_init__(self):
        self._cache: dict[tuple[int, int], dict[str, np.ndarray]] = {}
        self._zone_cache: dict[tuple[int, int], list[np.ndarray]] = {}

    def meta(self, i: int) -> dict:
        m = self.roi_meta[i] if i < len(self.roi_meta) else {}
        limit = m.get("limit")
        return {"name": str(m.get("name") or f"Vùng {i + 1}"), "limit": None if limit is None else float(limit)}

    def validate(self) -> None:
        for kind, polys in (("vùng giám sát", self.roi), ("vùng loại trừ", self.exclude)):
            for poly in polys:
                if len(poly) < 3:
                    raise ValueError(f"Mỗi {kind} cần ít nhất 3 điểm.")
                if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in poly):
                    raise ValueError(f"Tọa độ {kind} phải nằm trong khoảng 0–1.")
        for i in range(len(self.roi)):
            limit = self.meta(i)["limit"]
            if limit is not None and limit < 0:
                raise ValueError(f"Sức chứa của {self.meta(i)['name']} phải ≥ 0.")

    def masks(self, h: int, w: int) -> dict[str, np.ndarray]:
        """Mask bool kích thước (h, w): 'roi', 'exclude', 'watch' (= trong ROI và ngoài vùng loại trừ)."""
        if (h, w) not in self._cache:
            roi = _fill(self.roi or [FULL_FRAME], h, w)
            exclude = _fill(self.exclude, h, w)
            self._cache[(h, w)] = {"roi": roi, "exclude": exclude, "watch": roi & ~exclude}
        return self._cache[(h, w)]

    def zone_masks(self, h: int, w: int) -> list[np.ndarray]:
        """Mask riêng của từng vùng giám sát, đã bỏ vùng loại trừ."""
        if (h, w) not in self._zone_cache:
            exclude = self.masks(h, w)["exclude"]
            self._zone_cache[(h, w)] = [_fill([poly], h, w) & ~exclude for poly in self.roi]
        return self._zone_cache[(h, w)]

    def to_dict(self) -> dict:
        return {"roi": [[list(p) for p in poly] for poly in self.roi],
                "exclude": [[list(p) for p in poly] for poly in self.exclude],
                "roi_meta": [self.meta(i) for i in range(len(self.roi))]}

    @classmethod
    def from_dict(cls, data: dict) -> "ZoneSet":
        def polys(key):
            return [[(float(x), float(y)) for x, y in poly] for poly in data.get(key, [])]
        return cls(polys("roi"), polys("exclude"), [dict(m) for m in data.get("roi_meta") or []])


def to_pixels(poly: Polygon, w: int, h: int) -> np.ndarray:
    return np.round(np.array(poly, np.float32) * [w, h]).astype(np.int32)


def _fill(polys: list[Polygon], h: int, w: int) -> np.ndarray:
    m = np.zeros((h, w), np.uint8)
    for poly in polys:
        cv2.fillPoly(m, [to_pixels(poly, w, h)], 1)
    return m.astype(bool)
