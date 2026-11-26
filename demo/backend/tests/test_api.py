import shutil
import time

import pytest
from fastapi.testclient import TestClient

from crowd_demo.api import create_app
from crowd_demo.config import Settings
from crowd_demo.model import load_model

ROI = {"roi": [[[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]], "exclude": []}
ENV = {"CROWD_ADMIN_USER": "qt", "CROWD_ADMIN_PASSWORD": "mk1", "CROWD_VIEWER_USER": "xem",
       "CROWD_VIEWER_PASSWORD": "mk2", "CROWD_SECRET": "k"}


@pytest.fixture(scope="module")
def model():
    path = Settings().model_path
    if not path.exists():
        pytest.skip(f"Không có model ở {path}")
    return load_model(path)


@pytest.fixture
def app_client(model, tmp_path, sample_video):
    settings = Settings(data_dir=tmp_path, max_cameras=2)
    settings.videos_dir.mkdir(parents=True)
    shutil.copy(sample_video, settings.videos_dir / "a.mp4")
    (settings.videos_dir / "b.webm").write_bytes(b"")
    (settings.videos_dir / "c.txt").write_text("x")
    with TestClient(create_app(settings, model, env=ENV)) as c:
        yield c


def login(c, user="qt", pw="mk1"):
    r = c.post("/api/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def client(app_client):
    return login(app_client)


def new_camera(c, name="Cổng A"):
    r = c.post("/api/cameras", json={"name": name, "kind": "file", "source": "a.mp4", "tz": "UTC"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def started(c, name="Cổng A"):
    cid = new_camera(c, name)
    assert c.post(f"/api/cameras/{cid}/start").status_code == 200
    return cid


# ---------------------------------------------------------------- đăng nhập
def test_everything_requires_login(app_client):
    for path in ("/api/cameras", "/api/videos", "/api/events", "/api/cameras/1/stream.mjpg", "/evidence/1/x.jpg"):
        assert app_client.get(path).status_code == 401, path
    with pytest.raises(Exception):
        with app_client.websocket_connect("/api/ws") as ws:
            ws.receive_json()
    assert app_client.post("/api/login", json={"username": "qt", "password": "sai"}).status_code == 401
    login(app_client)
    assert app_client.get("/api/me").json()["role"] == "admin"
    app_client.post("/api/logout")
    app_client.cookies.clear()
    assert app_client.get("/api/me").status_code == 401


def test_viewer_can_read_and_ack_but_not_change(app_client):
    login(app_client)
    cid = started(app_client)
    app_client.cookies.clear()
    login(app_client, "xem", "mk2")
    assert app_client.get("/api/cameras").status_code == 200
    assert app_client.put(f"/api/cameras/{cid}/zones", json=ROI).status_code == 403
    assert app_client.post(f"/api/cameras/{cid}/stop").status_code == 403
    assert app_client.post("/api/cameras", json={"name": "X", "kind": "file", "source": "a.mp4"}).status_code == 403
    assert app_client.get("/api/audit").status_code == 403


# ---------------------------------------------------------------- camera
def test_seeded_cameras_list_and_videos(client):
    assert client.get("/api/videos").json() == ["a.mp4", "b.webm"]
    cams = client.get("/api/cameras").json()
    assert cams and cams[0]["kind"] == "youtube" and not cams[0]["running"]     # camera mẫu tạo lúc đầu


def test_camera_crud_validation_and_limit(client):
    assert client.post("/api/cameras", json={"name": "X", "kind": "file", "source": "missing.mp4"}).status_code == 422
    a, b = started(client, "A"), started(client, "B")
    c3 = new_camera(client, "C")
    r = client.post(f"/api/cameras/{c3}/start")
    assert r.status_code == 409 and "giới hạn phần cứng" in r.json()["detail"]
    assert client.put(f"/api/cameras/{a}", json={"name": "A mới"}).json()["name"] == "A mới"
    assert client.delete(f"/api/cameras/{b}").status_code == 200
    assert client.post(f"/api/cameras/{c3}/start").status_code == 200
    actions = [r["action"] for r in client.get("/api/audit").json()]
    assert "delete_camera" in actions and "start_camera" in actions and "login" in actions


def test_status_ws_stream_and_snapshot(client):
    cid = started(client)
    with client.websocket_connect("/api/ws") as ws:
        msg = ws.receive_json()
        assert msg["cameras"][str(cid)]["state"] == "running" and msg["max_cameras"] == 2
    with client.stream("GET", f"/api/cameras/{cid}/stream.mjpg") as r:
        assert r.headers["content-type"].startswith("multipart/x-mixed-replace")
        data = b""
        for chunk in r.iter_bytes():
            data += chunk
            if data.count(b"\xff\xd8") >= 2:
                break
    assert client.get(f"/api/cameras/{cid}/snapshot.jpg").headers["content-type"] == "image/jpeg"
    assert client.put(f"/api/cameras/{cid}/view", json={"mode": "thermal"}).status_code == 422


def test_zones_rules_models_saved_per_camera(client):
    cid = started(client)
    body = {**ROI, "roi_meta": [{"name": "Cổng A", "limit": 25}]}
    assert client.put(f"/api/cameras/{cid}/zones", json=body).json()["roi_meta"] == [{"name": "Cổng A", "limit": 25.0, "direction": None}]
    assert client.put(f"/api/cameras/{cid}/zones", json={**ROI, "roi_meta": [{"limit": -3}]}).status_code == 422
    assert client.put(f"/api/cameras/{cid}/rules", json={"cooldown_s": 5}).json()["cooldown_s"] == 5
    assert client.put(f"/api/cameras/{cid}/anomaly-model", json={"name": "speed"}).json()["model"] == "speed"
    assert client.put(f"/api/cameras/{cid}/anomaly-model", json={"name": "nope"}).status_code == 422
    assert client.put(f"/api/cameras/{cid}/model", json={"name": "nope"}).status_code == 404
    client.post(f"/api/cameras/{cid}/stop")
    cfg = client.get(f"/api/cameras/{cid}").json()["config"]
    assert cfg["zones"]["roi_meta"][0]["name"] == "Cổng A" and cfg["rules"]["cooldown_s"] == 5
    assert cfg["anomaly_model"] == "speed"
    assert client.get(f"/api/cameras/{cid}/rules").json()["cooldown_s"] == 5      # đọc được cả khi camera tắt


def test_models_listing(client):
    models = {m["name"]: m for m in client.get("/api/models").json()}
    assert models["mask"]["available"] and models["mask"]["has_mask"] and models["mask"]["mae"] == 8.49
    names = [m["name"] for m in client.get("/api/anomaly-models").json()["models"]]
    assert names[:2] == ["speed", "if_flow_mask_density"] and [n for n in names if n.startswith("if_")] == ["if_flow_mask_density"]


# ---------------------------------------------------------------- lịch sử và thống kê
def test_events_history_ack_csv_context_and_stats(client):
    cid = started(client)
    assert client.put(f"/api/cameras/{cid}/rules", json={"count_limit": -1.0, "persist_s": 0, "smooth": 1}).status_code == 200
    rows = []
    end = time.time() + 15
    while time.time() < end and not rows:
        rows = client.get(f"/api/events?camera_id={cid}").json()["rows"]
        time.sleep(0.3)
    assert rows and rows[0]["rule"] == "zone_limit" and rows[0]["status"] == "new"
    assert client.get(rows[0]["snapshot"]).status_code == 200
    assert client.get("/api/system").json()["unacked"] >= 1
    acked = client.post(f"/api/events/{rows[0]['id']}/ack", json={"note": "đã kiểm tra"}).json()
    assert acked["status"] == "ack" and acked["ack_by"] == "qt"
    assert client.get("/api/events?status=ack").json()["total"] == 1
    csv_text = client.get(f"/api/events.csv?camera_id={cid}").content.decode("utf-8-sig")
    assert csv_text.startswith("id,t,camera_id") and "zone_limit" in csv_text
    ctx = client.get(f"/api/events/{rows[0]['id']}/context").json()
    assert ctx["event"]["id"] == rows[0]["id"] and ctx["series"]
    now = time.time()
    st = client.get(f"/api/stats?camera_id={cid}&t0={now - 3600}&t1={now + 60}").json()
    assert st["bucket"] == 60 and st["series"] and st["summary"]["events"].get("zone_limit")
    assert st["heatmap"] and st["events_by_day"]
    assert client.get(f"/api/stats?t0={now}&t1={now - 1}").status_code == 422


def test_upload_rules(client):
    assert client.post("/api/videos", files={"file": ("x.txt", b"abc", "text/plain")}).status_code == 415
    r = client.post("/api/videos", files={"file": ("new.webm", b"\x1a\x45\xdf\xa3", "video/webm")})
    assert r.status_code == 200 and "new.webm" in client.get("/api/videos").json()
