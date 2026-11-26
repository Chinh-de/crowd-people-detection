"""Đóng gói nhãn thành dataset cho notebook fine-tune: ảnh 960×540 + annotations.json."""
import json
from pathlib import Path

from PIL import Image

W, H = 960, 540


def export_dataset(src: Path, out: Path) -> tuple[int, int]:
    """Ghi dataset vào `out`; trả (số ảnh, số điểm). Tọa độ được nhân theo tỉ lệ ảnh gốc → 960×540."""
    (out / "images").mkdir(parents=True, exist_ok=True)
    records = []
    for lab in sorted((src / "labels").glob("*.json")):
        d = json.loads(lab.read_text(encoding="utf-8"))
        name = d["image"]
        img = Image.open(src / "frames" / name).convert("RGB")
        sx, sy = W / img.width, H / img.height

        def scale(pts):
            return [[round(x * sx, 2), round(y * sy, 2)] for x, y in pts]

        img.resize((W, H), Image.LANCZOS).save(out / "images" / name, quality=95)
        utc = name.split("_")[1]                      # live_20261112T201512Z_...
        records.append({"image": name, "utc": f"{utc[:4]}-{utc[4:6]}-{utc[6:8]}T{utc[9:11]}:{utc[11:13]}:{utc[13:15]}Z",
                        "status": d.get("status", ""), "points": scale(d["points"]),
                        "ignore": [scale(p) for p in d.get("ignore", [])]})
    meta = {"width": W, "height": H, "source": "Temple Bar (Dublin) live camera", "images": records}
    (out / "annotations.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (out / "dataset-metadata.json").write_text(json.dumps(
        {"title": "Dublin Temple Bar crowd labels", "id": "chinhde/dublin-temple-bar-crowd",
         "licenses": [{"name": "other"}]}, indent=2), encoding="utf-8")
    return len(records), sum(len(r["points"]) for r in records)
