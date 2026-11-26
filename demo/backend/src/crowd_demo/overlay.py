"""Vẽ lớp nhận diện lên frame theo 4 chế độ hiển thị. Số liệu dạng chữ hiển thị ở web, không vẽ ở đây.

Lớp phủ chỉ thay đổi sau mỗi lần phân tích (vài lần/giây) trong khi video chạy 25–30 FPS, nên phần
tốn kém (heatmap màu, đường bao, mũi tên) được dựng một lần cho mỗi `Layers` và kích thước ảnh,
rồi chỉ ghép lên từng frame.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np

from .zones import ZoneSet, to_pixels

ROI_COLOR = (80, 220, 80)          # BGR
EXCLUDE_COLOR = (60, 60, 230)
MASK_COLOR = (0, 215, 255)
HOT_COLOR = (40, 40, 255)          # viền khung khi đang cảnh báo
ANOMALY_COLOR = (0, 140, 255)      # cam: ô có sai số dựng lại vượt ngưỡng (autoencoder)
ARROW_COLOR = (255, 255, 255)
WRONG_COLOR = (40, 40, 255)        # đỏ: chuyển động đi ngược chiều cho phép
ARROW_STEP = 24                    # khoảng cách lưới mũi tên flow, pixel ảnh đầu ra
HEAT_MAX_ALPHA = 0.6
EXCLUDE_SHADE = 0.35               # độ sáng còn lại của vùng loại trừ


@dataclass
class Layers:
    density: np.ndarray | None = None
    mask: np.ndarray | None = None
    flow: np.ndarray | None = None               # (h, w, 2), đơn vị pixel của ảnh flow
    flow_valid: np.ndarray | None = None
    zones: ZoneSet = field(default_factory=ZoneSet)
    wrong: np.ndarray | None = None              # bool cùng cỡ flow: điểm đi ngược chiều cho phép
    alert_active: bool = False
    heat_vmax: float = 0.05
    anomaly_cells: np.ndarray | None = None      # (8, 8) mức bất thường theo ô
    anomaly_limit: float | None = None
    _painted: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class _Paint:
    heat: np.ndarray | None          # BGR uint8
    heat_alpha: np.ndarray | None    # (h, w, 1) uint16, 0–255
    exclude: np.ndarray | None       # bool (h, w)
    lines: np.ndarray                # BGR uint8: đường vùng, đường bao, mũi tên, ô đông
    lines_mask: np.ndarray           # bool (h, w)


def render(frame_bgr: np.ndarray, layers: Layers | None, mode: str, out_width: int) -> np.ndarray:
    h0, w0 = frame_bgr.shape[:2]
    out_h = round(h0 * out_width / w0)
    base = cv2.resize(frame_bgr, (out_width, out_h), interpolation=cv2.INTER_AREA)
    if mode == "video":
        return base
    if mode == "overlay_only":
        img = np.zeros_like(base)
    elif mode == "gray":
        img = cv2.cvtColor(cv2.cvtColor(base, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    else:
        img = base
    if layers is None:
        return img

    p = _paint(layers, out_h, out_width)
    if p.heat is not None:
        a = p.heat_alpha
        img = ((img.astype(np.uint16) * (255 - a) + p.heat.astype(np.uint16) * a) // 255).astype(np.uint8)
    if p.exclude is not None:
        img[p.exclude] = (img[p.exclude] * EXCLUDE_SHADE).astype(np.uint8)
    img[p.lines_mask] = p.lines[p.lines_mask]
    if layers.alert_active:
        cv2.rectangle(img, (0, 0), (img.shape[1] - 1, img.shape[0] - 1), HOT_COLOR, 6)
    return img


def _paint(layers: Layers, h: int, w: int) -> _Paint:
    key = (h, w)
    if key not in layers._painted:
        heat, alpha = _heat(layers, h, w)
        lines = np.zeros((h, w, 3), np.uint8)
        _draw_zones(lines, layers.zones)
        _draw_mask(lines, layers.mask)
        _draw_flow(lines, layers)
        _draw_directions(lines, layers.zones)
        _draw_anomaly_cells(lines, layers)
        exclude = layers.zones.masks(h, w)["exclude"] if layers.zones.exclude else None
        layers._painted[key] = _Paint(heat, alpha, exclude, lines, lines.any(axis=2))
    return layers._painted[key]


def _heat(layers: Layers, h: int, w: int) -> tuple[np.ndarray | None, np.ndarray | None]:
    if layers.density is None:
        return None, None
    den = np.clip(layers.density, 0, None).astype(np.float32)
    norm = np.clip(cv2.resize(den, (w, h)) / max(layers.heat_vmax, 1e-6), 0, 1)
    heat = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_JET)
    alpha = (norm * HEAT_MAX_ALPHA * 255).astype(np.uint16)[..., None]
    return heat, alpha


def _draw_zones(img: np.ndarray, zones: ZoneSet) -> None:
    h, w = img.shape[:2]
    for poly in zones.exclude:
        cv2.polylines(img, [to_pixels(poly, w, h)], True, EXCLUDE_COLOR, 2, cv2.LINE_AA)
    for poly in zones.roi:
        cv2.polylines(img, [to_pixels(poly, w, h)], True, ROI_COLOR, 2, cv2.LINE_AA)


def _draw_mask(img: np.ndarray, mask: np.ndarray | None) -> None:
    if mask is None:
        return
    h, w = img.shape[:2]
    m = (cv2.resize(mask.astype(np.float32), (w, h)) > 0.5).astype(np.uint8)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(img, contours, -1, MASK_COLOR, 2, cv2.LINE_AA)


def _draw_flow(img: np.ndarray, layers: Layers) -> None:
    if layers.flow is None:
        return
    h, w = img.shape[:2]
    fh, fw = layers.flow.shape[:2]
    sx, sy = w / fw, h / fh
    for y in range(ARROW_STEP // 2, h, ARROW_STEP):
        for x in range(ARROW_STEP // 2, w, ARROW_STEP):
            fy, fx = min(int(y / sy), fh - 1), min(int(x / sx), fw - 1)
            wrong = layers.wrong is not None and bool(layers.wrong[fy, fx])
            if not wrong and layers.flow_valid is not None and not layers.flow_valid[fy, fx]:
                continue
            dx, dy = layers.flow[fy, fx]
            if dx * dx + dy * dy < 0.25:
                continue
            end = (int(x + dx * sx * 3), int(y + dy * sy * 3))      # phóng 3 lần cho dễ nhìn
            cv2.arrowedLine(img, (x, y), end, WRONG_COLOR if wrong else ARROW_COLOR, 2 if wrong else 1,
                            cv2.LINE_AA, tipLength=0.35)


def _draw_directions(img: np.ndarray, zones: ZoneSet) -> None:
    """Mũi tên xanh lớn giữa vùng: chiều đi cho phép."""
    h, w = img.shape[:2]
    for i, poly in enumerate(zones.roi):
        deg = zones.meta(i)["direction"]
        if deg is None:
            continue
        center = to_pixels(poly, w, h).mean(axis=0)
        half = np.array([np.cos(np.radians(deg)), np.sin(np.radians(deg))]) * w * 0.05
        start, end = (center - half).astype(int), (center + half).astype(int)
        cv2.arrowedLine(img, tuple(map(int, start)), tuple(map(int, end)), ROI_COLOR, 5, cv2.LINE_AA, tipLength=0.4)


def _draw_anomaly_cells(img: np.ndarray, layers: Layers) -> None:
    """Ô lưới 8×8 có sai số dựng lại vượt ngưỡng: vị trí bất thường do autoencoder chỉ ra."""
    if layers.anomaly_cells is None or not layers.anomaly_limit:
        return
    h, w = img.shape[:2]
    gh, gw = layers.anomaly_cells.shape
    ys = np.linspace(0, h, gh + 1).astype(int)
    xs = np.linspace(0, w, gw + 1).astype(int)
    for r, c in zip(*np.nonzero(layers.anomaly_cells > layers.anomaly_limit)):
        cv2.rectangle(img, (int(xs[c]) + 2, int(ys[r]) + 2), (int(xs[c + 1]) - 3, int(ys[r + 1]) - 3), ANOMALY_COLOR, 2)
