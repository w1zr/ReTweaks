from ui.widgets.banners import (extract_per_core, extract_total_load, normalize_style,
                                smooth_step, tile_grid, trim_wave)


def test_tile_grid():
    assert tile_grid(8) == (2, 4)
    assert tile_grid(16) == (2, 8)
    assert tile_grid(28) == (2, 14)
    assert tile_grid(64) == (3, 22)
    assert tile_grid(33) == (3, 11)
    assert tile_grid(1) == (1, 1)
    assert tile_grid(0) == (0, 0)


def test_tile_grid_covers_all_threads():
    for n in (1, 2, 7, 12, 20, 32, 33, 48, 64, 128):
        r, c = tile_grid(n)
        assert r * c >= n


def test_smooth_step():
    v = 0.0
    for _ in range(40):
        v = smooth_step(v, 80.0)
    assert v == 80.0
    assert smooth_step(50.0, 50.1) == 50.1
    assert 0 < smooth_step(0.0, 100.0) < 100
    assert smooth_step(30.0, None) == 30.0


def test_trim_wave():
    data = [(0, 1), (30, 2), (50, 3), (100, 4)]
    assert trim_wave(data, 100) == [(50, 3), (100, 4)]
    assert trim_wave([], 5) == []


def test_normalize_style():
    for s in ("off", "cores", "circuit", "galaxy", "wave"):
        assert normalize_style(s) == s
    assert normalize_style("WAVE") == "wave"
    assert normalize_style("bogus") == "cores"
    assert normalize_style(None) == "cores"
    assert normalize_style(5) == "cores"


def test_extractors():
    s = {"cpu": {"load": 12.5, "per_core": [10, 150, -5]}}
    assert extract_total_load(s) == 12.5
    assert extract_per_core(s) == [10.0, 100.0, 0.0]
    assert extract_total_load({}) is None
    assert extract_per_core({"cpu": {"per_core": []}}) is None
    assert extract_per_core({"cpu": {"load": None}}) is None
