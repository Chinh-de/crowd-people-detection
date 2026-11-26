"""Đóng gói nhãn Temple Bar thành dataset Kaggle (cũng làm được trên web, trang Gắn nhãn).

Chạy từ thư mục gốc: python scripts/export_dublin_kaggle.py
Kết quả: kaggle/dublin_dataset/ (tải thư mục này lên Kaggle → New Dataset).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'demo' / 'backend' / 'src' / 'crowd_demo' / 'labeling'))

from export import export_dataset  # noqa: E402  (chỉ cần Pillow, không nạp torch)

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    out = ROOT / 'kaggle' / 'dublin_dataset'
    images, points = export_dataset(ROOT / 'demo' / 'data' / 'labels' / 'dublin_live', out)
    print(f'{images} ảnh, {points} điểm -> {out}')
