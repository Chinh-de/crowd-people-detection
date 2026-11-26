"""Cấu hình chung của demo. Đường dẫn có thể ghi đè bằng biến môi trường."""
import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]      # demo/backend
DEMO_DIR = BACKEND_DIR.parent                           # demo/
PROJECT_DIR = DEMO_DIR.parent                           # thư mục gốc dự án

VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".ts"}
VIEW_MODES = ("video", "overlay", "overlay_only", "gray")
DEFAULT_TZ = "Europe/Dublin"

# Model chọn được trên web: tên → (nhãn, file trong models_dir). Mỗi cách lấy checkpoint tốt nhất.
MODELS = {
    "mask": ("MobileCount + Mask", "mask.pth"),
    "baseline": ("MobileCount (baseline)", "baseline.pth"),
    "mask_dublin": ("MobileCount + Mask · tinh chỉnh Dublin", "mask_dublin.pth"),
}
DEFAULT_MODEL = "mask"
# Kết quả nghiên cứu giai đoạn 1 (MAE, MSE trên tập test ShanghaiTech Part B; bản Dublin: MAE 5,15 trên test Temple Bar, trước tinh chỉnh 12,58), hiển thị trên web để so sánh
MODEL_METRICS = {"mask": (8.49, 13.77), "baseline": (9.30, 15.47),
                 "mask_dublin": (10.03, 16.78)}

# MAE trên tập test Temple Bar (80 ảnh ngày 18–19/11); chỉ có số cho bản đã tinh chỉnh
MODEL_MAE_DUBLIN = {"mask_dublin": 5.15}


@dataclass
class Settings:
    models_dir: Path = field(default_factory=lambda: Path(os.environ.get("CROWD_MODELS", DEMO_DIR / "models")))
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("CROWD_DATA", DEMO_DIR / "data")))
    analysis_width: int = 960      # frame được thu về chiều rộng này trước khi đưa vào model
    cell_px: int = 64              # cạnh ô lưới khoanh vùng đông, tính trên frame phân tích
    flow_width: int = 320          # optical flow tính trên ảnh xám thu nhỏ
    flow_gap_s: float = 0.2        # hai frame dùng cho flow cách nhau khoảng này
    ring_seconds: float = 6.0      # bộ đệm frame cho clip bằng chứng
    clip_pre_s: float = 5.0
    clip_post_s: float = 5.0
    stream_fps: float = 10.0       # FPS luồng hiển thị: mức máy CPU giữ đều được khi model chạy song song
    stream_width: int = 960        # chiều rộng luồng MJPEG gửi lên web
    jpeg_quality: int = 80
    calib_seconds: float = 300.0   # thời gian học mức bình thường mặc định (5 phút)
    # Giới hạn phần cứng: mỗi camera tốn một luồng phân tích trên CPU
    max_cameras: int = field(default_factory=lambda: int(os.environ.get("CROWD_MAX_CAMERAS", "4")))
    raw_days: float = field(default_factory=lambda: float(os.environ.get("CROWD_RAW_DAYS", "3")))
    clip_days: float = field(default_factory=lambda: float(os.environ.get("CROWD_CLIP_DAYS", "30")))

    def model_file(self, name: str) -> Path:
        return self.models_dir / MODELS[name][1]

    @property
    def model_path(self) -> Path:
        return self.model_file(DEFAULT_MODEL)

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def zones_dir(self) -> Path:
        return self.data_dir / "zones"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "crowd.db"

    @property
    def labels_dir(self) -> Path:
        return self.data_dir / "labels" / "dublin_live"

    @property
    def samples_dir(self) -> Path:
        return self.data_dir / "samples"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"
