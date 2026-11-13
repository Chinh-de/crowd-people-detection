import cv2
import numpy as np

from crowd_demo.domain import Alert
from crowd_demo.evidence import EvidenceRecorder, FrameRing, write_clip
from crowd_demo.storage import Store


def frame(i, w=64, h=48):
    f = np.zeros((h, w, 3), np.uint8)
    f[:, (i * 3) % w] = 255
    return f


def test_write_clip_is_h264_mp4(tmp_path):
    path = write_clip([frame(i) for i in range(20)], 10, tmp_path / "c.mp4")
    assert path.stat().st_size > 0
    cap = cv2.VideoCapture(str(path))
    n = 0
    while cap.read()[0]:
        n += 1
    assert n >= 15


def test_recorder_writes_clip_after_post_window(tmp_path):
    ring = FrameRing(seconds=20, fps_cap=10)
    store = Store(tmp_path / "db.sqlite")
    rec = EvidenceRecorder(ring, store, tmp_path / "ev", pre_s=5, post_s=5)
    for i in range(0, 121):                        # 0..12 s, 10 frame/s
        t = i / 10
        ring.push(t, frame(i, 128, 96))
        if i == 60:
            rec.on_alert(Alert("surge", 6.0, 30, 15, "Tăng đột ngột"), frame(i, 128, 96), "cam")
        if i == 100:
            rec.tick(10.0)
            assert store.events()[0]["clip"] is None
    rec.tick(11.5)
    ev = store.events()[0]
    assert ev["clip"] and (tmp_path / "ev" / ev["clip"]).exists()
    assert (tmp_path / "ev" / ev["snapshot"]).exists()
