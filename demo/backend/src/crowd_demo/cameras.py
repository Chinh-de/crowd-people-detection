"""Quản lý danh sách camera: lưu cấu hình trong SQLite, bật/tắt pipeline, giới hạn số camera chạy cùng lúc.

Mỗi camera đang chạy là một `Pipeline` (một luồng đọc + một luồng phân tích). Mô hình đếm được nạp một lần và
dùng chung. Cấu hình người dùng đổi trên web (vùng, luật, mô hình, chế độ hiển thị) được ghi lại vào camera
nên bật lại hay khởi động lại server vẫn giữ nguyên.
"""
import json
import logging
import threading
from dataclasses import asdict, fields
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .anomaly import DEFAULT_ANOMALY, NORM_MODES
from .config import DEFAULT_MODEL, VIDEO_EXTS, Settings
from .model import CountModel
from .pipeline import Pipeline, source_slug
from .rules import RuleConfig
from .zones import ZoneSet

log = logging.getLogger(__name__)
KINDS = ("file", "youtube")
DEFAULT_LIVE_URL = "https://www.youtube.com/watch?v=3nyPER2kzqk"
UMN_CAMERAS = (("UMN · bãi cỏ", "umn_bai_co.avi"), ("UMN · trong nhà", "umn_trong_nha.avi"),
               ("UMN · quảng trường", "umn_quang_truong.avi"))


class CameraLimitError(RuntimeError):
    pass


def rule_config_from(saved: dict | None) -> RuleConfig:
    """Cấu hình luật đã lưu → RuleConfig; bỏ khóa cũ không còn dùng, thiếu khóa thì lấy mặc định."""
    base = asdict(RuleConfig())
    names = {f.name for f in fields(RuleConfig)}
    merged = {**base, **{k: v for k, v in (saved or {}).items() if k in names}}
    merged["enabled"] = {**base["enabled"], **(saved or {}).get("enabled", {})}
    return RuleConfig(**merged)


class CameraManager:
    def __init__(self, settings: Settings, db, models: dict[str, CountModel]):
        self.settings, self.db, self.models = settings, db, models
        self._pipelines: dict[int, Pipeline] = {}
        self._lock = threading.RLock()

    # ---------------------------------------------------------------- kiểm tra dữ liệu
    def _validate(self, data: dict) -> dict:
        name = str(data.get("name", "")).strip()
        kind, source, tz = data.get("kind"), str(data.get("source", "")).strip(), data.get("tz") or "UTC"
        if not name or len(name) > 80:
            raise ValueError("Tên camera phải có từ 1 đến 80 ký tự.")
        if kind not in KINDS:
            raise ValueError("Loại nguồn phải là 'file' hoặc 'youtube'.")
        if kind == "file":
            if Path(source).name != source or Path(source).suffix.lower() not in VIDEO_EXTS:
                raise ValueError("Video phải là tên một file trong thư mục video.")
            if not (self.settings.videos_dir / source).exists():
                raise ValueError(f"Không có video {source}.")
        elif not source.startswith(("http://", "https://")):
            raise ValueError("Link livestream phải bắt đầu bằng http:// hoặc https://")
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"Múi giờ không hợp lệ: {tz}") from e
        return {"name": name, "kind": kind, "source": source, "tz": tz, "autostart": bool(data.get("autostart", False))}

    # ---------------------------------------------------------------- CRUD
    def create(self, data: dict) -> int:
        v = self._validate(data)
        return self.db.create_camera(v["name"], v["kind"], v["source"], v["tz"], v["autostart"], data.get("config") or {})

    def update(self, camera_id: int, data: dict) -> None:
        cam = self.db.get_camera(camera_id)
        if cam is None:
            raise KeyError(camera_id)
        v = self._validate({**cam, **data})
        self.db.update_camera(camera_id, **v)
        with self._lock:
            p = self._pipelines.get(camera_id)
        if p is None:
            return
        if any(v[k] != cam[k] for k in ("kind", "source", "tz")):
            self.stop(camera_id)                         # đổi nguồn: chạy lại với nguồn mới
            self.start(camera_id)
        else:
            p.name = v["name"]

    def delete(self, camera_id: int) -> None:
        self.stop(camera_id)
        self.db.delete_camera(camera_id)

    # ---------------------------------------------------------------- chạy / dừng
    def running_ids(self) -> list[int]:
        with self._lock:
            return list(self._pipelines)

    def get(self, camera_id: int) -> Pipeline | None:
        with self._lock:
            return self._pipelines.get(camera_id)

    def start(self, camera_id: int) -> Pipeline:
        with self._lock:
            if camera_id in self._pipelines:
                return self._pipelines[camera_id]
            cam = self.db.get_camera(camera_id)
            if cam is None:
                raise KeyError(camera_id)
            if len(self._pipelines) >= self.settings.max_cameras:
                raise CameraLimitError(
                    f"Đang chạy {len(self._pipelines)}/{self.settings.max_cameras} camera: đây là giới hạn phần cứng "
                    "(mỗi camera cần một luồng phân tích trên CPU). Hãy tắt bớt một camera.")
            p = self._build(cam)
            p.start(self._spec(cam))                     # ném SourceError nếu không mở được nguồn
            self._pipelines[camera_id] = p
            return p

    def stop(self, camera_id: int) -> None:
        with self._lock:
            p = self._pipelines.pop(camera_id, None)
        if p is not None:
            p.stop()

    def stop_all(self) -> None:
        for cid in self.running_ids():
            self.stop(cid)

    def autostart(self) -> None:
        for cam in self.db.list_cameras():
            if cam["autostart"]:
                try:
                    self.start(cam["id"])
                except Exception as e:                   # nguồn lỗi không được làm hỏng lúc khởi động
                    log.warning("Không tự chạy được camera %s: %s", cam["name"], e)

    def _spec(self, cam: dict) -> dict:
        if cam["kind"] == "file":
            return {"kind": "file", "path": str(self.settings.videos_dir / cam["source"]), "tz": cam["tz"]}
        return {"kind": "youtube", "url": cam["source"], "tz": cam["tz"]}

    def _build(self, cam: dict) -> Pipeline:
        cfg, cid = cam["config"], cam["id"]
        model_name = cfg.get("model") if cfg.get("model") in self.models else (
            DEFAULT_MODEL if DEFAULT_MODEL in self.models else next(iter(self.models)))
        p = Pipeline(self.settings, self.models[model_name], model_name, self.db, cid, cam["name"],
                     on_change=lambda key, value: self._persist(cid, key, value))
        p.mode = cfg.get("view_mode", "overlay")
        p.rule_config = rule_config_from(cfg.get("rules"))
        p.anomaly_name = DEFAULT_ANOMALY                 # web chỉ dùng Isolation Forest
        p.anomaly_norm = cfg.get("anomaly_norm") if cfg.get("anomaly_norm") in NORM_MODES else "camera"
        if cfg.get("zones"):
            p.preset_zones = ZoneSet.from_dict(cfg["zones"])
        return p

    def _persist(self, camera_id: int, key: str, value) -> None:
        with self._lock:
            cam = self.db.get_camera(camera_id)
            if cam is None:
                return
            cfg = cam["config"]
            if key == "anomaly":
                cfg["anomaly_model"], cfg["anomaly_norm"] = value["name"], value["norm"]
            else:
                cfg[key] = value
            self.db.update_camera(camera_id, config=cfg)

    def set_model(self, camera_id: int, name: str) -> None:
        if name not in self.models:
            raise ValueError(f"Chưa nạp mô hình {name}")
        p = self.get(camera_id)
        if p is None:
            self._persist(camera_id, "model", name)
        else:
            p.set_model(name, self.models[name])

    # ---------------------------------------------------------------- tổng quan
    def list(self) -> list[dict]:
        out = []
        for cam in self.db.list_cameras():
            p = self.get(cam["id"])
            st = p.status() if p else None
            out.append({
                "id": cam["id"], "name": cam["name"], "kind": cam["kind"], "source": cam["source"], "tz": cam["tz"],
                "autostart": cam["autostart"], "running": p is not None,
                "state": st["state"] if st else "stopped", "error": st["error"] if st else None,
                "roi": st["counts"]["roi"] if st else None,
                "active_alerts": st["active_alerts"] if st else [],
                "analysis_fps": st["perf"]["analysis_fps"] if st else None,
                "model": cam["config"].get("model", DEFAULT_MODEL),
                "anomaly_model": DEFAULT_ANOMALY,
            })
        return out

    # ---------------------------------------------------------------- dữ liệu mẫu
    def seed_defaults(self) -> None:
        """Chạy mỗi lần khởi động. Lần đầu (chưa có camera): tạo sẵn camera Temple Bar. Ba video UMN tách theo bối
        cảnh luôn được thêm nếu có file mà chưa camera nào dùng. Vùng đã vẽ lấy từ data/zones/."""
        vids = self.settings.videos_dir
        cameras = self.db.list_cameras()
        samples = []
        if not cameras:
            samples.append(("Temple Bar · trực tiếp", "youtube", DEFAULT_LIVE_URL, "Europe/Dublin"))
            if (vids / "part_1794421962_000.webm").exists():
                samples.append(("Temple Bar · bản ghi", "file", "part_1794421962_000.webm", "Europe/Dublin"))
        used = {c["source"] for c in cameras}
        samples += [(name, "file", source, "UTC") for name, source in UMN_CAMERAS
                    if source not in used and (vids / source).exists()]
        for name, kind, source, tz in samples:
            spec = {"url": source} if kind == "youtube" else {"path": source}
            zfile = self.settings.zones_dir / f"{source_slug(spec)}.json"
            config = {"zones": json.loads(zfile.read_text(encoding="utf-8"))} if zfile.exists() else {}
            self.db.create_camera(name, kind, source, tz, False, config)
