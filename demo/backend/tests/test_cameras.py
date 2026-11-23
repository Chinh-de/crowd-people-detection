import shutil
import time

import pytest

from crowd_demo.cameras import CameraLimitError, CameraManager
from crowd_demo.config import Settings
from crowd_demo.model import load_model
from crowd_demo.storage import Database


@pytest.fixture(scope="module")
def model():
    path = Settings().model_path
    if not path.exists():
        pytest.skip(f"Không có model ở {path}")
    return load_model(path)


@pytest.fixture
def manager(model, tmp_path, sample_video):
    s = Settings(data_dir=tmp_path, max_cameras=2)
    s.videos_dir.mkdir(parents=True)
    shutil.copy(sample_video, s.videos_dir / "a.mp4")
    db = Database(s.db_path)
    m = CameraManager(s, db, {"mask": model})
    yield m
    m.stop_all()
    db.close()


def wait_for(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_create_start_and_persist_config_changes(manager):
    cid = manager.create({"name": "Cổng A", "kind": "file", "source": "a.mp4", "tz": "UTC"})
    manager.start(cid)
    p = manager.get(cid)
    assert p is not None and p.status()["camera"] == "Cổng A"
    assert wait_for(lambda: p.status()["perf"]["analysis_fps"] > 0)
    p.set_mode("gray")
    from crowd_demo.zones import ZoneSet
    p.set_zones(ZoneSet([[(0, 0), (1, 0), (1, 1)]], [], [{"name": "Sảnh", "limit": 10}]))
    cfg = manager.db.get_camera(cid)["config"]
    assert cfg["view_mode"] == "gray" and cfg["zones"]["roi_meta"] == [{"name": "Sảnh", "limit": 10.0}]
    manager.stop(cid)
    manager.start(cid)                                  # bật lại: dùng cấu hình đã lưu
    assert manager.get(cid).mode == "gray" and manager.get(cid).zones.meta(0)["name"] == "Sảnh"


def test_limit_on_running_cameras(manager):
    ids = [manager.create({"name": f"C{i}", "kind": "file", "source": "a.mp4", "tz": "UTC"}) for i in range(3)]
    manager.start(ids[0])
    manager.start(ids[1])
    with pytest.raises(CameraLimitError):
        manager.start(ids[2])
    summary = {c["id"]: c for c in manager.list()}
    assert summary[ids[0]]["running"] and not summary[ids[2]]["running"]
    manager.stop(ids[0])
    manager.start(ids[2])                               # còn chỗ thì bật được


def test_delete_stops_camera_and_autostart(manager):
    cid = manager.create({"name": "Tự chạy", "kind": "file", "source": "a.mp4", "tz": "UTC", "autostart": True})
    other = manager.create({"name": "Không", "kind": "file", "source": "a.mp4", "tz": "UTC"})
    manager.autostart()
    assert manager.get(cid) is not None and manager.get(other) is None
    manager.delete(cid)
    assert manager.get(cid) is None and manager.db.get_camera(cid) is None


def test_validation_of_camera_fields(manager):
    with pytest.raises(ValueError):
        manager.create({"name": "", "kind": "file", "source": "a.mp4", "tz": "UTC"})
    with pytest.raises(ValueError):
        manager.create({"name": "X", "kind": "ftp", "source": "a.mp4", "tz": "UTC"})
    with pytest.raises(ValueError):
        manager.create({"name": "X", "kind": "file", "source": "../ngoai.mp4", "tz": "UTC"})
    with pytest.raises(ValueError):
        manager.create({"name": "X", "kind": "file", "source": "a.mp4", "tz": "Sao/Hoa"})


def test_seed_defaults_only_when_empty(manager):
    manager.seed_defaults()
    names = [c["name"] for c in manager.db.list_cameras()]
    assert len(names) >= 1
    manager.seed_defaults()
    assert len(manager.db.list_cameras()) == len(names)
