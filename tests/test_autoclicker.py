import ctypes
import random

import pytest

from core import autoclicker as AC


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(s, 0)


class FakeClicker:
    def __init__(self, clock=None, fail_at=None):
        self.calls, self.clock, self.fail_at = [], clock, fail_at

    def click(self, button):
        if self.fail_at is not None and len(self.calls) + 1 == self.fail_at:
            raise OSError("blocked")
        self.calls.append((button, self.clock() if self.clock else 0))


def run(cfg, fail_at=None):
    clock = FakeClock()
    clicker = FakeClicker(clock, fail_at)
    eng = AC.ClickEngine(cfg, clicker, clock=clock, sleep=clock.sleep)
    eng.run()
    return eng, clicker


def test_intervals():
    assert AC.base_interval_s(AC.ClickerConfig(speed_mode="cps", cps=10)) == pytest.approx(0.1)
    assert AC.base_interval_s(AC.ClickerConfig(speed_mode="interval", interval_ms=250)) == pytest.approx(0.25)
    assert AC.base_interval_s(AC.ClickerConfig(cps=100)) == pytest.approx(0.01)


def test_random_interval_in_range():
    cfg = AC.ClickerConfig(random_enabled=True, random_min_ms=50, random_max_ms=150)
    rng = random.Random(1)
    vals = [AC.next_interval_s(cfg, rng) for _ in range(500)]
    assert all(0.05 <= v <= 0.15 for v in vals)
    assert max(vals) - min(vals) > 0.05


def test_validation_limits():
    ok = AC.ClickerConfig()
    assert AC.validate_config(ok) == []
    assert AC.validate_config(AC.ClickerConfig(cps=0.5))
    assert AC.validate_config(AC.ClickerConfig(cps=101))
    assert AC.validate_config(AC.ClickerConfig(cps="abc"))
    assert AC.validate_config(AC.ClickerConfig(cps=float("nan")))
    assert AC.validate_config(AC.ClickerConfig(speed_mode="interval", interval_ms=9))
    assert AC.validate_config(AC.ClickerConfig(speed_mode="interval", interval_ms=60001))
    assert AC.validate_config(AC.ClickerConfig(start_delay_s=11))
    assert AC.validate_config(AC.ClickerConfig(start_delay_s=-1))
    assert AC.validate_config(AC.ClickerConfig(button="x"))
    assert AC.validate_config(AC.ClickerConfig(stop_after_clicks=1.5))
    assert AC.validate_config(AC.ClickerConfig(stop_after_seconds=AC.SECONDS_MAX + 1))
    # a bad cps is ignored when interval mode is used
    assert AC.validate_config(AC.ClickerConfig(speed_mode="interval", cps=0)) == []


def test_random_range_validation():
    assert AC.validate_config(AC.ClickerConfig(random_enabled=True, random_min_ms=100, random_max_ms=100)) == []
    assert AC.validate_config(AC.ClickerConfig(random_enabled=True, random_min_ms=200, random_max_ms=100))
    assert AC.validate_config(AC.ClickerConfig(random_enabled=True, random_min_ms=5, random_max_ms=100))
    # ignored when random is off
    assert AC.validate_config(AC.ClickerConfig(random_min_ms=200, random_max_ms=100)) == []


def test_hotkey_validation():
    assert AC.validate_hotkeys("F6", "F8") == []
    assert AC.validate_hotkeys("F6", "F6")
    assert AC.validate_hotkeys("F6", "Q")
    assert all(k in AC.HOTKEY_VKS for k in ("F1", "F12"))
    assert AC.HOTKEY_VKS["F6"] == 0x75


def test_config_from_dict_repairs_bad_values():
    cfg = AC.config_from_dict({"button": "bogus", "cps": 9999, "start_delay_s": "x",
                               "random_min_ms": 500, "random_max_ms": 100, "interval_ms": 120})
    assert AC.validate_config(cfg) == []
    assert cfg.interval_ms == 120 and cfg.button == "left"
    assert AC.config_from_dict({}) == AC.ClickerConfig()


def test_stop_after_clicks():
    eng, clicker = run(AC.ClickerConfig(cps=10, stop_after_clicks=5))
    assert len(clicker.calls) == 5 and eng.reason == "count" and eng.state == "stopped"
    # timing: 10 CPS -> a click every 0.1 s on the fake clock, no drift
    times = [t for _, t in clicker.calls]
    assert times == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4])


def test_double_click_counts_both_and_respects_limit():
    eng, clicker = run(AC.ClickerConfig(click_type="double", cps=10, stop_after_clicks=5))
    assert len(clicker.calls) == 5  # 2 + 2 + 1
    assert eng.reason == "count"


def test_stop_after_seconds():
    eng, clicker = run(AC.ClickerConfig(cps=10, stop_after_seconds=1))
    assert eng.reason == "time"
    assert 10 <= len(clicker.calls) <= 11
    assert all(t < 1.0 for _, t in clicker.calls)


def test_start_delay_before_first_click():
    eng, clicker = run(AC.ClickerConfig(cps=10, stop_after_clicks=2, start_delay_s=3))
    assert clicker.calls[0][1] == pytest.approx(3.0)


def test_button_passed_through():
    _, clicker = run(AC.ClickerConfig(button="right", stop_after_clicks=1))
    assert clicker.calls[0][0] == "right"


def test_error_stops_loop():
    eng, clicker = run(AC.ClickerConfig(stop_after_clicks=10), fail_at=3)
    assert eng.reason == "error" and "blocked" in eng.error and len(clicker.calls) == 2


def test_stop_reason_function():
    cfg = AC.ClickerConfig(stop_after_clicks=3, stop_after_seconds=5)
    assert AC.stop_reason(cfg, 2, 1) is None
    assert AC.stop_reason(cfg, 3, 1) == "count"
    assert AC.stop_reason(cfg, 1, 5) == "time"
    assert AC.stop_reason(AC.ClickerConfig(), 10**6, 10**6) is None


def test_real_thread_stops_promptly():
    import time
    clicker = FakeClicker()
    eng = AC.ClickEngine(AC.ClickerConfig(speed_mode="interval", interval_ms=20), clicker)
    eng.start()
    time.sleep(0.3)
    eng.stop("emergency")
    assert eng.join(1.0)
    n = len(clicker.calls)
    assert 5 <= n <= 20 and eng.reason == "emergency"
    time.sleep(0.1)
    assert len(clicker.calls) == n  # nothing after stop


def test_stop_during_start_delay():
    import time
    clicker = FakeClicker()
    eng = AC.ClickEngine(AC.ClickerConfig(start_delay_s=5), clicker)
    eng.start()
    time.sleep(0.1)
    eng.stop("user")
    assert eng.join(1.0) and clicker.calls == [] and eng.state == "stopped"


def test_hotkey_edge_detection_and_emergency_priority():
    keys = {AC.HOTKEY_VKS["F6"]: False, AC.HOTKEY_VKS["F8"]: False}
    events = []
    w = AC.HotkeyWatcher("F6", "F8", lambda: events.append("toggle"),
                         lambda: events.append("stop"), get_key_state=lambda vk: keys[vk])
    prev = (False, False)
    keys[AC.HOTKEY_VKS["F6"]] = True
    prev = w.poll_once(prev)
    prev = w.poll_once(prev)          # held: no repeat
    assert events == ["toggle"]
    keys[AC.HOTKEY_VKS["F6"]] = False
    prev = w.poll_once(prev)
    keys[AC.HOTKEY_VKS["F8"]] = True
    w.poll_once(prev)
    assert events == ["toggle", "stop"]
    with pytest.raises(ValueError):
        w.set_keys("F8", "F8")


def test_hotkey_thread_runs():
    import time
    keys = {AC.HOTKEY_VKS["F6"]: False, AC.HOTKEY_VKS["F8"]: False}
    events = []
    w = AC.HotkeyWatcher("F6", "F8", lambda: events.append("t"), lambda: events.append("s"),
                         get_key_state=lambda vk: keys[vk], interval=0.005)
    w.start()
    time.sleep(0.05)
    keys[AC.HOTKEY_VKS["F8"]] = True
    time.sleep(0.1)
    w.stop()
    assert events == ["s"]


def test_input_struct_sizes():
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(AC.INPUT) == expected
    assert ctypes.sizeof(AC.MOUSEINPUT) == (32 if expected == 40 else 24)
    inp = AC._make_mouse_input(AC.MOUSEEVENTF_LEFTDOWN)
    assert inp.type == 0 and inp.mi.dwFlags == 0x0002


def test_sendinput_up_always_sent(monkeypatch):
    c = AC.SendInputClicker.__new__(AC.SendInputClicker)
    sent = []
    c._event = lambda flags: sent.append(flags)
    c.click("middle")
    assert sent == [AC.MOUSEEVENTF_MIDDLEDOWN, AC.MOUSEEVENTF_MIDDLEUP]
    # release fails twice, then works: still released
    calls = {"n": 0}

    def flaky(flags):
        if flags == AC.MOUSEEVENTF_LEFTUP:
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("x")
    c._event = flaky
    c.click("left")
    assert calls["n"] == 3
