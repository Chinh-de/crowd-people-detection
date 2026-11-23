"""Ghép các module thành hệ thống chạy liên tục.

Hai luồng:
- Luồng đọc: lấy frame ở FPS gốc, vẽ lớp phủ mới nhất, mã hóa JPEG cho luồng MJPEG.
- Luồng phân tích: lấy frame mới nhất, chạy model + optical flow + luật, cập nhật lớp phủ và CSDL.
Lớp phủ vì vậy trễ hơn hình đúng bằng thời gian một lần phân tích, nhưng video luôn mượt.
"""
import json
import re
import threading
import time
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from .anomaly import ANOMALY_MODELS, DEFAULT_ANOMALY, NORM_MODES, AnomalyMonitor, cell_features
from .config import VIEW_MODES, Settings
from .density import analyze_density
from .domain import DensityStats, MotionStats
from .evidence import EvidenceRecorder, FrameRing
from .model import STRIDE, CountModel, infer
from .motion import compute_flow, flow_features
from .overlay import Layers, render
from .rules import RuleConfig, RuleEngine
from .sources import FileSource, SourceError, VideoSource, open_source
from .storage import Database, Store
from .zones import ZoneSet

AUTO_CALIB_AFTER = 5     # tự học mức bình thường sau ngần này lần phân tích (để đo được tốc độ phân tích)
MAX_UPSCALE = 2.0        # không phóng frame quá 2 lần: video nhỏ (UMN 320×240) phóng lên 960 làm đầu người quá to,
                         # mô hình đếm gần như bằng 0 (đo trên UMN: 960 px → 0,2 người; 640 px → 5,5 người)


class _Rate:
    """Tốc độ (lần/giây) làm mượt bằng trung bình trượt mũ."""

    def __init__(self):
        self.value, self._last = 0.0, None

    def tick(self, now: float) -> None:
        if self._last is not None and now > self._last:
            inst = 1.0 / (now - self._last)
            self.value = inst if self.value == 0 else 0.9 * self.value + 0.1 * inst
        self._last = now


def source_slug(spec: dict) -> str:
    key = spec.get("url") or Path(spec.get("path", "source")).name
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", key)[-80:]


class Pipeline:
    """Xử lý một camera. `on_change(khóa, giá_trị)` được gọi khi người dùng đổi cấu hình (vùng, luật, mô hình,
    chế độ hiển thị) để bộ quản lý camera lưu vào cơ sở dữ liệu."""

    def __init__(self, settings: Settings, model: CountModel, model_name: str = "mask", db: Database | None = None,
                 camera_id: int = 0, name: str | None = None, on_change=None):
        self.settings, self.model, self.model_name = settings, model, model_name
        self.db = db
        self.camera_id, self.name, self.on_change = camera_id, name, on_change
        self.preset_zones: ZoneSet | None = None     # vùng lưu theo camera; None = đọc file theo nguồn (kiểu cũ)
        self.started_at: float | None = None
        self.mode = "overlay"
        self.rule_config = RuleConfig()
        self.anomaly_name, self.anomaly_norm = DEFAULT_ANOMALY, "camera"
        self._lock = threading.Lock()
        self._frame_cond = threading.Condition()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._reset_run_state()

    def _reset_run_state(self) -> None:
        self.state, self.error = "idle", None
        self.source: VideoSource | None = None
        self.spec: dict | None = None
        self.run_dir: Path | None = None
        self.store: Store | None = None
        self.zones = ZoneSet()
        self.engine = RuleEngine(self.rule_config)
        self.monitor = AnomalyMonitor(self.anomaly_name, self.settings.models_dir, self.anomaly_norm)
        self._latest: tuple[float, np.ndarray] | None = None
        self._layers: Layers | None = None
        self._jpeg: bytes | None = None
        self.frame_seq = 0
        self._video_rate, self._analysis_rate = _Rate(), _Rate()
        self._analysis_ms = 0.0
        self._density = DensityStats(0, 0, 0, np.zeros((1, 1)))
        self._motion = MotionStats()
        self._last_sample_t: float | None = None
        self._latest_event_id = 0

    # ---------- điều khiển ----------
    def start(self, spec: dict) -> None:
        self.stop()
        source = open_source(spec)                  # ném SourceError nếu không mở được
        self._reset_run_state()
        s = self.settings
        self.source, self.spec = source, spec
        if self.db is None:
            self.db = Database(s.db_path)
        self.started_at = time.time()
        self.run_dir = s.evidence_dir / str(self.camera_id)
        self.store = self.db.store(self.camera_id)
        self.ring = FrameRing(s.ring_seconds + s.clip_post_s + 1)
        self.recorder = EvidenceRecorder(self.ring, self.store, self.run_dir, s.clip_pre_s, s.clip_post_s,
                                         url_prefix=f"/evidence/{self.camera_id}/")
        self.zones = self.preset_zones if self.preset_zones is not None else self._load_zones()
        self.engine = RuleEngine(self.rule_config)
        self.monitor = AnomalyMonitor(self.anomaly_name, self.settings.models_dir, self.anomaly_norm)
        self.state = "running"
        self._stop.clear()
        self._threads = [threading.Thread(target=self._read_loop, name="crowd-reader", daemon=True),
                         threading.Thread(target=self._analyze_loop, name="crowd-analyzer", daemon=True)]
        for th in self._threads:
            th.start()

    def stop(self) -> None:
        self._stop.set()
        if self.source:
            self.source.interrupt()
        with self._frame_cond:
            self._frame_cond.notify_all()
        for th in self._threads:
            th.join(timeout=10)
        self._threads = []
        if self.source:
            self.source.close()
        self._reset_run_state()

    def set_model(self, name: str, model: CountModel) -> None:
        """Đổi model khi đang chạy. Hai model đếm lệch nhau nên học lại mức bình thường."""
        self.model, self.model_name = model, name
        self._changed("model", name)
        if self.state == "running":
            self.engine = RuleEngine(self.rule_config)
            self.calibrate(self.settings.calib_seconds)

    def set_anomaly(self, name: str, norm: str | None = None) -> None:
        """Đổi mô hình giai đoạn 2. Mô hình mới học lại ngay từ các mẫu bình thường đã thu, không cần chờ."""
        if name not in ANOMALY_MODELS:
            raise ValueError(f"Không có mô hình {name}")
        if norm is not None and norm not in NORM_MODES:
            raise ValueError(f"Cách chuẩn hóa phải là một trong {NORM_MODES}")
        self.monitor.select(name, norm)          # ném FileNotFoundError nếu thiếu file trọng số
        self.anomaly_name, self.anomaly_norm = name, self.monitor.norm_mode
        self._changed("anomaly", {"name": name, "norm": self.anomaly_norm})

    def set_mode(self, mode: str) -> None:
        if mode not in VIEW_MODES:
            raise ValueError(f"Chế độ hiển thị không hợp lệ: {mode}")
        self.mode = mode
        self._changed("view_mode", mode)

    def set_zones(self, zones: ZoneSet) -> None:
        zones.validate()
        with self._lock:
            self.zones = zones
        self.preset_zones = zones
        if self.on_change:
            self._changed("zones", zones.to_dict())
        elif self.spec:
            path = self.settings.zones_dir / f"{source_slug(self.spec)}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(zones.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def set_rules(self, config: RuleConfig) -> None:
        self.rule_config = config
        self.engine.config = config
        self._changed("rules", asdict(config))

    def _changed(self, key: str, value) -> None:
        if self.on_change:
            self.on_change(key, value)

    def calibrate(self, seconds: float) -> None:
        rate = max(self._analysis_rate.value, 0.5)
        self.engine.start_calibration(seconds, time.time(), rate)
        self.monitor.start_calibration(int(round(seconds * rate)))

    def playback(self, action: str, value: float | None = None) -> None:
        if not isinstance(self.source, FileSource):
            raise ValueError("Chỉ điều khiển phát được với video có sẵn.")
        {"pause": self.source.pause, "play": self.source.resume}.get(action, lambda: None)()
        if action == "seek" and value is not None:
            self.source.seek(value)

    def _load_zones(self) -> ZoneSet:
        path = self.settings.zones_dir / f"{source_slug(self.spec)}.json"
        if path.exists():
            return ZoneSet.from_dict(json.loads(path.read_text(encoding="utf-8")))
        return ZoneSet()

    # ---------- truy vấn ----------
    def latest_jpeg(self) -> bytes | None:
        return self._jpeg

    def wait_frame(self, after_seq: int, timeout: float = 2.0) -> tuple[int, bytes | None]:
        with self._frame_cond:
            self._frame_cond.wait_for(lambda: self.frame_seq > after_seq or self._stop.is_set(), timeout=timeout)
            return self.frame_seq, self._jpeg

    def status(self) -> dict:
        src, d, m, mon = self.source, self._density, self._motion, self.monitor
        have, need = self.engine.calibration_progress()
        a_have, a_need = mon.progress()
        last = mon.last
        label, kind, auc = ANOMALY_MODELS[mon.name]
        source = None
        if src is not None:
            source = {"label": src.label, "kind": self.spec.get("kind"), "live": src.live, "tz": src.tz,
                      "fps": src.fps, "size": list(src.size),
                      "run": f"{self.camera_id}-{int(self.started_at or 0)}"}
            if isinstance(src, FileSource):
                source.update(position_s=src.position_s, duration_s=src.duration_s, paused=src.paused)
        return {
            "camera_id": self.camera_id, "camera": self.name,
            "state": self.state, "error": self.error, "mode": self.mode, "model": self.model_name, "source": source,
            "counts": {"total": d.total, "roi": d.roi, "excluded": d.excluded, "max_cell": d.max_cell,
                       "hot_cells": len(d.hot_cells)},
            "motion": {"speed": m.speed, "direction_deg": m.direction_deg, "entropy": m.entropy,
                       "counterflow": m.counterflow, "active_ratio": m.active_ratio},
            "perf": {"video_fps": round(self._video_rate.value, 1), "analysis_fps": round(self._analysis_rate.value, 2),
                     "analysis_ms": round(self._analysis_ms)},
            "calibration": {"done": self.engine.calibrated and mon.ready, "have": have, "need": need},
            "anomaly": {"model": mon.name, "label": label, "kind": kind, "umn_auc": auc, "norm": mon.norm_mode,
                        "ready": mon.ready, "learning": mon.learning, "have": a_have, "need": a_need,
                        "score": None if last is None else last.score, "limit": None if last is None else last.limit},
            "zones": [{"name": z.name, "count": z.count, "limit": z.limit} for z in d.zones],
            "thresholds": self.engine.thresholds(),
            "active_alerts": self.engine.active(),
            "latest_event_id": self._latest_event_id,
            "sample_t": self._last_sample_t,
        }

    # ---------- luồng đọc ----------
    def _read_loop(self) -> None:
        s = self.settings
        while not self._stop.is_set():
            try:
                item = self.source.read()
            except SourceError as e:
                self.state, self.error = "error", str(e)
                return
            if item is None:
                continue
            t, frame = item
            self.ring.push(t, frame)
            with self._lock:
                self._latest = (t, frame)
                layers = self._layers
            img = render(frame, layers, self.mode, s.stream_width)
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, s.jpeg_quality])
            if ok:
                with self._frame_cond:
                    self._jpeg = buf.tobytes()
                    self.frame_seq += 1
                    self._frame_cond.notify_all()
            self._video_rate.tick(time.monotonic())

    # ---------- luồng phân tích ----------
    def _analyze_loop(self) -> None:
        s = self.settings
        last_t, n_done, heat_vmax = None, 0, 0.05
        while not self._stop.is_set():
            with self._lock:
                latest, zones = self._latest, self.zones
            if latest is None or latest[0] == last_t:
                time.sleep(0.01)
                continue
            last_t, frame = latest
            started = time.perf_counter()

            res = infer(self.model, frame, min(s.analysis_width, round(MAX_UPSCALE * frame.shape[1])))
            cell = max(1, round(s.cell_px / STRIDE))
            d = analyze_density(res.density, zones, cell, self.engine.cell_limit)
            motion = self._motion_stats(last_t, res, zones)
            if motion is None:      # chưa có cặp frame hợp lệ (vừa bắt đầu / luồng bị khựng): giữ số đo trước
                m, flow, valid, feats = self._motion, None, None, None
            else:
                m, flow, valid, feats = motion
            reading = None if feats is None else self.monitor.update(feats)

            alerts = self.engine.update(last_t, d, m, reading)
            dh, dw = res.density.shape
            q = float(np.quantile(res.density, 0.999)) if res.density.size else 0.0
            heat_vmax = 0.9 * heat_vmax + 0.1 * max(q, 0.01)
            layers = Layers(density=res.density, mask=res.mask, flow=flow, flow_valid=valid, zones=zones,
                            hot_cells=d.hot_cells, cell_frac=(cell / dw, cell / dh),
                            alert_active=bool(self.engine.active()), heat_vmax=heat_vmax,
                            anomaly_cells=None if reading is None else reading.cells,
                            anomaly_limit=None if reading is None else reading.limit)
            for a in alerts:
                evidence = render(frame, layers, "overlay", s.stream_width)
                self._latest_event_id = self.recorder.on_alert(a, evidence, self.source.label)
            self.store.add_sample(last_t, self.source.label, d, m, reading)
            self.recorder.tick(last_t)

            with self._lock:
                self._layers = layers
            self._density, self._motion, self._last_sample_t = d, m, last_t
            self._analysis_ms = (time.perf_counter() - started) * 1000
            self._analysis_rate.tick(time.monotonic())
            n_done += 1
            if n_done == AUTO_CALIB_AFTER and not self.engine.calibrated and not self.engine.learning:
                self.calibrate(s.calib_seconds)

    def _motion_stats(self, t: float, res, zones: ZoneSet):
        s = self.settings
        prev, cur = self.ring.nearest(t - s.flow_gap_s), self.ring.nearest(t)
        if prev is None or cur is None or not (0.05 <= cur[0] - prev[0] <= 1.0):
            return None
        flow = compute_flow(prev[1], cur[1], s.flow_width)
        fh, fw = flow.shape[:2]
        dt = cur[0] - prev[0]
        watch = zones.masks(fh, fw)["watch"]
        weight = watch.astype(np.float32)
        if res.mask is not None:
            prob = cv2.resize(res.mask.astype(np.float32), (fw, fh))
            weight = weight * prob
            valid = watch & (prob > 0.5)
        else:
            valid = watch
        feats = cell_features(flow, weight, res.density, res.mask, dt, watch=zones.masks(*res.density.shape)["watch"])
        return flow_features(flow, valid, dt), flow, valid, feats
