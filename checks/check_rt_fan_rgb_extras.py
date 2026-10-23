"""RETWEAKS improvements on the base app's v1.5 Fan control / RGB lighting (owner request 2026-10-22).
Linux via tools/linux_shim.py. All hardware writes go to fakes.
Fan curves: Use this curve sends a bounded duty, state label, saved to config, manual Apply / Automatic take
over, drag -> Custom, failsafe on a missing temperature, no start at launch unless ticked, Quit hands back.
RGB: Breathing offered only when every controller has it, brightness scales colours, device on/off,
profiles saved/applied/deleted in config, apply-on-start is off by default."""
import json, os, sys, tempfile, time
TMP = tempfile.mkdtemp(prefix="rt_fanrgb_")
os.environ["APPDATA"] = TMP
os.environ["LOCALAPPDATA"] = TMP
from types import SimpleNamespace
from unittest.mock import Mock, patch

import retweaks as app
import hubplus
import automation
import fan_curves as fc
from openrgb.utils import DeviceType, ModeColors, ModeFlags


class Hotkeys:
    def __init__(self, *a): self.thread = Mock()
    def update(self, *a): pass
    def close(self): pass


def pump(hub, condition):
    deadline = time.monotonic() + 3
    while not condition() and time.monotonic() < deadline:
        hub.update(); time.sleep(.02)
    assert condition(), 'Worker did not finish'


def config():
    return json.load(open(os.path.join(TMP, "RETWEAKS", "config.json")))


automation.Hotkeys = Hotkeys
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
errors = []
hub.report_callback_exception = lambda *a: errors.append(a)
try:
    hub.update(); hub.geometry('1250x950')
    hub.sidebar_nav.buttons["Fan control"].command(); hub.update()
    page = hub.rt_pages["Fan control"]
    card, fan, engine = page.curves, page.inner, hub.fan_curves
    sampler = hub.temperatures; sampler.stop.set()
    sent = []
    sampler.fan_command = lambda op, id=None, value=None: sent.append((op, [id], value)) or True
    sampler.fan_batch = lambda op, ids, value=None: sent.append((op, list(ids), value)) or True

    def reading(c):
        sampler.extended = [dict(part='CPU', hardware='Test CPU', name='Test CPU / CPU Package', c=c)]
        sampler.extended_time = time.monotonic()
    reading(60)
    sampler.fans = [dict(id='/fan/0', hardware='Test board', name='CPU Fan', rpm=1200)]
    sampler.fan_controls = [dict(id='/control/0', hardware='Test board', name='CPU Fan', min=30, max=100, value=40, manual=False)]
    fan.refresh(); hub.update()
    assert fan.select.get() == 'CPU Fan · Test board', fan.select.get()
    assert card.state.cget('text').startswith('Automatic (BIOS)')
    assert not sent                                           # opening the page sends nothing
    # drag the 60 C point -> Custom
    card.points = list(fc.PRESETS["Balanced"]); card.redraw()
    x, y = card._xy(60, 60)
    card.graph.event_generate('<ButtonPress-1>', x=int(x), y=int(y))
    x2, y2 = card._xy(60, 70)
    card.graph.event_generate('<B1-Motion>', x=int(x2), y=int(y2))
    card.graph.event_generate('<ButtonRelease-1>', x=int(x2), y=int(y2))
    assert card.preset.get() == 'Custom' and (60, 70) in card.points, card.points
    assert not sent                                           # editing is a draft
    card._pick_preset('Balanced')
    card.use.event_generate('<ButtonPress-1>', x=30, y=18); card.use.event_generate('<ButtonRelease-1>', x=30, y=18)
    hub.update()
    assert sent[-1] == ('manual', ['/control/0'], 60), sent
    assert 'RETWEAKS curve' in card.state.cget('text'), card.state.cget('text')
    saved = config()['fan_curves']['CPU Fan · Test board']
    assert saved['active'] and saved['source'] == 'CPU' and saved['ids'] == ['/control/0'] and saved['preset'] == 'Balanced'
    assert config().get('fan_curves_on_start', False) is False
    # failsafe: temperature gone for longer than FAILSAFE_SECONDS -> automatic
    sampler.extended, sampler.extended_time, sampler.rows, sampler.updated = [], 0, [], 0
    now = time.monotonic()
    engine.evaluate('CPU Fan · Test board', now=now)
    engine.evaluate('CPU Fan · Test board', now=now + fc.FAILSAFE_SECONDS + .1)
    assert sent[-1] == ('default', ['/control/0'], None) and 'Failsafe' in card.state.cget('text')
    reading(70); engine.evaluate('CPU Fan · Test board'); assert sent[-1][0] == 'manual'
    # manual Apply on the speed card takes over from the curve
    fan.slider.set(80)
    fan.apply.event_generate('<ButtonPress-1>', x=30, y=18); fan.apply.event_generate('<ButtonRelease-1>', x=30, y=18)
    hub.update()
    assert not engine.running('CPU Fan · Test board')
    assert sent[-2] == ('default', ['/control/0'], None) and sent[-1] == ('manual', ['/control/0'], 80), sent[-2:]
    # back to automatic marks the saved curve inactive
    card.use_curve(); card.back_to_auto(); hub.update()
    assert sent[-1] == ('default', ['/control/0'], None) and not config()['fan_curves']['CPU Fan · Test board']['active']
    # launch behaviour: saved active curve does NOT start unless "Start my fan curves" is ticked
    cur = config()['fan_curves']; cur['CPU Fan · Test board']['active'] = True; hub.settings['fan_curves'] = cur
    n = len(sent); card.on_start.set(False); card._resume_saved(); assert not engine.curves and len(sent) == n
    card.on_start.set(True); card._save_on_start(); card._resume_saved()
    assert engine.running('CPU Fan · Test board') and config()['fan_curves_on_start'] is True
    # Quit: page close() hands every fan back
    page.close()
    assert sent[-1] == ('default', ['/control/0'], None) and not engine.curves

    # ---------------------------------------------------------------- RGB
    rgb = hub.rgb_lighting; rgb.tried = True; rgb.retry_at = time.monotonic() + 3600
    hub.sidebar_nav.buttons["RGB lighting"].command(); hub.update()
    assert rgb.start_profile_pending is None and config().get('rgb_apply_on_start', False) is False
    devices = []
    for index, (kind, name) in enumerate(((DeviceType.COOLER, 'Fan Hub'), (DeviceType.DRAM, 'RGB RAM'))):
        modes = [SimpleNamespace(id=0, name='Static', color_mode=ModeColors.PER_LED, flags=ModeFlags(0)),
                 SimpleNamespace(id=1, name='Breathing', color_mode=ModeColors.MODE_SPECIFIC, flags=ModeFlags.HAS_SPEED,
                                 speed_min=0, speed_max=4, colors_min=1)]
        devices.append(SimpleNamespace(id=index, name=name, type=kind, leds=[1], modes=modes, active_mode=0,
                                       set_mode=Mock(), set_color=Mock(), zones=[]))
    client = Mock(); client.devices = devices
    with patch('rgb_service.server_available', return_value=True), patch('openrgb.OpenRGBClient', return_value=client):
        rgb.connect(); pump(hub, lambda: not rgb.busy)
    assert len(rgb.power_vars) == 2
    rgb.choose_group('Fans + RAM')
    assert 'Breathing' in rgb.effect.values and 'Color cycle' not in rgb.effect.values   # only modes every device has
    devices[1].modes = devices[1].modes[:1]; rgb.refresh_effects()
    assert 'Breathing' not in rgb.effect.values
    devices[1].modes.append(SimpleNamespace(id=1, name='Breathing', color_mode=ModeColors.MODE_SPECIFIC,
                                            flags=ModeFlags.HAS_SPEED, speed_min=0, speed_max=4, colors_min=1))
    writes = []
    with patch.object(rgb.service, 'start'), patch('rgb_service.connect', return_value=client), \
            patch('rgb_service.write_solid', side_effect=lambda d, z, c: writes.append((d.name, c.red, c.green, c.blue))):
        rgb.preset('Red', '#ff0000'); rgb.brightness.set(50); rgb.quick_apply_color(); pump(hub, lambda: not rgb.busy)
        assert writes and all(w[1:] == (128, 0, 0) for w in writes), writes          # 50 % brightness
        # device off -> black on that device only
        writes.clear()
        rgb.set_device_power(rgb.devices[1]['label'], False); pump(hub, lambda: not rgb.busy)
        assert writes == [('RGB RAM', 0, 0, 0)] and 'RGB RAM' in rgb.off_devices
        # profiles: save -> config, apply -> same writes, delete
        assert rgb.save_profile('Night')
        prof = config()['rgb_profiles']['Night']
        assert prof['color'] == '#ff0000' and prof['brightness'] == 50 and prof['off'] == ['RGB RAM'] and prof['group'] == 'Fans + RAM'
        rgb.preset('Blue', '#0000ff'); rgb.brightness.set(100); writes.clear()
        assert rgb.apply_profile('Night'); pump(hub, lambda: not rgb.busy and not rgb.post_queue)
        for _ in range(5): rgb.tick(); pump(hub, lambda: not rgb.busy)
        assert ('Fan Hub', 128, 0, 0) in writes and writes[-1] == ('RGB RAM', 0, 0, 0), writes
        assert rgb.delete_profile('Night') and 'Night' not in config().get('rgb_profiles', {})
    # hardware Breathing goes through write_effect with the brightness/speed
    with patch.object(rgb.service, 'start'), patch('rgb_service.connect', return_value=client), \
            patch('rgb_service.write_effect') as eff:
        rgb.effect.set('Breathing'); rgb.effect_changed(); rgb.effect_speed.set(60); rgb.brightness.set(80)
        rgb.quick_apply_color(); pump(hub, lambda: not rgb.busy)
        assert eff.call_count == 2 and eff.call_args.args[1] == 'Breathing' and eff.call_args.kwargs['brightness'] == 80
    # apply-on-start: ticking it saves the setting (nothing is applied now)
    rgb.save_profile('Day'); rgb.start_profile.set('Day'); rgb.apply_on_start.set(True); rgb._save_start()
    assert config()['rgb_apply_on_start'] is True and config()['rgb_start_profile'] == 'Day'
    errors = [e for e in errors if 'zoomed' not in str(e[1])]
    assert not errors, errors
finally:
    hub.destroy()
print('PASS: fan curves (draft-only editing, Use this curve sends a bounded duty, saved to config, failsafe on missing '
      'temperature, manual Apply takes over, Automatic marks it inactive, no start at launch unless ticked, Quit hands '
      'back) and RGB extras (Breathing only when supported, brightness, device on/off, profiles, apply-on-start setting).')
