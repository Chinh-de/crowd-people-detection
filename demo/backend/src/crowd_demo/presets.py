"""Mốc bình thường học sẵn cho giai đoạn 2: mở video là chấm điểm được ngay, không phải học lúc đang chạy.

Mỗi video UMN (một bối cảnh) có mốc riêng, lấy từ 200 khung đầu của từng clip (đều là khung bình thường, đúng cách
chia trong báo cáo). Camera Temple Bar (bản ghi và livestream) dùng chung mốc lấy từ 20 phút đầu của bản ghi.
Nguồn khác không có mốc sẵn.

Tạo lại: uv run python -m crowd_demo.presets   (cần data/videos/umn.avi; có bản ghi Temple Bar thì tạo luôn mốc Temple Bar)
"""
import json
from pathlib import Path

import cv2
import numpy as np

from .anomaly import CellFeats, cell_features

# tên file video → (khung đầu mỗi clip trong umn.avi), khung kết thúc bối cảnh
SCENE_VIDEOS = {"umn_bai_co": (0, 1453), "umn_trong_nha": (1453, 5596), "umn_quang_truong": (5596, 7739)}
CLIP_STARTS = (0, 615, 1453, 1986, 2685, 3429, 4018, 4929, 5596, 6235, 6913)
TRAIN_FRAMES = 200
DUBLIN = "part_1794421962_000"          # bản ghi camera Temple Bar
DUBLIN_LIVE_ID = "3nyPER2kzqk"          # livestream YouTube của chính camera đó
DUBLIN_TRAIN_S, DUBLIN_EVERY_S = 1200, 2


def preset_dir(models_dir: Path) -> Path:
    return models_dir / "anomaly" / "presets"


def save_preset(path: Path, samples: list[CellFeats]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **{k: np.stack([getattr(s, k) for s in samples]) for k in ("fm", "f0", "d")})


def load_preset(models_dir: Path, count_model: str, source_name: str | None) -> tuple[str, list[CellFeats]] | None:
    """(tên mốc, mẫu) của tên file video hoặc link livestream; video không có mốc riêng thì None (học mức bình thường như thường).
    Không dùng mốc chung: đo trên video Temple Bar, mốc từ UMN vượt ngưỡng 84% thời gian."""
    if not source_name:
        return None
    name = DUBLIN if DUBLIN_LIVE_ID in source_name else Path(source_name).stem
    path = preset_dir(models_dir) / count_model / f"{name}.npz"
    if not path.exists():
        return None
    z = np.load(path)
    return name, [CellFeats(fm=a, f0=b, d=c) for a, b, c in zip(z["fm"], z["f0"], z["d"])]


def extract(model, settings, frames: list[np.ndarray], zones, idx) -> list[CellFeats]:
    """Đặc trưng tại các khung `idx`, tính đúng như luồng phân tích của ứng dụng."""
    from .model import infer
    from .motion import compute_flow
    from .pipeline import MAX_UPSCALE

    gap = round(settings.flow_gap_s * 30)
    out = []
    for i in idx:
        cur = frames[i]
        res = infer(model, cur, min(settings.analysis_width, round(MAX_UPSCALE * cur.shape[1])))
        flow = compute_flow(frames[i - gap], cur, settings.flow_width)
        fh, fw = flow.shape[:2]
        watch = zones.masks(fh, fw)["watch"]
        weight = watch.astype(np.float32)
        if res.mask is not None:
            weight = weight * cv2.resize(res.mask.astype(np.float32), (fw, fh))
        out.append(cell_features(flow, weight, res.density, res.mask, gap / 30,
                                 watch=zones.masks(*res.density.shape)["watch"]))
    return out


def build_dublin(settings) -> None:
    """Mốc Temple Bar cho mọi mô hình đếm có sẵn: mỗi DUBLIN_EVERY_S giây một mẫu trong 20 phút đầu bản ghi."""
    from .config import MODELS
    from .model import load_model
    from .zones import ZoneSet

    video = settings.videos_dir / f"{DUBLIN}.webm"
    if not video.exists():
        print("bỏ qua Temple Bar: không có", video.name)
        return
    zones = ZoneSet.from_dict(json.loads((settings.zones_dir / f"{video.name}.json").read_text(encoding="utf-8")))
    models = {n: load_model(settings.model_file(n)) for n in MODELS if settings.model_file(n).exists()}
    samples = {n: [] for n in models}
    gap, every = round(settings.flow_gap_s * 30), DUBLIN_EVERY_S * 30
    cap, frames = cv2.VideoCapture(str(video)), {}
    for i in range(DUBLIN_TRAIN_S * 30):
        if not cap.grab():
            break
        if i % every in (0, gap):
            frames[i] = cap.retrieve()[1]
        if i % every == gap:
            for n, m in models.items():
                samples[n] += extract(m, settings, frames, zones, [i])
            frames = {}
            if i // every % 60 == 0:
                print("Temple Bar", i // 30, "giây", flush=True)
    cap.release()
    for n, got in samples.items():
        save_preset(preset_dir(settings.models_dir) / n / f"{DUBLIN}.npz", got)
        print(n, DUBLIN, len(got))


def main() -> None:
    from .config import MODELS, Settings
    from .model import load_model
    from .zones import ZoneSet

    s = Settings()
    cap = cv2.VideoCapture(str(s.videos_dir / "umn.avi"))
    frames = []
    while (item := cap.read())[0]:
        frames.append(item[1])
    cap.release()
    assert len(frames) == 7739, "umn.avi không đúng bản dùng trong báo cáo"
    zone_text = (s.zones_dir / "umn.avi.json").read_text(encoding="utf-8")
    zones = ZoneSet.from_dict(json.loads(zone_text))

    for name, (a, b) in SCENE_VIDEOS.items():
        out = cv2.VideoWriter(str(s.videos_dir / f"{name}.avi"), cv2.VideoWriter_fourcc(*"MJPG"), 30,
                              (frames[0].shape[1], frames[0].shape[0]))
        for f in frames[a:b]:
            out.write(f)
        out.release()
        (s.zones_dir / f"{name}.avi.json").write_text(zone_text, encoding="utf-8")

    gap = round(s.flow_gap_s * 30)
    for model_name in MODELS:
        if not s.model_file(model_name).exists():
            continue
        model = load_model(s.model_file(model_name))
        for name, (a, b) in SCENE_VIDEOS.items():
            idx = [i for start in CLIP_STARTS if a <= start < b for i in range(start + gap, start + TRAIN_FRAMES, 3)]
            samples = extract(model, s, frames, zones, idx)
            save_preset(preset_dir(s.models_dir) / model_name / f"{name}.npz", samples)
            print(model_name, name, len(samples), flush=True)
    build_dublin(s)


if __name__ == "__main__":
    main()
