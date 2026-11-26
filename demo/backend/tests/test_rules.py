import numpy as np
import pytest

from crowd_demo.anomaly import Reading
from crowd_demo.domain import RULE_NAMES, DensityStats, MotionStats, ZoneCount
from crowd_demo.motion import wrong_way
from crowd_demo.rules import RuleConfig, RuleEngine
from crowd_demo.zones import ZoneSet


def stats(roi, zones=()):
    return DensityStats(total=roi, roi=roi, excluded=0.0, cells=np.zeros((1, 1)), max_cell=1.0, zones=list(zones))


def feed(engine, values, t0=0.0, dt=1.0, reading=None):
    out = []
    for i, v in enumerate(values):
        out += engine.update(t0 + i * dt, v if isinstance(v, DensityStats) else stats(v), MotionStats(), reading)
    return out


def cfg(**kw):
    return RuleConfig(**{"smooth": 1, **kw})


def test_only_four_rules_remain():
    assert RULE_NAMES == ("zone_limit", "surge", "panic", "counterflow")


def test_whole_frame_capacity_persists_then_reports_once():
    e = RuleEngine(cfg(count_limit=100, persist_s=6))
    alerts = [(i, a.rule, a.message) for i in range(12) for a in feed(e, [200], t0=i)]
    assert [(i, r) for i, r, _ in alerts] == [(6, "zone_limit")]
    assert "Toàn khung 200/100 người" in alerts[0][2]


def test_zone_capacity_names_the_zone_and_needs_no_learning():
    e = RuleEngine(cfg(persist_s=0))
    zones = [ZoneCount("Cổng A", 35.0, 30.0), ZoneCount("Cổng B", 10.0, 30.0), ZoneCount("Sảnh", 99.0, None)]
    alerts = feed(e, [stats(40, zones)])
    assert [a.rule for a in alerts] == ["zone_limit"] and "Cổng A 35/30" in alerts[0].message
    assert "Sảnh" not in alerts[0].message


def test_no_capacity_set_means_no_crowd_alert_however_many_people():
    assert feed(RuleEngine(cfg()), [500] * 20) == []


def test_surge_needs_both_absolute_and_relative_rise_and_says_from_to():
    quiet = RuleEngine(cfg(persist_s=0))
    assert feed(quiet, [60] * 60 + [75] * 10) == []                  # +15 nhưng chỉ 25%
    e = RuleEngine(cfg(persist_s=0))
    alerts = feed(e, [20] * 60 + [38] * 5)
    assert [a.rule for a in alerts] == ["surge"] and "từ 20 lên 38 người" in alerts[0].message


def test_wrong_way_needs_a_zone_direction_and_a_large_share():
    e = RuleEngine(cfg(persist_s=0, counterflow_share=0.4))
    ok = [ZoneCount("Lối A", 5, None, direction=0.0, wrong_share=0.2),
          ZoneCount("Phố", 5, None, direction=None, wrong_share=None)]
    assert feed(e, [stats(10, ok)]) == []
    bad = [ZoneCount("Lối A", 5, None, direction=0.0, wrong_share=0.7)]
    alerts = feed(e, [stats(10, bad)], t0=10)
    assert [a.rule for a in alerts] == ["counterflow"]
    assert "Lối A" in alerts[0].message and "70%" in alerts[0].message


def test_wrong_way_share_against_allowed_direction():
    flow = np.zeros((40, 40, 2), np.float32)
    flow[:, :30, 0] = 3.0                # 3/4 đi sang phải
    flow[:, 30:, 0] = -3.0               # 1/4 đi sang trái
    zone = np.ones((40, 40), bool)
    share, wrong = wrong_way(flow, zone, 0.0)                   # chiều cho phép: sang phải
    assert share == pytest.approx(0.25) and wrong[:, 30:].all() and not wrong[:, :30].any()
    assert wrong_way(flow, zone, 180.0)[0] == pytest.approx(0.75)
    assert wrong_way(np.zeros_like(flow), zone, 0.0)[0] is None          # không ai di chuyển: không kết luận
    tiny = np.zeros_like(flow)
    tiny[:3, :3, 0] = -3.0
    assert wrong_way(tiny, zone, 0.0)[0] is None                         # quá ít điểm chuyển động: coi là nhiễu


def test_zone_direction_is_saved_and_validated():
    poly = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]]
    z = ZoneSet.from_dict({"roi": [poly], "roi_meta": [{"name": "Lối A", "direction": 90}]})
    z.validate()
    assert z.meta(0)["direction"] == 90.0 and z.to_dict()["roi_meta"][0]["direction"] == 90.0
    assert ZoneSet.from_dict({"roi": [poly]}).meta(0)["direction"] is None
    with pytest.raises(ValueError):
        ZoneSet.from_dict({"roi": [poly], "roi_meta": [{"direction": 400}]}).validate()


def test_panic_uses_anomaly_score_with_short_persistence_even_in_empty_frame():
    e = RuleEngine(cfg(panic_persist_s=2))
    assert feed(e, [60] * 5, reading=Reading(0.4, 0.6, None)) == []
    assert [a.rule for a in feed(e, [1] * 4, t0=10, reading=Reading(0.9, 0.6, None))] == ["panic"]
    assert e.thresholds()["panic_score"] == 0.6


def test_disabled_rule_never_fires():
    c = cfg(count_limit=100, persist_s=0)
    c.enabled["zone_limit"] = False
    assert feed(RuleEngine(c), [200] * 10) == []


def test_cooldown_blocks_repeated_alerts():
    e = RuleEngine(cfg(count_limit=100, persist_s=0, cooldown_s=60))
    e.config.enabled["surge"] = False                                  # chỉ xét thời gian nghỉ của một luật
    assert len(feed(e, [200], t0=0)) == 1
    feed(e, [50], t0=10)
    assert feed(e, [200, 200], t0=20, dt=10) == []
    assert [a.rule for a in feed(e, [200], t0=61)] == ["zone_limit"]
