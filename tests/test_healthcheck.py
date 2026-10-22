"""Health Check thresholds, summary counting and error handling (runs on any OS)."""
from datetime import datetime

import core.healthcheck as hc

GB = 1024 ** 3


def test_startup_threshold():
    assert hc.classify_startup(5)[0] == hc.GOOD
    assert hc.classify_startup(hc.STARTUP_WARN_COUNT)[0] == hc.GOOD
    s, d = hc.classify_startup(hc.STARTUP_WARN_COUNT + 1)
    assert s == hc.WARN and "start with Windows" in d
    assert hc.classify_startup(1)[1] == "1 app starts with Windows"


def test_temp_thresholds():
    assert hc.classify_temp(10 * 1024 ** 2, 4)[0] == hc.GOOD
    assert hc.classify_temp(2 * GB, 4)[0] == hc.WARN
    assert hc.classify_temp(11 * GB, 4)[0] == hc.BAD


def test_power_plan():
    assert hc.classify_power("Power saver", False)[0] == hc.WARN
    assert hc.classify_power("Power saver", True)[0] == hc.GOOD     # laptop on battery plan is normal
    assert hc.classify_power("Balanced", False)[0] == hc.GOOD
    assert hc.classify_power("", False)[0] == hc.NA


def test_disks():
    assert hc.classify_disks([("A", "Healthy"), ("B", "Healthy")])[0] == hc.GOOD
    s, d = hc.classify_disks([("A", "Healthy"), ("B", "Warning")])
    assert s == hc.BAD and "B: Warning" in d
    assert hc.classify_disks([])[0] == hc.NA


def test_free_space():
    assert hc.classify_free_space(50, 100)[0] == hc.GOOD
    assert hc.classify_free_space(14, 100)[0] == hc.WARN
    assert hc.classify_free_space(4, 100)[0] == hc.BAD
    assert hc.classify_free_space(15, 100)[0] == hc.GOOD
    assert hc.classify_free_space(0, 0)[0] == hc.NA


def test_reboot_and_updates():
    assert hc.classify_reboot([])[0] == hc.GOOD
    assert hc.classify_reboot(["Windows Update"])[0] == hc.WARN
    assert hc.classify_update_age(45)[0] == hc.GOOD
    assert hc.classify_update_age(46)[0] == hc.WARN
    assert hc.classify_update_age(None)[0] == hc.NA
    assert hc.days_since("2026-09-01\n", now=datetime(2026, 10, 1)) == 30
    assert hc.days_since("garbage") is None


def test_refresh():
    modes = [(1920, 1080, 60), (1920, 1080, 144), (1920, 1080, 1), (2560, 1440, 240)]
    assert hc.max_rate_for(modes, 1920, 1080) == 144
    assert hc.max_rate_for(modes, 800, 600) is None
    assert hc.classify_refresh(60, 144)[0] == hc.WARN
    assert hc.classify_refresh(144, 144)[0] == hc.GOOD
    assert hc.classify_refresh(None, 144)[0] == hc.NA
    fake = [{"name": "M", "width": 1920, "height": 1080, "current_hz": 60, "modes": modes}]
    r = hc.check_refresh(fake)
    assert r["status"] == hc.WARN and r["fix_id"] == "open_display"
    fake[0]["current_hz"] = 144
    r = hc.check_refresh(fake)
    assert r["status"] == hc.GOOD and r["fix_id"] is None


def test_ram():
    assert hc.classify_ram(40, 1, 2)[0] == hc.GOOD
    assert hc.classify_ram(90, 1, 2)[0] == hc.WARN
    assert hc.classify_ram(97, 1, 2)[0] == hc.BAD


def test_summary_counts():
    rs = ([hc.result("a", "A", hc.GOOD, "")] * 7 + [hc.result("b", "B", hc.WARN, "")] +
          [hc.result("c", "C", hc.BAD, "")] + [hc.result("d", "D", hc.NA, "")])
    s = hc.summarize(rs)
    assert (s["good"], s["look"], s["unavailable"]) == (7, 2, 1)
    assert s["text"] == "7 good · 2 to look at · 1 unavailable"
    assert hc.summarize(rs[:7])["text"] == "7 good · 0 to look at"


def test_failing_check_becomes_unavailable():
    def boom():
        raise RuntimeError("kaboom")

    def good():
        return hc.result("ok", "Ok", hc.GOOD, "fine")

    def bad_shape():
        return {"status": "weird"}

    seen = []
    out = hc.run_all([("boom", "Boom", boom), ("ok", "Ok", good), ("shape", "Shape", bad_shape)],
                     on_result=seen.append)
    assert [r["status"] for r in out] == [hc.NA, hc.GOOD, hc.NA]
    assert "kaboom" in out[0]["detail"] and out[0]["id"] == "boom" and out[0]["fix_id"] is None
    assert len(seen) == 3


def test_fix_only_when_needed():
    assert hc.result("x", "X", hc.GOOD, "d", None, "label")["fix_label"] == ""
    assert hc.result("x", "X", hc.WARN, "d", "open_storage", "Go")["fix_id"] == "open_storage"
    assert hc.apply_power_high()[0] is False or hc.IS_WINDOWS
