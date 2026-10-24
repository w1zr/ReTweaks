"""Check for rt_pages/fps.py + rt_pages/overlay_tk.py (Linux: via tools/linux_shim.py + Xvfb).
Builds the real app, then drives the FPS test page with fake PresentMon / frame streams:
process list, a full test run (result saved and shown), notes, compare, delete, overlay start/stop,
overlay settings persisted, and the overlay window's text/position.
    xvfb-run -a python3.12 tools/linux_shim.py checks/check_rt_fps.py [screenshot.png]"""
import os
import sys
import tempfile
import time
from unittest.mock import Mock

tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp
os.environ["LOCALAPPDATA"] = tmp

import retweaks as app
import hubplus
import automation
from tkinter import messagebox
from core import fps, overlay_fps as of
import core.etw_frames as etw


class Hotkeys:
    def __init__(self, *a): self.thread = Mock()
    def update(self, *a): pass
    def close(self): pass


automation.Hotkeys = Hotkeys
app.Hub._load_info = lambda self: None
hubplus.write_json = lambda *a: None
hubplus.install(vars(app))

runs_file = os.path.join(tmp, "fps_runs.json")
from pathlib import Path
fps.runs_path = lambda: Path(runs_file)
fps.list_processes = lambda: [("FortniteClient-Win64-Shipping.exe", "Fortnite"), ("notepad.exe", "Untitled")]
warnings = []
messagebox.showwarning = lambda *a, **k: warnings.append(a)
messagebox.askyesno = lambda *a, **k: True


class FakeCapture:
    def __init__(self, exe, name, seconds):
        self.exe, self.name, self.seconds = exe, name, seconds
        self.t0 = None
        self.cleaned = False
    def start(self): self.t0 = time.time()
    def running(self): return time.time() - self.t0 < 0.4
    def overdue(self): return False
    def elapsed(self): return time.time() - self.t0
    def terminate(self): pass
    def cancel(self): pass
    def cleanup(self): self.cleaned = True
    def finish(self): return ([16.6] * 300 + [33.3] * 5, None)


fps.Capture = FakeCapture
fps.validate_presentmon_path = lambda p: (bool(p), "No PresentMon.exe selected." if not p else "")


class FakeStream:
    instances = []
    def __init__(self, name, *a, **k):
        self.name = name; self.started = self.stopped = False; self.error = None; self.source = "api"
        self.state = "running"
        FakeStream.instances.append(self)
    def start(self): self.started = True
    def stop(self): self.stopped = True
    def snapshot(self): return ({"fps": 144.0, "low1": 98.0, "frame_ms": 6.9}, self.state)
    def has_frames(self): return True


etw.BuiltinOverlayStream = FakeStream

hub = app.Hub(show_intro=False, enable_ai=False)
hub.geometry("1500x940+0+0")
errors = []
hub.report_callback_exception = lambda *a: errors.append(a)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        hub.update(); time.sleep(0.02)


# renamed page (owner request 2026-10-22): "FPS overlay" in the registry, sidebar and title; old key gone
assert "FPS test" not in hub.rt_pages and "FPS test" not in hub.sidebar_nav.targets
page = hub.rt_pages["FPS overlay"]
assert page is not None, "FPS page failed to load"
assert page.title == "FPS overlay" and "FPS overlay" in hub.sidebar_nav.targets
hub.show_tab(hub.rt_tabs["FPS overlay"])
pump(0.6)
# layout: in-game overlay card first, then PresentMon, then the FPS test (owner choice)
def card_title(w):
    stack = [w]
    while stack:
        x = stack.pop(0)
        if isinstance(x, app.tk.Label) and x.cget("text") in ("In-game overlay", "PresentMon", "FPS test"):
            return x.cget("text")
        stack.extend(x.winfo_children())
order = [t for t in (card_title(c) for c in page.body.winfo_children()) if t]
assert order[:3] == ["In-game overlay", "PresentMon", "FPS test"], order
# timing explanations are on the page
help_text = page.timing_help.cget("text")
assert "1% low window" in help_text and "FPS averaging" in help_text and "2 seconds" in help_text
# search still finds it by the old name
assert hub.global_search.search("fps test")[0][0] == "FPS overlay"
assert page.proc_names == ["FortniteClient-Win64-Shipping.exe", "notepad.exe"], page.proc_names
page.search_var.set("fort"); pump(0.1)
assert page.proc_names == ["FortniteClient-Win64-Shipping.exe"]
page.search_var.set(""); pump(0.1)

# no PresentMon -> refuses honestly
page.start(); assert "PresentMon" in page.status.cget("text")
page.path_var.set(r"C:\Tools\PresentMon.exe"); page._path_typed()
assert hub.settings["fps_presentmon_path"] == r"C:\Tools\PresentMon.exe"
page.start(); assert "Pick the running program" in page.status.cget("text")
page.proc_list.selection_set(0)
page.duration.set("10 seconds"); page._duration_changed("10 seconds")
assert hub.settings["fps_test_seconds"] == 10
page.start()
assert page.capture and page.capture.seconds == 10
end = time.time() + 5
while page.capture is not None and time.time() < end:
    pump(0.1)
pump(0.3)
assert page.capture is None
assert page.status.cget("text").startswith("Done."), page.status.cget("text")
saved = fps.load_runs()
assert len(saved) == 1 and saved[0]["game"] == "FortniteClient-Win64-Shipping.exe" and saved[0]["avg_fps"] > 0
assert page.result_body is not None
assert len(page.table.get_children()) == 1

# second run, then notes + compare
page.start()
end = time.time() + 5
while page.capture is not None and time.time() < end:
    pump(0.1)
pump(0.3)
rows = page.table.get_children()
assert len(rows) == 2
page.table.selection_set(rows[0]); pump(0.1)
page.notes_var.set("Game Mode off"); page.save_notes()
assert any(r.get("notes") == "Game Mode off" for r in fps.load_runs())
page.table.selection_set(page.table.get_children()); pump(0.1)
page.compare(); pump(0.1)
assert page.compare_body is not None and len(page.compare_tree.get_children()) == len(fps.METRIC_ROWS) or \
    len(page.compare_tree.get_children()) > 0

# FPS test length: 5 minutes and a validated custom length, remembered
assert "5 minutes" in page.duration.values and "Custom…" in page.duration.values
page.duration.set("5 minutes"); page._duration_changed("5 minutes")
assert hub.settings["fps_test_seconds"] == 300 and page.test_seconds() == 300
page.duration.set("Custom…"); page._duration_changed("Custom…")
assert page.custom_box.winfo_manager() == "pack"
page.custom_var.set("3"); page._custom_seconds_typed()
assert page.test_seconds() is None and hub.settings["fps_test_seconds"] == 300 and "5 to 1800" in page.duration_help.cget("text")
page.start(); assert "between 5 and 1800" in page.status.cget("text") and page.capture is None
page.custom_var.set("45"); page._custom_seconds_typed()
assert page.test_seconds() == 45 and hub.settings["fps_test_seconds"] == 45
page._load_duration(); assert page.duration.get() == "Custom…" and page.custom_var.get() == "45"
hub.settings["fps_test_seconds"] = "garbage"; page._load_duration(); assert page.test_seconds() == 30
page.duration.set("10 seconds"); page._duration_changed("10 seconds")

# overlay timings: saved, validated, applied live to the frame maths (also a running overlay)
from core import overlay_fps as of
page.ov_low.set("30 s"); page.ov_span.set("0.5 s"); page._overlay_setting_changed()
assert hub.settings["overlay_low_window_s"] == 30 and hub.settings["overlay_fps_span_s"] == 0.5
assert of.timings() == {"low_window_s": 30.0, "fps_span_s": 0.5}
assert of.RollingMetrics().window_ms == 30000
page.ov_low.set("10 s"); page.ov_span.set("1 s"); page._overlay_setting_changed()
assert of.timings() == {"low_window_s": 10.0, "fps_span_s": 1.0}

# overlay settings persist
page.ov_pos.set("Bottom right"); page.ov_size.set("Large"); page.ov_opacity.set(70)
page.ov_load_var.set(False); page._overlay_setting_changed()
for k, v in {"overlay_position": "bottom-right", "overlay_size": "large", "overlay_opacity": 70,
             "overlay_show_load": False, "overlay_source": "builtin"}.items():
    assert hub.settings[k] == v, (k, hub.settings.get(k))

# overlay start without a selected program -> warning, nothing started
page.proc_list.selection_clear(0, "end")
page.start_overlay()
assert warnings and not FakeStream.instances
page.proc_list.selection_set(0)
page.start_overlay(); pump(0.6)
assert page.overlay_stream and page.overlay_stream.started
win = page.overlay_win
assert win.lines[0] == "FPS 144" and win.lines[1] == "1% low 98", win.lines
assert len(win.lines) == 3                       # load line hidden (setting off)
assert not page.btn_start.enabled                # one capture at a time
win.win.update()
w, h = win.win.winfo_width(), win.win.winfo_height()
sw, sh = hub.winfo_screenwidth(), hub.winfo_screenheight()
assert abs((win.win.winfo_x() + w) - (sw - 16)) <= 2 and abs((win.win.winfo_y() + h) - (sh - 16)) <= 2, \
    (win.win.winfo_x(), win.win.winfo_y(), w, h)  # bottom-right corner, 16 px margin
page.ov_load_var.set(True); page._overlay_setting_changed(); pump(0.6)
assert len(win.lines) == 4 and win.lines[3].startswith("CPU"), win.lines
service = page.overlay_telemetry
assert service is not None and page in service.holders
saved_metrics = {key: var.get() for key, var in page.ov_metric_vars.items()}
for key, var in page.ov_metric_vars.items():
    var.set(key == 'ram')
hub.rt_last_sample = {'time': time.time(), 'ram': {'percent': 50}}
page._overlay_setting_changed()
assert win.lines == ['RAM 50%'], win.lines
assert hub.settings['overlay_show_ram'] is True and hub.settings['overlay_show_low1'] is False
page.ov_layout.set('Compact')
page.ov_refresh.set('250 ms')
page.ov_margin.set('32 px')
page._overlay_setting_changed()
assert win.cfg['overlay_refresh_ms'] == 250 and win.cfg['overlay_margin'] == 32
for key, value in saved_metrics.items():
    page.ov_metric_vars[key].set(value)
page.ov_layout.set('Stacked')
page.ov_margin.set('16 px')
page._overlay_setting_changed()
shot = sys.argv[1] if len(sys.argv) > 1 else None
if shot:
    from PIL import ImageGrab
    hub.update()
    x, y = page.tab.winfo_rootx(), page.tab.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + page.tab.winfo_width(), y + page.tab.winfo_height())).save(shot)
    cv = page.body.master
    cv.yview_moveto(0.55); hub.update(); time.sleep(0.2); hub.update()
    x, y = page.tab.winfo_rootx(), page.tab.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + page.tab.winfo_width(), y + page.tab.winfo_height())).save(shot.replace(".png", "_lower.png"))
    x, y = win.win.winfo_rootx(), win.win.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + win.win.winfo_width(), y + win.win.winfo_height())).save(shot.replace(".png", "_overlay.png"))
# game closes -> 'Game closed', then stops
stream = page.overlay_stream
stream.state = "closed"; pump(0.6)
assert page.overlay_win is None or page.overlay_win.lines == ["Game closed"]
page._stop_overlay_later_job = None
page.stop_overlay("stopped by check"); pump(0.1)
assert stream.stopped and page.overlay_stream is None and page.btn_start.enabled
assert page not in service.holders

# delete one run
page.table.selection_set(page.table.get_children()[0]); pump(0.1)
page.delete()
assert len(fps.load_runs()) == 1
page.close()
import traceback
mine = [e for e in errors if any(("rt_pages/fps.py" in str(f.filename) or "overlay_tk.py" in str(f.filename))
                                 for f in traceback.extract_tb(e[2]))]
assert not mine, [traceback.format_exception(*e) for e in mine]
print(f"(ignored {len(errors) - len(mine)} errors from other parts of the app on Linux)")
hub.destroy()
# "Open on: FPS test" from before the rename still opens this page
from rt_pages import settings_store
import json as _json
p = settings_store.config_path(); d = _json.loads(p.read_text()); d["startup_page"] = "FPS test"; p.write_text(_json.dumps(d))
assert settings_store.load()["startup_page"] == "FPS overlay"
assert settings_store.load()["startup_page"] == "FPS overlay"      # repeat-safe
print("PASS: FPS overlay page (renamed, overlay first, timings with explanations saved + applied live, test length "
      "incl. 5 min + custom, process list, test run saved/shown, notes, compare, delete, overlay start/text/corner/"
      "settings/game-closed stop, Open-on migration).")
