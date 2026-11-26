"""Trang Gắn nhãn trong web chính: API nhãn (chỉ quản trị) kèm chụp khung, tạo nhãn nháp, xuất dataset."""
import datetime as dt
import json
import shutil
import tempfile
from pathlib import Path

import cv2
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from ..config import DEFAULT_MODEL, Settings
from ..model import infer
from .autolabel import density_to_points, keep_mask, label_record
from .export import export_dataset
from .server import NAME_RE, STATIC, build_router

TUNED_MODEL = "mask_dublin"


class CaptureRequest(BaseModel):
    camera_id: int


def mount_labeling(app, settings: Settings, admin) -> None:
    root = settings.labels_dir
    guard = [Depends(admin)]

    def on_status(request: Request, name: str, status: str) -> None:
        app.state.db.audit(request.state.user.name, "label_status", f"{name}: {status}")

    app.include_router(build_router(root, on_status, guard, prefix="/api/labels"))
    extra = APIRouter(prefix="/api/labels", dependencies=guard)

    @extra.post("/capture")
    def capture(req: CaptureRequest, request: Request) -> dict:
        p = app.state.cameras.get(req.camera_id)
        frame = None if p is None else p.raw_frame()
        if frame is None:
            raise HTTPException(409, "Camera chưa có hình. Bật camera rồi thử lại.")
        name = f"live_{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}_cam{req.camera_id}.jpg"
        for d in ("frames", "labels"):
            (root / d).mkdir(parents=True, exist_ok=True)
        if (root / "frames" / name).exists():
            raise HTTPException(409, "Vừa chụp khung này. Đợi một giây rồi thử lại.")
        cv2.imwrite(str(root / "frames" / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        h, w = frame.shape[:2]
        rec = label_record(name, w, h, [], 0.0) | {"auto_count": None}
        (root / "labels" / f"{Path(name).stem}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        app.state.db.audit(request.state.user.name, "label_capture", name)
        return {"image": name}

    @extra.post("/prelabel/{name}")
    def prelabel(name: str, model: str | None = None) -> dict:
        """Nhãn nháp từ bản đồ mật độ. Không tự lưu: trình duyệt nhận điểm rồi người dùng quyết định."""
        path = root / "frames" / name
        if not NAME_RE.match(name) or not path.is_file():
            raise HTTPException(404, "không có ảnh này")
        # mặc định dùng bản tinh chỉnh cho đúng camera này nếu đã có file
        model = model or (TUNED_MODEL if TUNED_MODEL in app.state.models else DEFAULT_MODEL)
        if model not in app.state.models:
            raise HTTPException(409, f"Mô hình {model} chưa được nạp.")
        frame = cv2.imread(str(path))
        res = infer(app.state.models[model], frame, settings.analysis_width)
        density = res.density
        noperson = root / "noperson.json"
        if noperson.exists():
            polys = json.loads(noperson.read_text(encoding="utf-8"))
            density = density * keep_mask(density.shape, polys, (frame.shape[1], frame.shape[0]), res.scale)
        return {"points": density_to_points(density, res.scale, mask=res.mask), "auto_count": float(density.sum())}

    @extra.get("/export")
    def export(request: Request) -> FileResponse:
        if not any((root / "labels").glob("*.json")):
            raise HTTPException(409, "Chưa có nhãn nào để xuất.")
        tmp = Path(tempfile.mkdtemp(prefix="crowd-export-"))
        images, points = export_dataset(root, tmp / "dataset")
        zip_path = shutil.make_archive(str(tmp / "dublin_dataset"), "zip", tmp / "dataset")
        app.state.db.audit(request.state.user.name, "label_export", f"{images} ảnh, {points} điểm")
        return FileResponse(zip_path, filename="dublin_dataset.zip", media_type="application/zip",
                            background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True))

    app.include_router(extra)

    @app.get("/labeling")
    def labeling_page() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})
