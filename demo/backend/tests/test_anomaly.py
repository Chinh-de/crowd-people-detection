import numpy as np
import pytest
import torch

from crowd_demo.anomaly import (ANOMALY_MODELS, GRID, AnomalyMonitor, GridAE, cell_features, frame_vectors,
                                make_detector)


def flow_field(h=240, w=320, dx=1.0, dy=0.0):
    f = np.zeros((h, w, 2), np.float32)
    f[..., 0], f[..., 1] = dx, dy
    return f


def test_cell_features_shapes_and_values():
    h, w = 240, 320
    flow = flow_field(h, w, dx=2.0)
    weight = np.ones((h, w), np.float32)
    density = np.full((60, 80), 0.01, np.float32)                 # 48 người
    feats = cell_features(flow, weight, density, np.ones((60, 80), np.float32), dt=1 / 30)
    assert feats.fm.shape == feats.f0.shape == (GRID, GRID, 11) and feats.d.shape == (GRID, GRID, 2)
    assert np.allclose(feats.fm[..., 0], 2.0, atol=1e-3)           # tốc độ = px mỗi khung 1/30 s
    assert np.allclose(feats.fm[..., 1:9].sum(-1), 1.0, atol=1e-3) # histogram hướng chuẩn hóa
    assert np.allclose(feats.fm[..., 9], 0.0, atol=1e-3)           # một hướng duy nhất: entropy 0
    assert np.allclose(feats.fm[..., 10], 1.0, atol=1e-3)          # đồng hướng tuyệt đối
    assert np.isclose(feats.d[..., 0].sum(), 48.0, rtol=1e-4) and np.allclose(feats.d[..., 1], 1.0)


def test_speed_is_normalised_to_one_frame_at_30fps():
    flow = flow_field(dx=12.0)                                     # 12 px trong 0,2 s = 2 px mỗi 1/30 s
    w = np.ones(flow.shape[:2], np.float32)
    f = cell_features(flow, w, np.zeros((60, 80), np.float32), None, dt=0.2)
    assert np.allclose(f.fm[..., 0], 2.0, atol=1e-3)


def test_mask_weight_removes_background_motion():
    flow = flow_field(dx=3.0)
    weight = np.zeros(flow.shape[:2], np.float32)
    f = cell_features(flow, weight, np.zeros((60, 80), np.float32), None, dt=1 / 30)
    assert np.allclose(f.fm[..., 0], 0.0) and np.allclose(f.f0[..., 0], 3.0, atol=1e-3)


def test_frame_vectors_mean_max_std():
    grid = np.zeros((2, GRID, GRID, 3), np.float32)
    grid[1, 0, 0] = 64.0
    v = frame_vectors(grid)
    assert v.shape == (2, 9) and v[1, 0] == pytest.approx(1.0) and v[1, 3] == pytest.approx(64.0)


def _normal_feats(rng, n, speed=1.0):
    from crowd_demo.anomaly import CellFeats
    out = []
    for _ in range(n):
        fm = rng.normal(0, .05, (GRID, GRID, 11)).astype(np.float32)
        fm[..., 0] += speed
        d = np.abs(rng.normal(1, .1, (GRID, GRID, 2))).astype(np.float32)
        if speed > 1:      # hoảng loạn như trên UMN: chạy nhanh, hướng tập trung, người rời khung hình
            fm[..., 9] -= 0.5
            fm[..., 10] += 0.5
            d[..., 0] *= 0.2
        out.append(CellFeats(fm=fm, f0=fm.copy(), d=d))
    return out


@pytest.mark.parametrize("name", [n for n in ANOMALY_MODELS if not n.startswith("ae_")])
def test_detectors_flag_fast_motion_after_fit(name):
    rng = np.random.default_rng(0)
    det = make_detector(name)
    det.fit(_normal_feats(rng, 200))
    normal = [det.score(f)[0] for f in _normal_feats(rng, 20)]
    fast = [det.score(f)[0] for f in _normal_feats(rng, 20, speed=8.0)]
    assert det.limit is not None and np.median(fast) > det.limit > np.median(normal)


def test_ae_detector_loads_notebook_checkpoint_and_scores(tmp_path):
    model = GridAE(16 * 13)
    torch.save(model.state_dict(), tmp_path / "ae.pth")
    np.savez(tmp_path / "ae_norm.npz", mean=np.zeros((GRID, GRID, 13)), std=np.ones((GRID, GRID, 13)))
    det = make_detector("ae_scene1", weights=tmp_path / "ae.pth", norm=tmp_path / "ae_norm.npz")
    rng = np.random.default_rng(1)
    det.fit(_normal_feats(rng, 60))
    s, cells = det.score(_normal_feats(rng, 1)[0])
    assert np.isfinite(s) and cells.shape == (GRID, GRID) and det.limit is not None


def test_monitor_learns_then_scores_and_switches_without_relearning():
    rng = np.random.default_rng(2)
    mon = AnomalyMonitor("if_flow_mask_density")
    mon.start_calibration(50)
    for f in _normal_feats(rng, 50):
        assert mon.update(f) is None                               # đang học: chưa chấm điểm
    assert mon.ready
    r = mon.update(_normal_feats(rng, 1, speed=8.0)[0])
    assert r is not None and r.score > r.limit
    mon.select("speed")                                            # đổi mô hình: học lại từ dữ liệu đã có
    assert mon.ready and mon.update(_normal_feats(rng, 1)[0]) is not None
