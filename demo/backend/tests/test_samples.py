"""Mẫu học liên tục: lưu cảnh báo kèm mask + nhãn, admin đánh giá đúng/nhầm, dùng lại để học."""
import io
import json
import zipfile

import numpy as np

from crowd_demo.anomaly import CellFeats
from crowd_demo.rules import Alert
from crowd_demo.samples import load_features, save_sample
from test_api import app_client, client, login, model, new_camera, started  # noqa: F401  (fixture dùng chung)
from test_pipeline import wait_for


def feats(speed, seed):
    rng = np.random.default_rng(seed)
    f = (rng.random((8, 8, 11)) * 0.1 + speed).astype(np.float32)
    d = (rng.random((8, 8, 2)) * 0.1).astype(np.float32)
    return CellFeats(fm=f, f0=f.copy(), d=d)


def make_sample(folder):
    frame = np.full((540, 960, 3), 80, np.uint8)
    density = np.zeros((135, 240), np.float32)
    density[40:42, 50:52] = 0.5          # tổng 2 người
    density[90, 180] = 1.0               # thêm 1 người
    mask = (density > 0).astype(np.float32)
    save_sample(folder, frame, density, mask, scale=1.0, feats=[feats(1.0, i) for i in range(3)], meta={"rule": "panic"})


def test_sample_keeps_frame_mask_labels_and_features(tmp_path):
    make_sample(tmp_path / "1")
    label = json.loads((tmp_path / "1" / "label.json").read_text(encoding="utf-8"))
    assert label["rule"] == "panic" and label["width"] == 960 and label["count"] == 3.0
    assert 1 <= len(label["points"]) <= 3
    for name in ("frame.jpg", "mask.png", "preview.jpg", "density.npz"):
        assert (tmp_path / "1" / name).stat().st_size > 0, name
    back = load_features(tmp_path / "1")
    assert len(back) == 3 and np.allclose(back[2].fm, feats(1.0, 2).fm)


def add_event(c, cid, rule="panic"):
    db = c.app.state.db
    eid = db.add_event(cid, Alert(rule=rule, t=1_800_000_000.0, value=1.0, threshold=0.5, message="x: y"),
                       "Cổng A", "/evidence/1/x.jpg")
    make_sample(c.app.state.settings.samples_dir / str(eid))
    db.mark_sample(eid)
    return eid


def test_verdict_classification_labeling_and_export(client):
    cid = new_camera(client)
    eid = add_event(client, cid)
    add_event(client, cid)                                      # một cảnh báo chưa phân loại
    assert client.get(f"/api/events/{eid}/sample/preview.jpg").headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/events/{eid}/sample/features.npz").status_code == 404     # chỉ phục vụ ảnh
    assert client.get("/api/feedback/export").status_code == 409                       # chưa phân loại gì

    ev = client.post(f"/api/events/{eid}/verdict", json={"verdict": "false", "note": "người qua đường"}).json()
    assert ev["verdict"] == "false" and ev["status"] == "ack" and ev["verdict_by"] == "qt"
    page = client.get("/api/events?verdict=false").json()
    assert page["total"] == 1 and page["verdicts"] == {"none": 1, "true": 0, "false": 1}
    assert client.get("/api/events?verdict=none").json()["total"] == 1

    sent = client.post(f"/api/events/{eid}/to-labeling").json()
    assert client.get(f"/api/labels/label/{sent['image']}").json()["status"] == "auto"
    assert client.post(f"/api/events/{eid}/to-labeling").json()["image"] == sent["image"]   # không tạo trùng

    z = zipfile.ZipFile(io.BytesIO(client.get("/api/feedback/export").content))
    for name in ("frame.jpg", "mask.png", "label.json", "features.npz"):
        assert f"samples/{eid}/{name}" in z.namelist(), name
    manifest = z.read("manifest.csv").decode("utf-8-sig")
    assert "false" in manifest and len(manifest.strip().splitlines()) == 2    # chỉ mẫu đã phân loại

    assert client.post(f"/api/events/{eid}/verdict", json={"verdict": None}).json()["verdict"] is None


def test_viewer_cannot_judge_and_old_unreviewed_samples_are_purged(client, tmp_path):
    cid = new_camera(client)
    old, judged = add_event(client, cid), add_event(client, cid)
    client.post(f"/api/events/{judged}/verdict", json={"verdict": "true"})
    s = client.app.state.settings
    client.app.state.db.purge(1_900_000_000.0, 3, 30, s.evidence_dir, s.samples_dir)
    assert not (s.samples_dir / str(old)).exists() and (s.samples_dir / str(judged)).exists()
    client.cookies.clear()
    login(client, "xem", "mk2")
    assert client.post(f"/api/events/{judged}/verdict", json={"verdict": "false"}).status_code == 403


def test_pipeline_saves_sample_with_each_alert(client):
    cid = started(client)
    p = client.app.state.cameras.get(cid)
    original, fired = p.engine.update, []

    def update(t, d, m, reading):
        original(t, d, m, reading)
        if fired or reading is None and not p._recent_feats:
            return []
        fired.append(t)
        return [Alert(rule="panic", t=t, value=1.0, threshold=0.5, message="x: y")]

    p.engine.update = update
    assert wait_for(lambda: client.get("/api/events").json()["total"] == 1, timeout=30)
    ev = wait_sample(client)
    folder = client.app.state.settings.samples_dir / str(ev["id"])
    assert (folder / "frame.jpg").exists() and load_features(folder)
    label = json.loads((folder / "label.json").read_text(encoding="utf-8"))
    assert label["camera_id"] == cid and label["count_model"] and label["anomaly_model"]


def wait_sample(client):
    assert wait_for(lambda: client.get("/api/events").json()["rows"][0]["has_sample"], timeout=10)
    return client.get("/api/events").json()["rows"][0]
