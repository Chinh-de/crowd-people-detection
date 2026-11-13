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
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .config import VIEW_MODES, Settings
from .density import analyze_density
from .domain import DensityStats, MotionStats
from .evidence import EvidenceRecorder, FrameRing
from .model import STRIDE, CountModel, infer
from .motion import compute_flow, flow_features
from .overlay import Layers, render
from .rules import RuleConfig, RuleEngine
from .sources import FileSource, SourceError, VideoSource, open_source
from .storage import Store
from .zones import ZoneSet

AUTO_CALIB_AFTER = 5     # tự học mức bình thường sau ngần này lần phân tích (để đo được tốc độ phân tích)


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
    def __init__(self, settings: Settings, model: CountModel, model_name: str = "mask"):
        self.settings, self.model, self.model_name = settings, model, model_name
        self.mode = "overlay"
        self.rule_config = RuleConfig()
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
        self.run_dir = s.runs_dir / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.store = Store(self.run_dir / "crowd.db")
        self.ring = FrameRing(s.ring_seconds + s.clip_post_s + 1)
        self.recorder = EvidenceRecorder(self.ring, self.store, self.run_dir / "evidence", s.clip_pre_s, s.clip_post_s,
                                         url_prefix=f"/evidence/{self.run_dir.name}/evidence/")
        self.zones = self._load_zones()
        self.engine = RuleEngine(self.rule_config)
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
        if self.store:
            self.store.close()
        self._reset_run_state()

    def set_model(self, name: str, model: CountModel) -> None:
        """Đổi model khi đang chạy. Hai model đếm lệch nhau nên học lại mức bình thường."""
        self.model, self.model_name = model, name
        if self.state == "running":
            self.engine = RuleEngine(self.rule_config)
            self.calibrate(self.settings.calib_seconds)

    def set_mode(self, mode: str) -> None:
        if mode not in VIEW_MODES:
            raise ValueError(f"Chế độ hiển thị không hợp lệ: {mode}")
        self.mode = mode

    def set_zones(self, zones: ZoneSet) -> None:
        zones.validate()
        with self._lock:
            self.zones = zones
        if self.spec:
            path = self.settings.zones_dir / f"{source_slug(self.spec)}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(zones.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def set_rules(self, config: RuleConfig) -> None:
        self.rule_config = config
        self.engine.config = config

    def calibrate(self, seconds: float) -> None:
        self.engine.start_calibration(seconds, time.time(), max(self._analysis_rate.value, 0.5))

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
        src, d, m = self.source, self._density, self._motion
        have, need = self.engine.calibration_progress()
        source = None
        if src is not None:
            source = {"label": src.label, "kind": self.spec.get("kind"), "live": src.live, "tz": src.tz,
                      "fps": src.fps, "size": list(src.size), "run": self.run_dir.name if self.run_dir else None}
            if isinstance(src, FileSource):
                source.update(position_s=src.position_s, duration_s=src.duration_s, paused=src.paused)
        return {
            "state": self.state, "error": self.error, "mode": self.mode, "model": self.model_name, "source": source,
            "counts": {"total": d.total, "roi": d.roi, "excluded": d.excluded, "max_cell": d.max_cell,
                       "hot_cells": len(d.hot_cells)},
            "motion": {"speed": m.speed, "direction_deg": m.direction_deg, "entropy": m.entropy,
                       "counterflow": m.counterflow, "active_ratio": m.active_ratio},
            "perf": {"video_fps": round(self._video_rate.value, 1), "analysis_fps": round(self._analysis_rate.value, 2),
                     "analysis_ms": round(self._analysis_ms)},
            "calibration": {"done": self.engine.calibrated, "have": have, "need": need},
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

            res = infer(self.model, frame, s.analysis_width)
            cell = max(1, round(s.cell_px / STRIDE))
            d = analyze_density(res.density, zones, cell, self.engine.cell_limit)
            motion = self._motion_stats(last_t, res, zones)
            if motion is None:      # chưa có cặp frame hợp lệ (vừa bắt đầu / luồng bị khựng): giữ số đo trước
                m, flow, valid = self._motion, None, None
            else:
                m, flow, valid = motion

            alerts = self.engine.update(last_t, d, m)
            dh, dw = res.density.shape
            q = float(np.quantile(res.density, 0.999)) if res.density.size else 0.0
            heat_vmax = 0.9 * heat_vmax + 0.1 * max(q, 0.01)
            layers = Layers(density=res.density, mask=res.mask, flow=flow, flow_valid=valid, zones=zones,
                            hot_cells=d.hot_cells, cell_frac=(cell / dw, cell / dh),
                            alert_active=bool(self.engine.active()), heat_vmax=heat_vmax)
            for a in alerts:
                evidence = render(frame, layers, "overlay", s.stream_width)
                self._latest_event_id = self.recorder.on_alert(a, evidence, self.source.label)
            self.store.add_sample(last_t, self.source.label, d, m)
            self.recorder.tick(last_t)

            with self._lock:
                self._layers = layers
            self._density, self._motion, self._last_sample_t = d, m, last_t
            self._analysis_ms = (time.perf_counter() - started) * 1000
            self._analysis_rate.tick(time.monotonic())
            n_done += 1
            if n_done == AUTO_CALIB_AFTER and not self.engine.calibrated:
                self.calibrate(s.calib_seconds)

    def _motion_stats(self, t: float, res, zones: ZoneSet):
        s = self.settings
        prev, cur = self.ring.nearest(t - s.flow_gap_s), self.ring.nearest(t)
        if prev is None or cur is None or not (0.05 <= cur[0] - prev[0] <= 1.0):
            return None
        flow = compute_flow(prev[1], cur[1], s.flow_width)
        fh, fw = flow.shape[:2]
        valid = zones.masks(fh, fw)["watch"]
        if res.mask is not None:
            valid = valid & (cv2.resize(res.mask.astype(np.float32), (fw, fh)) > 0.5)
        return flow_features(flow, valid, cur[0] - prev[0]), flow, valid
