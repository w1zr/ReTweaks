"""Fan curve maths, hysteresis, limits and failsafes (fan_curves.py) with a fake sensor host. No hardware."""
import time

import pytest

import fan_curves as fc


def test_interpolation_and_flat_ends():
    pts = [(30, 30), (50, 50), (70, 90), (80, 100)]
    assert fc.interpolate(pts, 10) == 30
    assert fc.interpolate(pts, 40) == 40
    assert fc.interpolate(pts, 60) == 70
    assert fc.interpolate(pts, 75) == 95
    assert fc.interpolate(pts, 99) == 100


@pytest.mark.parametrize("bad", [
    [(30, 30), (50, 50), (70, 90)],                                  # too few
    [(30, 30)] * 7,                                                  # too many
    [(30, 20), (50, 50), (70, 90), (80, 100)],                       # below 30 %
    [(30, 30), (50, 101), (70, 90), (80, 100)],                      # above 100 %
    [(30, 30), (30.5, 50), (70, 90), (80, 100)],                     # too close
    [(30, 30), (50, float("nan")), (70, 90), (80, 100)],
    [(-5, 30), (50, 50), (70, 90), (80, 100)],
    [("a", 30), (50, 50), (70, 90), (80, 100)],
])
def test_bad_points_refused(bad):
    with pytest.raises(ValueError):
        fc.clean_points(bad)


def test_presets_are_valid_and_reach_full_speed_before_the_safety_limit():
    for name, pts in fc.PRESETS.items():
        clean = fc.clean_points(pts)
        assert clean[-1][1] == 100 and clean[-1][0] < fc.SAFETY_TEMP, name


def test_hysteresis_and_ramp():
    s = fc.CurveState([(30, 30), (50, 50), (70, 90), (80, 100)], hysteresis=4, ramp_down=5)
    assert s.next_duty(60) == 70
    assert s.next_duty(65) == 80              # heating: follows the curve at once
    assert s.next_duty(63) == 80              # within 4 C of where it was: no change
    assert s.next_duty(61) == 80              # 61+4 = 65 -> curve 80: still no change
    assert s.next_duty(50) == 75              # cooled well past the band: down by at most 5 per tick
    assert s.next_duty(50) == 70
    for _ in range(10):
        s.next_duty(50)
    assert s.duty == pytest.approx(58)        # settles at curve(50 + 4) = 58, not curve(50)
    assert s.next_duty(52) == pytest.approx(58)


def test_limits_respect_controller_range_and_30_percent():
    s = fc.CurveState([(30, 30), (50, 50), (70, 90), (80, 100)])
    assert s.next_duty(20, low=35, high=95) == 35
    s2 = fc.CurveState([(30, 30), (50, 50), (70, 90), (80, 100)])
    assert s2.next_duty(90, low=20, high=95) == 95
    assert fc.clamp(10, 0, 100) == 30


class FakeTemps:
    def __init__(self):
        self.extended = []
        self.extended_time = 0
        self.rows, self.updated = [], 0
        self.fan_controls = [dict(id="a", min=30, max=100), dict(id="b", min=35, max=100)]
        self.sent = []

    def reading(self, part, c):
        self.extended = [dict(part=part, hardware="X", name="X / " + ("CPU Package" if part == "CPU" else "GPU Core"), c=c)]
        self.extended_time = time.monotonic()

    def fan_command(self, op, id=None, value=None):
        self.sent.append((op, [id], value))
        return True

    def fan_batch(self, op, ids, value=None):
        self.sent.append((op, list(ids), value))
        return True


class FakeHub:
    def __init__(self):
        self.jobs = []

    def after(self, ms, fn):
        self.jobs.append(fn)
        return len(self.jobs)

    def after_cancel(self, job):
        pass


def engine():
    t = FakeTemps()
    e = fc.CurveEngine(FakeHub(), t)
    return t, e


def test_engine_sends_bounded_duty_and_skips_tiny_changes():
    t, e = engine()
    t.reading("CPU", 60)
    e.start("All", ["a", "b"], "CPU", fc.PRESETS["Balanced"])
    assert t.sent[-1] == ("manual_many", ["a", "b"], 60)
    n = len(t.sent)
    t.reading("CPU", 60.5)
    e.evaluate("All")
    assert len(t.sent) == n                    # < 2 % change: nothing sent
    t.reading("CPU", 20)                       # cold, but group minimum is 35 % (controller b)
    for _ in range(20):
        e.evaluate("All")
    assert t.sent[-1][2] >= 35
    e.close()


def test_failsafe_when_temperature_disappears_then_resumes():
    t, e = engine()
    t.reading("CPU", 60)
    e.start("A", ["a"], "CPU", fc.PRESETS["Balanced"])
    now = time.monotonic()
    t.extended, t.extended_time = [], 0
    assert e.evaluate("A", now=now) is None
    assert t.sent[-1][0] == "manual"          # not yet: only a moment without readings
    assert e.evaluate("A", now=now + fc.FAILSAFE_SECONDS + 0.1) is None
    assert t.sent[-1] == ("default", ["a"], None)
    assert "Failsafe" in e.curves["A"]["status"]
    t.reading("CPU", 55)
    assert e.evaluate("A") is not None and t.sent[-1][0] == "manual"
    e.close()


def test_hand_back_at_85_and_on_stop_and_close():
    t, e = engine()
    t.reading("GPU", 90)
    e.start("G", ["a"], "GPU", fc.PRESETS["Silent"])
    assert t.sent == [("default", ["a"], None)]          # never a manual duty at >= 85 C
    t.reading("GPU", 50)
    e.evaluate("G")
    assert t.sent[-1][0] == "manual"
    e.stop("G")
    assert t.sent[-1] == ("default", ["a"], None) and not e.curves
    e.start("G", ["a"], "Hottest of CPU and GPU", fc.PRESETS["Silent"])
    e.close()
    assert t.sent[-1] == ("default", ["a"], None) and not e.curves


def test_one_curve_per_controller_and_manual_takes_over():
    t, e = engine()
    t.reading("CPU", 50)
    e.start("one", ["a"], "CPU", fc.PRESETS["Silent"])
    e.start("both", ["a", "b"], "CPU", fc.PRESETS["Balanced"])
    assert "one" not in e.curves and "both" in e.curves
    e.stop_for(["b"])
    assert not e.curves and t.sent[-1] == ("default_many", ["a", "b"], None)
    e.close()


def test_errors_in_a_tick_hand_control_back():
    t, e = engine()
    t.reading("CPU", 50)
    e.start("A", ["a"], "CPU", fc.PRESETS["Silent"])
    e.evaluate = lambda name, now=None: 1 / 0
    e.tick()
    assert not e.curves and t.sent[-1] == ("default", ["a"], None)
    e.close()


def test_hottest_source_uses_the_hotter_part():
    t = FakeTemps()
    t.extended = [dict(part="CPU", hardware="C", name="C / CPU Package", c=40),
                  dict(part="GPU", hardware="G", name="G / GPU Core", c=70)]
    t.extended_time = time.monotonic()
    assert fc.source_temperature(t, "Hottest of CPU and GPU") == 70
    assert fc.source_temperature(t, "CPU") == 40
    t.extended_time = time.monotonic() - 60
    assert fc.source_temperature(t, "CPU") is None
