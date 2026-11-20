"""Lấy khung hình trong quá khứ của livestream YouTube qua luồng DASH (khoảng 7 ngày gần nhất).

Luồng DASH của YouTube live cho tải từng đoạn theo số thứ tự `&sq=<n>` (mỗi đoạn vài giây, 1080p, tự giải mã được).
Phần còn giữ lại dài khoảng 7 ngày (luồng HLS chỉ khoảng 6 giờ). Mỗi đoạn lấy khung đầu tiên.
Các khung được rải đều theo thời gian kèm độ lệch ngẫu nhiên, nên phủ đủ giờ trong ngày và các ngày trong tuần.

Chạy: uv run crowd-grab --n 200
"""
import argparse
import csv
import datetime as dt
import random
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import cv2

from ..config import DEMO_DIR

DEFAULT_URL = "https://www.youtube.com/watch?v=3nyPER2kzqk"
DEFAULT_OUT = DEMO_DIR / "data" / "labels" / "dublin_live"
MANIFEST_FIELDS = ["image", "utc", "sq", "source", "grab_session"]


def dash_video_url(url: str, max_height: int = 1080) -> tuple[str, float]:
    """(URL DASH của luồng hình H.264 cao nhất ≤ max_height, độ dài mỗi đoạn tính bằng giây)."""
    import yt_dlp

    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "live_from_start": True}) as y:
        info = y.extract_info(url, download=False)
    fmts = [f for f in info["formats"] if "dash" in (f.get("protocol") or "") and (f.get("vcodec") or "").startswith("avc")
            and (f.get("height") or 0) <= max_height]
    if not fmts:
        raise RuntimeError("Không có luồng DASH H.264: livestream không bật tua lại hoặc đã kết thúc")
    f = max(fmts, key=lambda f: f.get("height") or 0)
    return f["url"], float(f.get("target_duration") or 5)


def seg_url(base: str, sq: int) -> str:
    return f"{base}&sq={sq}"


def seg_time(head_sq: int, head_time: dt.datetime, sq: int, seg_s: float) -> dt.datetime:
    """Giờ gần đúng của đoạn sq (giả định các đoạn liên tục, mỗi đoạn seg_s giây)."""
    return head_time - dt.timedelta(seconds=(head_sq - sq) * seg_s)


def oldest_available(newest: int, exists: Callable[[int], bool], max_back: int) -> int:
    """sq cũ nhất còn tải được (tìm nhị phân trong [newest - max_back, newest])."""
    lo, hi = newest, max(0, newest - max_back)      # lo còn tồn tại, hi coi như đã mất
    if exists(hi):
        return hi
    while lo - hi > 1:
        mid = (lo + hi) // 2
        if exists(mid):
            lo = mid
        else:
            hi = mid
    return lo


def pick_spread(first: int, last: int, n: int, jitter: float = 0.4, seed: int = 42) -> list[int]:
    """n số sq rải đều trong [first, last], mỗi số lệch ngẫu nhiên tối đa ±jitter bước để không trùng nhịp giờ."""
    if n <= 1 or last <= first:
        return [last]
    rng = random.Random(seed)
    step = (last - first) / (n - 1)
    out = {min(last, max(first, round(first + i * step + rng.uniform(-jitter, jitter) * step))) for i in range(n)}
    return sorted(out)


def _head(base: str) -> tuple[int, dt.datetime]:
    req = urllib.request.Request(base, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["X-Head-Seqnum"]), dt.datetime.fromtimestamp(int(r.headers["X-Walltime-Ms"]) / 1000, dt.timezone.utc)


def _exists(url: str) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=0-0"}), timeout=60) as r:
            return r.status in (200, 206)
    except urllib.error.HTTPError:
        return False


def _fetch(url: str, timeout: float = 90) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def first_frame(data: bytes):
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as fh:
        fh.write(data)
        path = fh.name
    try:
        cap = cv2.VideoCapture(path)
        ok, frame = cap.read()
        cap.release()
    finally:
        Path(path).unlink(missing_ok=True)
    return frame if ok else None


def grab(url: str, out: Path, n: int, days: float = 7.0, margin_min: float = 30.0, seed: int = 42, log=print) -> int:
    frames_dir = out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.csv"
    done = set()
    if manifest.exists():
        with manifest.open(encoding="utf-8") as fh:
            done = {int(r["sq"]) for r in csv.DictReader(fh)}

    base, seg_s = dash_video_url(url)
    head, head_time = _head(base)
    oldest = oldest_available(head, lambda sq: _exists(seg_url(base, sq)), int(days * 1.5 * 86400 / seg_s))
    start = max(oldest + int(margin_min * 60 / seg_s), head - int(days * 86400 / seg_s))   # chừa biên ở mép bị xóa dần
    when = lambda sq: seg_time(head, head_time, sq, seg_s)
    log(f"DASH: còn lại từ {when(oldest):%Y-%m-%d %H:%M} UTC ({(head - oldest) * seg_s / 86400:.1f} ngày); "
        f"lấy {n} khung trong {when(start):%m-%d %H:%M} → {when(head):%m-%d %H:%M} UTC")
    session = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%MZ")
    new = 0
    write_header = not manifest.exists()
    with manifest.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        if write_header:
            w.writeheader()
        for i, sq in enumerate(pick_spread(start, head - 2, n, seed=seed)):
            if sq in done:
                continue
            try:
                frame = first_frame(_fetch(seg_url(base, sq)))
            except (urllib.error.URLError, TimeoutError) as e:
                log(f"  bỏ sq {sq}: {e}")
                continue
            if frame is None:
                log(f"  bỏ sq {sq}: không giải mã được")
                continue
            t = when(sq)
            name = f"live_{t:%Y%m%dT%H%M%SZ}_sq{sq}.jpg"
            cv2.imwrite(str(frames_dir / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            w.writerow({"image": name, "utc": t.isoformat(timespec="seconds"), "sq": sq, "source": url, "grab_session": session})
            fh.flush()
            new += 1
            if (i + 1) % 20 == 0:
                log(f"  {i + 1}/{n}")
    log(f"xong: thêm {new} khung vào {frames_dir}")
    return new


def run() -> None:
    ap = argparse.ArgumentParser(description="Lấy khung hình trong phần tua lại (DASH) của livestream YouTube")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42, help="đổi seed để lấy thêm khung khác lần trước")
    ap.add_argument("--days", type=float, default=7.0, help="lùi tối đa bao nhiêu ngày (YouTube giữ khoảng 7 ngày)")
    a = ap.parse_args()
    grab(a.url, a.out, a.n, a.days, seed=a.seed)


if __name__ == "__main__":
    run()
