# Demo giám sát đám đông (web local) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Web app chạy local trên CPU: phát video (file có sẵn, gồm cả webm, hoặc livestream YouTube) ở FPS gốc, phủ kết quả đếm người / khoanh vùng / chuyển động lên hình, ROI và vùng loại trừ vẽ trên web, cảnh báo bất thường theo mật độ và chuyển động, lưu SQLite kèm ảnh và clip bằng chứng. Kèm theo báo cáo đề tài dạng Markdown (`baocao.md`) tổng hợp toàn bộ dự án.

**Architecture:** Backend FastAPI (Python, quản lý bằng uv) gồm các module thuần, mỗi module một trách nhiệm, được ghép bởi `Pipeline`. Pipeline có hai luồng: luồng đọc video ở FPS gốc và luồng phân tích chạy model MobileCount + Mask và Farneback trên frame mới nhất, 1 đến 5 lần mỗi giây tùy CPU. Endpoint MJPEG ghép lớp phủ mới nhất lên mỗi frame. Frontend React + Vite hiển thị luồng MJPEG, nhận trạng thái qua WebSocket và gọi REST để cấu hình.

**Tech Stack:** Python 3.12, uv, FastAPI, uvicorn, PyTorch CPU, torchvision, OpenCV, yt-dlp + deno, imageio-ffmpeg (ghi clip H.264), SQLite (sqlite3 chuẩn), pytest. Frontend: React 18, TypeScript, Vite, Recharts.

**Spec:** Yêu cầu trong hội thoại ngày 2026-11-13, dựa trên `de.md` mục 3.1–3.4, 4.1–4.2, 5.3. Notebook `app_shinsaibashi.ipynb` là bản tham chiếu cho model, ROI và các luật mật độ.

## Global Constraints

- Thư mục mới `demo/`, gồm `demo/backend` (uv) và `demo/frontend` (Vite React TypeScript).
- Model: `D:\Study_space\Ki9\ATTT\project\model.pth`, tức `../../model.pth` tính từ `demo/backend`, ghi đè được bằng biến môi trường `CROWD_MODEL`. Checkpoint là MobileCount + Mask (có `mask_head.*`, không có ASPP). Loader tự nhận biết `mask_head` và `deep.branches`.
- Chạy hoàn toàn trên CPU. Torch lấy từ index CPU của PyTorch.
- Video hiển thị ở FPS gốc của nguồn. Lớp phủ cập nhật theo tốc độ phân tích và có thể trễ hơn hình.
- 4 chế độ hiển thị: `video` (chỉ video), `overlay` (video + lớp nhận diện), `overlay_only` (chỉ lớp nhận diện trên nền đen), `gray` (video xám + lớp nhận diện).
- Optical flow: chỉ dùng **Farneback** (`cv2.calcOpticalFlowFarneback`), không dùng model.
- Chữ trên giao diện bằng tiếng Việt. Giao diện **không** hiển thị tính năng chưa làm. Mọi phần chưa làm (autoencoder, RAFT, thông báo email/Telegram, đa camera, hiệu chỉnh phối cảnh, đánh giá UMN, MAE trên camera thật) chỉ ghi ở `demo/README.md`, mục "Hướng phát triển".
- Mật độ: density stride 4, `DENSITY_SCALE = 100`, chuẩn hóa ImageNet; số người bằng tổng density.
- Thời gian lưu dạng UTC epoch (giây). Khi hiển thị, đổi sang múi giờ của nguồn (`tz`, mặc định `Europe/Dublin`).
- Dữ liệu chạy (video, CSDL, bằng chứng, zones) nằm trong `demo/data/` và được thêm vào `.gitignore`.
- Báo cáo đề tài: `baocao.md` ở thư mục gốc dự án, ảnh trong `report_assets/`. Người đọc là giảng viên. Số liệu chỉ lấy từ kết quả đã chạy thật; số chưa có ghi rõ `[CẦN BỔ SUNG: ...]`, không bịa.
- Dự án chưa phải git repo, nên các bước "commit" được thay bằng điểm kiểm tra. Không tự `git init`.
- Cài đặt chỉ diễn ra bên trong `demo/`: `uv sync` (tạo `demo/backend/.venv`) và `npm install` (tạo `demo/frontend/node_modules`). Không cài gì ra ngoài hai thư mục này.

## Review Focus

- **Link YouTube sai, hoặc livestream rớt kết nối giữa chừng:** nguồn tự kết nối lại tối đa 5 lần, sau đó trạng thái chuyển `error` kèm thông báo tiếng Việt hiện trên UI. Server không được treo. Test: `test_youtube_source_reports_error_on_bad_url` (Task 6).
- **Video file chạy hết:** phát lặp lại từ đầu, giữ nguyên dữ liệu thống kê và CSDL. Test: `test_file_source_loops` (Task 6).
- **Đổi nguồn khi pipeline đang chạy:** luồng cũ dừng hẳn, không rò thread hay file, và luồng MJPEG chuyển sang nguồn mới. Test: `test_switch_source_stops_old_threads` (Task 8).
- **Polygon vùng không hợp lệ** (dưới 3 điểm, tọa độ ngoài khoảng 0–1): API trả 422 và giữ cấu hình cũ. Không có ROI nào thì coi cả khung là ROI. Test: `test_put_zones_rejects_invalid_polygon` (Task 9), `test_no_roi_means_full_frame` (Task 2).
- **Bấm "Học mức bình thường" khi chưa đủ mẫu, hoặc chưa calibrate:** không có cảnh báo thống kê (chỉ chạy ngưỡng tuyệt đối nếu người dùng đặt), và UI hiện "đang học (n/N mẫu)". Test: `test_no_statistical_alert_before_calibration` (Task 4).

---

## File Structure

```
demo/
  README.md                      # cài đặt, chạy, kiến trúc, cách dùng, hướng phát triển
  .gitignore
  data/                          # tạo khi chạy: videos/, zones/, runs/<run_id>/{crowd.db, evidence/}
  backend/
    pyproject.toml  .python-version (3.12)
    src/crowd_demo/
      config.py      # Settings: đường dẫn, kích thước phân tích, mặc định ngưỡng
      model.py       # CountModel, load_model, infer → DensityResult
      zones.py       # ZoneSet (ROI, vùng loại trừ, chuẩn hóa 0–1), mask theo kích thước
      density.py     # analyze_density → DensityStats (đếm theo vùng, ô lưới)
      motion.py      # FlowEstimator (Farneback) + flow_features → MotionStats
      rules.py       # Calibrator, RuleEngine → Alert (5 luật)
      overlay.py     # render(frame, layers, mode) → frame
      storage.py     # SQLite: samples, events
      evidence.py    # FrameRing + lưu ảnh, clip H.264 trước/sau sự kiện
      sources.py     # FileSource, YouTubeSource, open_source
      pipeline.py    # Pipeline: luồng đọc + luồng phân tích, trạng thái mới nhất
      api.py         # FastAPI: REST, WebSocket, MJPEG, file tĩnh bằng chứng
      main.py        # điểm chạy `uv run crowd-demo`
    tests/           # pytest, mỗi module một file; conftest tạo video tổng hợp
  frontend/
    package.json  vite.config.ts (proxy /api → :8000)  tsconfig.json  index.html
    src/
      main.tsx  App.tsx  styles.css
      types.ts                    # kiểu khớp với schema API
      api.ts                      # các hàm REST có kiểu + kết nối WebSocket
      hooks/useLiveStatus.ts      # trạng thái trực tiếp qua WebSocket
      components/
        SourcePanel.tsx           # chọn video có sẵn, upload, hoặc dán link YouTube + múi giờ
        VideoStage.tsx            # <img> MJPEG + <canvas> vẽ vùng
        ModeSwitch.tsx            # 4 chế độ hiển thị
        ZoneEditor.tsx            # công cụ vẽ ROI, vùng loại trừ, lưu
        StatsPanel.tsx            # số người, chuyển động, FPS
        RulesPanel.tsx            # ngưỡng, nút học mức bình thường
        CountChart.tsx            # biểu đồ số người, tốc độ
        AlertList.tsx             # danh sách cảnh báo, ảnh nhỏ, xem clip
```

## Shared types (Python, `dataclasses`, dùng xuyên suốt)

```python
@dataclass
class DensityResult:  density: np.ndarray; mask: np.ndarray | None; scale: float   # density (H/4, W/4); scale = analysis_w / frame_w
@dataclass
class DensityStats:   total: float; roi: float; excluded: float; cells: np.ndarray; hot_cells: list[tuple[int, int]]; max_cell: float
@dataclass
class MotionStats:    speed: float; direction_deg: float; entropy: float; counterflow: float; active_ratio: float
@dataclass
class Alert:          rule: str; t: float; value: float; threshold: float; message: str
```

Tên luật dùng trong toàn hệ thống: `overcrowd`, `hot_cell`, `surge`, `panic`, `counterflow`.

---

### Task 1: Khung backend và model

**Files:**
- Create: `demo/.gitignore`, `demo/backend/pyproject.toml`, `demo/backend/.python-version`, `demo/backend/src/crowd_demo/__init__.py`, `config.py`, `model.py`
- Test: `demo/backend/tests/test_model.py`

**Interfaces:**
- Produces: `Settings` (dataclass, đọc env `CROWD_MODEL`, `CROWD_DATA`): `model_path`, `data_dir`, `analysis_width=960`, `cell_px=64`, `flow_width=320`, `flow_gap_s=0.2`, `ring_seconds=6`, `clip_pre_s=5`, `clip_post_s=5`, `stream_width=960`, `jpeg_quality=80`, `calib_seconds=60`.
- Produces: `load_model(path: Path) -> CountModel` (eval, CPU); `infer(model, frame_bgr: np.ndarray, analysis_width: int) -> DensityResult`.

- [ ] **Step 1: Viết `pyproject.toml`.** Tên `crowd-demo`, `requires-python = ">=3.12,<3.13"`. Dependencies: `fastapi`, `uvicorn[standard]`, `python-multipart`, `numpy`, `opencv-python`, `torch`, `torchvision`, `yt-dlp[default]`, `deno`, `imageio-ffmpeg`. Dev: `pytest`, `httpx`. Script: `crowd-demo = "crowd_demo.main:run"`. Torch và torchvision lấy từ index `pytorch-cpu` (`https://download.pytorch.org/whl/cpu`, `explicit = true`) qua `[tool.uv.sources]`.
- [ ] **Step 2: Viết test**

```python
def test_load_model_detects_mask_head():
    m = load_model(Settings().model_path)
    assert m.mask_head is not None

def test_infer_shapes_and_count():
    frame = np.zeros((720, 1280, 3), np.uint8)
    r = infer(load_model(Settings().model_path), frame, analysis_width=960)
    assert r.density.shape == (math.ceil(540 / 4), 960 // 4)
    assert r.mask is not None and r.mask.shape == r.density.shape
    assert abs(r.scale - 0.75) < 1e-6
    assert r.density.sum() < 5          # ảnh đen: gần như không có người
```
Test bị bỏ qua (`pytest.skip`) nếu không có file model.

- [ ] **Step 3: Chạy test, mong đợi FAIL** (`uv run pytest tests/test_model.py -v` báo lỗi import).
- [ ] **Step 4: Viết `model.py`.** `CountModel` chép từ ô "1. Model" của `app_shinsaibashi.ipynb`: CRP, ASPP, CountModel với `torchvision.models.mobilenet_v2(weights=None)`. `infer` làm các bước: resize về `analysis_width` giữ tỉ lệ, đệm lên bội số của 32, chuẩn hóa ImageNet, chạy `torch.inference_mode()`, cắt về `ceil(h/4) × ceil(w/4)`, chia `DENSITY_SCALE`, mask = sigmoid. Gọi `torch.set_num_threads(max(1, os.cpu_count() - 2))` một lần khi load.
- [ ] **Step 5: Chạy `uv sync` rồi `uv run pytest tests/test_model.py -v`, mong đợi PASS.**

### Task 2: Vùng giám sát và thống kê mật độ

**Files:** Create `zones.py`, `density.py`. Test `tests/test_zones.py`, `tests/test_density.py`.

**Interfaces:**
- Produces: `Polygon = list[tuple[float, float]]` (chuẩn hóa 0–1). `ZoneSet(roi: list[Polygon], exclude: list[Polygon])` có `validate()` (ném `ValueError` khi polygon dưới 3 điểm hoặc tọa độ ngoài 0–1), `masks(h, w) -> dict[str, np.ndarray]` gồm khóa `roi`, `exclude`, `watch`, có cache theo `(h, w)`, `to_dict()` và `from_dict()`.
- Produces: `analyze_density(den: np.ndarray, zones: ZoneSet, cell: int, cell_limit: float | None) -> DensityStats`. `cell` tính theo ô density, bằng `round(cell_px * scale / 4)`. `hot_cells` là các ô có giá trị lớn hơn `cell_limit`.

- [ ] **Step 1: Viết test**

```python
def test_no_roi_means_full_frame():
    m = ZoneSet([], []).masks(10, 20); assert m["watch"].all()
def test_exclude_removed_from_watch():
    z = ZoneSet([[(0,0),(1,0),(1,1),(0,1)]], [[(0,0),(0.5,0),(0.5,1),(0,1)]])
    m = z.masks(10, 20); assert m["watch"][:, :10].sum() == 0 and m["watch"][:, 11:].all()
def test_validate_rejects_short_polygon():
    with pytest.raises(ValueError): ZoneSet([[(0,0),(1,1)]], []).validate()
def test_analyze_density_counts_by_zone():
    den = np.zeros((40, 40)); den[5, 5] = 3; den[30, 30] = 2
    z = ZoneSet([[(0,0),(0.5,0),(0.5,0.5),(0,0.5)]], [])
    s = analyze_density(den, z, cell=8, cell_limit=2.5)
    assert s.total == pytest.approx(5) and s.roi == pytest.approx(3)
    assert s.max_cell == pytest.approx(3) and s.hot_cells == [(0, 0)]
```

- [ ] **Step 2: FAIL. Step 3: Cài đặt** bằng `cv2.fillPoly` trên tọa độ nhân `(w, h)`, rồi cộng density theo ô lưới bằng padding và `reshape` (như hàm `cell_sums` trong notebook). **Step 4: PASS.**

### Task 3: Chuyển động bằng Farneback

**Files:** Create `motion.py`. Test `tests/test_motion.py`.

**Interfaces:**
- Produces: `compute_flow(prev_bgr, cur_bgr, width: int) -> np.ndarray`, trả về (h, w, 2) tính trên ảnh xám đã thu nhỏ về `width`. Tham số Farneback: `pyr_scale=0.5, levels=3, winsize=15, iterations=3, poly_n=5, poly_sigma=1.2, flags=0`.
- Produces: `flow_features(flow: np.ndarray, valid: np.ndarray | None, dt: float, min_mag: float = 0.5) -> MotionStats`.
  - `speed`: độ dài vector trung bình trên các điểm đang chuyển động, chia `dt`, đơn vị px/s ở độ phân giải flow.
  - `direction_deg`: góc của tổng các vector (hướng chính).
  - `entropy`: entropy của histogram 16 ngăn hướng có trọng số độ dài, chuẩn hóa về 0–1.
  - `counterflow`: tỉ lệ trọng số các vector lệch hơn 120° so với hướng chính.
  - `active_ratio`: tỉ lệ điểm hợp lệ có độ dài ≥ `min_mag`.
  - `valid`: mask người × mask vùng giám sát, resize về kích thước flow. Không có điểm đang chuyển động thì mọi giá trị bằng 0.

- [ ] **Step 1: Viết test trên flow tổng hợp (không cần ảnh):**

```python
def uniform(dx, dy, h=40, w=40): f = np.zeros((h, w, 2), np.float32); f[..., 0] = dx; f[..., 1] = dy; return f
def test_uniform_flow_low_entropy_no_counterflow():
    s = flow_features(uniform(2, 0), None, dt=0.2)
    assert s.entropy < 0.05 and s.counterflow == 0 and s.speed == pytest.approx(10) and abs(s.direction_deg) < 1
def test_opposite_halves_counterflow():
    f = uniform(2, 0); f[:, :20, 0] = -2; f[:, :15, 0] = 2      # 25/40 sang phải, 15/40 sang trái
    assert flow_features(f, None, dt=1).counterflow == pytest.approx(15 / 40, abs=0.02)
def test_random_directions_high_entropy():
    a = np.random.default_rng(0).uniform(0, 2*np.pi, (40, 40)); f = np.stack([np.cos(a), np.sin(a)], -1) * 3
    assert flow_features(f.astype(np.float32), None, dt=1).entropy > 0.9
def test_valid_mask_and_still_scene():
    assert flow_features(uniform(0, 0), None, dt=1).speed == 0
    v = np.zeros((40, 40), bool); assert flow_features(uniform(2, 0), v, dt=1).active_ratio == 0
def test_compute_flow_detects_shift():
    img = np.random.default_rng(1).integers(0, 255, (240, 320, 3), np.uint8)
    flow = compute_flow(img, np.roll(img, 4, axis=1), width=320)
    assert np.median(flow[20:-20, 20:-20, 0]) == pytest.approx(4, abs=1)
```

- [ ] **Step 2: FAIL. Step 3: Cài đặt. Step 4: PASS.**

### Task 4: Luật cảnh báo

**Files:** Create `rules.py`. Test `tests/test_rules.py`.

**Interfaces:**
- Produces: `RuleConfig` (dataclass, đổi được qua API):
  - `k_sigma=3.0`, `persist=3`, `smooth=3`;
  - `surge_window_s=60`, `surge_abs=15`, `surge_rel=0.5`;
  - `cell_factor=1.3`, `min_cell_limit=2.0`;
  - `panic_k=4.0`, `counterflow_k=4.0`;
  - `count_limit: float | None = None` (ngưỡng tuyệt đối, có hiệu lực cả khi chưa calibrate);
  - `enabled: dict[str, bool]`, mặc định cả 5 luật đều bật.
- Produces: `RuleEngine(config)`:
  - `start_calibration(seconds: float, now: float)`.
  - `calibration_progress() -> tuple[int, int]`, trả về số mẫu đã có và số mẫu cần, với số mẫu cần = `seconds × tốc độ phân tích ước tính`, tối thiểu 10.
  - `update(t: float, d: DensityStats, m: MotionStats) -> list[Alert]`.
  - `cell_limit` (property, `None` khi chưa calibrate).
  - `thresholds() -> dict`: ngưỡng hiện tại, để hiển thị trên UI.
- Năm luật:

  | Luật | Điều kiện |
  |---|---|
  | `overcrowd` | roi (đã làm mượt) > trung vị + k·max(1,4826·MAD, 0,05·trung vị, 1), hoặc > `count_limit` |
  | `hot_cell` | max_cell (đã làm mượt) > max(min_cell_limit, cell_factor × phân vị 95 của max_cell khi calibrate) |
  | `surge` | roi − trung vị(roi trong [t−W, t−W/3]) > max(surge_abs, surge_rel × trung vị đó) |
  | `panic` | speed > trung vị + panic_k·σ **và** entropy > trung vị + panic_k·σ, chỉ khi active_ratio > 0,02 |
  | `counterflow` | counterflow > trung vị + counterflow_k·σ |

  - σ = max(1,4826·MAD, 1e-3).
  - Mỗi luật phải đúng `persist` lần liên tiếp mới sinh `Alert`.
  - Mỗi đợt chỉ sinh **một** Alert, lúc bắt đầu. Đợt kết thúc khi điều kiện hết đúng.
  - `message` là câu tiếng Việt, ví dụ `"Quá đông: 87 người (ngưỡng 64)"`.

- [ ] **Step 1: Viết test dùng helper `feed(engine, rois, speeds=..., entropies=...)`:**
  - `test_no_statistical_alert_before_calibration`: chuỗi 200 người không sinh cảnh báo khi `count_limit=None`. Khi `count_limit=100` thì sinh đúng 1 cảnh báo `overcrowd`.
  - `test_overcrowd_after_calibration_with_persistence`: calibrate trên 60 mẫu khoảng 60±3, sau đó 2 mẫu 120 không sinh gì, mẫu 120 thứ 3 sinh 1 `overcrowd`, các mẫu 120 tiếp theo không sinh thêm.
  - `test_surge_detected_on_fast_rise`: t cách nhau 2 s; 40 mẫu ở mức 60, rồi tăng 60 → 110 trong 10 mẫu. Có `surge` và thời điểm phát hiện ≤ 8 mẫu sau khi bắt đầu tăng.
  - `test_panic_requires_speed_and_entropy`: chỉ tốc độ tăng thì không báo; tốc độ và entropy cùng tăng thì báo `panic`.
  - `test_counterflow_alert`: calibrate với counterflow khoảng 0,1, sau đó 0,5 thì báo.
- [ ] **Step 2: FAIL. Step 3: Cài đặt** bằng `collections.deque` cho cửa sổ làm mượt và lịch sử surge; thống kê calibrate lưu một lần khi đủ mẫu. **Step 4: PASS.**

### Task 5: Lưu trữ và bằng chứng

**Files:** Create `storage.py`, `evidence.py`. Test `tests/test_storage.py`, `tests/test_evidence.py`.

**Interfaces:**
- Produces: `Store(db_path: Path)`:
  - Bảng `samples(t REAL, source TEXT, total, roi, excluded, max_cell, speed, entropy, counterflow REAL)`.
  - Bảng `events(id INTEGER PK, t REAL, source TEXT, rule TEXT, value REAL, threshold REAL, message TEXT, snapshot TEXT, clip TEXT NULL)`.
  - Các phương thức: `add_sample(t, source, d, m)`, `add_event(alert, source, snapshot) -> int`, `set_clip(event_id, path)`, `series(since_t) -> list[dict]`, `events(limit=50) -> list[dict]`.
  - Một kết nối với `check_same_thread=False` và một `threading.Lock`.
- Produces: `FrameRing(seconds: float, fps_cap: float = 10)`: `push(t, frame)` (thu nhỏ về 640 px, lấy mẫu tối đa `fps_cap`), `snapshot(t0, t1) -> list[(t, frame)]`.
- Produces: `save_snapshot(frame, path)`; `write_clip(frames: list[np.ndarray], fps: float, path) -> Path` dùng `imageio_ffmpeg.write_frames` với `codec="libx264"`, `pix_fmt_out="yuv420p"` để trình duyệt phát được.
- Produces: `EvidenceRecorder(ring, store, out_dir, pre_s, post_s)`:
  - `on_alert(alert, frame, source)`: lưu ảnh ngay, ghi event, hẹn ghi clip.
  - `tick(now)`: khi đã qua `post_s` giây thì ghi clip [t−pre, t+post] và cập nhật `events.clip`.

- [ ] **Step 1: Viết test**
  - Store: ghi và đọc lại sample và event qua `tmp_path`, `series(since)` lọc đúng theo thời gian.
  - `test_write_clip_is_h264_mp4`: ghi 20 frame 64×48, file tồn tại và kích thước > 0. Đọc lại bằng `cv2.VideoCapture` được ≥ 15 frame.
  - `test_recorder_writes_clip_after_post_window`: đẩy frame từ t=0 đến 12 s, alert ở t=6, `tick(10)` chưa có clip, `tick(11.5)` có clip và `events.clip` khác rỗng.
- [ ] **Step 2: FAIL. Step 3: Cài đặt. Step 4: PASS.**

### Task 6: Nguồn video

**Files:** Create `sources.py`. Test `tests/test_sources.py`, `tests/conftest.py` (fixture `sample_video`: ghi bằng cv2 một file mp4 dài 3 s, 10 fps, 320×240, có hình vuông chạy ngang).

**Interfaces:**
- Produces: `VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".ts"}`. Mọi nơi lọc file video dùng hằng số này. OpenCV đọc webm (VP8/VP9) qua FFmpeg đi kèm `opencv-python`.
- Produces: protocol `VideoSource` gồm:
  - `fps: float`, `size: tuple[int, int]`, `label: str`, `tz: str`, `live: bool`;
  - `read() -> tuple[float, np.ndarray] | None`: trả về (t, frame), trong đó t là epoch UTC của frame;
  - `close()`.
- Produces: `FileSource(path, tz)`:
  - Phát đúng nhịp `fps`: tự `sleep` cho đủ thời gian mỗi frame.
  - Hết file thì quay lại đầu; `t` = thời điểm bắt đầu phát + thời gian video, tăng liên tục qua các vòng lặp.
  - Có `pause()`, `resume()`, `seek(sec)`, `position_s`, `duration_s`.
- Produces: `YouTubeSource(url, tz)`:
  - Lấy link HLS bằng logic chọn luồng ≤ 1080p của notebook (`youtube_stream_url`, kèm fallback in cảnh báo khi không có luồng).
  - `read()` tự kết nối lại tối đa 5 lần, sau đó ném `SourceError` với thông điệp tiếng Việt.
- Produces: `open_source(spec: dict) -> VideoSource`, với spec dạng `{"kind": "file", "path", "tz"}` hoặc `{"kind": "youtube", "url", "tz"}`.

- [ ] **Step 1: Viết test**
  - `test_file_source_paced_at_native_fps`: đọc 10 frame mất khoảng 0,9–1,3 s.
  - `test_file_source_loops`: đọc 40 frame từ video 30 frame không lỗi, và `t` tăng đơn điệu.
  - `test_file_source_reads_webm`: fixture `sample_webm` ghi video bằng fourcc `VP80`; `FileSource` đọc được ≥ 25 frame và `size` đúng. Nếu bản OpenCV trên máy không ghi được VP80 thì skip, ghi rõ lý do.
  - `test_seek_and_pause`.
  - `test_youtube_source_reports_error_on_bad_url`: monkeypatch hàm lấy link để luôn ném lỗi, mong đợi `SourceError`.
- [ ] **Step 2: FAIL. Step 3: Cài đặt. Step 4: PASS.**

### Task 7: Vẽ lớp phủ

**Files:** Create `overlay.py`. Test `tests/test_overlay.py`.

**Interfaces:**
- Produces: `Layers` (dataclass):
  - `density`, `mask`, `flow` (đều `np.ndarray | None`);
  - `zones: ZoneSet`, `hot_cells`, `cell_px_frame: float`;
  - `alert_active: bool`;
  - `heat_vmax: float`, là giá trị lớn nhất của heatmap, cập nhật bằng EMA của phân vị 99,9 để màu không nhấp nháy.
- Produces: `render(frame_bgr, layers: Layers | None, mode: str, out_width: int) -> np.ndarray`, vẽ theo thứ tự:
  1. Nền theo `mode`.
  2. Heatmap JET, alpha tỉ lệ với mật độ, tối đa 0,6.
  3. Đường bao mask ở mức 0,5 (vàng).
  4. Mũi tên flow trên lưới 24 px, chỉ ở chỗ có người.
  5. ROI (xanh lá), vùng loại trừ (xám, viền đỏ).
  6. Ô đông (khung đỏ).
  7. Viền đỏ 6 px nếu đang có cảnh báo.

  Chế độ `video` trả về frame gốc (đã resize). Không vẽ chữ: số liệu hiển thị ở React.

- [ ] **Step 1: Viết test**
  - Mỗi chế độ trả về ảnh `(out_h, out_width, 3)` kiểu uint8.
  - `video` khớp frame gốc đã resize.
  - `overlay_only` với density bằng 0 và không có vùng thì toàn ảnh đen.
  - `gray` không có density thì 3 kênh màu bằng nhau.
  - `layers=None` không lỗi.
- [ ] **Step 2: FAIL. Step 3: Cài đặt. Step 4: PASS.**

### Task 8: Pipeline

**Files:** Create `pipeline.py`. Test `tests/test_pipeline.py`.

**Interfaces:**
- Consumes: Task 1–7.
- Produces: `Pipeline(settings, model)`:
  - `start(spec: dict)`, `stop()`;
  - `set_mode(mode)`, `set_zones(zones: ZoneSet)`, `set_rules(cfg: RuleConfig)`, `calibrate(seconds)`;
  - `playback(action, value=None)`, chỉ áp dụng cho nguồn file;
  - `latest_jpeg() -> bytes | None`: frame mới nhất đã vẽ lớp phủ theo `mode`;
  - `status() -> dict`: JSON cho WebSocket, gồm `state` (`idle|running|error`), `error`, `source{label, kind, live, tz, fps, size, position_s, duration_s, paused}`, `counts{total, roi, excluded, max_cell, hot_cells}`, `motion{...}`, `perf{video_fps, analysis_fps, analysis_ms}`, `calibration{done, have, need}`, `thresholds`, `active_alerts[]`, `new_events[]` (các event có id mới kể từ lần gửi trước), `mode`.
- Luồng chạy:
  - **Luồng đọc:** gọi `source.read()`, rồi `ring.push`, rồi render bằng `Layers` mới nhất và mã hóa JPEG (`stream_width`, `jpeg_quality`). Kết quả lưu vào biến dùng chung có lock, kèm `threading.Condition` để luồng MJPEG đợi frame mới.
  - **Luồng phân tích**, lặp liên tục:
    1. Lấy frame mới nhất và frame cách đó khoảng `flow_gap_s` từ ring.
    2. Chạy `infer`, `analyze_density`, `compute_flow` và `flow_features`, với `valid` = mask > 0,5 và vùng watch.
    3. Chạy `rules.update`; với mỗi alert gọi `recorder.on_alert`.
    4. Ghi `store.add_sample`, gọi `recorder.tick`, cập nhật `Layers`.
  - **Lỗi nguồn:** ghi vào `state="error"`, `error=<thông điệp>` rồi dừng luồng.
- Mỗi lần `start` tạo một thư mục `data/runs/<YYYYmmdd-HHMMSS>/` chứa `crowd.db` và `evidence/`. Zones nạp từ `data/zones/<slug nguồn>.json` nếu có.

- [ ] **Step 1: Viết test** với model thật và `sample_video`:
  - `test_pipeline_produces_frames_and_status`: sau 2 s, `latest_jpeg()` khác `None`, `status()["perf"]["analysis_fps"] > 0`, `video_fps` gần 10.
  - `test_switch_source_stops_old_threads`: `start(a)`, `start(b)`, rồi `stop()`. Số thread `threading.enumerate()` quay về như ban đầu trong 3 s.
  - `test_mode_change_applies`: đặt `set_mode("gray")` thì JPEG kế tiếp giải mã ra ảnh có 3 kênh gần bằng nhau.
- [ ] **Step 2: FAIL. Step 3: Cài đặt. Step 4: PASS.**

### Task 9: API FastAPI

**Files:** Create `api.py`, `main.py`. Test `tests/test_api.py` (`fastapi.testclient`).

**Interfaces:**
- Consumes: `Pipeline`, `Store`.
- Produces: các route.

  | Route | Mô tả |
  |---|---|
  | `GET /api/videos` | Danh sách file có đuôi thuộc `VIDEO_EXTS` trong `data/videos` |
  | `POST /api/videos` | Upload file vào `data/videos`; 415 nếu đuôi không thuộc `VIDEO_EXTS` |
  | `POST /api/source` | Body `{kind, path\|url, tz}`; trả 409 nếu lỗi mở nguồn, kèm thông điệp |
  | `POST /api/stop` | Dừng pipeline |
  | `POST /api/playback` | Body `{action: play\|pause\|seek, value?}` |
  | `PUT /api/view` | Body `{mode}`; 422 nếu mode không thuộc 4 chế độ |
  | `GET /api/zones`, `PUT /api/zones` | Lấy và lưu vùng; validate, 422 nếu sai; lưu theo nguồn |
  | `GET /api/rules`, `PUT /api/rules` | Lấy và đổi `RuleConfig` |
  | `POST /api/calibrate` | Body `{seconds}` |
  | `GET /api/series?minutes=10` | Chuỗi số liệu |
  | `GET /api/events?limit=50` | Danh sách sự kiện |
  | `GET /api/stream.mjpg` | `StreamingResponse` multipart, đợi frame mới qua Condition, nhịp theo FPS nguồn |
  | `WS /api/ws` | Gửi `status()` mỗi 0,5 s |
  | `/evidence/...` | `StaticFiles` trỏ tới thư mục `data/runs` |
  | `/` | Phục vụ `frontend/dist` nếu đã build |

  `main.run()` chạy `uvicorn` ở `127.0.0.1:8000` và load model một lần khi khởi động (lifespan).

- [ ] **Step 1: Viết test**
  - `test_list_videos`: thư mục có `a.mp4`, `b.webm`, `c.txt` thì danh sách trả về đúng `a.mp4` và `b.webm`.
  - `test_upload_rejects_unsupported_extension`: upload `x.txt` trả 415.
  - `test_start_file_source_then_status_ws`: kết nối WS nhận được `state == "running"`.
  - `test_put_zones_rejects_invalid_polygon`: polygon 2 điểm trả 422, `GET` vẫn ra vùng cũ.
  - `test_put_view_rejects_unknown_mode`.
  - `test_stream_returns_jpeg_parts`: đọc khoảng 2 phần, nội dung bắt đầu bằng `b"\xff\xd8"`.
  - `test_events_endpoint_after_forced_alert`: đặt `count_limit=0` thì trong 5 s có ít nhất 1 event, `snapshot` truy cập được qua `/evidence`.
- [ ] **Step 2: FAIL. Step 3: Cài đặt. Step 4: PASS**, rồi chạy toàn bộ: `uv run pytest -v`.

### Task 10: Khung frontend, chọn nguồn, xem video, chế độ hiển thị

**Files:** `demo/frontend/` tạo bằng `npm create vite@latest frontend -- --template react-ts`, sau đó dọn bỏ file mẫu. Create: `src/types.ts`, `api.ts`, `hooks/useLiveStatus.ts`, `App.tsx`, `styles.css`, `components/SourcePanel.tsx`, `VideoStage.tsx`, `ModeSwitch.tsx`. Sửa `vite.config.ts`: `server.proxy` cho `/api` (bật `ws: true`) và `/evidence` trỏ tới `http://127.0.0.1:8000`.

**Interfaces:**
- `types.ts` khai báo đúng tên trường của `status()` (Task 8), `ZoneSet` (`{roi: [number, number][][], exclude: ...}`), `RuleConfig`, `EventRow`, `SeriesRow`.
- `api.ts` có các hàm `listVideos`, `uploadVideo`, `startSource`, `stopSource`, `playback`, `setMode`, `getZones`, `putZones`, `getRules`, `putRules`, `calibrate`, `getSeries`, `getEvents`. Lỗi HTTP ném `Error(message)` lấy từ `detail` của server.
- `SourcePanel`: ô upload có `accept=".mp4,.webm,.mkv,.avi,.mov,.ts"`, khớp `VIDEO_EXTS` của backend.
- `useLiveStatus(): {status: Status | null, connected: boolean}`: tự kết nối lại WebSocket sau 2 s khi mất kết nối.
- Bố cục `App`: thanh trên chứa SourcePanel; cột trái gồm VideoStage (chiếm phần lớn) và ModeSwitch ngay dưới, cùng nút phát, dừng, tua nếu là nguồn file; cột phải dành cho các panel ở Task 11–12. Theme tối, dùng biến CSS.
- `VideoStage`: `<img src="/api/stream.mjpg?k={sessionKey}">`, đổi key khi đổi nguồn để trình duyệt mở lại luồng. Có lớp `<canvas>` cùng kích thước cho ZoneEditor.

- [ ] **Step 1:** Scaffold và `npm install recharts`.
- [ ] **Step 2:** Cài đặt các file trên.
- [ ] **Step 3: Kiểm tra** `npm run build` (gồm `tsc -b`) thành công, không cảnh báo TypeScript.
- [ ] **Step 4: Kiểm tra thủ công:**
  1. Chạy `uv run crowd-demo` và `npm run dev`.
  2. Chọn `sample.mp4` (đặt vào `data/videos`): video chạy mượt.
  3. Đổi 4 chế độ: hình đổi ngay.
  4. Link YouTube sai: hiện thông báo lỗi tiếng Việt.

### Task 11: Vẽ vùng và luật cảnh báo trên web

**Files:** Create `components/ZoneEditor.tsx`, `RulesPanel.tsx`.

**Interfaces:**
- `ZoneEditor({zones, onSave})`, thao tác:
  - Chọn công cụ: "Vùng giám sát" hoặc "Vùng loại trừ".
  - Click để thêm điểm; double-click hoặc click vào điểm đầu để đóng polygon.
  - Esc hủy polygon đang vẽ; click phải lên một vùng để xóa vùng đó.
  - Nút "Lưu vùng" gọi `putZones`.
  - Tọa độ chuẩn hóa theo kích thước ảnh đang hiển thị. Đang ở chế độ vẽ thì chỉ hiện các vùng trên canvas.
- `RulesPanel({status})`:
  - Công tắc bật/tắt từng luật, thanh trượt `k_sigma`, `persist`, `surge_abs`, `surge_rel`, ô nhập `count_limit`.
  - Nút "Học mức bình thường (N giây)"; khi đang học hiện thanh tiến độ `have/need`.
  - Bảng ngưỡng hiện tại lấy từ `status.thresholds`.
  - Đổi giá trị thì gọi `putRules`, có debounce 300 ms.

- [ ] **Step 1: Cài đặt. Step 2: `npm run build` thành công. Step 3: Kiểm tra thủ công:**
  - Vẽ ROI rồi lưu: số "trong vùng" thay đổi.
  - Vẽ vùng loại trừ lên chỗ có người: số giảm tương ứng.
  - Tải lại trang: vùng vẫn còn.
  - Đặt `count_limit` thấp: video có viền đỏ.

### Task 12: Thống kê, biểu đồ, danh sách cảnh báo

**Files:** Create `components/StatsPanel.tsx`, `CountChart.tsx`, `AlertList.tsx`.

**Interfaces:**
- `StatsPanel({status})`:
  - Thẻ số lớn: người trong vùng giám sát; thẻ phụ: toàn khung, vùng loại trừ, ô đông nhất.
  - Chuyển động: tốc độ, hướng (mũi tên xoay theo `direction_deg`), mức hỗn loạn (entropy), tỉ lệ ngược chiều.
  - Hiệu năng: FPS video, FPS phân tích, ms mỗi lần phân tích. Giờ hiện tại theo `tz` của nguồn.
- `CountChart({tz})`:
  - Lấy `getSeries(10)` khi mở, sau đó nối thêm mẫu mới từ WebSocket.
  - Recharts `LineChart` gồm đường số người trong vùng (trục trái), đường tốc độ chuyển động (trục phải), vạch ngưỡng quá đông, chấm tại các thời điểm có sự kiện.
- `AlertList()`:
  - Lấy `getEvents()` khi mở và khi `status.new_events` khác rỗng.
  - Mỗi dòng: ảnh nhỏ (`/evidence/...`), giờ địa phương, tên luật tiếng Việt, thông điệp.
  - Click mở hộp thoại phát clip (`<video controls>`). Clip chưa ghi xong thì hiện "Đang ghi clip…".
- Tên tiếng Việt của các luật: `overcrowd` = "Quá đông", `hot_cell` = "Ô quá dày", `surge` = "Tăng đột ngột", `panic` = "Hỗn loạn", `counterflow` = "Ngược chiều".

- [ ] **Step 1: Cài đặt. Step 2: `npm run build` thành công. Step 3: Kiểm tra thủ công:**
  - Với `count_limit` thấp, một cảnh báo có ảnh hiện ra; sau khoảng 5 s clip phát được.
  - Biểu đồ chạy liên tục.
  - Đổi nguồn: biểu đồ và danh sách cảnh báo được làm mới cho lần chạy mới.

### Task 13: README và kiểm tra tổng thể

**Files:** Create `demo/README.md`. Modify `demo/backend/src/crowd_demo/api.py` nếu cần phục vụ `frontend/dist`.

README gồm các mục:
1. **Giới thiệu.** Ánh xạ tới de.md mục 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 5.3.
2. **Cài đặt:**
   - `cd demo/backend && uv sync`
   - `cd demo/frontend && npm install`
   - Đặt model ở `model.pth`, hoặc đặt biến `CROWD_MODEL`.
3. **Chạy:**
   - Chế độ dev: chạy `uv run crowd-demo` và `npm run dev` ở hai cửa sổ.
   - Hoặc build: `npm run build`, rồi chỉ cần `uv run crowd-demo` và mở `http://127.0.0.1:8000`.
4. **Cách dùng:** chọn nguồn, 4 chế độ hiển thị, vẽ vùng, học mức bình thường, đọc cảnh báo và xem bằng chứng.
5. **Kiến trúc:** sơ đồ hai luồng, bảng các module, schema SQLite, danh sách API.
6. **Cách hệ thống phát hiện bất thường:** 5 luật kèm công thức; giải thích Farneback, entropy hướng, ngược chiều.
7. **Giới hạn đã biết:**
   - Lớp phủ trễ hơn hình bằng thời gian một lần phân tích.
   - Mũi tên flow tính theo pixel, chưa đổi ra m/s.
   - Camera rung có thể gây báo nhầm luật chuyển động.
8. **Hướng phát triển (chưa làm):**
   - Autoencoder trên đặc trưng chuyển động.
   - RAFT.
   - Hiệu chỉnh phối cảnh ra người/m².
   - Đánh giá trên UMN (độ trễ, AUC).
   - MAE trên camera thật (gán nhãn frame).
   - Hướng đi quy định cho từng ROI.
   - Thông báo email/Telegram.
   - Đa camera, dự đoán quá tải.

- [ ] **Step 1: Viết README.**
- [ ] **Step 2: Chạy `uv run pytest -v` (tất cả PASS) và `npm run build` (thành công).**
- [ ] **Step 3: Kiểm tra tổng thể thủ công trên cả hai nguồn:**
  - Một video có sẵn và link YouTube cam Dublin `https://www.youtube.com/watch?v=3nyPER2kzqk` (`tz = Europe/Dublin`).
  - Đủ 4 chế độ hiển thị, vẽ vùng, học mức bình thường 60 s, có cảnh báo kèm ảnh và clip, biểu đồ chạy.
  - Ghi lại FPS video và FPS phân tích đo được vào README, mục "Hiệu năng (máy thử)".

### Task 14: Báo cáo đề tài `baocao.md`

**Files:**
- Create: `baocao.md` ở thư mục gốc dự án.
- Create: `report_assets/` chứa ảnh dùng trong báo cáo:
  - ảnh chụp demo, lấy từ Task 13;
  - ảnh xuất từ notebook Kaggle (`eda_partB.png`, `final_*.png`), do người dùng tải về.

**Nguồn số liệu** (chỉ dùng các nguồn này):

| Nguồn | Số liệu |
|---|---|
| `shanghaitech-baseline.ipynb` | MCNN, CSRNet: MAE, MSE |
| `improve-mobilecount-tr-n-shanghaitech.ipynb` (cosine 400) | Baseline 9,35 / 15,43; C1 8,88 / 14,24 (epoch cuối 8,49); C2, C5, C1+C5; đếm nhầm ở nền; IoU; FPS |
| Các lần chạy plateau và C6 trước đó | Dùng cho phần "các hướng đã thử" |
| `final_mobilecount.ipynb` | Nếu đã chạy thì ưu tiên số của notebook này cho bảng chính; chưa chạy thì ghi `[CẦN BỔ SUNG]` |
| Demo (Task 13) | FPS video, FPS phân tích, độ trễ, ảnh chụp |

**Dàn ý** (sắp theo mạch lập luận của báo cáo: vấn đề → giải pháp → kiểm chứng → triển khai; không chép thứ tự de.md):

1. **Đặt vấn đề:**
   - Bối cảnh an ninh nơi công cộng.
   - Vì sao đếm bằng detection kém ở đám đông dày.
   - Mục tiêu, phạm vi (người đi bộ, camera đường phố).
   - Tóm tắt đóng góp và kết quả chính trong 3–4 gạch đầu dòng.
2. **Tổng quan và lựa chọn hướng tiếp cận:**
   - Ba hướng đếm người: detection, hồi quy số đếm, density map.
   - So sánh MCNN, CSRNet, MobileCount, và lý do chọn MobileCount (nhẹ, chạy CPU).
   - Hai nhóm dấu hiệu bất thường: mật độ và chuyển động.
3. **Phương pháp đề xuất:**
   - Mở đầu bằng sơ đồ tổng thể: camera → đếm → phân tích vùng → chuyển động → luật → cảnh báo.
   - 3.1. Mô hình MobileCount + Mask: density map Gaussian, nhánh mask và nhãn tạo tự động, loss.
   - 3.2. Phân tích không gian: ROI, vùng loại trừ, ô lưới khoanh vùng đám đông.
   - 3.3. Phân tích chuyển động: Farneback; các đặc trưng tốc độ, hướng chính, entropy hướng, tỉ lệ ngược chiều.
   - 3.4. Phát hiện bất thường: 5 luật, học mức bình thường bằng trung vị và MAD, điều kiện kéo dài.
4. **Thực nghiệm mô hình đếm:**
   - 4.1. Dữ liệu ShanghaiTech Part B, EDA.
   - 4.2. Thiết lập: quy trình train, chọn checkpoint, các chỉ số.
   - 4.3. So sánh với baseline (MCNN, CSRNet, MobileCount, kèm số công bố trong paper).
   - 4.4. Ablation các hướng cải tiến, nêu cả hướng không hiệu quả (C2, C5, C6).
   - 4.5. Phân tích lỗi: theo nhóm mật độ, đếm nhầm ở nền, khoanh vùng (IoU), ảnh minh họa.
   - 4.6. Bài học về quy trình train: plateau so với cosine; tập val 40 ảnh không ổn định; checkpoint epoch cuối.
5. **Triển khai hệ thống:**
   - 5.1. Kiến trúc phần mềm: hai luồng, API, SQLite, ảnh và clip bằng chứng.
   - 5.2. Giao diện giám sát: 4 chế độ hiển thị, vẽ vùng, biểu đồ, danh sách cảnh báo.
   - 5.3. Chạy trên camera thật: ảnh chụp và quan sát.
   - 5.4. Hiệu năng: FPS video, FPS phân tích, độ trễ lớp phủ.
6. **Đánh giá phát hiện bất thường:**
   - Kiểm thử luật trên chuỗi giả lập: phát hiện được không, trễ bao lâu.
   - Báo nhầm trên camera thật lúc bình thường `[CẦN BỔ SUNG]`.
7. **Thảo luận:**
   - Hạn chế: chênh lệch miền dữ liệu, phối cảnh, 1 seed, camera rung.
   - Khía cạnh an toàn thông tin và quyền riêng tư: hệ thống chỉ ước lượng mật độ, không nhận dạng cá nhân; dữ liệu bằng chứng lưu cục bộ.
8. **Kết luận và hướng phát triển.**
9. **Tài liệu tham khảo:** MobileCount, MCNN, CSRNet, Counting with Focus for Free, SFANet, MobileNetV2, Light-Weight RefineNet, Farneback, ShanghaiTech.
10. **Phụ lục:**
    - Hướng dẫn chạy các notebook Kaggle và demo.
    - Bảng cấu hình train.
    - Bảng đối chiếu: mỗi yêu cầu của de.md nằm ở mục nào trong báo cáo, kèm tình trạng đã làm hay chưa.

- [ ] **Step 1:** Viết `baocao.md` theo dàn ý. Bảng số liệu lấy đúng từ các nguồn trên.
- [ ] **Step 2: Kiểm tra:**
  - Mọi con số trong báo cáo có thể truy về một nguồn trong bảng trên.
  - Không có số không rõ nguồn.
  - Các chỗ còn thiếu có dạng `[CẦN BỔ SUNG: ...]` và được liệt kê ở cuối file, mục "Việc cần bổ sung trước khi nộp".
