"""Gán nhãn nháp: MobileCount + Mask (bản đồ mật độ → điểm) kết hợp mô hình phát hiện người Faster R-CNN.

Số điểm = round(tổng mật độ); vị trí = các đỉnh cục bộ cao nhất của bản đồ mật độ đã làm mượt.
Đây là NHÃN NHÁP để người sửa, không phải ground truth.

Chạy: uv run crowd-autolabel
"""
import argparse
import datetime as dt
import json
from pathlib import Path

import cv2
import numpy as np

from ..config import DEMO_DIR
from ..model import STRIDE, infer, load_model
from .grab import DEFAULT_OUT

DEFAULT_MODEL = DEMO_DIR / "models" / "mask.pth"


def density_to_points(density: np.ndarray, scale: float, stride: int = STRIDE, min_peak: float = 0.02,
                      mask: np.ndarray | None = None, mask_min: float = 0.5) -> list[list[float]]:
    """Điểm (x, y) theo pixel ảnh gốc. density: người mỗi ô stride×stride của ảnh đã thu về tỉ lệ `scale`."""
    count = int(round(float(density.sum())))
    if count <= 0:
        return []
    smooth = cv2.GaussianBlur(density.astype(np.float32), (0, 0), 1.0)
    peaks = (smooth == cv2.dilate(smooth, np.ones((3, 3), np.uint8))) & (smooth > min_peak * smooth.max()) & (smooth > 1e-5)
    if mask is not None:
        peaks &= mask >= mask_min
    ys, xs = np.nonzero(peaks)
    order = np.argsort(-smooth[ys, xs])[:count]
    return [[round(float((x + 0.5) * stride / scale), 1), round(float((y + 0.5) * stride / scale), 1)]
            for x, y in zip(xs[order], ys[order])]


# Vùng chắc chắn không có đầu người của camera Temple Bar (tỉ lệ x, y theo khung): mặt tiền phía trên mái hiên,
# ban công đặt camera và dải hoa bên trái, đèn trang trí góc trên trái. Ghi ra root/noperson.json để sửa được.
DEFAULT_NOPERSON = [
    [[0.27, 0.0], [1.0, 0.0], [1.0, 0.50], [0.74, 0.50], [0.74, 0.37], [0.27, 0.37]],
    [[0.0, 0.0], [0.27, 0.0], [0.27, 0.24], [0.10, 0.24], [0.10, 0.38], [0.04, 0.40], [0.12, 1.0], [0.0, 1.0]],
]


def keep_mask(shape: tuple[int, int], polygons: list, frame_wh: tuple[int, int], scale: float, stride: int = STRIDE) -> np.ndarray:
    """Mặt nạ 0/1 trên lưới mật độ: 0 ở các vùng không thể có người."""
    keep = np.ones(shape, np.uint8)
    w, h = frame_wh
    for poly in polygons:
        pts = np.round(np.array([(x * w, y * h) for x, y in poly], np.float32) * scale / stride).astype(np.int32)
        cv2.fillPoly(keep, [pts], 0)
    return keep


def label_record(image: str, width: int, height: int, points: list, auto_count: float) -> dict:
    return {"image": image, "width": width, "height": height, "points": points, "ignore": [],
            "auto_count": round(auto_count, 2), "status": "auto", "note": "",
            "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


VEHICLE_LABELS = {3, 6, 8}      # COCO: car, bus, truck


def head_point(box) -> tuple[float, float]:
    """Tâm đầu ước lượng từ khung người: giữa chiều ngang, cách mép trên ~0,22 bề rộng (bền khi chân bị che/cắt)."""
    x1, y1, x2, y2 = box[:4]
    w, h = x2 - x1, y2 - y1
    return (x1 + x2) / 2, y1 + min(0.22 * w, 0.5 * h)


def fuse_points(dens_pts: list, persons: list, vehicles: list, inside_noperson=lambda x, y: False) -> list[list[float]]:
    """Hợp nhất điểm từ bản đồ mật độ với khung người của mô hình phát hiện.

    - Mỗi khung người tin cậy cho một điểm ở đầu; nếu gần đó có điểm mật độ thì điểm đó được thay (chính xác hơn).
    - Điểm mật độ còn lại: bỏ nếu là điểm trùng trên một người đã có (gần đầu của khung đó), hoặc nằm trên xe
      (trong khung xe mà không thuộc khung người nào). Giữ các điểm khác (người ở xa, nhỏ, bị che).
    """
    dens = [tuple(p) for p in dens_pts]
    used = [False] * len(dens)
    out = []
    heads = []
    for box in sorted(persons, key=lambda b: -b[4]):
        hx, hy = head_point(box)
        if inside_noperson(hx, hy):
            continue
        w = box[2] - box[0]
        r = max(10.0, 0.45 * w)
        best, bd = -1, r * r
        for i, (x, y) in enumerate(dens):
            d = (x - hx) ** 2 + (y - hy) ** 2
            if not used[i] and d < bd:
                best, bd = i, d
        if best >= 0:
            used[best] = True
        heads.append((hx, hy, w, box))
        out.append([round(hx, 1), round(hy, 1)])

    def in_box(x, y, b):
        return b[0] <= x <= b[2] and b[1] <= y <= b[3]

    for i, (x, y) in enumerate(dens):
        if used[i]:
            continue
        if any((x - hx) ** 2 + (y - hy) ** 2 < (0.6 * w) ** 2 for hx, hy, w, _ in heads):
            continue                                            # điểm trùng trên người đã có điểm
        # camera nhìn từ trên xuống: đầu người đứng sau nằm cao hơn trong ảnh, nên điểm trong khung mà thấp hơn đầu
        # là điểm rơi trên thân của chính người đó
        if any(in_box(x, y, b) and y > hy + 0.25 * w for hx, hy, w, b in heads):
            continue
        if any(in_box(x, y, v) for v in vehicles) and not any(in_box(x, y, b) for b in persons):
            continue                                            # nằm trên xe
        out.append([round(x, 1), round(y, 1)])
    return out


class PersonDetector:
    """Faster R-CNN (COCO) của torchvision; trọng số tự tải lần đầu (~170 MB)."""

    def __init__(self, person_score: float = 0.5, vehicle_score: float = 0.5):
        import torch
        from torchvision.models.detection import FasterRCNN_ResNet50_FPN_V2_Weights, fasterrcnn_resnet50_fpn_v2

        self.torch = torch
        self.model = fasterrcnn_resnet50_fpn_v2(weights=FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT,
                                                box_score_thresh=min(person_score, vehicle_score)).eval()
        self.person_score, self.vehicle_score = person_score, vehicle_score

    def __call__(self, frame_bgr: np.ndarray) -> tuple[list, list]:
        x = self.torch.from_numpy(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float() / 255
        with self.torch.inference_mode():
            o = self.model([x])[0]
        boxes, labels, scores = o["boxes"].numpy(), o["labels"].numpy(), o["scores"].numpy()
        persons = [[*map(float, b), float(s)] for b, l, s in zip(boxes, labels, scores) if l == 1 and s >= self.person_score]
        vehicles = [[*map(float, b), float(s)] for b, l, s in zip(boxes, labels, scores)
                    if l in VEHICLE_LABELS and s >= self.vehicle_score]
        return persons, vehicles


def noperson_test(polygons: list, w: int, h: int):
    polys = [np.array([(x * w, y * h) for x, y in poly], np.float32) for poly in polygons]
    return lambda x, y: any(cv2.pointPolygonTest(p, (float(x), float(y)), False) >= 0 for p in polys)


def autolabel(root: Path, model_path: Path, analysis_width: int, overwrite: bool = False,
              detector: bool = True, log=print) -> int:
    frames, labels = root / "frames", root / "labels"
    labels.mkdir(parents=True, exist_ok=True)
    np_file = root / "noperson.json"
    if not np_file.exists():
        np_file.write_text(json.dumps(DEFAULT_NOPERSON), encoding="utf-8")
    noperson = json.loads(np_file.read_text(encoding="utf-8"))
    model = load_model(model_path)
    det = PersonDetector() if detector else None
    n = 0
    for img_path in sorted(frames.glob("*.jpg")):
        out = labels / (img_path.stem + ".json")
        if out.exists() and not overwrite:
            continue
        frame = cv2.imread(str(img_path))
        res = infer(model, frame, analysis_width)
        keep = keep_mask(res.density.shape, noperson, (frame.shape[1], frame.shape[0]), res.scale)
        den = res.density * keep
        pts = density_to_points(den, res.scale, mask=keep)
        if det is not None:
            persons, vehicles = det(frame)
            pts = fuse_points(pts, persons, vehicles, noperson_test(noperson, frame.shape[1], frame.shape[0]))
        rec = label_record(img_path.name, frame.shape[1], frame.shape[0], pts, float(den.sum()))
        out.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        n += 1
    log(f"gán nhãn nháp {n} ảnh → {labels}")
    return n


def run() -> None:
    ap = argparse.ArgumentParser(description="Gán nhãn nháp điểm đầu người bằng MobileCount + Mask")
    ap.add_argument("--root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--width", type=int, default=1920, help="chiều rộng ảnh đưa vào mô hình (lớn để tách người ở xa)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--no-detector", action="store_true", help="chỉ dùng bản đồ mật độ, không dùng mô hình phát hiện người")
    a = ap.parse_args()
    autolabel(a.root, a.model, a.width, a.overwrite, detector=not a.no_detector)


if __name__ == "__main__":
    run()
