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


def test_displayconfig_struct_sizes_match_windows_sdk():
    # Values from the Windows SDK headers (checked with mingw-w64 static asserts)
    import ctypes
    from core import display as d
    assert ctypes.sizeof(d.DISPLAYCONFIG_PATH_INFO) == 72
    assert d.DISPLAYCONFIG_PATH_INFO.targetInfo.offset == 20 and d._PATH_TARGET.rotation.offset == 20
    assert ctypes.sizeof(d.DISPLAYCONFIG_MODE_INFO) == 64
    w = ctypes.sizeof(ctypes.c_wchar)        # 2 on Windows (the SDK sizes below); 4 on Linux test runs
    assert ctypes.sizeof(d.DISPLAYCONFIG_SOURCE_DEVICE_NAME) == 20 + 32 * w          # 84 on Windows
    assert ctypes.sizeof(d.DISPLAYCONFIG_TARGET_DEVICE_NAME) == 36 + (64 + 128) * w  # 420 on Windows
    assert d.DISPLAYCONFIG_TARGET_DEVICE_NAME.monitorFriendlyDeviceName.offset == 36
    assert ctypes.sizeof(d.DISPLAYCONFIG_TARGET_PREFERRED_MODE) == 80
    assert d.DISPLAYCONFIG_TARGET_PREFERRED_MODE.targetMode.offset == 32


def test_native_prefers_monitor_preferred_mode():
    from core import display as d
    # A 1080p monitor whose driver also offers 4K super-resolution modes (NVIDIA DSR / AMD VSR)
    disp = {"width": 1920, "height": 1080, "native": (1920, 1080),
            "modes": [(3840, 2160, 32, 60), (1920, 1080, 32, 240), (1720, 1080, 32, 240)]}
    assert d.native_size(disp) == (1920, 1080)
    assert (1720, 1080, 240) in d.stretch_choices(disp)
    disp.pop("native")
    assert d.native_size(disp) == (3840, 2160)        # fallback only when Windows can't say


def test_display_config_matches_names_to_the_right_display(monkeypatch):
    """Two monitors whose paths come back in a different order than DISPLAY1/2: each name, native size
    and rotation must stay with its own \\\\.\\DISPLAYn."""
    import ctypes
    from core import display as d
    monitors = [  # (gdi name, monitor name, native, rotation) in path order
        ("\\\\.\\DISPLAY2", "LG HDR 4K", (3840, 2160), 2),
        ("\\\\.\\DISPLAY1", "ED320Q X2", (1920, 1080), 1),
    ]

    class U:
        def GetDisplayConfigBufferSizes(self, flags, np_, nm):
            np_._obj.value, nm._obj.value = len(monitors), 0
            return 0

        def QueryDisplayConfig(self, flags, np_, paths, nm, modes, topo):
            for i, (_, _, _, rot) in enumerate(monitors):
                paths[i].sourceInfo.id = i
                paths[i].targetInfo.id = 100 + i
                paths[i].targetInfo.rotation = rot
            return 0

        def DisplayConfigGetDeviceInfo(self, ref):
            info = ref._obj
            hdr = info.header
            if hdr.type == d.GET_SOURCE_NAME:
                info.viewGdiDeviceName = monitors[hdr.id][0]
            elif hdr.type == d.GET_TARGET_NAME:
                info.monitorFriendlyDeviceName = monitors[hdr.id - 100][1]
            else:
                info.width, info.height = monitors[hdr.id - 100][2]
            return 0

    monkeypatch.setattr(d, "IS_WINDOWS", True)
    monkeypatch.setattr(d, "_user32", lambda: U(), raising=False)
    cfg = d.display_config()
    assert cfg["\\\\.\\DISPLAY1"] == {"name": "ED320Q X2", "native": (1920, 1080), "rotated": False}
    assert cfg["\\\\.\\DISPLAY2"] == {"name": "LG HDR 4K", "native": (3840, 2160), "rotated": True}
