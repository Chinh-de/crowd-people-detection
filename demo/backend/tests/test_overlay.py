import cv2
import numpy as np
import pytest

from crowd_demo.config import VIEW_MODES
from crowd_demo.overlay import Layers, render
from crowd_demo.zones import ZoneSet


@pytest.fixture
def frame():
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, (240, 320, 3), np.uint8)


@pytest.mark.parametrize("mode", VIEW_MODES)
def test_all_modes_shape(frame, mode):
    layers = Layers(density=np.random.default_rng(1).random((60, 80)) * 0.05,
                    mask=np.ones((60, 80)), flow=np.ones((60, 80, 2), np.float32),
                    zones=ZoneSet([[(0.1, 0.1), (0.9, 0.1), (0.9, 0.9)]], []),
                    hot_cells=[(0, 0)], cell_frac=(0.2, 0.2), alert_active=True)
    out = render(frame, layers, mode, 160)
    assert out.shape == (120, 160, 3) and out.dtype == np.uint8


def test_video_mode_is_resized_frame(frame):
    expected = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
    assert np.array_equal(render(frame, Layers(density=np.ones((60, 80))), "video", 160), expected)


def test_overlay_only_empty_layers_is_black(frame):
    out = render(frame, Layers(density=np.zeros((60, 80))), "overlay_only", 160)
    assert out.max() == 0


def test_gray_without_density_has_equal_channels(frame):
    out = render(frame, Layers(), "gray", 160).astype(int)
    assert np.array_equal(out[..., 0], out[..., 1]) and np.array_equal(out[..., 1], out[..., 2])


def test_paint_built_once_per_layers_and_size(frame):
    layers = Layers(density=np.ones((60, 80)) * 0.02, mask=np.ones((60, 80)))
    render(frame, layers, "overlay", 160)
    first = layers._painted[(120, 160)]
    render(frame, layers, "gray", 160)
    assert layers._painted[(120, 160)] is first and len(layers._painted) == 1


def test_none_layers_ok(frame):
    assert render(frame, None, "overlay", 160).shape == (120, 160, 3)
