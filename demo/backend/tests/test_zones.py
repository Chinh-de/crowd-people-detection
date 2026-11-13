import pytest

from crowd_demo.zones import ZoneSet

FULL = [(0, 0), (1, 0), (1, 1), (0, 1)]
LEFT = [(0, 0), (0.5, 0), (0.5, 1), (0, 1)]


def test_no_roi_means_full_frame():
    m = ZoneSet([], []).masks(10, 20)
    assert m["watch"].all()


def test_exclude_removed_from_watch():
    m = ZoneSet([FULL], [LEFT]).masks(10, 20)
    assert m["watch"][:, :10].sum() == 0 and m["watch"][:, 11:].all()


def test_validate_rejects_short_polygon():
    with pytest.raises(ValueError):
        ZoneSet([[(0, 0), (1, 1)]], []).validate()


def test_validate_rejects_out_of_range():
    with pytest.raises(ValueError):
        ZoneSet([[(0, 0), (1.5, 0), (1, 1)]], []).validate()


def test_dict_roundtrip():
    z = ZoneSet([FULL], [LEFT])
    assert ZoneSet.from_dict(z.to_dict()).to_dict() == z.to_dict()
