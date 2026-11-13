import numpy as np

from crowd_demo.domain import DensityStats, MotionStats
from crowd_demo.rules import RuleConfig, RuleEngine


def stats(roi, max_cell=1.0):
    return DensityStats(total=roi, roi=roi, excluded=0.0, cells=np.zeros((1, 1)), max_cell=max_cell)


def feed(engine, rois, t0=0.0, dt=2.0, speeds=None, entropies=None, counter=None, cells=None):
    alerts, n = [], len(rois)
    speeds = speeds if speeds is not None else [10.0] * n
    entropies = entropies if entropies is not None else [0.5] * n
    counter = counter if counter is not None else [0.1] * n
    cells = cells if cells is not None else [1.0] * n
    for i in range(n):
        m = MotionStats(speed=speeds[i], entropy=entropies[i], counterflow=counter[i], active_ratio=0.3)
        alerts += engine.update(t0 + i * dt, stats(rois[i], cells[i]), m)
    return alerts


def calibrated(n=60, cfg=None, **kw):
    rng = np.random.default_rng(0)
    e = RuleEngine(cfg or RuleConfig())
    e.start_calibration(n * 2.0, now=0.0, rate_hz=0.5)
    feed(e, list(60 + rng.normal(0, 3, n)),
         speeds=list(10 + rng.normal(0, 1, n)), entropies=list(0.5 + rng.normal(0, 0.03, n)),
         counter=list(0.1 + rng.normal(0, 0.02, n)), **kw)
    assert e.calibration_progress()[0] >= e.calibration_progress()[1]
    return e


def test_no_statistical_alert_before_calibration():
    assert feed(RuleEngine(RuleConfig()), [200.0] * 10) == []
    alerts = feed(RuleEngine(RuleConfig(count_limit=100)), [200.0] * 10)
    assert [a.rule for a in alerts] == ["overcrowd"]


def test_absolute_limit_active_during_calibration():
    e = RuleEngine(RuleConfig(count_limit=100))
    e.start_calibration(60, now=0.0, rate_hz=1.0)
    alerts = feed(e, [200.0] * 5)
    assert [a.rule for a in alerts] == ["overcrowd"] and not e.calibrated


def test_overcrowd_after_calibration_with_persistence():
    e = calibrated(cfg=RuleConfig(smooth=1, persist_s=4))   # không làm mượt để kiểm tra đúng điều kiện duy trì 4 s
    t0 = 200.0
    assert feed(e, [120.0, 120.0], t0=t0) == []
    assert [a.rule for a in feed(e, [120.0], t0=t0 + 4)] == ["overcrowd"]
    assert [a for a in feed(e, [120.0] * 5, t0=t0 + 6) if a.rule == "overcrowd"] == []


def test_surge_detected_on_fast_rise():
    e = calibrated()
    t0 = 200.0
    feed(e, [60.0] * 40, t0=t0)
    rise = list(np.linspace(60, 110, 10)) + [110.0] * 10
    alerts = []
    for i, v in enumerate(rise):
        for a in feed(e, [v], t0=t0 + 80 + i * 2):
            alerts.append((i, a.rule))
    surge = [i for i, r in alerts if r == "surge"]
    assert surge and surge[0] <= 10         # làm mượt 3 mẫu + duy trì 6 s: phát hiện trong ~20 s


def test_panic_requires_speed_and_entropy():
    e = calibrated()
    only_speed = feed(e, [60.0] * 5, t0=200, speeds=[40.0] * 5)
    assert all(a.rule != "panic" for a in only_speed)
    both = feed(e, [60.0] * 5, t0=220, speeds=[40.0] * 5, entropies=[0.95] * 5)
    assert any(a.rule == "panic" for a in both)


def test_counterflow_alert():
    e = calibrated()
    alerts = feed(e, [60.0] * 5, t0=200, counter=[0.5] * 5)
    assert any(a.rule == "counterflow" for a in alerts)


def test_disabled_rule_never_fires():
    cfg = RuleConfig(count_limit=100)
    cfg.enabled["overcrowd"] = False
    assert feed(RuleEngine(cfg), [200.0] * 10) == []


def test_persistence_measured_in_seconds():
    e = RuleEngine(RuleConfig(count_limit=100, persist_s=6, smooth=1))
    alerts = []
    for i in range(10):
        alerts += [(i, a.rule) for a in feed(e, [200.0], t0=i * 1.0)]
    assert alerts == [(6, "overcrowd")]        # đúng liên tục từ t=0 tới t=6


def test_cooldown_blocks_repeated_alerts():
    e = RuleEngine(RuleConfig(count_limit=100, persist_s=0, smooth=1, cooldown_s=60))
    assert len(feed(e, [200.0], t0=0)) == 1
    feed(e, [50.0], t0=10)                                       # hết đợt
    assert feed(e, [200.0, 200.0], t0=20, dt=10) == []           # đợt mới nhưng còn trong 60 s nghỉ
    assert [a.rule for a in feed(e, [200.0], t0=61)] == ["overcrowd"]   # đợt vẫn kéo dài: nhắc lại sau khi hết nghỉ


def test_threshold_floors_on_flat_calibration():
    """Phố vắng, không ai đi ngược: MAD = 0 không được làm ngưỡng sát mức hiện tại."""
    e = RuleEngine(RuleConfig())
    e.start_calibration(60, now=0.0, rate_hz=0.5)
    feed(e, [10.0] * 30, counter=[0.0] * 30, cells=[1.0] * 30)
    th = e.thresholds()
    assert th["overcrowd"] >= 15 and th["hot_cell"] >= 4 and th["counterflow"] >= 0.3


def test_baseline_follows_slow_change():
    """Mức nền cập nhật theo cửa sổ trượt: phố đông dần lên trong buổi tối thì ngưỡng cũng tăng theo."""
    e = RuleEngine(RuleConfig(baseline_window_s=600))
    e.start_calibration(60, now=0.0, rate_hz=0.5)
    feed(e, [10.0] * 30)
    before = e.thresholds()["overcrowd"]
    feed(e, [30.0] * 600, t0=60.0)                               # 20 phút đông hơn
    assert e.thresholds()["overcrowd"] > 30 > before
