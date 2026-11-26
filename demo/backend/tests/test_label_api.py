import io
import json
import time
import zipfile

from test_api import app_client, client, login, model, started  # noqa: F401  (fixture dùng chung)


def wait_capture(c, cid):
    end = time.time() + 15
    while time.time() < end:
        r = c.post("/api/labels/capture", json={"camera_id": cid})
        if r.status_code == 200:
            return r.json()["image"]
        time.sleep(0.2)
    raise AssertionError(r.text)


def test_capture_prelabel_save_export(client):
    cid = started(client)
    name = wait_capture(client, cid)
    assert name.startswith("live_") and name.endswith(f"_cam{cid}.jpg")
    assert client.get("/api/labels/items").json()[0]["image"] == name
    assert client.get(f"/api/labels/image/{name}").headers["content-type"] == "image/jpeg"
    pre = client.post(f"/api/labels/prelabel/{name}").json()
    assert pre["auto_count"] >= 0 and isinstance(pre["points"], list)
    assert client.get(f"/api/labels/label/{name}").json()["points"] == []     # nháp chưa tự lưu
    body = {"points": [[10, 20]], "ignore": [], "status": "done", "note": ""}
    assert client.put(f"/api/labels/label/{name}", json=body).status_code == 200
    assert client.put(f"/api/labels/label/{name}", json=body).status_code == 200
    log = [a for a in client.get("/api/audit").json() if a["action"] == "label_status"]
    assert len(log) == 1                                                        # chỉ ghi khi đổi trạng thái
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/labels/export").content))
    ann = json.loads(z.read("annotations.json"))
    assert ann["images"][0]["image"] == name and len(ann["images"][0]["points"]) == 1
    assert f"images/{name}" in z.namelist()


def test_labeling_is_admin_only(app_client):
    assert app_client.get("/api/labels/items").status_code == 401
    login(app_client, "xem", "mk2")
    assert app_client.get("/api/labels/items").status_code == 403
    assert app_client.get("/api/labels/export").status_code == 403
    assert app_client.get("/labeling").status_code == 200          # chỉ là trang tĩnh, dữ liệu nằm sau API
