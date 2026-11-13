import numpy as np

from crowd_demo.domain import Alert, DensityStats, MotionStats
from crowd_demo.storage import Store


def test_samples_and_events_roundtrip(tmp_path):
    s = Store(tmp_path / "crowd.db")
    d = DensityStats(total=10, roi=8, excluded=1, cells=np.zeros((1, 1)), max_cell=2)
    for t in (1.0, 2.0, 3.0):
        s.add_sample(t, "cam", d, MotionStats(speed=5))
    assert [r["t"] for r in s.series(2.0)] == [2.0, 3.0]
    assert s.series(0)[0]["roi"] == 8 and s.series(0)[0]["speed"] == 5

    eid = s.add_event(Alert("overcrowd", 2.0, 80, 60, "Quá đông"), "cam", "a.jpg")
    s.set_clip(eid, "a.mp4")
    ev = s.events()
    assert ev[0]["id"] == eid and ev[0]["clip"] == "a.mp4" and ev[0]["rule"] == "overcrowd"
