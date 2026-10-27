"""v2.0.8 first-launch guard: optional startup steps that fail are logged and skipped; if the main window itself
can't be created, RETWEAKS logs it and restarts itself once (packaged exe), else shows where the log is."""
import os, runpy, sys, tempfile, time, threading
T = tempfile.mkdtemp(prefix="rt_first_")
os.environ["APPDATA"] = T; os.environ["LOCALAPPDATA"] = T
import tkinter as tk
from tkinter import messagebox
import rt_welcome, rt_shell, rt_crashlog
sys.argv = ["retweaks.py"]
# 1) an optional step fails -> the app still opens
rt_welcome.prepare = lambda: (_ for _ in ()).throw(RuntimeError("shortcut failed"))
seen = {}
real_mainloop = tk.Tk.mainloop
def fake_mainloop(self, n=0):
    seen["hub"] = self
    end = time.time() + 2
    while time.time() < end:
        self.update(); time.sleep(0.01)
tk.Tk.mainloop = fake_mainloop
exits = []
os_exit = os._exit
os._exit = lambda code: exits.append(code)
rt_shell.exit_watchdog = lambda *a, **k: None
runpy.run_path("retweaks.py", run_name="__main__")
log = open(rt_crashlog.log_path(), encoding="utf-8").read()
assert "hub" in seen and "STARTUP STEP FAILED: welcome tour" in log and "shortcut failed" in log, log[-800:]
seen["hub"].destroy()
# 2) the window can't be created -> restart once (packaged) / message (second time)
import retweaks
calls = []
rt_shell.restart_after_exit = lambda *a: calls.append("restart") or True
src = open("retweaks.py", encoding="utf-8").read().replace("hub = Hub(show_intro=", "hub = _boom(show_intro=")
g = {"__name__": "__main__", "__file__": "retweaks.py"}
def _boom(**k):
    raise RuntimeError("window failed")
g["_boom"] = _boom
exits.clear()
class Stop(Exception):
    pass
os._exit = lambda code: (exits.append(code), (_ for _ in ()).throw(Stop()))
try:
    exec(compile(src.replace("\nif __name__", "\n_boom = globals().get('_boom')\nif __name__"), "retweaks.py", "exec"), g)
except Stop:
    pass
assert calls == ["restart"] and exits == [1], (calls, exits)
assert "STARTUP FAILED" in open(rt_crashlog.log_path(), encoding="utf-8").read()
sys.argv = ["retweaks.py", "--restarted"]
shown = []
messagebox.showerror = lambda *a, **k: shown.append(a)
calls.clear(); exits.clear()
try:
    exec(compile(src.replace("\nif __name__", "\n_boom = globals().get('_boom')\nif __name__"), "retweaks.py", "exec"), dict(g))
except Stop:
    pass
assert calls == [] and exits == [1] and shown and "crash.log" in shown[0][1], (calls, exits, shown)
print("PASS: first launch — failing optional steps are logged and skipped; a failed start restarts once, then explains.")
os_exit(0)
