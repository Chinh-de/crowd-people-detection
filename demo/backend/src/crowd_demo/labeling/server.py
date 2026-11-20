"""Web chỉnh nhãn điểm đầu người. Chạy: uv run crowd-label rồi mở http://127.0.0.1:8010"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .grab import DEFAULT_OUT

STATIC = Path(__file__).parent / "static"
NAME_RE = re.compile(r"^[\w.\-]+\.jpg$")
STATUSES = ("auto", "reviewed", "done")


class Label(BaseModel):
    points: list[list[float]]
    ignore: list[list[list[float]]] = Field(default_factory=list)
    status: str = "auto"
    note: str = ""


def create_app(root: Path) -> FastAPI:
    frames, labels = root / "frames", root / "labels"
    app = FastAPI(title="Chỉnh nhãn đầu người")

    def image_path(name: str) -> Path:
        p = frames / name
        if not NAME_RE.match(name) or not p.is_file():
            raise HTTPException(404, "không có ảnh này")
        return p

    def read_label(name: str) -> dict:
        p = labels / (Path(name).stem + ".json")
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {"image": name, "points": [], "ignore": [], "auto_count": None, "status": "auto", "note": ""}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})   # luôn lấy bản mới khi cập nhật

    @app.get("/api/items")
    def items():
        out = []
        for p in sorted(frames.glob("*.jpg")):
            lab = read_label(p.name)
            out.append({"image": p.name, "count": len(lab["points"]), "auto_count": lab.get("auto_count"),
                        "status": lab.get("status", "auto"), "note": lab.get("note", "")})
        return out

    @app.get("/api/image/{name}")
    def image(name: str):
        return FileResponse(image_path(name), media_type="image/jpeg")

    @app.get("/api/label/{name}")
    def get_label(name: str):
        image_path(name)
        return read_label(name)

    @app.put("/api/label/{name}")
    def put_label(name: str, body: Label):
        image_path(name)
        if body.status not in STATUSES:
            raise HTTPException(422, f"status phải là một trong {STATUSES}")
        rec = read_label(name)
        rec.update(points=[[round(x, 1), round(y, 1)] for x, y in body.points],
                   ignore=[[[round(x, 1), round(y, 1)] for x, y in poly] for poly in body.ignore if len(poly) >= 3],
                   status=body.status, note=body.note,
                   updated=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        labels.mkdir(parents=True, exist_ok=True)
        (labels / (Path(name).stem + ".json")).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "count": len(rec["points"])}

    return app


def run() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description="Web chỉnh nhãn điểm đầu người")
    ap.add_argument("--root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--port", type=int, default=8010)
    a = ap.parse_args()
    uvicorn.run(create_app(a.root), host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    run()
