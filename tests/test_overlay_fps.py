from core import overlay_fps as of


def test_command_uses_stdout_and_own_session():
    cmd = of.build_command("PresentMon.exe", "game.exe")
    assert "--output_stdout" in cmd and "--no_console_stats" in cmd
    assert cmd[cmd.index("--session_name") + 1] == "RETWEAKS_overlay"
    assert "--stop_existing_session" in cmd
    assert cmd[cmd.index("--process_name") + 1] == "game.exe"
    for bad in ("", "  ", None):
        try:
            of.build_command("p.exe", bad)
            assert False
        except ValueError:
            pass


def test_header_detection():
    assert of.parse_header("Application,ProcessID,MsBetweenPresents,MsInPresentApi") == 2
    assert of.parse_header("﻿Application,FrameTime") == 1
    assert of.parse_header("game.exe,123,6.9") is None
    assert of.parse_header("") is None


def test_line_parser_reads_header_once():
    p = of.LineParser()
    assert p.feed("Application,ProcessID,MsBetweenPresents\r\n") is None
    assert p.feed("game.exe,10,6.94\r\n") == 6.94
    assert p.feed("game.exe,10,abc") is None
    assert p.feed("game.exe,10,-1") is None
    assert p.feed("game.exe,10") is None
    assert p.feed("game.exe,10,nan") is None
    assert p.skipped == 4


def test_line_parser_skips_data_before_header():
    p = of.LineParser()
    assert p.feed("some banner text") is None
    assert p.feed("1,2,3") is None   # still no header: nothing parsed


def test_constant_144_fps():
    m = of.RollingMetrics()
    ft = 1000 / 144
    for _ in range(2000):
        m.add(ft)
    s = m.snapshot()
    assert abs(s["fps"] - 144) <= 1
    assert abs(s["low1"] - 144) < 0.5
    assert abs(s["frame_ms"] - ft) < 1e-6


def test_stutter_lowers_one_percent_low():
    m = of.RollingMetrics()
    for i in range(1400):   # about 10 s at 144 fps with a 50 ms hitch every 100 frames
        m.add(50.0 if i % 100 == 99 else 1000 / 144)
    s = m.snapshot()
    assert s["low1"] < 25          # slowest 1% are the 50 ms frames
    assert s["fps"] > 100          # current FPS is mostly unaffected


def test_window_drops_old_frames():
    m = of.RollingMetrics(window_s=10)
    for _ in range(500):
        m.add(100.0)               # 50 s at 10 fps
    assert len(m.frames) <= 101
    for _ in range(2000):
        m.add(5.0)                 # 10 s at 200 fps pushes the slow frames out
    assert abs(m.snapshot()["low1"] - 200) < 1


def test_unavailable_thresholds():
    m = of.RollingMetrics()
    assert m.snapshot() == {"fps": None, "low1": None, "frame_ms": None}
    for _ in range(99):
        m.add(10.0)
    s = m.snapshot()
    assert s["low1"] is None and abs(s["fps"] - 100.0) < 1e-6   # 99 frames in 0.99 s; below the 100 needed
    m.add(10.0)
    assert m.snapshot()["low1"] is not None


def test_format_lines():
    snap = {"fps": 143.6, "low1": 98.2, "frame_ms": 6.94}
    assert of.format_lines(snap, 32, 87.4) == ["FPS 144", "1% low 98", "Frame 6.9 ms", "CPU 32% · GPU 87%"]
    assert of.format_lines(snap, show_load=False) == ["FPS 144", "1% low 98", "Frame 6.9 ms"]
    empty = of.format_lines({"fps": None, "low1": None, "frame_ms": None})
    assert empty == ["FPS –", "1% low –", "Frame – ms", "CPU – · GPU –"]
    assert of.format_lines(None, state="closed") == ["Game closed"]


def test_loads_from_sample():
    assert of.loads_from_sample(None) == (None, None)
    assert of.loads_from_sample({"cpu": {"load": 12.0}, "gpus": [{"load": None}, {"load": 55.0}]}) == (12.0, 55.0)
    assert of.loads_from_sample({"cpu": {}, "gpus": []}) == (None, None)


def test_corner_position_and_settings():
    area, size = (1920, 0, 1920, 1080), (200, 100)
    assert of.corner_position(area, size, "top-left") == (1936, 16)
    assert of.corner_position(area, size, "top-right") == (1920 + 1920 - 200 - 16, 16)
    assert of.corner_position(area, size, "bottom-left") == (1936, 1080 - 100 - 16)
    assert of.corner_position(area, size, "bottom-right") == (3624, 964)
    c = of.clean_settings({"overlay_position": "bad", "overlay_opacity": "200", "overlay_size": "huge"})
    assert c == {"overlay_position": "top-left", "overlay_size": "medium",
                 "overlay_show_load": True, "overlay_opacity": 100, "overlay_source": "builtin",
                 "overlay_low_window_s": 10, "overlay_fps_span_s": 1.0}
    assert of.clean_settings({"overlay_source": "presentmon"})["overlay_source"] == "presentmon"
    assert of.clean_settings({"overlay_source": "evil"})["overlay_source"] == "builtin"
    assert of.clean_settings({"overlay_opacity": 10})["overlay_opacity"] == 50
    assert of.clean_settings({"overlay_opacity": "x"})["overlay_opacity"] == 85


# ---------------------------------------------------------------- changeable timings (owner request 2026-10-22)
def test_fps_span_divides_by_its_length():
    for span in (0.5, 1.0, 2.0):
        m = of.RollingMetrics(window_s=10, fps_span_s=span)
        for _ in range(3000):
            m.add(1000 / 120)          # 120 fps for 25 s
        assert abs(m.snapshot()["fps"] - 120) <= 1, span


def test_low_window_length_changes_what_counts():
    for window, expect_hitch in ((5, False), (30, True)):
        m = of.RollingMetrics(window_s=window, fps_span_s=1)
        for i in range(2400):          # 100 ms hitches in the first 10 s, then 10 s smooth (200 fps)
            m.add(100.0 if (i < 100 and i % 10 == 0) else 5.0)
        low = m.snapshot()["low1"]
        assert (low < 50) == expect_hitch, (window, low)


def test_live_timings_and_validation():
    try:
        assert of.set_timings(low_window_s=30, fps_span_s=0.5) == {"low_window_s": 30.0, "fps_span_s": 0.5}
        m = of.RollingMetrics()                # follows the live timings
        assert m.window_ms == 30000 and m.span_ms == 500
        of.set_timings(low_window_s=7, fps_span_s="x")   # not offered -> unchanged
        assert of.timings() == {"low_window_s": 30.0, "fps_span_s": 0.5}
        of.set_timings(low_window_s=5)
        assert m.window_ms == 5000                # running metrics pick it up immediately
    finally:
        of.set_timings(low_window_s=10, fps_span_s=1)
    c = of.clean_settings({"overlay_low_window_s": "60", "overlay_fps_span_s": 2})
    assert c["overlay_low_window_s"] == 60 and c["overlay_fps_span_s"] == 2.0
    c = of.clean_settings({"overlay_low_window_s": 999, "overlay_fps_span_s": None})
    assert c["overlay_low_window_s"] == 10 and c["overlay_fps_span_s"] == 1.0


def test_fps_test_length_validation():
    from core import fps
    assert 300 in fps.DURATIONS
    assert fps.clean_seconds("90") == 90 and fps.clean_seconds(4) == 30 and fps.clean_seconds(1801) == 30
    assert fps.clean_seconds("abc", default=60) == 60
