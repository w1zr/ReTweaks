"""Checks for the Tk Health Check, Snapshots and Fun tools pages (fakes; no Windows changes).
Run: xvfb-run -a python3.12 tools/linux_shim.py checks/check_rt_health_snapshots_fun.py"""
import time
import tkinter as tk
from datetime import datetime, timedelta

import retweaks as app
from core import fps as fpsmod
from core import healthcheck as hc
import rt_pages.health as health
import rt_pages.snapshots as snapshots
import rt_pages.fun as fun


class FakeHub(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = {"temp_unit": "C"}
        self.saved = 0
        self.logs = []
        self.shown = []
        self.rt_tabs = {"Startup apps": 31, "Cleanup": 32}

    def save_settings(self):
        self.saved += 1
        return True

    def log_action(self, *a):
        self.logs.append(a)

    def show_tab(self, i):
        self.shown.append(i)

    def _scroll_area(self, parent):
        return app.Hub._scroll_area(self, parent)


def pump(hub, cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end and not cond():
        hub.update()
        time.sleep(0.02)
    hub.update()
    assert cond(), "timed out"


g = vars(app)
hub = FakeHub()

# ---------------------------------------------------------------- Health Check
fake = {"startup": (hc.WARN, "open_startup"), "temp": (hc.GOOD, None), "power": (hc.BAD, "power_high")}


def run_one(cid, checks=None):
    name = dict((c, n) for c, n, _ in hc.CHECKS)[cid]
    st, fix = fake.get(cid, (hc.NA, None))
    return hc.result(cid, name, st, f"detail {cid}", fix, "Fix it")


health.hc.run_one = run_one
tab = tk.Frame(hub)
tab.pack(fill="both", expand=True)
hp = health.HealthPage(hub, tab, g)
hp.run_all()
pump(hub, lambda: not hp._running)
assert len(hp.results) == len(hc.CHECKS)
assert hp.summary.cget("text") == "1 good · 2 to look at · 7 unavailable", hp.summary.cget("text")
assert hp.chip.status[0] == hc.WARN and hp.chip.status[1] == hc.GOOD and hp.chip.status[2] == hc.BAD
assert hp.chip.status[5] is None and hp.chip.status[11] is None          # unused pins stay unlit
assert hp._rows["startup"]["btn"].label == "Open Startup apps"
assert hp._rows["temp"]["btn"] is None                                   # good -> no Fix button
hp.do_fix("startup")
assert hub.shown == [31]
health.confirm = lambda *a: True
health.hc.apply_power_high = lambda: (True, "High performance power plan is now active.")
hp.do_fix("power")
pump(hub, lambda: hub.logs)
assert hub.logs[0][0] == "Health Check: power plan" and hub.logs[0][3] == ""
print("PASS Health Check: scan, summary, pins, nav fix, power fix logged")

# ---------------------------------------------------------------- Snapshots
tab2 = tk.Frame(hub)
sp = snapshots.SnapshotsPage(hub, tab2, g)
sp._ensure_feed = lambda: None            # feed samples by hand
sp._release_feed = lambda: None
sp.length.set("15 seconds")
sp.toggle()
for k, (load, mhz, t, gl, gt, ram) in enumerate(((10, 3000, 50, 20, 60, 40), (30, 4000, 70, 60, 64, 60))):
    sp.recording["start"] = datetime.now() - timedelta(seconds=(5, 20)[k])
    sp.on_telemetry({"cpu": {"load": load, "mhz": mhz, "temp_c": t}, "ram": {"percent": ram},
                     "gpus": [{"load": gl, "temp_c": gt}]})
rows = sp.table.get_children()
assert len(rows) == 1, rows                # finished automatically after 15 s
v = sp.table.item(rows[0], "values")
assert v[3] == "20% / 30%" and v[4] == "3500 MHz" and v[5] == "70 °C", v
assert v[6] == "40% / 60%" and v[7] == "64 °C" and v[8] == "50%", v
assert sp.recording is None
row = snapshots.summarize("x", datetime.now(), [{"cpu": {}, "ram": {}, "gpus": []}], 1, sp.temp_text)
assert row[3] == "Unavailable / Unavailable" and row[5] == "Unavailable"    # no fake zeros

runs = [fpsmod.make_run("game.exe", 30, {"avg_fps": 100.0, "low1_fps": 60.0}),
        fpsmod.make_run("game.exe", 30, {"avg_fps": 120.0, "low1_fps": None})]
snapshots.fpsmod.load_runs = lambda path=None: runs
sp.load_runs()
sp.compare()
texts = [w.cget("text") for w in sp.cmp_box.winfo_children()[0].winfo_children()]
assert "+20.0 FPS (+20.0%)" in texts, texts
assert any(t.startswith("Unavailable") for t in texts)
print("PASS Snapshots: averages/max from real samples, Unavailable for missing, FPS compare")

# ---------------------------------------------------------------- Fun tools
tab3 = tk.Frame(hub)
fp = fun.FunPage(hub, tab3, g)
clock = [100.0]
fun.now = lambda: clock[0]
fp.cps_secs.set("5 s")
for i in range(40):
    clock[0] = 100.0 + i * 0.1
    fp._cps_click()
clock[0] = 106.0
fp._cps_finish(clock[0])
assert hub.settings["fun_cps_best"] == 8.0 and hub.saved == 1, hub.settings
fp.rx.begin_try = (lambda orig: (lambda t, delay=None: orig(t, delay=1.0)))(fp.rx.begin_try)
for k in range(5):
    clock[0] = 200.0 + k * 10
    fp._rx_click()                           # start try
    clock[0] += 1.0
    fp.rx.tick(clock[0])
    clock[0] += 0.25
    fp._rx_click()
assert abs(hub.settings["fun_reaction_best_ms"] - 250.0) < 0.5, hub.settings
fp.poll_meter.add(1.0); fp.poll_meter.add(1.001)
assert fp.poll_meter.total_events == 2
print("PASS Fun tools: CPS and reaction best saved to settings")
hub.destroy()
