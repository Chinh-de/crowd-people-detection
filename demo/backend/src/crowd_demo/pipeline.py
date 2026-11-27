"""Ghép các module thành hệ thống chạy liên tục.

Hai luồng:
- Luồng đọc: lấy frame ở FPS gốc, phát trễ một chút (sync.py), vẽ lớp phủ khớp frame, mã hóa JPEG cho luồng MJPEG.
- Luồng phân tích: lấy frame mới nhất, chạy model + optical flow + luật, cập nhật lớp phủ và CSDL.
Video trễ hơn thực tế khoảng một lần phân tích, đổi lại lớp phủ khớp với hình và video vẫn mượt.
"""
import json
import logging
import re
import threading
import time
from collections import deque
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
from .motion import compute_flow, flow_features, wrong_way
from .presets import DUBLIN, DUBLIN_LIVE_ID, load_preset
from .overlay import Layers, render
from .rules import RuleConfig, RuleEngine
from .samples import save_sample
from .sources import FileSource, SourceError, VideoSource, open_source
from .storage import Database, Store
from .sync import OverlaySync
from .zones import ZoneSet

SAMPLE_FEATS = 32        # số lần phân tích gần nhất lưu kèm mỗi cảnh báo (đủ cửa sổ 16 mẫu của autoencoder)
LIVE_K = 5.0             # Temple Bar/livestream: ngưỡng trung vị + 5σ (k=3 báo quá nhiều)
UPDATE_S = 60.0          # Temple Bar/livestream: cập nhật ngưỡng sau mỗi ngần này giây
LIVE_START_LIMIT = 0.75  # Temple Bar/livestream: ngưỡng trong lúc đầu, trước khi học được từ nguồn đang chạy
LIVE_GRACE_S = 10.0      # chưa cảnh báo bất thường trong mấy giây đầu
LIVE_MIN_PEOPLE = 3.0    # gần như không có người thì không cảnh báo (mốc luôn có người nên cảnh trống bị chấm điểm cao)
AUTO_CALIB_AFTER = 5     # tự học mức bình thường sau ngần này lần phân tích (để đo được tốc độ phân tích)
MAX_UPSCALE = 2.0        # không phóng frame quá 2 lần: video nhỏ (UMN 320×240) phóng lên 960 làm đầu người quá to,
                         # mô hình đếm gần như bằng 0 (đo trên UMN: 960 px → 0,2 người; 640 px → 5,5 người)

log = logging.getLogger(__name__)


class _Rate:
    """Tốc độ (lần/giây) trên cửa sổ WINDOW lần gần nhất: số khoảng chia tổng thời gian.
    Không lấy 1/khoảng cách từng lần, để hai lần sát nhau không làm số vọt lên."""

    WINDOW = 30

    def __init__(self):
        self.value = 0.0
        self._times: deque[float] = deque(maxlen=self.WINDOW)

    def tick(self, now: float) -> None:
        self._times.append(now)
        span = now - self._times[0]
        if span > 0:
            self.value = (len(self._times) - 1) / span


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
        self._recent_feats: deque = deque(maxlen=SAMPLE_FEATS)
        self.sync = OverlaySync()
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
        self._use_preset()
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
        """Đổi model khi đang chạy. Hai model cho mask và mật độ khác nhau nên mô hình bất thường học lại."""
        self.model, self.model_name = model, name
        self._changed("model", name)
        if self.state == "running":
            self.engine = RuleEngine(self.rule_config)
            if not self._use_preset():
                self.calibrate(self.settings.calib_seconds)
            elif self.monitor.initial:
                self._start_rolling()

    def _use_preset(self) -> bool:
        """Nạp mốc học sẵn hợp với nguồn và mô hình đếm đang dùng; chưa tạo mốc thì trả False (tự học như thường)."""
        spec = self.spec or {}
        source = spec.get("url") or (Path(spec["path"]).name if spec.get("path") else None)
        if spec.get("kind") == "youtube":
            source = DUBLIN_LIVE_ID                  # mọi livestream khởi đầu bằng mốc Temple Bar
        found = load_preset(self.settings.models_dir, self.model_name, source)
        if found is None:
            return False
        live = found[0] == DUBLIN                    # camera thật: mốc chỉ là ngưỡng khởi đầu, ngưỡng nới rộng hơn
        self.monitor.preload(*found, initial=live, k=LIVE_K if live else None,
                             floor=LIVE_START_LIMIT if live else 0.0)
        return True

    def set_anomaly(self, name: str, norm: str | None = None) -> None:
        """Đổi mô hình giai đoạn 2. Mô hình mới học lại ngay từ các mẫu bình thường đã thu, không cần chờ."""
        if name not in ANOMALY_MODELS:
            raise ValueError(f"Không có mô hình {name}")
        if norm is not None and norm not in NORM_MODES:
            raise ValueError(f"Cách chuẩn hóa phải là một trong {NORM_MODES}")
        self.monitor.select(name, norm)          # ném FileNotFoundError nếu thiếu file trọng số
        self.anomaly_name, self.anomaly_norm = name, self.monitor.norm_mode
        self._changed("anomaly", {"name": name, "norm": self.anomaly_norm})

    def _save_sample(self, event_id: int, alert, frame: np.ndarray, res) -> None:
        try:
            save_sample(self.settings.samples_dir / str(event_id), frame, res.density, res.mask, res.scale,
                        list(self._recent_feats),
                        {"event_id": event_id, "camera_id": self.camera_id, "camera": self.name, "t": alert.t,
                         "rule": alert.rule, "value": alert.value, "threshold": alert.threshold,
                         "count_model": self.model_name, "anomaly_model": self.monitor.name})
            self.db.mark_sample(event_id)
        except Exception:            # không lưu được mẫu thì vẫn phải tiếp tục giám sát
            log.exception("Không lưu được mẫu của cảnh báo #%s", event_id)

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
        self.monitor.start_calibration(self._calib_samples(seconds))

    def _start_rolling(self) -> None:
        self.monitor.start_rolling(self._calib_samples(self.settings.calib_seconds), self._calib_samples(UPDATE_S))

    def _calib_samples(self, seconds: float) -> int:
        return int(round(seconds * max(self._analysis_rate.value, 0.5)))

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
    def raw_frame(self) -> np.ndarray | None:
        """Frame gốc mới nhất (chưa vẽ lớp phủ, chưa thu nhỏ), dùng để chụp ảnh gắn nhãn."""
        with self._lock:
            return None if self._latest is None else self._latest[1].copy()

    def latest_jpeg(self) -> bytes | None:
        return self._jpeg

    def wait_frame(self, after_seq: int, timeout: float = 2.0) -> tuple[int, bytes | None]:
        with self._frame_cond:
            self._frame_cond.wait_for(lambda: self.frame_seq > after_seq or self._stop.is_set(), timeout=timeout)
            return self.frame_seq, self._jpeg

    def status(self) -> dict:
        src, d, m, mon = self.source, self._density, self._motion, self.monitor
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
            "counts": {"total": d.total, "roi": d.roi, "excluded": d.excluded, "max_cell": d.max_cell},
            "motion": {"speed": m.speed, "direction_deg": m.direction_deg, "entropy": m.entropy,
                       "counterflow": m.counterflow, "active_ratio": m.active_ratio},
            "perf": {"video_fps": round(self._video_rate.value, 1), "analysis_fps": round(self._analysis_rate.value, 2),
                     "analysis_ms": round(self._analysis_ms),
                     "delay_ms": round(self.sync.delay * 1000)},
            "calibration": {"done": mon.ready, "have": a_have, "need": a_need},
            "anomaly": {"model": mon.name, "label": label, "kind": kind, "umn_auc": auc, "norm": mon.norm_mode,
                        "ready": mon.ready, "learning": mon.learning, "preset": mon.preset, "have": a_have, "need": a_need,
                        "score": None if last is None else last.score, "limit": None if last is None else last.limit},
            "zones": [{"name": z.name, "count": z.count, "limit": z.limit, "direction": z.direction,
                       "wrong_share": z.wrong_share} for z in d.zones],
            "thresholds": self.engine.thresholds(),
            "active_alerts": self.engine.active(),
            "latest_event_id": self._latest_event_id,
            "sample_t": self._last_sample_t,
        }

    # ---------- luồng đọc ----------
    def _read_loop(self) -> None:
        s = self.settings
        period, next_emit = 1 / s.stream_fps, 0.0
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
            if t < next_emit - 1e-3:      # chỉ vẽ và nén theo nhịp hiển thị cố định
                continue
            next_emit = max(next_emit + period, t + period / 2)
            h, w = frame.shape[:2]
            if w > s.stream_width:        # thu nhỏ trước khi xếp hàng chờ để bộ đệm trễ không tốn RAM
                frame = cv2.resize(frame, (s.stream_width, round(h * s.stream_width / w)), interpolation=cv2.INTER_AREA)
            due = self.sync.push(t, frame)
            if due is None:
                continue
            img = render(due[0], due[1], self.mode, s.stream_width)
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
        last_t, n_done, heat_vmax, first_t = None, 0, 0.05, None
        while not self._stop.is_set():
            with self._lock:
                latest, zones = self._latest, self.zones
            if latest is None or latest[0] == last_t:
                time.sleep(0.01)
                continue
            last_t, frame = latest
            started = time.perf_counter()

            res = infer(self.model, frame, min(s.analysis_width, round(MAX_UPSCALE * frame.shape[1])))
            d = analyze_density(res.density, zones, max(1, round(s.cell_px / STRIDE)))
            motion = self._motion_stats(last_t, res, zones)
            if motion is None:      # chưa có cặp frame hợp lệ (vừa bắt đầu / luồng bị khựng): giữ số đo trước
                m, flow, valid, feats = self._motion, None, None, None
            else:
                m, flow, valid, feats = motion
            if feats is not None:
                self._recent_feats.append(feats)
            reading = None if feats is None else self.monitor.update(feats)

            wrong = None if flow is None else self._check_directions(d, zones, flow, valid)

            first_t = last_t if first_t is None else first_t
            muted = self.monitor.initial and (last_t - first_t < LIVE_GRACE_S or d.roi < LIVE_MIN_PEOPLE)
            alerts = self.engine.update(last_t, d, m, None if muted else reading)
            q = float(np.quantile(res.density, 0.999)) if res.density.size else 0.0
            heat_vmax = 0.9 * heat_vmax + 0.1 * max(q, 0.01)
            layers = Layers(density=res.density, mask=res.mask, flow=flow, flow_valid=valid, zones=zones,
                            wrong=wrong,
                            alert_active=bool(self.engine.active()), heat_vmax=heat_vmax,
                            anomaly_cells=None if reading is None else reading.cells,
                            anomaly_limit=None if reading is None else reading.limit)
            for a in alerts:
                evidence = render(frame, layers, "overlay", s.stream_width)
                self._latest_event_id = self.recorder.on_alert(a, evidence, self.source.label)
                self._save_sample(self._latest_event_id, a, frame, res)
            self.store.add_sample(last_t, self.source.label, d, m, reading)
            self.recorder.tick(last_t)

            with self._lock:
                newest_t = self._latest[0]
            interval = 1 / self._analysis_rate.value if self._analysis_rate.value > 0 else time.perf_counter() - started
            self.sync.add_layers(last_t, layers, newest_t, interval)
            self._density, self._motion, self._last_sample_t = d, m, last_t
            self._analysis_ms = (time.perf_counter() - started) * 1000
            self._analysis_rate.tick(time.monotonic())
            n_done += 1
            if n_done == AUTO_CALIB_AFTER and not self.monitor.ready and not self.monitor.learning:
                self.calibrate(s.calib_seconds)
            elif n_done == AUTO_CALIB_AFTER and self.monitor.initial:
                self._start_rolling()

    @staticmethod
    def _check_directions(d: DensityStats, zones: ZoneSet, flow: np.ndarray, valid: np.ndarray) -> np.ndarray | None:
        """Ghi phần đi ngược chiều vào từng vùng có đặt chiều; trả mask các điểm đi ngược để vẽ."""
        if not any(z.direction is not None for z in d.zones):
            return None
        wrong_all = np.zeros(valid.shape, bool)
        for z, area in zip(d.zones, zones.zone_masks(*valid.shape)):
            if z.direction is not None:
                z.wrong_share, wrong = wrong_way(flow, area & valid, z.direction)
                wrong_all |= wrong
        return wrong_all

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
