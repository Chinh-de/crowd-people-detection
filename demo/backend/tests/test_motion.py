import numpy as np
import pytest

from crowd_demo.motion import compute_flow, flow_features


def uniform(dx, dy, h=40, w=40):
    f = np.zeros((h, w, 2), np.float32)
    f[..., 0], f[..., 1] = dx, dy
    return f


def test_uniform_flow_low_entropy_no_counterflow():
    s = flow_features(uniform(2, 0), None, dt=0.2)
    assert s.entropy < 0.05 and s.counterflow == 0
    assert s.speed == pytest.approx(10) and abs(s.direction_deg) < 1


def test_opposite_halves_counterflow():
    f = uniform(2, 0)
    f[:, :15, 0] = -2                      # 25/40 cột sang phải, 15/40 sang trái
    assert flow_features(f, None, dt=1).counterflow == pytest.approx(15 / 40, abs=0.02)


def test_random_directions_high_entropy():
    a = np.random.default_rng(0).uniform(0, 2 * np.pi, (40, 40))
    f = (np.stack([np.cos(a), np.sin(a)], -1) * 3).astype(np.float32)
    assert flow_features(f, None, dt=1).entropy > 0.9


def test_valid_mask_and_still_scene():
    assert flow_features(uniform(0, 0), None, dt=1).speed == 0
    valid = np.zeros((40, 40), bool)
    assert flow_features(uniform(2, 0), valid, dt=1).active_ratio == 0


def test_compute_flow_detects_shift():
    rng = np.random.default_rng(1)
    base = (rng.integers(0, 255, (60, 80)).astype(np.uint8))
    img = np.repeat(np.repeat(base, 4, 0), 4, 1)                 # khối 4×4 để flow có cấu trúc
    img = np.stack([img] * 3, -1)
    flow = compute_flow(img, np.roll(img, 4, axis=1), width=320)
    assert np.median(flow[20:-20, 20:-20, 0]) == pytest.approx(4, abs=1)
