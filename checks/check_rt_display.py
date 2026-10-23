"""Display page (Tk): stretched-resolution trial/keep/revert, NVIDIA add flow, refresh-rate keep/revert,
Back to native and the Keep dialog timeout. All Windows calls are faked."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tkinter as tk
from _tk_harness import FakeHub, g, pump
from core import display as dsp
from core import nvidia_display as nvd
import rt_pages.display as page_mod

hub = FakeHub()
calls = []
D = {"device": "D1", "name": "ED320Q X2", "width": 1920, "height": 1080, "bpp": 32, "hz": 144, "max_hz": 240,
     "primary": True, "native": (1920, 1080), "modes": [(1920, 1080, 32, 240), (1920, 1080, 32, 144)]}
ADDED = dict(D, modes=D["modes"] + [(1720, 1080, 32, 240)])
displays = [D]
dsp.list_displays = lambda: list(displays)
dsp.list_gpu_drivers = lambda: [{"name": "NVIDIA GeForce RTX 4060", "vendor": "NVIDIA", "version": "32.0.15.6094",
                                  "date": None, "age_days": None, "nvml_version": "560.94", "url": "https://x"}]
dsp.set_resolution = lambda dev, w, h, hz=None, stretch=True, persist=False: (calls.append(("set", w, h, hz, persist)), (True, "ok"))[1]
dsp.restore_saved_mode = lambda dev: (calls.append(("restore",)), (True, "back"))[1]
dsp.set_refresh_rate = lambda dev, hz: (calls.append(("hz", hz)), (True, "ok", 144))[1]
page_mod._ask = lambda *a: True
page_mod.info = lambda *a, **k: calls.append(("info",) + a[1:2])


class FakeNv:
    log = []
    def __init__(self): pass
    def display_id(self, name): return 7
    def timing(self, did, w, h, hz): FakeNv.log.append(("timing", w, h, hz)); return object()
    def try_custom(self, did, custom): FakeNv.log.append(("try",))
    def save_custom(self, did): FakeNv.log.append(("save", did))
    def revert_trial(self, did): FakeNv.log.append(("revert", did))


nvd.NvApi = FakeNv
nvd.build_custom = lambda w, h, t: (w, h)

tab = tk.Frame(hub)
tab.pack(fill="both", expand=True)
p = page_mod.DisplayPage(hub, tab, g())
p.on_shown()
assert pump(hub, lambda: any(isinstance(w, tk.Canvas) for w in p.mon_box.winfo_children()) and
            len(p.drv_box.winfo_children()) >= 2), "cards not built"

# 1) stretched, mode already on the card, Keep -> trial then saved
keep = [True]
p.keep_dialog = lambda: keep[0]
p._stretch(D, 1720, 1080, 240)
assert calls[:2] == [("set", 1720, 1080, 240, False), ("set", 1720, 1080, 240, True)], calls
assert hub.logs[-1][2] == "Success"
# 2) not kept -> restore saved mode
calls.clear(); keep[0] = False
p._stretch(D, 1720, 1080, 240)
assert calls == [("set", 1720, 1080, 240, False), ("restore",)], calls
assert hub.logs[-1][2] == "Reverted"
# 3) NVIDIA add (mode missing), Keep both dialogs -> try, save, restore, then apply + save
calls.clear(); keep[0] = True; displays[:] = [ADDED]
p._stretch(D, 1720, 1080, None)
assert ("try",) in FakeNv.log and ("save", 7) in FakeNv.log and ("timing", 1920, 1080, 240) in FakeNv.log
assert calls == [("restore",), ("set", 1720, 1080, 240, False), ("set", 1720, 1080, 240, True)], calls
# 4) NVIDIA add not kept -> revert_trial, nothing else
calls.clear(); FakeNv.log.clear(); keep[0] = False; displays[:] = [D]
p._stretch(D, 1720, 1080, None)
assert FakeNv.log[-1] == ("revert", 7) and calls == [], calls
# 5) back to native: max Hz at native, saved
calls.clear()
p._native(dict(D, width=1720))
assert calls == [("set", 1920, 1080, 240, True)], calls
# 6) refresh rate: Set 240 Hz, not kept -> back to previous 144
calls.clear()
p._apply(D)
assert pump(hub, lambda: hub.logs[-1][2] == "Reverted"), (calls, hub.logs[-1])
assert calls[:2] == [("hz", 240), ("hz", 144)], calls
# 7) refresh rate kept
calls.clear(); keep[0] = True
p._apply(D)
assert pump(hub, lambda: hub.logs[-1][3] == "Kept after confirmation")
assert calls == [("hz", 240)]
# 8) the real Keep dialog reverts by itself after the countdown
t0 = __import__("time").time()
assert page_mod.KeepSettingsDialog(hub, g(), seconds=1).run() is False
assert __import__("time").time() - t0 < 5
# 9) portrait screen: no stretch offer; selector exists for landscape
assert dsp.stretch_choices(D) and hasattr(p, "_stretch_sel")
hub.destroy()
print("PASS: display page — stretched keep/revert, NVIDIA add keep/revert, native, refresh keep/revert, dialog timeout")
