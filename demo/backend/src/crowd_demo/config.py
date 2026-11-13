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
}
DEFAULT_MODEL = "mask"


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
    stream_width: int = 960        # chiều rộng luồng MJPEG gửi lên web
    jpeg_quality: int = 80
    calib_seconds: float = 300.0   # thời gian học mức bình thường mặc định (5 phút)

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
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"
