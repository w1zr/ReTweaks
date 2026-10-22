import random

from core import funtools as ft


def test_polling_meter_1000hz():
    m = ft.PollingMeter()
    for i in range(600):
        m.add(i * 0.001)
    assert abs(m.current() - 1000) < 1
    assert abs(m.average() - 1000) < 1
    assert abs(m.maximum() - 1000) < 1


def test_polling_meter_ignores_pauses_and_slides():
    m = ft.PollingMeter(window_s=1.0)
    t = 0.0
    for _ in range(100):          # 125 Hz
        t += 0.008
        m.add(t)
    t += 1.0                      # mouse stopped for a second
    for _ in range(100):          # then 500 Hz
        t += 0.002
        m.add(t)
    assert abs(m.current() - 500) < 1
    assert abs(m.average() - 500) < 5        # the old 125 Hz data slid out of the window
    assert m.stale(t + 1.0) and not m.stale(t + 0.001)


def test_polling_meter_empty():
    m = ft.PollingMeter()
    assert m.current() is None and m.average() is None and m.maximum() is None
    m.add(0.0)
    assert m.current() is None


def test_cps():
    c = ft.CpsTest(5)
    for i in range(30):
        assert c.click(10.0 + i * 0.1)          # 30 clicks over 2.9 s
    assert not c.finished(12.0)
    assert c.click(15.5) is False               # after the window: not counted
    assert c.finished(15.0)
    assert c.clicks == 30 and c.cps(16.0) == 6.0


def test_reaction_flow():
    r = ft.ReactionTest(tries=2)
    r.begin_try(0.0, delay=2.0)
    assert r.click(1.0) == "too_soon" and not r.results_ms
    r.begin_try(10.0, delay=2.0)
    assert r.tick(12.0) and r.state == "ready"
    assert r.click(12.25) == "shown"
    assert abs(r.last_ms - 250) < 1e-6
    r.begin_try(20.0, delay=1.5)
    assert r.click(21.7) == "done"              # click handles the tick itself
    assert abs(r.last_ms - 200) < 1e-6
    assert abs(r.average_ms() - 225) < 1e-6 and abs(r.best_ms() - 200) < 1e-6


def test_random_delay_range_and_best():
    rng = random.Random(1)
    assert all(1.5 <= ft.random_delay(rng) <= 5.0 for _ in range(200))
    assert ft.is_new_best(8, None) and ft.is_new_best(9, 8) and not ft.is_new_best(7, 8)
    assert ft.is_new_best(200, 250, lower_is_better=True)
    assert not ft.is_new_best(None, 5)
