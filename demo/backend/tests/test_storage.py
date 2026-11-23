import datetime as dt

import numpy as np
import pytest

from crowd_demo.anomaly import Reading
from crowd_demo.domain import Alert, DensityStats, MotionStats
from crowd_demo.storage import Database

T0 = dt.datetime(2026, 11, 23, 8, 0, tzinfo=dt.timezone.utc).timestamp()     # thứ Hai, 08:00 UTC


def dens(roi):
    return DensityStats(total=roi + 2, roi=roi, excluded=1, cells=np.zeros((1, 1)), max_cell=2)


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "crowd.db")
    yield d
    d.close()


def test_camera_crud_and_config_json(db):
    cid = db.create_camera("Cổng A", "youtube", "https://y/x", "Europe/Dublin", autostart=True,
                           config={"model": "mask", "zones": {"roi": []}})
    cam = db.get_camera(cid)
    assert cam["name"] == "Cổng A" and cam["autostart"] is True and cam["config"]["model"] == "mask"
    db.update_camera(cid, name="Cổng B", config={**cam["config"], "anomaly_model": "speed"})
    assert db.get_camera(cid)["name"] == "Cổng B" and db.get_camera(cid)["config"]["anomaly_model"] == "speed"
    assert [c["id"] for c in db.list_cameras()] == [cid]
    db.delete_camera(cid)
    assert db.get_camera(cid) is None and db.list_cameras() == []


def test_samples_roll_up_into_minutes_and_camera_scoped_store(db):
    a, b = db.store(1), db.store(2)
    for i, roi in enumerate([10, 20, 30]):
        a.add_sample(T0 + i * 10, "cam", dens(roi), MotionStats(speed=5), Reading(0.4 + i / 10, 0.6, None))
    a.add_sample(T0 + 70, "cam", dens(50), MotionStats(), None)            # phút sau
    b.add_sample(T0, "cam2", dens(99), MotionStats(), None)
    assert [r["roi"] for r in a.series(T0 + 5)] == [20, 30, 50]
    rows = db.stats_series(1, T0, T0 + 3600, bucket_s=60)
    assert [(r["t"], round(r["roi_avg"]), r["roi_max"]) for r in rows] == [(T0, 20, 30), (T0 + 60, 50, 50)]
    assert rows[0]["anomaly_max"] == pytest.approx(0.6)


def test_events_query_filters_ack_and_unacked_count(db):
    s = db.store(1)
    e1 = s.add_event(Alert("panic", T0, 0.9, 0.6, "Bất thường"), "Cổng A", "/evidence/1/a.jpg")
    s.set_clip(e1, "/evidence/1/a.mp4")
    db.store(2).add_event(Alert("overcrowd", T0 + 100, 80, 60, "Quá đông"), "Cổng B", "b.jpg")
    assert db.unacked_count() == 2
    rows, total = db.query_events(camera_id=1)
    assert total == 1 and rows[0]["clip"] == "/evidence/1/a.mp4" and rows[0]["status"] == "new"
    db.ack_event(e1, "admin", "đã cử bảo vệ")
    rows, _ = db.query_events(status="ack")
    assert rows[0]["ack_by"] == "admin" and rows[0]["note"] == "đã cử bảo vệ" and db.unacked_count() == 1
    rows, total = db.query_events(rule="overcrowd", t0=T0 + 50, t1=T0 + 200)
    assert total == 1 and rows[0]["camera_id"] == 2
    assert db.query_events(limit=1, offset=1)[0][0]["id"] == e1        # mới nhất trước


def test_summary_heatmap_and_events_by_day_in_camera_timezone(db):
    s = db.store(1)
    for i in range(3):
        s.add_sample(T0 + i * 60, "cam", dens(10 * (i + 1)), MotionStats(), None)
    s.add_event(Alert("panic", T0, 1, 0.5, "x"), "cam", "a.jpg")
    eid = s.add_event(Alert("surge", T0 + 60, 1, 0.5, "y"), "cam", "b.jpg")
    db.ack_event(eid, "admin", "")
    sm = db.summary(1, T0 - 1, T0 + 3600)
    assert sm["roi_avg"] == pytest.approx(20) and sm["roi_max"] == 30 and sm["roi_max_t"] == T0 + 120
    assert sm["events"] == {"panic": 1, "surge": 1} and sm["acked"] == 1
    hm = db.heatmap(1, T0 - 1, T0 + 3600, "Asia/Ho_Chi_Minh")       # 08:00 UTC = 15:00 giờ Việt Nam, thứ Hai
    assert hm == [{"weekday": 0, "hour": 15, "roi_avg": pytest.approx(20)}]
    days = db.events_by_day(1, T0 - 1, T0 + 3600, "Asia/Ho_Chi_Minh")
    assert days == [{"day": "2026-11-23", "rule": "panic", "n": 1}, {"day": "2026-11-23", "rule": "surge", "n": 1}]


def test_audit_log(db):
    db.audit("admin", "login", "")
    db.audit("viewer", "ack_event", "#3")
    rows = db.list_audit()
    assert [(r["user"], r["action"]) for r in rows] == [("viewer", "ack_event"), ("admin", "login")]


def test_retention_drops_old_raw_samples_and_clip_files(db, tmp_path):
    s = db.store(1)
    old, new = T0 - 40 * 86400, T0
    s.add_sample(old, "cam", dens(5), MotionStats(), None)
    s.add_sample(new, "cam", dens(5), MotionStats(), None)
    ev_dir = tmp_path / "evidence" / "1"
    ev_dir.mkdir(parents=True)
    (ev_dir / "a.jpg").write_bytes(b"x")
    (ev_dir / "a.mp4").write_bytes(b"x")
    eid = s.add_event(Alert("panic", old, 1, 0.5, "x"), "cam", "/evidence/1/a.jpg")
    s.set_clip(eid, "/evidence/1/a.mp4")
    out = db.purge(now=T0, raw_days=3, clip_days=30, evidence_root=tmp_path / "evidence")
    assert out == {"samples": 1, "clips": 1}
    assert [r["t"] for r in s.series(0)] == [new]
    assert db.stats_series(1, old - 60, old + 60, 60) != []           # thống kê theo phút vẫn còn
    ev = db.query_events()[0][0]
    assert ev["purged"] == 1 and not (ev_dir / "a.mp4").exists() and not (ev_dir / "a.jpg").exists()
