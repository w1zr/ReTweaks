"""Linux test helper: opens the Tk app (no AI, no web helpers) and saves screenshots of tabs.
    xvfb-run -a -s "-screen 0 1600x1000x24" python3.12 tools/linux_shim.py tools/tk_screens.py OUTDIR [tab ...]
Tabs are names as shown in the sidebar, or 'intro' for the startup screen."""
import os
import sys
import time
from unittest.mock import Mock

import retweaks as app
import hubplus
import automation
from PIL import ImageGrab


class Hotkeys:
    def __init__(self, *a): self.thread = Mock()
    def update(self, *a): pass
    def close(self): pass


automation.Hotkeys = Hotkeys
app.Hub._load_info = lambda self: None
hubplus.write_json = lambda *a: None
hubplus.install(vars(app))
out = sys.argv[1]
names = sys.argv[2:]
os.makedirs(out, exist_ok=True)
want_intro = "intro" in names
hub = app.Hub(show_intro=want_intro, enable_ai=False)
hub.geometry("1500x940+0+0")


def pump(sec=0.6):
    end = time.time() + sec
    while time.time() < end:
        hub.update()
        time.sleep(0.02)


def grab(path, w=None):
    w = w or hub
    w.update()
    x, y = w.winfo_rootx(), w.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + w.winfo_width(), y + w.winfo_height())).save(path)
    print("saved", path)


if want_intro:
    intro = hub.intro
    for target in (10, 26, 45):
        while intro.frame < target:
            if intro.job: hub.after_cancel(intro.job); intro.job = None
            intro.tick()
        pump(0.1)
        grab(os.path.join(out, f"intro_{target}.png"), intro.window)
    while not intro.closed:
        if intro.job: hub.after_cancel(intro.job); intro.job = None
        intro.tick()
    names = [n for n in names if n != "intro"]

hub.deiconify()
hub.geometry("1500x940+0+0")
pump()
by_name = {}
for n, i in getattr(getattr(hub, "sidebar_nav", None), "targets", {}).items():
    by_name[n.lower()] = i
for k, v in getattr(hub, "rt_tabs", {}).items():
    by_name[k.lower()] = v
for name in names:
    i = by_name.get(name.lower())
    if i is None:
        print("no tab", name, sorted(by_name)); continue
    hub.show_tab(i)
    pump(0.8)
    grab(os.path.join(out, name.replace(" ", "_") + ".png"))
hub.destroy()
