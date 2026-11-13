import shutil
import time

import pytest
from fastapi.testclient import TestClient

from crowd_demo.api import create_app
from crowd_demo.config import Settings
from crowd_demo.model import load_model

ROI = {"roi": [[[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]], "exclude": []}


@pytest.fixture(scope="module")
def model():
    path = Settings().model_path
    if not path.exists():
        pytest.skip(f"Không có model ở {path}")
    return load_model(path)


@pytest.fixture
def client(model, tmp_path, sample_video):
    settings = Settings(data_dir=tmp_path)
    settings.videos_dir.mkdir(parents=True)
    shutil.copy(sample_video, settings.videos_dir / "a.mp4")
    (settings.videos_dir / "b.webm").write_bytes(b"")
    (settings.videos_dir / "c.txt").write_text("x")
    with TestClient(create_app(settings, model)) as c:
        yield c


def start(client):
    r = client.post("/api/source", json={"kind": "file", "path": "a.mp4", "tz": "UTC"})
    assert r.status_code == 200, r.text


def test_list_videos(client):
    assert client.get("/api/videos").json() == ["a.mp4", "b.webm"]


def test_upload_rejects_unsupported_extension(client):
    r = client.post("/api/videos", files={"file": ("x.txt", b"abc", "text/plain")})
    assert r.status_code == 415


def test_upload_accepts_webm(client):
    r = client.post("/api/videos", files={"file": ("new.webm", b"\x1a\x45\xdf\xa3", "video/webm")})
    assert r.status_code == 200 and "new.webm" in client.get("/api/videos").json()


def test_bad_source_returns_409(client):
    r = client.post("/api/source", json={"kind": "file", "path": "missing.mp4", "tz": "UTC"})
    assert r.status_code == 409 and r.json()["detail"]


def test_start_file_source_then_status_ws(client):
    start(client)
    with client.websocket_connect("/api/ws") as ws:
        assert ws.receive_json()["state"] == "running"


def test_put_zones_rejects_invalid_polygon(client):
    start(client)
    assert client.put("/api/zones", json=ROI).status_code == 200
    bad = {"roi": [[[0, 0], [1, 1]]], "exclude": []}
    assert client.put("/api/zones", json=bad).status_code == 422
    assert client.get("/api/zones").json() == ROI


def test_put_view_rejects_unknown_mode(client):
    assert client.put("/api/view", json={"mode": "gray"}).status_code == 200
    assert client.put("/api/view", json={"mode": "thermal"}).status_code == 422


def test_stream_returns_jpeg_parts(client):
    start(client)
    with client.stream("GET", "/api/stream.mjpg") as r:
        assert r.headers["content-type"].startswith("multipart/x-mixed-replace")
        data = b""
        for chunk in r.iter_bytes():
            data += chunk
            if data.count(b"\xff\xd8") >= 2:
                break
    assert data.count(b"\xff\xd8") >= 2


def test_events_endpoint_after_forced_alert(client):
    start(client)
    rules = client.get("/api/rules").json()
    rules["count_limit"] = -1.0
    assert client.put("/api/rules", json=rules).status_code == 200
    events = []
    end = time.time() + 15
    while time.time() < end and not events:
        events = client.get("/api/events").json()
        time.sleep(0.3)
    assert events and events[0]["rule"] == "overcrowd"
    assert client.get(events[0]["snapshot"]).status_code == 200
    assert client.get("/api/series?minutes=5").json()


def test_list_and_switch_models(client):
    models = {m["name"]: m for m in client.get("/api/models").json()}
    assert set(models) == {"mask", "baseline"}
    assert models["mask"]["active"] and models["mask"]["available"] and models["mask"]["has_mask"]
    start(client)
    r = client.put("/api/model", json={"name": "baseline"})
    assert r.status_code == 200, r.text
    s = client.get("/api/models").json()
    assert [m["name"] for m in s if m["active"]] == ["baseline"]
    assert next(m for m in s if m["name"] == "baseline")["has_mask"] is False
    assert client.put("/api/model", json={"name": "nope"}).status_code == 404
