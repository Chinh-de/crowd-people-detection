import threading
import time

import cv2
import numpy as np
import pytest

from crowd_demo.config import Settings
from crowd_demo.model import load_model
from crowd_demo.pipeline import Pipeline


@pytest.fixture(scope="module")
def model():
    path = Settings().model_path
    if not path.exists():
        pytest.skip(f"Không có model ở {path}")
    return load_model(path)


@pytest.fixture
def pipeline(model, tmp_path):
    p = Pipeline(Settings(data_dir=tmp_path), model)
    yield p
    p.stop()


def wait_for(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_pipeline_produces_frames_and_status(pipeline, sample_video):
    pipeline.start({"kind": "file", "path": str(sample_video), "tz": "UTC"})
    assert wait_for(lambda: pipeline.status()["perf"]["analysis_fps"] > 0)
    s = pipeline.status()
    assert pipeline.latest_jpeg() is not None and s["state"] == "running"
    assert 6 <= s["perf"]["video_fps"] <= 13
    assert s["source"]["label"] == "sample.mp4" and s["source"]["live"] is False


def test_switch_source_stops_old_threads(pipeline, sample_video, tmp_path):
    before = threading.active_count()
    pipeline.start({"kind": "file", "path": str(sample_video), "tz": "UTC"})
    pipeline.start({"kind": "file", "path": str(sample_video), "tz": "UTC"})
    time.sleep(1)
    pipeline.stop()
    assert wait_for(lambda: threading.active_count() <= before, timeout=5)
    assert pipeline.status()["state"] == "idle"


def test_stop_while_paused_is_prompt(pipeline, sample_video):
    before = threading.active_count()
    pipeline.start({"kind": "file", "path": str(sample_video), "tz": "UTC"})
    time.sleep(0.5)
    pipeline.playback("pause")
    time.sleep(0.3)
    t0 = time.monotonic()
    pipeline.stop()
    assert time.monotonic() - t0 < 3
    assert wait_for(lambda: threading.active_count() <= before, timeout=3)


def test_motion_unavailable_without_frame_pair(pipeline, sample_video):
    """Không có cặp frame cách nhau hợp lý thì không tính flow (tránh ghi tốc độ 0 giả)."""
    pipeline.start({"kind": "file", "path": str(sample_video), "tz": "UTC"})
    pipeline.stop()
    from crowd_demo.evidence import FrameRing
    pipeline.ring = FrameRing(10)
    frame = np.zeros((240, 320, 3), np.uint8)
    pipeline.ring.push(100.0, frame)
    assert pipeline._motion_stats(100.0, None, pipeline.zones) is None          # chỉ có 1 frame
    pipeline.ring.push(103.0, frame)
    assert pipeline._motion_stats(103.0, None, pipeline.zones) is None          # khoảng cách 3 s: luồng bị khựng


def test_mode_change_applies(pipeline, sample_video):
    pipeline.start({"kind": "file", "path": str(sample_video), "tz": "UTC"})
    pipeline.set_mode("gray")
    seq = pipeline.frame_seq
    assert wait_for(lambda: pipeline.frame_seq > seq + 2)
    img = cv2.imdecode(np.frombuffer(pipeline.latest_jpeg(), np.uint8), cv2.IMREAD_COLOR).astype(int)
    # nền xám (lớp phủ màu chỉ chiếm một phần ảnh)
    assert np.median(np.abs(img[..., 0] - img[..., 2])) <= 2


def test_error_state_on_bad_source(pipeline, tmp_path):
    with pytest.raises(Exception):
        pipeline.start({"kind": "file", "path": str(tmp_path / "missing.mp4"), "tz": "UTC"})
    assert pipeline.status()["state"] == "idle"
