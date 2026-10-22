from datetime import date

from core import display


def test_max_refresh_picks_highest_at_resolution():
    modes = [(1920, 1080, 32, 60), (1920, 1080, 32, 144), (1920, 1080, 32, 120),
             (2560, 1440, 32, 165), (1920, 1080, 32, 1), (1920, 1080, 32, 0)]
    assert display.max_refresh_at(modes, 1920, 1080) == 144
    assert display.max_refresh_at(modes, 2560, 1440) == 165
    assert display.max_refresh_at(modes, 800, 600) is None


def test_max_refresh_prefers_same_bit_depth_and_accepts_dicts():
    modes = [{"width": 1920, "height": 1080, "bpp": 16, "hz": 240},
             {"width": 1920, "height": 1080, "bpp": 32, "hz": 144}]
    assert display.max_refresh_at(modes, 1920, 1080, bpp=32) == 144
    assert display.max_refresh_at(modes, 1920, 1080) == 240
    assert display.max_refresh_at([], 1920, 1080) is None


def test_parse_cim_date():
    assert display.parse_cim_date("20240315000000.000000+000") == date(2024, 3, 15)
    assert display.parse_cim_date("20231102134512.500000-300") == date(2023, 11, 2)
    assert display.parse_cim_date("2022-07-09") == date(2022, 7, 9)
    assert display.parse_cim_date("") is None
    assert display.parse_cim_date(None) is None
    assert display.parse_cim_date("garbage") is None
    assert display.parse_cim_date("20241399000000.000000+000") is None


def test_driver_age_text_and_urls():
    d = date(2024, 1, 1)
    assert display.driver_age_days(d, date(2024, 1, 11)) == 10
    assert display.driver_age_text(10) == "Driver is 10 days old"
    assert display.driver_age_text(None) == "Unavailable"
    assert "nvidia" in display.vendor_driver_url("NVIDIA GeForce RTX 4060")
    assert "amd" in display.vendor_driver_url("AMD Radeon RX 7800")
    assert "intel" in display.vendor_driver_url("Intel(R) UHD Graphics")
    assert display.vendor_driver_url("Other") is None


def test_stretch_choices_and_native():
    from core import display as d
    disp = {"width": 1920, "height": 1080, "bpp": 32,
            "modes": [(1920, 1080, 32, 165), (1720, 1080, 32, 144), (1280, 720, 32, 60), (1024, 768, 32, 60)]}
    assert d.native_size(disp) == (1920, 1080)
    ch = {(w, h): hz for w, h, hz in d.stretch_choices(disp)}
    assert ch[(1720, 1080)] == 144                       # already on the graphics card
    assert ch[(1440, 1080)] is None                      # 4:3, not added yet
    assert (1920, 1080) not in ch and (1280, 720) not in ch
    four_k = {"width": 3840, "height": 2160, "bpp": 32, "modes": [(3840, 2160, 32, 60)]}
    assert d.stretch_choices(four_k) == [(2880, 2160, None)]   # only 4:3 offered for non-1080 screens
    assert d.stretch_choices({"modes": []}) == []


def test_set_resolution_refuses_off_windows(monkeypatch):
    from core import display as d
    monkeypatch.setattr(d, "IS_WINDOWS", False)
    assert d.set_resolution("x", 1720, 1080)[0] is False
