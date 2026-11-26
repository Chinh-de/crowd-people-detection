"""Phân loại cảnh báo (đúng / báo nhầm), xem mẫu đã lưu, gửi sang Gắn nhãn và xuất bộ mẫu để fine-tune.

Hệ thống chỉ lưu và phân loại mẫu; việc train lại mô hình làm riêng, ngoài web.
"""
import csv
import datetime as dt
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from .config import Settings
from .labeling.autolabel import label_record
from .samples import FILES

MANIFEST = ("id", "camera_id", "source", "t", "rule", "value", "threshold", "verdict", "verdict_by", "note")


class VerdictRequest(BaseModel):
    verdict: Literal["true", "false"] | None = None
    note: str = ""


def mount_feedback(app, settings: Settings, admin) -> None:
    router = APIRouter()

    def event_or_404(eid: int) -> dict:
        ev = app.state.db.get_event(eid)
        if ev is None:
            raise HTTPException(404, f"Không có cảnh báo #{eid}")
        return ev

    def sample_or_409(eid: int) -> Path:
        folder = settings.samples_dir / str(eid)
        if not event_or_404(eid)["has_sample"] or not (folder / "label.json").exists():
            raise HTTPException(409, "Cảnh báo này không còn mẫu đã lưu.")
        return folder

    @router.get("/api/events/{eid}/sample/{name}")
    def sample_file(eid: int, name: str) -> FileResponse:
        path = settings.samples_dir / str(eid) / name
        if name not in FILES or not path.is_file():
            raise HTTPException(404, "Không có file này.")
        return FileResponse(path)

    @router.post("/api/events/{eid}/verdict")
    def verdict(eid: int, req: VerdictRequest, request: Request, user=Depends(admin)) -> dict:
        event_or_404(eid)
        note = req.note.strip()[:500]
        app.state.db.set_verdict(eid, req.verdict, user.name, note)
        app.state.db.audit(user.name, "verdict", f"#{eid} {req.verdict or 'bỏ đánh giá'} {note[:100]}".strip())
        return app.state.db.get_event(eid)

    @router.post("/api/events/{eid}/to-labeling")
    def to_labeling(eid: int, user=Depends(admin)) -> dict:
        folder = sample_or_409(eid)
        info = json.loads((folder / "label.json").read_text(encoding="utf-8"))
        when = dt.datetime.fromtimestamp(app.state.db.get_event(eid)["t"], dt.timezone.utc)
        name = f"live_{when:%Y%m%dT%H%M%SZ}_ev{eid}.jpg"
        frames, labels = settings.labels_dir / "frames", settings.labels_dir / "labels"
        if not (frames / name).exists():                    # gửi lần nữa không ghi đè nhãn đã sửa
            frames.mkdir(parents=True, exist_ok=True)
            labels.mkdir(parents=True, exist_ok=True)
            shutil.copy(folder / "frame.jpg", frames / name)
            rec = label_record(name, info["width"], info["height"], info["points"], info["count"])
            rec["note"] = f"Từ cảnh báo #{eid} ({info.get('camera', '')})"
            (labels / f"{Path(name).stem}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            app.state.db.audit(user.name, "to_labeling", f"#{eid} → {name}")
        return {"image": name}

    @router.get("/api/feedback/export", dependencies=[Depends(admin)])
    def export() -> FileResponse:
        """Zip mọi mẫu đã được đánh giá: manifest.csv + samples/<id>/…"""
        rows = [e for e in app.state.db.judged_events() if (settings.samples_dir / str(e["id"])).is_dir()]
        if not rows:
            raise HTTPException(409, "Chưa có cảnh báo nào được phân loại đúng hoặc nhầm.")
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=MANIFEST, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        tmp = Path(tempfile.mkdtemp(prefix="crowd-feedback-"))
        path = tmp / "feedback_samples.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.csv", "﻿" + buf.getvalue())
            for e in rows:
                for f in sorted((settings.samples_dir / str(e["id"])).iterdir()):
                    z.write(f, f"samples/{e['id']}/{f.name}")
        return FileResponse(path, filename=path.name, media_type="application/zip",
                            background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True))

    app.include_router(router)
