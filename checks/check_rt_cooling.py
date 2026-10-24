"""Fan control + RGB lighting pages (base app v1.5 check_cooling.py, adapted to RETWEAKS' page registry).
Linux via tools/linux_shim.py. Every hardware write is mocked: no fan duty and no lighting is ever sent.
Checks real widget events: dropdown clicks, slider drag, Apply, presets, Rainbow, LED-count setup."""
import json, os, sys, tempfile, time
TMP = tempfile.mkdtemp(prefix="rt_cooling_")
os.environ["APPDATA"] = TMP
os.environ["LOCALAPPDATA"] = TMP
from types import SimpleNamespace
from unittest.mock import Mock, patch

import retweaks as app
import hubplus
import automation
from openrgb.utils import DeviceType, ModeColors, ModeFlags
from rgb_service import solid_mode

static = SimpleNamespace(name='Static', color_mode=ModeColors.PER_LED)
assert solid_mode(SimpleNamespace(modes=[static]), zone=True) is static
assert solid_mode(SimpleNamespace(modes=[SimpleNamespace(name='Rainbow', color_mode=ModeColors.NONE)]), zone=True) is None


class Hotkeys:
    def __init__(self, *a): self.thread = Mock()
    def update(self, *a): pass
    def close(self): pass


def pump(hub, condition):
    deadline = time.monotonic() + 3
    while not condition() and time.monotonic() < deadline:
        hub.update(); time.sleep(.02)
    assert condition(), 'Worker did not finish'


automation.Hotkeys = Hotkeys
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
errors = []
hub.report_callback_exception = lambda *a: errors.append(a)
try:
    hub.update()
    try: hub.state('normal')
    except Exception: pass
    hub.geometry('1180x900')
    # sidebar + registry wiring
    side = hub.sidebar_nav
    for name in ("Temperatures", "Fan control", "RGB lighting", "Run"):
        assert name in side.targets and side.targets[name] == hub.rt_tabs[name], name
        assert hub.rt_pages[name] is not None, name
    fan_tab = hub.rt_tabs["Fan control"]
    side.open("Fan control", side.targets["Fan control"]); hub.update()
    assert hub.cur_tab == fan_tab
    sampler = hub.temperatures
    sampler.stop.set(); sampler.extended_time = time.monotonic()
    sampler.fans = [dict(id='/fan/0', hardware='Test board', name='CPU Fan', rpm=1200)]
    sampler.fan_controls = [dict(id='/control/0', hardware='Test board', name='CPU Fan', min=35, max=100, manual=False)]
    fan = hub.fan_control
    fan.refresh(); hub.update()
    assert fan.visual.rpm == 1200 and fan.slider.enabled

    def click_choice(selector, index):
        selector.button.event_generate('<ButtonPress-1>', x=25, y=18)
        selector.button.event_generate('<ButtonRelease-1>', x=25, y=18); hub.update()
        assert selector.menu is not None
        box = selector.listbox; box.update(); rect = box.bbox(index); assert rect
        box.event_generate('<ButtonPress-1>', x=30, y=rect[1] + rect[3] // 2)
        box.event_generate('<ButtonRelease-1>', x=30, y=rect[1] + rect[3] // 2); hub.update()
        assert selector.get() == selector.values[index] and selector.menu is None

    sampler.fans.append(dict(id='/fan/1', hardware='Test GPU', name='GPU Fan', rpm=1800))
    sampler.fan_controls.append(dict(id='/control/1', hardware='Test GPU', name='GPU Fan', min=30, max=100, value=50, manual=False))
    fan.refresh(); hub.update(); click_choice(fan.select, 1)
    assert fan.visual.rpm == 1800 and fan.selected()['id'] == '/control/1'
    click_choice(fan.select, 0); assert fan.visual.rpm == 1200
    with patch.object(sampler, 'fan_command') as command:
        fan.slider.set(10); assert fan.slider.value == 35; command.assert_not_called()   # 35 = this fan's minimum
        x = 16 + round((fan.slider.winfo_width() - 32) * (75 - 35) / 65)
        for ev in ('<ButtonPress-1>', '<B1-Motion>', '<ButtonRelease-1>'):
            fan.slider.event_generate(ev, x=x, y=28)
        assert fan.slider.value == 75
        command.assert_not_called()                      # dragging is a draft; nothing sent before Apply
        fan.apply.event_generate('<ButtonPress-1>', x=30, y=18)
        fan.apply.event_generate('<ButtonRelease-1>', x=30, y=18)
        command.assert_called_once_with('manual', '/control/0', 75)
        fan.automatic(); assert command.call_args.args == ('default', '/control/0')
    for label, expected in [('All system fans', ['/control/0']), ('All GPU fans', ['/control/1']),
                            ('Both · system + GPU fans', ['/control/0', '/control/1'])]:
        click_choice(fan.select, fan.select.values.index(label))
        assert [r['id'] for r in fan.selected_controls()] == expected
    assert fan.slider.low == 35 and fan.slider.high == 100
    with patch.object(sampler, 'fan_batch') as batch:
        fan.slider.set(70); fan.apply_manual(); batch.assert_called_once_with('manual_many', ['/control/0', '/control/1'], 70)
        fan.automatic(); assert batch.call_args.args == ('default_many', ['/control/0', '/control/1'])
    sampler.extended_time = time.monotonic() - 20; fan.refresh()
    assert not fan.slider.enabled and fan.visual.rpm is None       # stale readings: controls off, no fake RPM
    sampler.fan_controls = [dict(id='x', min=35, max=95)]
    process = Mock(); process.poll.return_value = None; sampler.extended_process = process
    for value in (0, 34, 96, float('nan'), float('inf')):
        try: sampler.fan_command('manual', 'x', value)
        except ValueError: pass
        else: raise AssertionError(value)
    process.stdin.write.assert_not_called()
    sampler.fan_command('manual', 'x', 65)
    assert json.loads(process.stdin.write.call_args.args[0]) == dict(op='manual', id='x', value=65)
    sampler.extended_process = None
    # PawnIO link card on the page
    texts = []
    def walk(w):
        for c in w.winfo_children():
            if c.winfo_class() == 'Label': texts.append(c.cget('text'))
            walk(c)
    walk(fan.body)
    assert any('PawnIO' in t for t in texts)

    # ---------------- RGB lighting
    rgb = hub.rgb_lighting; rgb.tried = True; rgb.retry_at = time.monotonic() + 3600
    side.open("RGB lighting", side.targets["RGB lighting"]); hub.update()
    assert hub.cur_tab == hub.rt_tabs["RGB lighting"]
    assert not rgb.advanced.winfo_manager() and rgb.quick_apply.winfo_ismapped()
    rgb.toggle_advanced(); hub.update()
    click_choice(rgb.preview, 1); assert rgb.visual.effect == 'Breathing'
    click_choice(rgb.preview, 2); assert rgb.visual.effect == 'Rainbow'
    devices = []
    for index, kind in enumerate((DeviceType.COOLER, DeviceType.DRAM)):
        modes = [SimpleNamespace(name='Static', color_mode=ModeColors.PER_LED)]
        devices.append(SimpleNamespace(id=index, name=('Fan Hub', 'RGB RAM')[index], type=kind, leds=[1], modes=modes,
                                       active_mode=0, set_mode=Mock(), set_color=Mock()))
    client = Mock(); client.devices = devices
    with patch('rgb_service.server_available', return_value=True), patch('openrgb.OpenRGBClient', return_value=client):
        rgb.connect(); pump(hub, lambda: not rgb.busy)
    assert len(rgb.devices) == 2
    devices[0].set_mode.assert_not_called(); devices[1].set_color.assert_not_called()   # connecting writes nothing
    click_choice(rgb.select, 1); assert rgb.visual.ram
    click_choice(rgb.mode, 0)

    def route_solid(d, z, c):
        d.set_mode('Static')
        if z is None: d.set_color(c)
        else:
            for target in z: target.set_color(c)
    rgb.color = '#ff8040'
    with patch('rgb_service.write_solid', side_effect=route_solid):
        rgb.apply_lighting(); pump(hub, lambda: not rgb.busy)
    devices[1].set_mode.assert_called_once_with('Static'); devices[1].set_color.assert_called_once()
    devices[0].set_color.assert_not_called()
    devices[1].set_mode.reset_mock(); devices[1].set_color.reset_mock()
    rgb.choose_group('RAM')
    with patch.object(rgb.service, 'start'), patch('rgb_service.connect', side_effect=[OSError('Disconnected'), client]), \
            patch('rgb_service.write_solid', side_effect=lambda d, z, c: d.set_color(c)):
        rgb.preset('White', '#ffffff'); rgb.quick_apply_color(); pump(hub, lambda: not rgb.busy)
    devices[1].set_color.assert_called_once()
    color = devices[1].set_color.call_args.args[0]; assert (color.red, color.green, color.blue) == (255, 255, 255)
    devices[0].set_color.assert_not_called()
    rgb.toggle_advanced(); hub.update(); assert not rgb.advanced.winfo_manager()
    rgb.choose_group('Fans + RAM'); writes = []
    with patch.object(rgb.service, 'start'), patch('rgb_service.connect', return_value=client), \
            patch('rgb_service.write_solid', side_effect=lambda d, z, c: writes.append((d.name, c.red, c.green, c.blue))):
        red = rgb.preset_buttons['Red']
        red.event_generate('<ButtonPress-1>', x=30, y=18); red.event_generate('<ButtonRelease-1>', x=30, y=18)
        assert not writes, 'Selecting a preset must not write hardware'
        rgb.quick_apply.event_generate('<ButtonPress-1>', x=30, y=18); rgb.quick_apply.event_generate('<ButtonRelease-1>', x=30, y=18)
        pump(hub, lambda: not rgb.busy)
        assert len(writes) == 2 and all(item[1:] == (255, 0, 0) for item in writes), writes
        rgb.busy = True; rgb.preset('Green', '#00ff00'); assert rgb.pending_request is None
        rgb.quick_apply_color(); assert rgb.pending_request is not None
        rgb.busy = False; rgb.tick(); pump(hub, lambda: not rgb.busy)
        assert len(writes) == 4 and all(item[1:] == (0, 255, 0) for item in writes[-2:]), writes
    for i, d in enumerate(devices):
        d.modes.append(SimpleNamespace(name='Rainbow wave' if i == 0 else 'Rainbow', flags=ModeFlags.HAS_SPEED,
                                       speed_min=0, speed_max=5, color_mode=ModeColors.NONE))
    rgb.refresh_effects()
    with patch('cooling_panel.RainbowSync') as synced:
        click_choice(rgb.effect, rgb.effect.values.index('Rainbow')); rgb.effect_speed.set(75); hub.update()
        synced.assert_not_called()
        assert not rgb.color_presets.winfo_manager() and not rgb.custom_color_button.winfo_manager()
        rgb.quick_apply_color(); pump(hub, lambda: not rgb.busy)
        synced.return_value.start.assert_called_once(); assert synced.call_args.args[2] == 75
        running = synced.return_value; running.keys = synced.call_args.args[1]; running.stop_event.is_set.return_value = False
        rgb.effect_speed.set(90); hub.update(); running.set_speed.assert_not_called()
        rgb.quick_apply_color(); pump(hub, lambda: not rgb.busy); running.set_speed.assert_called_once_with(90)
        running.stop.assert_not_called(); rgb.rainbow_sync = None
    rgb.effect.set('Solid color'); rgb.effect_changed()
    rgb.choose_group('RAM'); rgb.toggle_advanced(); hub.update()
    zone = SimpleNamespace(id=0, name='JRAINBOW1', leds=[], set_color=Mock())
    zone.resize = Mock(side_effect=lambda count: setattr(zone, 'leds', [1] * count))
    devices[0].type = DeviceType.MOTHERBOARD; devices[0].zones = [zone]
    devices[0].data = SimpleNamespace(zones=[SimpleNamespace(leds_min=0, leds_max=120)])
    devices[0].modes.append(SimpleNamespace(name='Direct', color_mode=ModeColors.PER_LED))
    devices[0].set_mode.side_effect = lambda name: setattr(devices[0], 'active_mode', 1 if name == 'Direct' else 0)
    click_choice(rgb.select, 0); click_choice(rgb.zone, 1)
    assert 'JRAINBOW1' in rgb.zone.get() and '0 LEDs' in rgb.zone.get()
    rgb.led_count.set('12'); rgb.resize_zone(); pump(hub, lambda: not rgb.busy)
    zone.resize.assert_called_once_with(12)
    assert '12 LEDs' in rgb.zone.get()
    with patch('rgb_service.write_solid', side_effect=route_solid):
        rgb.apply_lighting(); pump(hub, lambda: not rgb.busy)
    zone.set_color.assert_called_once(); devices[0].set_color.assert_not_called()
    rgb.choose_group('Fans')
    click_choice(rgb.quick_target, next(i for i, name in enumerate(rgb.quick_target.values)
                                        if getattr(rgb.targets[name]['zone'], 'name', None) == 'JRAINBOW1'))
    zone.set_color.reset_mock()
    with patch.object(rgb.service, 'start'), patch('rgb_service.connect', return_value=client), \
            patch('rgb_service.write_solid', side_effect=lambda d, z, c: [item.set_color(c) for item in z]):
        rgb.preset('Blue', '#247cff'); rgb.quick_apply_color(); pump(hub, lambda: not rgb.busy)
    zone.set_color.assert_called_once(); devices[0].set_color.assert_not_called()
    with patch('rgb_service.server_available', return_value=True), patch('openrgb.OpenRGBClient', side_effect=ConnectionRefusedError('Offline')):
        rgb.connect(); pump(hub, lambda: not rgb.busy)
    assert rgb.devices and 'automatically' in rgb.status.cget('text')
    # "Fan speed controls ->" link goes to the Fan control page
    rgb.hub.show_tab(hub.rt_tabs["Fan control"]); hub.update(); assert hub.cur_tab == fan_tab

    # ---------------- Quit cleanup: pages close; the RGB engine and sensor host are stopped
    svc = rgb.service
    svc.process = Mock(); svc.process.poll.return_value = None
    host = Mock(); host.poll.return_value = None; sampler.extended_process = host
    for key in ("RGB lighting", "Fan control", "Temperatures"):
        hub.rt_pages[key].close()
    svc.process.terminate.assert_called_once()
    assert host.stdin.write.call_args.args[0] == 'close\n'      # sensor host restores automatic fan control
    assert fan.closed and rgb.closed
    errors = [e for e in errors if 'zoomed' not in str(e[1])]
    assert not errors, errors
finally:
    hub.destroy()
print('PASS: Fan control + RGB lighting: sidebar/registry wiring, clicked dropdowns, dragged slider is draft-only, Apply sends '
      'the bounded duty, groups, stale readings disable controls, PawnIO link, RGB connect writes nothing, selected-device '
      'writes, presets need Apply, Rainbow sync + speed, LED-count setup, offline recovery, Quit stops OpenRGB + sensor host.')
