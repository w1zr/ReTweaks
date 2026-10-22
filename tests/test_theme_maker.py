"""Theme maker: palettes, share codes and validation (no Qt needed)."""

from core import themes as T


def test_share_code_roundtrip():
    colors = T.editable_colors("Galaxy")
    ok, name, back = T.parse_code(T.export_code("Night Sky", colors))
    assert ok and name == "Night Sky" and back == {k: v.lower() for k, v in colors.items()}


def test_bad_codes_are_rejected_safely():
    for code in ["", "hello", "RYT1-!!!", "RYT1-" + "A" * 3000, T.SHARE_PREFIX + "eyJuIjoxfQ"]:
        ok, msg, colors = T.parse_code(code)
        assert not ok and colors is None and msg


def test_code_with_bad_color_is_rejected():
    colors = T.editable_colors("Midnight")
    colors["accent"] = "red; background:url(x)"
    code = T.export_code("x", {**T.editable_colors("Midnight")})
    import base64, json
    data = {"n": "x", "c": colors}
    bad = T.SHARE_PREFIX + base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
    ok, msg, _ = T.parse_code(bad)
    assert not ok and "Accent" in msg and code


def test_custom_theme_registry_and_derived_tokens():
    colors = T.editable_colors("Midnight")
    colors["bg"] = "#ffffff"
    T.set_custom_themes({"Paper": colors, "Midnight": colors, "Broken": {"bg": "nope"}})
    assert T.custom_theme_names() == ["Paper"]           # built-in names and bad entries are skipped
    t = T.get_theme("Paper")
    assert t["light"] and t["logo"] == t["text"] and t["on_accent"] in ("#ffffff", "#0f1115")
    T.set_custom_themes({})


def test_contrast():
    assert round(T.contrast("#000000", "#ffffff")) == 21
    assert T.contrast("#777777", "#777777") == 1
