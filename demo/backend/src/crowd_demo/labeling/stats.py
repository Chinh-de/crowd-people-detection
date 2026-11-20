"""Thống kê bộ nhãn: so nhãn đã duyệt với bản nháp tự động (thêm / xóa / dời bao nhiêu điểm).

Chạy: uv run crowd-label-stats   (mặc định so labels/ với labels_draft/)
"""
import argparse
import json
from pathlib import Path

import numpy as np

from .grab import DEFAULT_OUT


def match_points(a: list, b: list, radius: float) -> list[tuple[int, int, float]]:
    """Ghép cặp tham lam theo khoảng cách tăng dần, mỗi điểm dùng tối đa một lần, chỉ ghép khi gần hơn radius."""
    if not a or not b:
        return []
    A, B = np.asarray(a, float), np.asarray(b, float)
    d = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(-1))
    pairs, used_a, used_b = [], set(), set()
    for i, j in zip(*np.unravel_index(np.argsort(d, axis=None), d.shape)):
        if d[i, j] > radius:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i); used_b.add(j); pairs.append((int(i), int(j), float(d[i, j])))
    return pairs


def compare(draft: list, final: list, radius: float = 15.0, moved_px: float = 3.0) -> dict:
    pairs = match_points(draft, final, radius)
    return {"draft": len(draft), "final": len(final), "kept": sum(d <= moved_px for *_, d in pairs),
            "moved": sum(d > moved_px for *_, d in pairs), "removed": len(draft) - len(pairs), "added": len(final) - len(pairs)}


def run() -> None:
    ap = argparse.ArgumentParser(description="So nhãn đã duyệt với nhãn nháp")
    ap.add_argument("--root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--radius", type=float, default=15.0, help="khoảng cách tối đa (px) để coi hai điểm là một người")
    a = ap.parse_args()
    rows = []
    for f in sorted((a.root / "labels").glob("*.json")):
        fin = json.loads(f.read_text(encoding="utf-8"))
        dr_file = a.root / "labels_draft" / f.name
        if fin.get("status") != "done" or not dr_file.exists():
            continue
        dr = json.loads(dr_file.read_text(encoding="utf-8"))
        rows.append(compare(dr["points"], fin["points"], a.radius))
    if not rows:
        print("Chưa có ảnh nào ở trạng thái 'Người đã duyệt'.")
        return
    tot = {k: sum(r[k] for r in rows) for k in rows[0]}
    mae = np.mean([abs(r["final"] - r["draft"]) for r in rows])
    print(f"Ảnh đã duyệt: {len(rows)}")
    print(f"Tổng điểm: nháp {tot['draft']} → cuối {tot['final']}")
    print(f"Giữ nguyên {tot['kept']} · dời {tot['moved']} · xóa {tot['removed']} · thêm {tot['added']}")
    print(f"Tỉ lệ điểm nháp được giữ (kể cả dời): {(tot['kept'] + tot['moved']) / max(tot['draft'], 1):.1%}")
    print(f"Sai lệch số đếm nháp so với nhãn cuối (MAE theo ảnh): {mae:.2f} người")


if __name__ == "__main__":
    run()
