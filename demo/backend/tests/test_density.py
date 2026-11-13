import numpy as np
import pytest

from crowd_demo.density import analyze_density
from crowd_demo.zones import ZoneSet


def test_analyze_density_counts_by_zone():
    den = np.zeros((40, 40))
    den[5, 5] = 3
    den[30, 30] = 2
    z = ZoneSet([[(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)]], [])
    s = analyze_density(den, z, cell=8, cell_limit=2.5)
    assert s.total == pytest.approx(5) and s.roi == pytest.approx(3)
    assert s.max_cell == pytest.approx(3) and s.hot_cells == [(0, 0)]


def test_excluded_counted_separately():
    den = np.ones((10, 10))
    z = ZoneSet([], [[(0, 0), (0.5, 0), (0.5, 1), (0, 1)]])
    s = analyze_density(den, z, cell=5, cell_limit=None)
    # fillPoly tính cả cạnh biên nên vùng loại trừ phủ 6/10 cột
    assert s.excluded == pytest.approx(60) and s.roi == pytest.approx(40) and s.hot_cells == []
    assert s.excluded + s.roi == pytest.approx(s.total)
