"""API web: chọn nguồn, luồng video MJPEG, trạng thái trực tiếp (WebSocket), cấu hình vùng và luật."""
import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import DEFAULT_MODEL, DEMO_DIR, MODELS, VIDEO_EXTS, VIEW_MODES, Settings
from .model import CountModel, load_model
from .pipeline import Pipeline
from .rules import RuleConfig
from .sources import SourceError
from .zones import ZoneSet

FRONTEND_DIST = DEMO_DIR / "frontend" / "dist"
STATUS_INTERVAL_S = 0.5


class SourceRequest(BaseModel):
    kind: Literal["file", "youtube"]
    path: str | None = None          # tên file trong data/videos
    url: str | None = None
    tz: str = "Europe/Dublin"


class PlaybackRequest(BaseModel):
    action: Literal["play", "pause", "seek"]
    value: float | None = None


class ViewRequest(BaseModel):
    mode: str


class ZonesBody(BaseModel):
    roi: list[list[tuple[float, float]]] = []
    exclude: list[list[tuple[float, float]]] = []


class ModelRequest(BaseModel):
    name: str


class CalibrateRequest(BaseModel):
    seconds: float = 60.0


def create_app(settings: Settings | None = None, model: CountModel | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        for d in (settings.videos_dir, settings.zones_dir, settings.runs_dir):
            d.mkdir(parents=True, exist_ok=True)
        app.state.models = {DEFAULT_MODEL: model or load_model(settings.model_path)}   # nạp model khác khi được chọn
        app.state.pipeline = Pipeline(settings, app.state.models[DEFAULT_MODEL], DEFAULT_MODEL)
        yield
        app.state.pipeline.stop()

    app = FastAPI(title="Giám sát đám đông", lifespan=lifespan)

    def pipe(app_: FastAPI = app) -> Pipeline:
        return app_.state.pipeline

    # ---------- model ----------
    @app.get("/api/models")
    def list_models() -> list[dict]:
        active = pipe().model_name
        out = []
        for name, (label, _) in MODELS.items():
            loaded = app.state.models.get(name)
            out.append({"name": name, "label": label, "active": name == active,
                        "available": settings.model_file(name).exists() or loaded is not None,
                        "has_mask": None if loaded is None else loaded.mask_head is not None})
        return out

    @app.put("/api/model")
    def set_model(req: ModelRequest) -> list[dict]:
        if req.name not in MODELS:
            raise HTTPException(404, f"Không có model {req.name}")
        if req.name not in app.state.models:
            path = settings.model_file(req.name)
            if not path.exists():
                raise HTTPException(404, f"Chưa có file {path.name} trong {settings.models_dir}")
            app.state.models[req.name] = load_model(path)
        pipe().set_model(req.name, app.state.models[req.name])
        return list_models()

    # ---------- nguồn video ----------
    @app.get("/api/videos")
    def list_videos() -> list[str]:
        return sorted(p.name for p in settings.videos_dir.iterdir()
                      if p.is_file() and p.suffix.lower() in VIDEO_EXTS)

    @app.post("/api/videos")
    async def upload_video(file: UploadFile) -> dict:
        name = Path(file.filename or "").name
        if Path(name).suffix.lower() not in VIDEO_EXTS:
            raise HTTPException(415, f"Chỉ hỗ trợ: {', '.join(sorted(VIDEO_EXTS))}")
        with open(settings.videos_dir / name, "wb") as fh:
            while chunk := await file.read(1 << 20):
                fh.write(chunk)
        return {"name": name}

    @app.post("/api/source")
    def start_source(req: SourceRequest) -> dict:
        if req.kind == "file":
            if not req.path:
                raise HTTPException(422, "Chưa chọn video.")
            spec = {"kind": "file", "path": str(settings.videos_dir / Path(req.path).name), "tz": req.tz}
        else:
            if not req.url:
                raise HTTPException(422, "Chưa nhập link YouTube.")
            spec = {"kind": "youtube", "url": req.url.strip(), "tz": req.tz}
        try:
            pipe().start(spec)
        except SourceError as e:
            raise HTTPException(409, str(e)) from e
        return pipe().status()

    @app.post("/api/stop")
    def stop_source() -> dict:
        pipe().stop()
        return pipe().status()

    @app.post("/api/playback")
    def playback(req: PlaybackRequest) -> dict:
        try:
            pipe().playback(req.action, req.value)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        return pipe().status()

    # ---------- hiển thị ----------
    @app.put("/api/view")
    def set_view(req: ViewRequest) -> dict:
        if req.mode not in VIEW_MODES:
            raise HTTPException(422, f"Chế độ phải là một trong {VIEW_MODES}")
        pipe().set_mode(req.mode)
        return {"mode": req.mode}

    @app.get("/api/stream.mjpg")
    def stream() -> StreamingResponse:
        p = pipe()

        def frames():
            seq = -1
            while True:
                seq, jpeg = p.wait_frame(seq)
                if jpeg is None:
                    time.sleep(0.1)
                    continue
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    # ---------- vùng và luật ----------
    @app.get("/api/zones")
    def get_zones() -> dict:
        return pipe().zones.to_dict()

    @app.put("/api/zones")
    def put_zones(body: ZonesBody) -> dict:
        zones = ZoneSet.from_dict(body.model_dump())
        try:
            pipe().set_zones(zones)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return zones.to_dict()

    @app.get("/api/rules")
    def get_rules() -> dict:
        return asdict(pipe().rule_config)

    @app.put("/api/rules")
    def put_rules(body: dict) -> dict:
        merged = {**asdict(pipe().rule_config), **body}
        try:
            config = RuleConfig(**merged)
        except TypeError as e:
            raise HTTPException(422, f"Cấu hình luật không hợp lệ: {e}") from e
        pipe().set_rules(config)
        return asdict(config)

    @app.post("/api/calibrate")
    def calibrate(req: CalibrateRequest) -> dict:
        pipe().calibrate(req.seconds)
        return pipe().status()["calibration"]

    # ---------- dữ liệu ----------
    @app.get("/api/series")
    def series(minutes: float = 10) -> list[dict]:
        store = pipe().store
        return [] if store is None else store.series(time.time() - minutes * 60)

    @app.get("/api/events")
    def events(limit: int = 50) -> list[dict]:
        store = pipe().store
        return [] if store is None else store.events(limit)

    @app.websocket("/api/ws")
    async def status_ws(ws: WebSocket) -> None:
        await ws.accept()
        try:
            while True:
                await ws.send_json(pipe().status())
                await asyncio.sleep(STATUS_INTERVAL_S)
        except WebSocketDisconnect:
            pass

    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/evidence", StaticFiles(directory=settings.runs_dir), name="evidence")
    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app
