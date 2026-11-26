import numpy as np
import pytest

from crowd_demo.density import analyze_density
from crowd_demo.zones import ZoneSet


def test_analyze_density_counts_by_zone():
    den = np.zeros((40, 40))
    den[5, 5] = 3
    den[30, 30] = 2
    z = ZoneSet([[(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)]], [])
    s = analyze_density(den, z, cell=8)
    assert s.total == pytest.approx(5) and s.roi == pytest.approx(3)
    assert s.max_cell == pytest.approx(3)


def test_excluded_counted_separately():
    den = np.ones((10, 10))
    z = ZoneSet([], [[(0, 0), (0.5, 0), (0.5, 1), (0, 1)]])
    s = analyze_density(den, z, cell=5)
    # fillPoly tính cả cạnh biên nên vùng loại trừ phủ 6/10 cột
    assert s.excluded == pytest.approx(60) and s.roi == pytest.approx(40)
    assert s.excluded + s.roi == pytest.approx(s.total)


def test_counts_per_named_zone_with_limits():
    den = np.zeros((40, 40))
    den[5, 5] = 3
    den[30, 30] = 2
    z = ZoneSet([[(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)], [(0.5, 0.5), (1, 0.5), (1, 1), (0.5, 1)]], [],
                [{"name": "Trái trên", "limit": 2}, {"name": "Phải dưới", "limit": None}])
    s = analyze_density(den, z, cell=8)
    assert [(c.name, round(c.count), c.limit) for c in s.zones] == [("Trái trên", 3, 2.0), ("Phải dưới", 2, None)]
