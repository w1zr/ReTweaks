from rt_pages.monitor import banner_palette, normalize_color


def test_default_is_original_purple():
    p = banner_palette(None, "#3b82f6")
    assert p["mode"] == "original" and p["space"] == "#0c0a1d" and p["nebula"] == ("#7c3aed", "#06b6d4")
    assert p["accent"] == "#3b82f6"


def test_black_and_white_has_no_colour():
    p = banner_palette("mono", "#ec4899")
    cols = [p["space"], *p["nebula"], *p["stars"].values(), p["title"], p["sub"], p["accent"]]
    for c in cols:
        r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
        assert r == g == b, c


def test_accent_and_custom():
    assert banner_palette("accent", "#22c55e")["nebula"][0] == "#22c55e"
    assert banner_palette("custom", "#22c55e", "#ff0000")["accent"] == "#ff0000"
    assert banner_palette("custom", "#22c55e", "bad")["mode"] == "accent"    # invalid HEX falls back
    assert normalize_color("nonsense") == "original"
