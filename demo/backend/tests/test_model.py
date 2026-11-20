import math

import numpy as np
import pytest

from crowd_demo.config import Settings
from crowd_demo.model import infer, load_model, warmup


@pytest.fixture(scope="module")
def model():
    path = Settings().model_path
    if not path.exists():
        pytest.skip(f"Không có model ở {path}")
    return load_model(path)


def test_load_model_detects_mask_head(model):
    assert model.mask_head is not None


def test_infer_shapes_and_count(model):
    frame = np.zeros((720, 1280, 3), np.uint8)
    r = infer(model, frame, analysis_width=960)
    assert r.density.shape == (math.ceil(540 / 4), 960 // 4)
    assert r.mask is not None and r.mask.shape == r.density.shape
    assert abs(r.scale - 0.75) < 1e-6
    assert r.density.sum() < 5


def test_warmup_runs_on_16_9_frame(model):
    seconds = warmup(model, analysis_width=960)
    assert seconds > 0
