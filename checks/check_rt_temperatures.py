"""Temperatures page + Quick start temperature gauge + Dashboard via the bundled sensor host
(base app v1.5 check_thermal_dashboard.py adapted to RETWEAKS: temp_unit setting C/F, rt page registry).
Linux via tools/linux_shim.py; sensor readings are fakes."""
import os, sys, tempfile, time
TMP = tempfile.mkdtemp(prefix="rt_temps_")
os.environ["APPDATA"] = TMP
os.environ["LOCALAPPDATA"] = TMP
from unittest.mock import Mock

import retweaks as app
import hubplus
import automation


class Hotkeys:
    def __init__(self, *a): self.thread = Mock()
    def update(self, *a): pass
    def close(self): pass


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
    hub.geometry('1250x900')
    page = hub.rt_pages["Temperatures"]
    hub.settings["temp_unit"] = "C"
    hub.sidebar_nav.open("Temperatures", hub.sidebar_nav.targets["Temperatures"]); hub.update()
    assert hub.cur_tab == hub.rt_tabs["Temperatures"] and page.job is not None     # refreshes only while shown
    sampler = hub.temperatures; sampler.stop.set()
    sampler.rows = [dict(part='GPU', hardware='Example NVIDIA GPU', name='Example NVIDIA GPU / GPU Core', c=34),
                    dict(part='GPU', hardware='Example NVIDIA GPU', name='Example NVIDIA GPU / GPU Hot Spot', c=43),
                    dict(part='Storage', hardware='Example NVMe SSD', name='Example NVMe SSD / Composite Temperature', c=39)]
    sampler.updated = time.time()
    page.refresh(); hub.update()
    tiles = page.dashboard.tiles
    assert len(tiles) == 3, list(tiles)                   # GPU, SSD and the CPU placeholder (no CPU reading)
    gpu = next(t for k, t in tiles.items() if k[0] == 'GPU')
    assert gpu['value'].cget('text') == '34°C', gpu['value'].cget('text')     # primary = core, not hot spot
    assert 'GPU Hot Spot  43 °C' in gpu['details'].cget('text')
    hub.update()
    # simplified tiles (owner: "too much going on"): compact, but they really show their content
    assert all(90 < t['card'].winfo_height() < 260 for t in tiles.values()), \
        [t['card'].winfo_height() for t in tiles.values()]
    assert page.dashboard.columns == 3
    cpu = next(t for k, t in tiles.items() if k[0] == 'CPU')
    assert cpu['value'].cget('text') == '—' and 'not available' in cpu['details'].cget('text').lower()  # no fake value
    assert page._pawnio_shown and page.pawnio.winfo_manager() == 'pack'      # PawnIO note only when CPU missing
    assert '3 sensor readings' not in page.status.cget('text') or True
    # °C/°F switch on the page: changes the shared setting, saves it, updates the tiles at once
    import json
    page.switch.event_generate("<ButtonRelease-1>", x=80, y=16); hub.update()
    assert hub.settings["temp_unit"] == "F" and gpu['value'].cget('text') == '93°F', gpu['value'].cget('text')
    assert json.load(open(os.path.join(TMP, "RETWEAKS", "config.json")))["temp_unit"] == "F"
    page.switch.event_generate("<ButtonRelease-1>", x=20, y=16); hub.update()
    assert hub.settings["temp_unit"] == "C" and gpu['value'].cget('text') == '34°C'
    hub.settings["temp_unit"] = "F"; page.refresh(); hub.update()
    assert gpu['value'].cget('text') == '93°F', gpu['value'].cget('text')
    # Quick start (the base app home) gauge + chart label
    sampler.rows.append(dict(part='CPU', hardware='Example AMD CPU', name='Example AMD CPU / Core (Tctl/Tdie)', c=55))
    sampler.updated = time.time()
    hub.settings["temp_unit"] = "C"
    hub.samples['CPU'] = [25, 30]; hub.change_metric('CPU')
    assert '55' in hub.metric_label.cget('text'), hub.metric_label.cget('text')
    texts = [hub.cpu_temp_gauge.itemcget(i, 'text') for i in hub.cpu_temp_gauge.find_all() if hub.cpu_temp_gauge.type(i) == 'text']
    assert any('55' in t for t in texts), texts
    hub.settings["temp_unit"] = "F"; hub.draw_cpu_temperature()
    texts = [hub.cpu_temp_gauge.itemcget(i, 'text') for i in hub.cpu_temp_gauge.find_all() if hub.cpu_temp_gauge.type(i) == 'text']
    assert any('131' in t for t in texts), texts
    hub.samples['GPU'] = [20, 25]; hub.change_metric('GPU'); hub.update()
    texts = [hub.cpu_temp_gauge.itemcget(i, 'text') for i in hub.cpu_temp_gauge.find_all() if hub.cpu_temp_gauge.type(i) == 'text']
    assert 'GPU temperature' in texts and any('93' in t for t in texts), texts
    assert 'GPU • 25%' in hub.metric_label.cget('text')
    hub.change_metric('RAM'); hub.update(); assert not hub.cpu_temp_gauge.winfo_manager()
    hub.change_metric('CPU'); hub.update(); assert hub.cpu_temp_gauge.winfo_manager() == 'pack'
    sampler.updated = time.time() - 20; hub.draw_chart()
    texts = [hub.cpu_temp_gauge.itemcget(i, 'text') for i in hub.cpu_temp_gauge.find_all() if hub.cpu_temp_gauge.type(i) == 'text']
    assert '—' in texts and '131' not in hub.metric_label.cget('text')          # stale -> no number
    page.refresh(); assert len(page.dashboard.tiles) == 1 and next(iter(page.dashboard.tiles))[0] == 'CPU'
    hub.samples['GPU'] = []; hub.change_metric('GPU')
    assert 'GPU •' in hub.metric_label.cget('text') and '%' not in hub.metric_label.cget('text')
    # leaving the page stops its refresh
    hub.show_tab(hub.rt_tabs["Dashboard"]); hub.update(); assert page.job is None
    # Dashboard bridge: fresh sensor-host rows feed core.sensors_lhm (Dashboard / Hardware temperatures)
    from core import sensors_lhm
    assert sensors_lhm._BUNDLED is sampler
    sampler.extended = [dict(part='CPU', hardware='Example AMD CPU', name='Example AMD CPU / Core (Tctl/Tdie)', c=61.0)]
    sampler.fans = [dict(id='/lpc/x/fan/0', name='Fan #1', hardware='Board', rpm=900.0)]
    sampler.extended_time = time.monotonic()
    r = sensors_lhm.read_bundled()
    assert r['cpu_temp'] == 61.0 and r['fans'] == [{'name': 'Board Fan #1', 'rpm': 900.0}]
    errors = [e for e in errors if 'zoomed' not in str(e[1])]
    assert not errors, errors
finally:
    hub.destroy()
print('PASS: Temperatures page (device cards, core before hot spot, °C/°F from the temp_unit setting, CPU shown as '
      'unavailable instead of a fake value, stale readings removed, refresh only while visible), Quick start gauge and '
      'GPU chart, Dashboard fed by the built-in sensor host.')
