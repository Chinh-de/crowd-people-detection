import datetime as dt
import json

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from crowd_demo.labeling.autolabel import density_to_points, keep_mask
from crowd_demo.labeling.grab import oldest_available, pick_spread, seg_time, seg_url
from crowd_demo.labeling.server import create_app


def test_segment_url_and_time():
    assert seg_url("https://host/videoplayback?a=1", 42) == "https://host/videoplayback?a=1&sq=42"
    head_time = dt.datetime(2026, 11, 19, 18, 0, tzinfo=dt.timezone.utc)
    assert seg_time(1000, head_time, 988, 5.0) == dt.datetime(2026, 11, 19, 17, 59, tzinfo=dt.timezone.utc)


def test_oldest_available_binary_search():
    assert oldest_available(1000, lambda sq: sq >= 731, max_back=900) == 731
    assert oldest_available(1000, lambda sq: True, max_back=900) == 100


def test_pick_spread_covers_range_with_jitter():
    sq = pick_spread(0, 10_000, 50)
    assert len(sq) == 50 and sq == sorted(sq) and 0 <= sq[0] < 150 and 9_850 < sq[-1] <= 10_000
    gaps = [b - a for a, b in zip(sq, sq[1:])]
    assert max(gaps) < 2 * 10_000 / 49 and len(set(gaps)) > 10      # đều nhưng không cùng nhịp
    assert pick_spread(0, 10_000, 50) == sq                          # cố định theo seed


def test_density_to_points_matches_count_and_peaks():
    den = np.zeros((40, 60), np.float32)
    for y, x in ((10, 10), (20, 30), (30, 50)):
        den[y - 1:y + 2, x - 1:x + 2] += 1 / 9
    pts = density_to_points(den, scale=0.5)
    assert len(pts) == 3
    got = sorted((round(y / 8 - 0.5), round(x / 8 - 0.5)) for x, y in pts)   # stride 4, scale 0.5 → ×8
    assert got == [(10, 10), (20, 30), (30, 50)]


def test_density_to_points_respects_mask_and_empty():
    den = np.zeros((20, 20), np.float32)
    den[5, 5] = den[15, 15] = 1.0
    mask = np.zeros_like(den); mask[:10, :10] = 1
    assert len(density_to_points(den, 1.0, mask=mask)) == 1
    assert density_to_points(np.zeros((8, 8), np.float32), 1.0) == []


def test_keep_mask_blanks_noperson_polygon():
    keep = keep_mask((27, 48), [[[0.5, 0.0], [1.0, 0.0], [1.0, 0.5], [0.5, 0.5]]], (192, 108), scale=1.0)
    assert keep[:12, 26:].sum() == 0 and keep[20:, :].all() and keep[:, :22].all()


@pytest.fixture
def label_root(tmp_path):
    (tmp_path / "frames").mkdir()
    (tmp_path / "labels").mkdir()
    cv2.imwrite(str(tmp_path / "frames" / "live_20261119T180000Z_sq1.jpg"), np.zeros((36, 64, 3), np.uint8))
    (tmp_path / "labels" / "live_20261119T180000Z_sq1.json").write_text(json.dumps(
        {"image": "live_20261119T180000Z_sq1.jpg", "points": [[1, 2]], "ignore": [], "auto_count": 1.2,
         "status": "auto", "note": ""}), encoding="utf-8")
    return tmp_path


def test_label_api_roundtrip(label_root):
    c = TestClient(create_app(label_root))
    items = c.get("/api/items").json()
    assert items == [{"image": "live_20261119T180000Z_sq1.jpg", "count": 1, "auto_count": 1.2, "status": "auto", "note": ""}]
    assert c.get("/api/image/live_20261119T180000Z_sq1.jpg").status_code == 200
    r = c.put("/api/label/live_20261119T180000Z_sq1.jpg",
              json={"points": [[3.14159, 4], [5, 6]], "ignore": [[[0, 0], [5, 0], [5, 5]], [[1, 1]]],
                    "status": "reviewed", "note": "thiếu người gần camera"})
    assert r.json() == {"ok": True, "count": 2}
    lab = c.get("/api/label/live_20261119T180000Z_sq1.jpg").json()
    assert lab["points"] == [[3.1, 4], [5, 6]] and len(lab["ignore"]) == 1
    assert lab["status"] == "reviewed" and lab["auto_count"] == 1.2 and "updated" in lab


def test_label_api_rejects_bad_names_and_status(label_root):
    c = TestClient(create_app(label_root))
    assert c.get("/api/image/..%2Fsecret.jpg").status_code == 404
    assert c.get("/api/label/missing.jpg").status_code == 404
    r = c.put("/api/label/live_20261119T180000Z_sq1.jpg", json={"points": [], "status": "bogus"})
    assert r.status_code == 422
    assert c.get("/").status_code == 200


def test_fuse_points_snaps_adds_and_removes():
    from crowd_demo.labeling.autolabel import fuse_points, head_point
    person = [100, 100, 140, 220, 0.9]                  # đầu ≈ (120, 108.8)
    far_point = [500, 50]                               # người xa, không có khung → giữ
    dup_on_body = [120, 150]                            # điểm thứ hai trên cùng người → bỏ
    near_head = [118, 112]                              # điểm mật độ ở đầu → thay bằng điểm đầu của khung
    on_van = [300, 300]
    van = [250, 250, 400, 380, 0.8]
    missed = [700, 400, 760, 560, 0.95]                 # người mô hình mật độ bỏ sót → thêm
    out = fuse_points([far_point, dup_on_body, near_head, on_van], [person, missed], [van])
    hx, hy = head_point(person)
    assert [round(hx, 1), round(hy, 1)] in out and far_point in out
    assert dup_on_body not in out and near_head not in out and on_van not in out
    assert len(out) == 3


def test_fuse_points_ignores_heads_in_noperson_zone():
    from crowd_demo.labeling.autolabel import fuse_points
    out = fuse_points([], [[0, 0, 20, 60, 0.9]], [], inside_noperson=lambda x, y: True)
    assert out == []


def test_compare_counts_kept_moved_removed_added():
    from crowd_demo.labeling.stats import compare
    draft = [[0, 0], [100, 100], [200, 200]]
    final = [[0, 1], [108, 100], [400, 400]]          # giữ, dời 8 px, xóa (200,200), thêm (400,400)
    assert compare(draft, final) == {"draft": 3, "final": 3, "kept": 1, "moved": 1, "removed": 1, "added": 1}
    assert compare([], [[1, 1]])["added"] == 1
