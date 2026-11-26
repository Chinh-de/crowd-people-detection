"""Mẫu học liên tục: mỗi cảnh báo lưu ảnh gốc, mask, bản đồ mật độ, nhãn điểm nháp và đặc trưng chuyển động.

Thư mục data/samples/<id cảnh báo>/:
- frame.jpg    ảnh gốc, không vẽ gì (dùng để gắn nhãn và train lại);
- mask.png     xác suất "có người" 0–255 (không có nếu mô hình đếm không có nhánh mask);
- density.npz  bản đồ mật độ (người mỗi ô 4×4 của ảnh phân tích);
- label.json   nhãn điểm nháp theo pixel ảnh gốc, số đếm, luật, mô hình, thời điểm;
- features.npz đặc trưng lưới 8×8 của vài lần phân tích ngay trước cảnh báo (cho mô hình bất thường);
- preview.jpg  ảnh có tô mask và điểm nhãn để người duyệt xem nhanh.
"""
import json
from pathlib import Path

import cv2
import numpy as np

from .anomaly import CellFeats
from .labeling.autolabel import density_to_points

FILES = ("frame.jpg", "mask.png", "preview.jpg")     # các file ảnh được phép xem qua web
PREVIEW_WIDTH = 960


def save_sample(folder: Path, frame: np.ndarray, density: np.ndarray, mask: np.ndarray | None, scale: float,
                feats: list[CellFeats], meta: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    h, w = frame.shape[:2]
    points = density_to_points(density, scale, mask=mask)
    cv2.imwrite(str(folder / "frame.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if mask is not None:
        cv2.imwrite(str(folder / "mask.png"), np.round(np.clip(mask, 0, 1) * 255).astype(np.uint8))
    np.savez_compressed(folder / "density.npz", density=density.astype(np.float16), scale=scale)
    if feats:
        np.savez_compressed(folder / "features.npz", fm=np.stack([f.fm for f in feats]),
                            f0=np.stack([f.f0 for f in feats]), d=np.stack([f.d for f in feats]))
    label = {**meta, "width": w, "height": h, "count": round(float(density.sum()), 2), "points": points}
    (folder / "label.json").write_text(json.dumps(label, ensure_ascii=False), encoding="utf-8")
    cv2.imwrite(str(folder / "preview.jpg"), _preview(frame, mask, points), [cv2.IMWRITE_JPEG_QUALITY, 88])


def load_features(folder: Path) -> list[CellFeats]:
    path = folder / "features.npz"
    if not path.exists():
        return []
    with np.load(path) as z:
        return [CellFeats(fm=fm, f0=f0, d=d) for fm, f0, d in zip(z["fm"], z["f0"], z["d"])]


def _preview(frame: np.ndarray, mask: np.ndarray | None, points: list) -> np.ndarray:
    k = min(1.0, PREVIEW_WIDTH / frame.shape[1])
    img = cv2.resize(frame, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else frame.copy()
    if mask is not None:
        on = (cv2.resize(mask.astype(np.float32), (img.shape[1], img.shape[0])) > 0.5).astype(np.uint8)
        tint = img.copy()
        tint[on > 0] = (0, 215, 255)                       # vàng (BGR)
        img = cv2.addWeighted(tint, 0.3, img, 0.7, 0)
        contours, _ = cv2.findContours(on, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(img, contours, -1, (0, 215, 255), 2)
    for x, y in points:
        center = (int(x * k), int(y * k))
        cv2.circle(img, center, 5, (40, 40, 255), -1, cv2.LINE_AA)
        cv2.circle(img, center, 5, (255, 255, 255), 1, cv2.LINE_AA)
    return img
