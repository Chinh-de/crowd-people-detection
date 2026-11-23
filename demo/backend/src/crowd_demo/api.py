"""API web: đăng nhập, danh sách camera, luồng video, cấu hình theo camera, lịch sử cảnh báo, thống kê, nhật ký.

Mọi route /api/* (trừ /api/login), luồng video, file bằng chứng và WebSocket đều cần phiên đăng nhập.
Route thay đổi cấu hình cần quyền quản trị; tài khoản chỉ xem được xem và xác nhận cảnh báo.
"""
import asyncio
import csv
import io
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .anomaly import ANOMALY_MODELS, NORM_MODES, available as anomaly_available
from .auth import COOKIE, Auth, User
from .cameras import CameraLimitError, CameraManager, rule_config_from
from .config import BACKEND_DIR, DEFAULT_MODEL, DEMO_DIR, MODEL_METRICS, MODELS, VIDEO_EXTS, VIEW_MODES, Settings
from .model import CountModel, load_model, warmup
from .pipeline import Pipeline
from .rules import RuleConfig
from .sources import SourceError
from .storage import Database
from .zones import ZoneSet

log = logging.getLogger(__name__)
FRONTEND_DIST = DEMO_DIR / "frontend" / "dist"
STATUS_INTERVAL_S = 0.5
PURGE_EVERY_S = 6 * 3600
LOGIN_FAIL_DELAY_S = 0.5


class LoginRequest(BaseModel):
    username: str
    password: str


class CameraBody(BaseModel):
    name: str
    kind: Literal["file", "youtube"]
    source: str
    tz: str = "UTC"
    autostart: bool = False


class CameraPatch(BaseModel):
    name: str | None = None
    kind: Literal["file", "youtube"] | None = None
    source: str | None = None
    tz: str | None = None
    autostart: bool | None = None


class PlaybackRequest(BaseModel):
    action: Literal["play", "pause", "seek"]
    value: float | None = None


class ViewRequest(BaseModel):
    mode: str


class ZoneMeta(BaseModel):
    name: str = ""
    limit: float | None = None


class ZonesBody(BaseModel):
    roi: list[list[tuple[float, float]]] = []
    exclude: list[list[tuple[float, float]]] = []
    roi_meta: list[ZoneMeta] = []


class ModelRequest(BaseModel):
    name: str


class AnomalyRequest(BaseModel):
    name: str
    norm: str | None = None


class CalibrateRequest(BaseModel):
    seconds: float = 60.0


class AckRequest(BaseModel):
    note: str = ""


def create_app(settings: Settings | None = None, model: CountModel | None = None,
               env: dict[str, str] | None = None) -> FastAPI:
    settings = settings or Settings()
    if env is None:
        load_dotenv(BACKEND_DIR / ".env")
        env = dict(os.environ)
    auth = Auth(env)
    if auth.using_default:
        log.warning("CHƯA ĐẶT CROWD_ADMIN_USER / CROWD_ADMIN_PASSWORD: đang dùng tài khoản mặc định admin/admin. "
                    "Hãy tạo demo/backend/.env theo .env.example.")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        for d in (settings.videos_dir, settings.zones_dir, settings.evidence_dir):
            d.mkdir(parents=True, exist_ok=True)
        # Nạp và chạy thử sẵn mọi model có file, dùng chung cho mọi camera
        models = {DEFAULT_MODEL: model or load_model(settings.model_path)}
        for name in MODELS:
            if name not in models and settings.model_file(name).exists():
                models[name] = load_model(settings.model_file(name))
        for m in models.values():
            warmup(m, settings.analysis_width)
        app.state.models = models
        app.state.db = Database(settings.db_path)
        app.state.cameras = CameraManager(settings, app.state.db, models)
        app.state.cameras.seed_defaults()
        app.state.cameras.autostart()
        stop = threading.Event()
        threading.Thread(target=_purge_loop, args=(app.state.db, settings, stop), name="crowd-purge", daemon=True).start()
        yield
        stop.set()
        app.state.cameras.stop_all()
        app.state.db.close()

    app = FastAPI(title="Giám sát đám đông", lifespan=lifespan)
    app.state.auth = auth

    # ---------------------------------------------------------------- xác thực
    @app.middleware("http")
    async def require_login(request: Request, call_next):
        path = request.url.path
        if (path.startswith("/api/") and path != "/api/login") or path.startswith("/evidence/"):
            user = auth.verify(request.cookies.get(COOKIE))
            if user is None:
                return JSONResponse({"detail": "Chưa đăng nhập hoặc phiên đã hết hạn."}, status_code=401)
            request.state.user = user
        return await call_next(request)

    def current_user(request: Request) -> User:
        return request.state.user

    def admin(user: User = Depends(current_user)) -> User:
        if not user.is_admin:
            raise HTTPException(403, "Tài khoản chỉ xem không được thay đổi cấu hình.")
        return user

    def db() -> Database:
        return app.state.db

    def mgr() -> CameraManager:
        return app.state.cameras

    def audit(user: User, action: str, detail: str = "") -> None:
        app.state.db.audit(user.name, action, detail)

    @app.post("/api/login")
    async def login(req: LoginRequest, response: Response) -> dict:
        user = auth.check(req.username, req.password)
        if user is None:
            app.state.db.audit(req.username[:64] or "?", "login_failed")
            await asyncio.sleep(LOGIN_FAIL_DELAY_S)          # làm chậm việc dò mật khẩu
            raise HTTPException(401, "Sai tên đăng nhập hoặc mật khẩu.")
        response.set_cookie(COOKIE, auth.issue(user), max_age=int(auth.ttl_s), httponly=True, samesite="lax")
        audit(user, "login")
        return {"name": user.name, "role": user.role}

    @app.post("/api/logout")
    def logout(response: Response, user: User = Depends(current_user)) -> dict:
        response.delete_cookie(COOKIE)
        audit(user, "logout")
        return {"ok": True}

    @app.get("/api/me")
    def me(user: User = Depends(current_user)) -> dict:
        return {"name": user.name, "role": user.role, "default_credentials": auth.using_default}

    @app.get("/api/system")
    def system() -> dict:
        return {"max_cameras": settings.max_cameras, "running": len(mgr().running_ids()),
                "unacked": db().unacked_count(), "cpu_count": os.cpu_count(), "clip_days": settings.clip_days}

    # ---------------------------------------------------------------- model và video
    @app.get("/api/models")
    def list_models() -> list[dict]:
        out = []
        for name, (label, _) in MODELS.items():
            loaded = app.state.models.get(name)
            mae, mse = MODEL_METRICS.get(name, (None, None))
            out.append({"name": name, "label": label, "mae": mae, "mse": mse,
                        "available": loaded is not None or settings.model_file(name).exists(),
                        "has_mask": None if loaded is None else loaded.mask_head is not None})
        return out

    @app.get("/api/anomaly-models")
    def list_anomaly_models() -> dict:
        return {"norm_modes": list(NORM_MODES),
                "models": [{"name": n, "label": label, "kind": kind, "umn_auc": auc,
                            "available": anomaly_available(n, settings.models_dir)}
                           for n, (label, kind, auc) in ANOMALY_MODELS.items()]}

    @app.get("/api/videos")
    def list_videos() -> list[str]:
        return sorted(p.name for p in settings.videos_dir.iterdir()
                      if p.is_file() and p.suffix.lower() in VIDEO_EXTS)

    @app.post("/api/videos")
    async def upload_video(file: UploadFile, user: User = Depends(admin)) -> dict:
        name = Path(file.filename or "").name
        if Path(name).suffix.lower() not in VIDEO_EXTS:
            raise HTTPException(415, f"Chỉ hỗ trợ: {', '.join(sorted(VIDEO_EXTS))}")
        with open(settings.videos_dir / name, "wb") as fh:
            while chunk := await file.read(1 << 20):
                fh.write(chunk)
        audit(user, "upload_video", name)
        return {"name": name}

    # ---------------------------------------------------------------- camera
    def camera_or_404(cid: int) -> dict:
        cam = db().get_camera(cid)
        if cam is None:
            raise HTTPException(404, f"Không có camera #{cid}")
        return cam

    def running(cid: int) -> Pipeline:
        camera_or_404(cid)
        p = mgr().get(cid)
        if p is None:
            raise HTTPException(409, "Camera đang tắt.")
        return p

    @app.get("/api/cameras")
    def list_cameras() -> list[dict]:
        return mgr().list()

    @app.post("/api/cameras")
    def create_camera(body: CameraBody, user: User = Depends(admin)) -> dict:
        try:
            cid = mgr().create(body.model_dump())
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        audit(user, "create_camera", f"#{cid} {body.name}")
        return db().get_camera(cid)

    @app.get("/api/cameras/{cid}")
    def get_camera(cid: int) -> dict:
        return camera_or_404(cid)

    @app.put("/api/cameras/{cid}")
    def update_camera(cid: int, body: CameraPatch, user: User = Depends(admin)) -> dict:
        camera_or_404(cid)
        try:
            mgr().update(cid, body.model_dump(exclude_none=True))
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        except SourceError as e:
            raise HTTPException(409, str(e)) from e
        audit(user, "update_camera", f"#{cid} {body.model_dump(exclude_none=True)}")
        return db().get_camera(cid)

    @app.delete("/api/cameras/{cid}")
    def delete_camera(cid: int, user: User = Depends(admin)) -> dict:
        cam = camera_or_404(cid)
        mgr().delete(cid)
        audit(user, "delete_camera", f"#{cid} {cam['name']}")
        return {"ok": True}

    @app.post("/api/cameras/{cid}/start")
    def start_camera(cid: int, user: User = Depends(admin)) -> dict:
        cam = camera_or_404(cid)
        try:
            mgr().start(cid)
        except CameraLimitError as e:
            raise HTTPException(409, str(e)) from e
        except SourceError as e:
            raise HTTPException(409, str(e)) from e
        audit(user, "start_camera", f"#{cid} {cam['name']}")
        return mgr().get(cid).status()

    @app.post("/api/cameras/{cid}/stop")
    def stop_camera(cid: int, user: User = Depends(admin)) -> dict:
        cam = camera_or_404(cid)
        mgr().stop(cid)
        audit(user, "stop_camera", f"#{cid} {cam['name']}")
        return {"ok": True}

    @app.get("/api/cameras/{cid}/status")
    def camera_status(cid: int) -> dict:
        return running(cid).status()

    @app.get("/api/cameras/{cid}/stream.mjpg")
    def stream(cid: int) -> StreamingResponse:
        p = running(cid)

        def frames():
            seq = -1
            while mgr().get(cid) is p:
                seq, jpeg = p.wait_frame(seq)
                if jpeg is None:
                    time.sleep(0.1)
                    continue
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    @app.get("/api/cameras/{cid}/snapshot.jpg")
    def snapshot(cid: int) -> Response:
        jpeg = running(cid).latest_jpeg()
        if jpeg is None:
            raise HTTPException(404, "Chưa có hình.")
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/cameras/{cid}/playback")
    def playback(cid: int, req: PlaybackRequest) -> dict:
        p = running(cid)
        try:
            p.playback(req.action, req.value)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return p.status()

    @app.put("/api/cameras/{cid}/view")
    def set_view(cid: int, req: ViewRequest) -> dict:
        if req.mode not in VIEW_MODES:
            raise HTTPException(422, f"Chế độ phải là một trong {VIEW_MODES}")
        running(cid).set_mode(req.mode)
        return {"mode": req.mode}

    @app.get("/api/cameras/{cid}/zones")
    def get_zones(cid: int) -> dict:
        p = mgr().get(cid)
        if p is not None:
            return p.zones.to_dict()
        return ZoneSet.from_dict(camera_or_404(cid)["config"].get("zones") or {}).to_dict()

    @app.put("/api/cameras/{cid}/zones")
    def put_zones(cid: int, body: ZonesBody, user: User = Depends(admin)) -> dict:
        zones = ZoneSet.from_dict(body.model_dump())
        try:
            zones.validate()
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        p = mgr().get(cid)
        if p is not None:
            p.set_zones(zones)
        else:
            camera_or_404(cid)
            mgr()._persist(cid, "zones", zones.to_dict())
        audit(user, "set_zones", f"#{cid} {len(zones.roi)} vùng giám sát, {len(zones.exclude)} vùng loại trừ")
        return zones.to_dict()

    @app.get("/api/cameras/{cid}/rules")
    def get_rules(cid: int) -> dict:
        p = mgr().get(cid)
        return asdict(p.rule_config if p else rule_config_from(camera_or_404(cid)["config"].get("rules")))

    @app.put("/api/cameras/{cid}/rules")
    def put_rules(cid: int, body: dict, user: User = Depends(admin)) -> dict:
        current = get_rules(cid)
        try:
            config = RuleConfig(**{**current, **body})
        except TypeError as e:
            raise HTTPException(422, f"Cấu hình luật không hợp lệ: {e}") from e
        p = mgr().get(cid)
        if p is not None:
            p.set_rules(config)
        else:
            mgr()._persist(cid, "rules", asdict(config))
        changed = {k: v for k, v in asdict(config).items() if current.get(k) != v}
        audit(user, "set_rules", f"#{cid} {changed}")
        return asdict(config)

    @app.put("/api/cameras/{cid}/model")
    def set_model(cid: int, req: ModelRequest, user: User = Depends(admin)) -> dict:
        camera_or_404(cid)
        if req.name not in MODELS:
            raise HTTPException(404, f"Không có model {req.name}")
        if req.name not in app.state.models:
            path = settings.model_file(req.name)
            if not path.exists():
                raise HTTPException(404, f"Chưa có file {path.name} trong {settings.models_dir}")
            app.state.models[req.name] = load_model(path)
        mgr().set_model(cid, req.name)
        audit(user, "set_model", f"#{cid} {req.name}")
        return {"model": req.name}

    @app.put("/api/cameras/{cid}/anomaly-model")
    def set_anomaly_model(cid: int, req: AnomalyRequest, user: User = Depends(admin)) -> dict:
        p = running(cid)
        try:
            p.set_anomaly(req.name, req.norm)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from e
        audit(user, "set_anomaly_model", f"#{cid} {req.name} ({p.anomaly_norm})")
        return {"model": p.anomaly_name, "norm": p.anomaly_norm}

    @app.post("/api/cameras/{cid}/calibrate")
    def calibrate(cid: int, req: CalibrateRequest, user: User = Depends(admin)) -> dict:
        p = running(cid)
        p.calibrate(req.seconds)
        audit(user, "calibrate", f"#{cid} {req.seconds:.0f} s")
        return p.status()["calibration"]

    @app.get("/api/cameras/{cid}/series")
    def series(cid: int, minutes: float = 10) -> list[dict]:
        camera_or_404(cid)
        return db().series(cid, time.time() - minutes * 60)

    # ---------------------------------------------------------------- lịch sử cảnh báo
    def event_filters(camera_id: int | None, rule: str | None, status: str | None,
                      t0: float | None, t1: float | None) -> dict:
        return {"camera_id": camera_id, "rule": rule or None, "status": status or None, "t0": t0, "t1": t1}

    @app.get("/api/events")
    def events(camera_id: int | None = None, rule: str | None = None, status: str | None = None,
               t0: float | None = None, t1: float | None = None, limit: int = 50, offset: int = 0) -> dict:
        rows, total = db().query_events(**event_filters(camera_id, rule, status, t0, t1),
                                        limit=max(1, min(limit, 500)), offset=max(0, offset))
        return {"rows": rows, "total": total}

    @app.get("/api/events.csv")
    def events_csv(camera_id: int | None = None, rule: str | None = None, status: str | None = None,
                   t0: float | None = None, t1: float | None = None) -> Response:
        rows, _ = db().query_events(**event_filters(camera_id, rule, status, t0, t1), limit=100_000)
        buf = io.StringIO()
        cols = ["id", "t", "camera_id", "source", "rule", "value", "threshold", "message", "status", "ack_by", "ack_at",
                "note", "snapshot", "clip"]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",   # BOM để Excel đọc đúng tiếng Việt
                        headers={"Content-Disposition": 'attachment; filename="canh_bao.csv"'})

    @app.get("/api/events/{eid}/context")
    def event_context(eid: int, seconds: float = 120) -> dict:
        ev = db().get_event(eid)
        if ev is None:
            raise HTTPException(404, f"Không có cảnh báo #{eid}")
        return {"event": ev, "series": db().series(ev["camera_id"], ev["t"] - seconds, ev["t"] + seconds)}

    @app.post("/api/events/{eid}/ack")
    def ack_event(eid: int, req: AckRequest, user: User = Depends(current_user)) -> dict:
        if not db().ack_event(eid, user.name, req.note.strip()[:500]):
            raise HTTPException(404, f"Không có cảnh báo #{eid}")
        audit(user, "ack_event", f"#{eid} {req.note.strip()[:100]}")
        return db().get_event(eid)

    # ---------------------------------------------------------------- thống kê
    def tz_of(camera_id: int | None) -> str:
        cam = db().get_camera(camera_id) if camera_id is not None else None
        return cam["tz"] if cam else "UTC"

    @app.get("/api/stats")
    def stats(t0: float, t1: float, camera_id: int | None = None, bucket: int | None = None) -> dict:
        if t1 <= t0:
            raise HTTPException(422, "Khoảng thời gian không hợp lệ.")
        span = t1 - t0
        bucket = bucket or (60 if span <= 6 * 3600 else 3600 if span <= 8 * 86400 else 86400)
        tz = tz_of(camera_id)
        series_rows = [] if camera_id is None else db().stats_series(camera_id, t0, t1, bucket)
        return {"tz": tz, "bucket": bucket, "summary": db().summary(camera_id, t0, t1), "series": series_rows,
                "heatmap": db().heatmap(camera_id, t0, t1, tz), "events_by_day": db().events_by_day(camera_id, t0, t1, tz)}

    # ---------------------------------------------------------------- nhật ký
    @app.get("/api/audit")
    def audit_log(limit: int = 100, offset: int = 0, user: User = Depends(admin)) -> list[dict]:
        return db().list_audit(max(1, min(limit, 500)), max(0, offset))

    # ---------------------------------------------------------------- trạng thái trực tiếp
    @app.websocket("/api/ws")
    async def status_ws(ws: WebSocket) -> None:
        if auth.verify(ws.cookies.get(COOKIE)) is None:
            await ws.close(code=4401)
            return
        await ws.accept()
        try:
            while True:
                m = mgr()
                live = {}
                for cid in m.running_ids():
                    p = m.get(cid)
                    if p is not None:
                        live[cid] = p.status()
                await ws.send_json({"cameras": live, "unacked": db().unacked_count(),
                                    "max_cameras": settings.max_cameras})
                await asyncio.sleep(STATUS_INTERVAL_S)
        except WebSocketDisconnect:
            pass

    settings.evidence_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/evidence", StaticFiles(directory=settings.evidence_dir), name="evidence")
    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


def _purge_loop(db: Database, settings: Settings, stop: threading.Event) -> None:
    """Dọn số liệu thô và clip cũ lúc khởi động và định kỳ."""
    while not stop.is_set():
        try:
            out = db.purge(time.time(), settings.raw_days, settings.clip_days, settings.evidence_dir)
            if out["samples"] or out["clips"]:
                log.info("Đã dọn %s mẫu thô, %s clip cũ", out["samples"], out["clips"])
        except Exception:
            log.exception("Lỗi khi dọn dữ liệu cũ")
        stop.wait(PURGE_EVERY_S)
