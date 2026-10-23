"""Hardware logic from the base app v1.5 (ported from its check_rgb_effects / check_rgb_solid / check_rgb_sync /
check_temperature_accuracy, 2026-10-22) + the RETWEAKS bridge from the bundled sensor host to the Dashboard.
No hardware is touched: every OpenRGB device and the sensor host are fakes."""
import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

openrgb = pytest.importorskip("openrgb")
from openrgb.utils import ModeColors, ModeFlags, RGBColor  # noqa: E402

import rgb_service  # noqa: E402
from rgb_service import LightingWriter, effect_mode, solid_mode, write_effect, write_solid  # noqa: E402
from rgb_sync import RainbowSync, frame_color, rainbow_period  # noqa: E402
from temperatures import Temperatures, format_temperature, live_sensor, merge_readings, primary_reading  # noqa: E402
from core.sensors_lhm import bundled_to_lhm, read_bundled, set_bundled_provider  # noqa: E402


# ------------------------------------------------------------------ RGB effects (check_rgb_effects.py)
class EffectDevice:
    def __init__(self, name, low, high):
        self.modes = [NS(id=0, name='Static', flags=ModeFlags(0), color_mode=ModeColors.PER_LED),
                      NS(id=1, name=name, flags=ModeFlags.HAS_SPEED, color_mode=ModeColors.NONE, speed_min=low,
                         speed_max=high, speed=low)]
        self.active_mode = 0
        self.colors = [RGBColor(1, 2, 3)]
        self.leds = [NS(id=0)]

    def set_mode(self, mode):
        self.modes[mode.id] = copy.deepcopy(mode)
        self.active_mode = mode.id

    def _set_device_colors(self, colors, fast=False):
        self.colors = copy.deepcopy(colors)

    def update(self):
        pass


@pytest.mark.parametrize("name,low,high", [('Rainbow', 0, 5), ('Rainbow wave', 0, 2), ('Rainbow', 5, 0)])
def test_rainbow_aliases_and_speed_ranges(name, low, high):
    d = EffectDevice(name, low, high)
    assert effect_mode(d, 'Rainbow').name == name
    write_effect(d, 'Rainbow', RGBColor(255, 0, 0), 75)
    assert d.active_mode == 1 and d.modes[1].speed == round(low + (high - low) * .75)


def test_solid_mode_needs_a_real_solid_mode():
    static = NS(name='Static', color_mode=ModeColors.PER_LED)
    assert solid_mode(NS(modes=[static]), zone=True) is static
    assert solid_mode(NS(modes=[NS(name='Rainbow', color_mode=ModeColors.NONE)]), zone=True) is None


# ------------------------------------------------------------------ solid colour writes (check_rgb_solid.py)
class SolidDevice:
    def __init__(self):
        self.modes = [NS(id=0, name='Static', color_mode=ModeColors.PER_LED),
                      NS(id=1, name='Breathing', color_mode=ModeColors.PER_LED)]
        self.active_mode = 1
        self.colors = [RGBColor(10, 20, 30), RGBColor(40, 50, 60), RGBColor(70, 80, 90)]
        self.leds = [NS(id=i) for i in range(3)]
        self.mode_writes = 0
        self.fail = False

    def _set_device_colors(self, colors, fast=False):
        if self.fail and not fast:
            self.fail = False
            raise OSError('Disconnected during write')
        self.colors = copy.deepcopy(colors)

    def set_mode(self, mode):
        self.mode_writes += 1
        self.active_mode = mode if isinstance(mode, int) else next(
            m.id for m in self.modes if m.name == (mode if isinstance(mode, str) else mode.name))
        self.colors = [RGBColor(0, 0, 0) for _ in self.colors]   # hardware that blanks its buffer on mode change

    def update(self):
        pass


def test_solid_keeps_other_leds_and_rolls_back_on_failure():
    d = SolidDevice()
    zone = NS(leds=[d.leds[0]])
    original = copy.deepcopy(d.colors)
    write_solid(d, [zone], RGBColor(36, 124, 255))
    assert d.colors[0] == RGBColor(36, 124, 255) and d.colors[1:] == original[1:]
    assert d.mode_writes == 1
    write_solid(d, [zone], RGBColor(255, 60, 80))
    assert d.mode_writes == 1 and d.colors[0] == RGBColor(255, 60, 80) and d.colors[1:] == original[1:]
    before = copy.deepcopy(d.colors)
    d.fail = True
    with pytest.raises(OSError):
        write_solid(d, [zone], RGBColor(255, 255, 255))
    assert d.colors == before, 'failure rollback must not leave other LEDs black'


# ------------------------------------------------------------------ synchronized Rainbow (check_rgb_sync.py)
class _Stop:
    def __init__(self):
        self.frames = 0

    def is_set(self):
        return self.frames >= 3

    def wait(self, seconds):
        self.frames += 1
        return self.is_set()


def test_rainbow_same_colour_on_every_controller():
    log = []

    def device(name, count):
        def write(colors, fast=False):
            assert len(colors) == count and fast
            log.append((name, colors[0]))
        return NS(_set_device_colors=write, leds=[None] * count)

    s = RainbowSync(Mock(), [], 70, Mock())
    s.origin = 100
    s.stop_event = _Stop()
    s.devices = [device('Fans', 10), device('RAM', 24)]
    with patch('rgb_sync.time.monotonic', side_effect=[101, 102, 103]):
        s.run()
    assert len(log) == 6
    for i in range(0, 6, 2):
        assert log[i][1] == log[i + 1][1]
    assert log[0][1] != log[2][1]


def test_rainbow_speed_change_keeps_hue():
    s = RainbowSync(Mock(), [], 0, Mock())
    s.origin = 100
    before = s.color(110)
    with patch('rgb_sync.time.monotonic', return_value=110):
        s.set_speed(100)
    assert s.color(110) == before
    assert s.color(111) != frame_color(11, 0)


def test_rainbow_transport_error_pauses():
    s = RainbowSync(Mock(), [], 50, Mock())
    s.devices = [NS(_set_device_colors=Mock(side_effect=OSError('lost')), leds=[None])]
    s.prepare = Mock()
    s.run()
    assert s.stop_event.is_set() and not s.prepare.called
    assert 'paused' in s.status.call_args.args[0]


def test_only_one_lighting_writer(tmp_path, monkeypatch):
    monkeypatch.setattr(rgb_service.tempfile, 'gettempdir', lambda: str(tmp_path))
    first, second = LightingWriter(), LightingWriter()
    first.acquire()
    try:
        with pytest.raises(RuntimeError):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_rainbow_period_range():
    assert rainbow_period(0) == 120 and abs(rainbow_period(100) - 8) < 1e-5
    periods = [rainbow_period(v) for v in range(101)]
    assert all(a > b for a, b in zip(periods, periods[1:]))
    for speed in (0, 25, 50, 75, 100):
        duration = rainbow_period(speed)
        assert frame_color(duration / 4, speed) == frame_color(30, 0)
        assert frame_color(duration, speed) == frame_color(0, speed)


# ------------------------------------------------------------------ temperatures (check_temperature_accuracy.py)
def test_temperature_filtering_and_conversion():
    core = dict(part='GPU', name='NVIDIA GPU / GPU Core', hardware='NVIDIA GPU', c=34, source='LibreHardwareMonitor')
    hot = dict(core, name='NVIDIA GPU / GPU Hot Spot', c=43)
    fallback = dict(part='GPU', name='NVIDIA GPU', c=35, source='NVIDIA driver')
    zero = dict(part='CPU', name='AMD CPU / Core (Tctl/Tdie)', c=0)
    threshold = dict(part='Storage', name='SSD / Critical Temperature', c=84)
    warning = dict(threshold, name='SSD / Warning Temperature', c=74)
    ssd = dict(threshold, name='SSD / Composite Temperature', c=39)
    assert not live_sensor(zero) and not live_sensor(threshold) and not live_sensor(warning)
    assert live_sensor(hot) and live_sensor(core) and live_sensor(ssd)
    assert merge_readings([fallback], [core, hot, zero, threshold, warning, ssd]) == [core, hot, ssd]
    assert format_temperature(34) == '34 °C / 93 °F'
    assert format_temperature(34, 'F') == '93 °F' and format_temperature(None) == 'Sensor unavailable'
    other = dict(fallback, name='Second GPU', c=50)
    assert other in merge_readings([other], [core])
    assert primary_reading([hot, core], 'GPU') is core          # core before hot spot


def test_full_scan_starts_automatically_only_when_asked():
    with patch.object(Temperatures, 'full_scan') as scan, patch('temperatures.threading.Thread'):
        Temperatures(auto_full=True).close()
        scan.assert_called_once()
    with patch.object(Temperatures, 'full_scan') as scan, patch('temperatures.threading.Thread'):
        Temperatures(auto_full=False).close()
        scan.assert_not_called()


def test_fan_command_bounds_and_wire_format():
    with patch('temperatures.threading.Thread'):
        t = Temperatures()
    t.fan_controls = [dict(id='x', min=35, max=95)]
    proc = Mock()
    proc.poll.return_value = None
    t.extended_process = proc
    for value in (0, 29, 34, 96, float('nan'), float('inf')):
        with pytest.raises(ValueError):
            t.fan_command('manual', 'x', value)
    proc.stdin.write.assert_not_called()
    assert t.fan_command('manual', 'x', 65)
    assert json.loads(proc.stdin.write.call_args.args[0]) == dict(op='manual', id='x', value=65)
    with pytest.raises(ValueError):
        t.fan_command('format_disk')
    t.close()
    assert proc.stdin.write.call_args.args[0] == 'close\n'        # host restores automatic control on close


# ------------------------------------------------------------------ RETWEAKS Dashboard bridge
def test_bundled_rows_become_dashboard_sensors():
    rows = [dict(part='CPU', hardware='Test CPU', name='Test CPU / CPU Package', c=52.0),
            dict(part='GPU', hardware='Test GPU', name='Test GPU / GPU Core', c=44.0),
            dict(part='GPU', hardware='Test GPU', name='Test GPU / GPU Hot Spot', c=51.0),
            dict(part='Storage', hardware='Test SSD', name='Test SSD / Temperature', c=38.0)]
    fans = [dict(id='/lpc/x/fan/0', name='Fan #1', hardware='Test board', rpm=1180.0),
            dict(id='/gpu/0/fan/0', name='GPU Fan', hardware='Test GPU', rpm=0)]
    r = bundled_to_lhm(rows, fans)
    assert r['cpu_temp'] == 52.0
    assert r['gpu_temps'] == {'Test GPU': {'core': 44.0, 'hotspot': 51.0}}
    assert r['storage_temps'] == {'Test SSD': 38.0}
    assert r['fans'] == [{'name': 'Test board Fan #1', 'rpm': 1180.0}]      # 0 RPM = stopped, not shown as a fan
    assert bundled_to_lhm([], []) is None


def test_read_bundled_only_uses_fresh_readings():
    import time
    p = NS(extended=[dict(part='CPU', hardware='C', name='C / CPU Package', c=40.0)], fans=[],
           extended_time=time.monotonic())
    set_bundled_provider(p)
    try:
        assert read_bundled()['cpu_temp'] == 40.0
        p.extended_time = time.monotonic() - 60
        assert read_bundled() is None
    finally:
        set_bundled_provider(None)
    assert read_bundled() is None
