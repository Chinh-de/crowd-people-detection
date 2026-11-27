"""Giai đoạn 2: phát hiện chuyển động bất thường (hoảng loạn) bằng các mô hình đã nghiên cứu trên UMN.

Đặc trưng giống hệt notebook `anomaly_umn.ipynb`: khung được chia lưới 8×8 ô. Mỗi ô có
- 11 kênh chuyển động: tốc độ, histogram 8 hướng, entropy hướng, độ đồng hướng.
  `fm` lấy trọng số theo mask người, `f0` lấy trên toàn vùng theo dõi;
- 2 kênh mật độ `d`: số người và tỉ lệ diện tích có người, từ mô hình đếm.

Tốc độ đổi về "pixel mỗi khung 1/30 s ở ảnh rộng 320", đúng đơn vị của UMN, để dùng được thống kê
chuẩn hóa gốc của autoencoder.

Các mô hình:
- `speed`: ngưỡng tốc độ (mốc B0).
- `if_flow_mask_density`: Isolation Forest (chuyển động trong mask + mật độ), học tại chỗ trên camera trong lúc
  "học mức bình thường". Đây là biến thể tốt nhất trong nghiên cứu; hai biến thể thiếu mask hoặc mật độ không đưa vào.
- `ae_scene*`: autoencoder đã train trên từng bối cảnh UMN (file trong `models/anomaly/`).
  Chuẩn hóa theo thống kê camera (mặc định) hoặc thống kê gốc của UMN.

Ngưỡng của mọi mô hình học từ điểm trên dữ liệu bình thường của chính camera:
max(phân vị 99%, trung vị + 4 × độ lệch bền); riêng Isolation Forest là trung vị + 3 × độ lệch bền.
"""
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.ensemble import IsolationForest

GRID = 8
NBINS = 8
WIN = 16                 # số mẫu liên tiếp mỗi cửa sổ của autoencoder
TOPK = 3                 # điểm AE = trung bình 3 ô sai số lớn nhất
REF_FPS = 30.0           # UMN: 30 khung/giây
REF_WIDTH = 320          # UMN: 320×240
MIN_SAMPLES = 20
SMOOTH_N = 3             # làm mượt điểm: trung bình 3 mẫu gần nhất (~1 s ở 2–3 lần phân tích/giây)

# tên → (nhãn, loại, AUC trung bình 3 bối cảnh trên UMN trong báo cáo)
ANOMALY_MODELS: dict[str, tuple[str, str, float]] = {
    "speed": ("Ngưỡng tốc độ (B0)", "speed", 0.839),
    "if_flow_mask_density": ("Isolation Forest · flow + mask + mật độ", "if", 0.975),
    "ae_scene1": ("Autoencoder · UMN bãi cỏ", "ae", 0.989),
    "ae_scene2": ("Autoencoder · UMN trong nhà", "ae", 0.890),
    "ae_scene3": ("Autoencoder · UMN quảng trường", "ae", 0.929),
}
DEFAULT_ANOMALY = "if_flow_mask_density"
NORM_MODES = ("camera", "umn")


@dataclass
class CellFeats:
    fm: np.ndarray       # (8, 8, 11) chuyển động trong mask người
    f0: np.ndarray       # (8, 8, 11) chuyển động toàn vùng theo dõi
    d: np.ndarray        # (8, 8, 2) số người, tỉ lệ có người


@dataclass
class Reading:
    score: float
    limit: float
    cells: np.ndarray | None     # (8, 8) mức bất thường theo ô (chỉ autoencoder)


# ---------------------------------------------------------------- đặc trưng
def _cell_sum(a: np.ndarray) -> np.ndarray:
    """Tổng theo lưới 8×8 cho ảnh (h, w[, c]) bất kỳ kích thước."""
    ys = np.linspace(0, a.shape[0], GRID + 1).astype(int)[:-1]
    xs = np.linspace(0, a.shape[1], GRID + 1).astype(int)[:-1]
    return np.add.reduceat(np.add.reduceat(a, ys, axis=0), xs, axis=1)


def _cell_area(h: int, w: int) -> np.ndarray:
    return _cell_sum(np.ones((h, w), np.float32))


def _flow_cells(flow: np.ndarray, w: np.ndarray, to_ref: float) -> np.ndarray:
    fx, fy = flow[..., 0] * to_ref, flow[..., 1] * to_ref
    mag = np.hypot(fx, fy)
    ang = np.arctan2(fy, fx)
    b = ((ang + np.pi) / (2 * np.pi) * NBINS).astype(np.int64) % NBINS
    wm = w * mag
    cw, cwm = _cell_sum(w), _cell_sum(wm)
    speed = cwm / (cw + 1e-6)
    onehot = (b[..., None] == np.arange(NBINS)).astype(np.float32) * wm[..., None]
    hist = _cell_sum(onehot)
    p = hist / (cwm[..., None] + 1e-6)
    ent = -(p * np.log(p + 1e-9)).sum(-1) / np.log(NBINS)
    coh = np.hypot(_cell_sum(w * fx), _cell_sum(w * fy)) / (cwm + 1e-6)
    return np.concatenate([speed[..., None], p, ent[..., None], coh[..., None]], -1).astype(np.float32)


def cell_features(flow: np.ndarray, weight: np.ndarray, density: np.ndarray, mask: np.ndarray | None,
                  dt: float, watch: np.ndarray | None = None) -> CellFeats:
    """flow (h, w, 2) tính trong `dt` giây; weight (h, w) = xác suất có người × vùng theo dõi;
    density, mask: bản đồ của mô hình đếm (độ phân giải riêng); watch: vùng theo dõi theo kích thước density."""
    h, w = flow.shape[:2]
    to_ref = (1.0 / REF_FPS) / max(dt, 1e-6) * (REF_WIDTH / w)
    full = np.ones((h, w), np.float32) if watch is None else _resize_bool(watch, h, w)
    fm = _flow_cells(flow, weight.astype(np.float32), to_ref)
    f0 = _flow_cells(flow, full, to_ref)
    den = density if watch is None else np.where(watch, density, 0.0)
    count = _cell_sum(den.astype(np.float32))
    m = np.ones_like(density, np.float32) if mask is None else mask.astype(np.float32)
    if watch is not None:
        m = np.where(watch, m, 0.0)
    ratio = _cell_sum(m) / _cell_area(*density.shape)
    return CellFeats(fm=fm, f0=f0, d=np.stack([count, ratio], -1).astype(np.float32))


def _resize_bool(m: np.ndarray, h: int, w: int) -> np.ndarray:
    ys = np.minimum((np.arange(h) * m.shape[0] / h).astype(int), m.shape[0] - 1)
    xs = np.minimum((np.arange(w) * m.shape[1] / w).astype(int), m.shape[1] - 1)
    return m[ys][:, xs].astype(np.float32)


def frame_vectors(grid: np.ndarray) -> np.ndarray:
    """(N, 8, 8, C) → (N, 3C): trung bình, max, độ lệch chuẩn qua các ô của từng kênh."""
    flat = grid.reshape(len(grid), -1, grid.shape[-1])
    return np.concatenate([flat.mean(1), flat.max(1), flat.std(1)], 1).astype(np.float32)


def smooth(scores, n: int = SMOOTH_N) -> np.ndarray:
    """Trung bình trượt nhân quả n mẫu (như notebook), dùng cho cả điểm học lẫn điểm trực tiếp."""
    s = np.asarray(scores, np.float64)
    c = np.cumsum(np.r_[0.0, s])
    k = np.arange(1, len(s) + 1)
    lo = np.maximum(0, k - n)
    return (c[k] - c[lo]) / (k - lo)


def _limit(scores: np.ndarray, k: float = 4.0, quantile: float | None = 0.99) -> float:
    """Ngưỡng tính trên điểm đã làm mượt của dữ liệu bình thường."""
    s = smooth(scores)
    med = float(np.median(s))
    mad = 1.4826 * float(np.median(np.abs(s - med)))
    robust = med + k * max(mad, 1e-3 * abs(med), 1e-6)
    return robust if quantile is None else max(float(np.quantile(s, quantile)), robust)


# ---------------------------------------------------------------- mô hình
class SpeedDetector:
    """Mốc B0: tốc độ trung bình của người (theo mask)."""
    limit: float | None = None

    @staticmethod
    def _value(f: CellFeats) -> float:
        w = f.d[..., 1]
        return float((f.fm[..., 0] * w).sum() / (w.sum() + 1e-6)) if w.sum() > 0 else float(f.fm[..., 0].mean())

    def fit(self, samples: list[CellFeats]) -> None:
        self.limit = _limit([self._value(f) for f in samples])

    def score(self, f: CellFeats) -> tuple[float, None]:
        return self._value(f), None


class IFDetector:
    """Isolation Forest trên véc-tơ khung (trung bình, max, độ lệch chuẩn qua 64 ô)."""
    limit: float | None = None

    @staticmethod
    def _grid(f: CellFeats) -> np.ndarray:
        return np.concatenate([f.fm, f.d], -1)

    def fit(self, samples: list[CellFeats]) -> None:
        X = frame_vectors(np.stack([self._grid(f) for f in samples]))
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-6
        self.iso = IsolationForest(n_estimators=200, random_state=0).fit((X - self.mu) / self.sd)
        # Điểm IF bị chặn trên: khung nằm ngoài vùng dữ liệu train chỉ nhận điểm ngang các khung train ở rìa,
        # nên ngưỡng không dùng phân vị 99% của chính dữ liệu train (gần như không bao giờ vượt được).
        self.limit = _limit(-self.iso.score_samples((X - self.mu) / self.sd), k=3.0, quantile=None)

    def score(self, f: CellFeats) -> tuple[float, None]:
        x = (frame_vectors(self._grid(f)[None]) - self.mu) / self.sd
        return float(-self.iso.score_samples(x)[0]), None


class GridAE(nn.Module):
    """Đúng kiến trúc trong notebook: cửa sổ 16 mẫu × 13 kênh gộp thành kênh, trên lưới 8×8."""

    def __init__(self, cin: int, hid: int = 64, code: int = 16):
        super().__init__()
        self.enc = nn.Sequential(nn.Conv2d(cin, hid, 3, padding=1), nn.ReLU(inplace=True),
                                 nn.Conv2d(hid, code, 3, padding=1), nn.ReLU(inplace=True))
        self.dec = nn.Sequential(nn.Conv2d(code, hid, 3, padding=1), nn.ReLU(inplace=True),
                                 nn.Conv2d(hid, cin, 3, padding=1))

    def forward(self, x):
        return self.dec(self.enc(x))


class AEDetector:
    limit: float | None = None

    def __init__(self, weights: Path, norm: Path, norm_mode: str = "camera"):
        self.model = GridAE(WIN * 13)
        self.model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
        self.model.eval()
        z = np.load(norm)
        self.umn_mu, self.umn_sd = z["mean"].astype(np.float32), z["std"].astype(np.float32)
        self.norm_mode = norm_mode
        self.mu, self.sd = self.umn_mu, self.umn_sd
        self._win: deque[np.ndarray] = deque(maxlen=WIN)

    def _norm(self, f: CellFeats) -> np.ndarray:
        x = np.concatenate([f.fm, f.d], -1)
        return np.clip((x - self.mu) / (self.sd + 1e-3), -10, 10).transpose(2, 0, 1).astype(np.float32)

    @torch.no_grad()
    def _score_window(self, frames: list[np.ndarray]) -> tuple[float, np.ndarray]:
        frames = [frames[0]] * (WIN - len(frames)) + list(frames)        # đầu luồng: lặp mẫu đầu như notebook
        x = torch.from_numpy(np.stack(frames)).reshape(1, -1, GRID, GRID)
        err = (self.model(x) - x).pow(2).reshape(WIN, -1, GRID, GRID).mean((0, 1))
        cells = err.numpy()
        return float(np.sort(cells.ravel())[-TOPK:].mean()), cells

    def fit(self, samples: list[CellFeats]) -> None:
        if self.norm_mode == "camera":
            X = np.stack([np.concatenate([f.fm, f.d], -1) for f in samples])
            self.mu, self.sd = X.mean(0), X.std(0)
        else:
            self.mu, self.sd = self.umn_mu, self.umn_sd
        win: deque[np.ndarray] = deque(maxlen=WIN)
        scores = []
        for f in samples:
            win.append(self._norm(f))
            scores.append(self._score_window(list(win))[0])
        # Bỏ các cửa sổ khởi động (chưa đủ 16 mẫu, phải lặp mẫu đầu): sai số của chúng cao giả tạo, đẩy ngưỡng lên.
        steady = scores[WIN - 1:] if len(scores) - (WIN - 1) >= 10 else scores
        self.limit = _limit(steady)
        self._win = win            # nối tiếp cửa sổ của dữ liệu học, tránh lặp mẫu đầu khi bắt đầu chấm trực tiếp

    def score(self, f: CellFeats) -> tuple[float, np.ndarray]:
        self._win.append(self._norm(f))
        return self._score_window(list(self._win))


def make_detector(name: str, models_dir: Path | None = None, weights: Path | None = None, norm: Path | None = None,
                  norm_mode: str = "camera"):
    if name not in ANOMALY_MODELS:
        raise KeyError(name)
    kind = ANOMALY_MODELS[name][1]
    if kind == "speed":
        return SpeedDetector()
    if kind == "if":
        return IFDetector()
    scene = name.removeprefix("ae_")
    base = (models_dir or Path(".")) / "anomaly"
    weights = weights or base / f"ae_umn_{scene}.pth"
    norm = norm or base / f"ae_umn_{scene}_norm.npz"
    if not Path(weights).exists():
        raise FileNotFoundError(f"Chưa có {Path(weights).name} trong {Path(weights).parent}")
    return AEDetector(Path(weights), Path(norm), norm_mode)


def available(name: str, models_dir: Path) -> bool:
    if ANOMALY_MODELS[name][1] != "ae":
        return True
    return (models_dir / "anomaly" / f"ae_umn_{name.removeprefix('ae_')}.pth").exists()


# ---------------------------------------------------------------- điều phối
class AnomalyMonitor:
    """Giữ mẫu bình thường đã học, mô hình đang chọn và điểm gần nhất.
    Đổi mô hình hay cách chuẩn hóa thì học lại ngay từ các mẫu đã có, không cần học lại từ camera."""

    def __init__(self, name: str = DEFAULT_ANOMALY, models_dir: Path | None = None, norm_mode: str = "camera"):
        self.models_dir, self.norm_mode = models_dir, norm_mode
        self.name = name
        self.detector = make_detector(name, models_dir, norm_mode=norm_mode)
        self._samples: list[CellFeats] = []
        self._need = 0
        self.learning = False
        self.preset: str | None = None       # tên mốc học sẵn đang dùng; None = mốc học từ nguồn đang chạy
        self.last: Reading | None = None
        self._recent: deque[float] = deque(maxlen=SMOOTH_N)

    @property
    def ready(self) -> bool:
        return self.detector.limit is not None

    def progress(self) -> tuple[int, int]:
        return len(self._samples), self._need

    def preload(self, name: str, samples: list[CellFeats]) -> None:
        """Dùng mốc bình thường học sẵn: chấm điểm được ngay."""
        self.preset, self._samples, self._need, self.learning = name, list(samples), len(samples), False
        self._recent.clear()
        self.last = None
        self.detector.fit(self._samples)

    def start_calibration(self, n_samples: int) -> None:
        self.preset = None
        self._samples, self._need, self.learning = [], max(MIN_SAMPLES, n_samples), True
        self._recent.clear()
        self.detector.limit, self.last = None, None

    def select(self, name: str, norm_mode: str | None = None) -> None:
        detector = make_detector(name, self.models_dir, norm_mode=norm_mode or self.norm_mode)
        self.name, self.detector = name, detector
        self.norm_mode = norm_mode or self.norm_mode
        self.last = None
        self._recent.clear()
        if not self.learning and len(self._samples) >= MIN_SAMPLES:
            self.detector.fit(self._samples)

    def update(self, f: CellFeats) -> Reading | None:
        if self.learning:
            self._samples.append(f)
            if len(self._samples) >= self._need:
                self.detector.fit(self._samples)
                self.learning = False
            return None
        if not self.ready:
            return None
        score, cells = self.detector.score(f)
        self._recent.append(score)
        self.last = Reading(float(np.mean(self._recent)), float(self.detector.limit), cells)
        return self.last
