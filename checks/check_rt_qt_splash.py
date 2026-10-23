"""v1.6 startup screen in its own process (rt_splash_qt + rt_splash_client): the app hands over 'ready',
the splash finishes the (slower) reveal, holds, sends show/alpha/done, and the window ends fully visible.
Also: a splash process that dies early never leaves the window hidden.
Needs a Python with PySide6 for the splash process: SPLASH_PY (default python3)."""
import os, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["APPDATA"] = tempfile.mkdtemp(); os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
py = os.environ.get("SPLASH_PY", "python3")
os.environ["RETWEAKS_SPLASH_CMD"] = f"{py}|{os.path.join(ROOT, 'rt_splash_qt.py')}"
DEAD = "--dead" in sys.argv
if DEAD:
    os.environ["RETWEAKS_SPLASH_CMD"] = f"{py}|-c|import sys;sys.exit(0)"
import retweaks as app, hubplus, rt_splash_client
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
if DEAD:
    # splash process that dies right away: the window still appears, no waiting
    hub = app.Hub(enable_ai=False)
    end = time.monotonic() + 5
    while not hub.intro.closed and time.monotonic() < end:
        hub.update(); time.sleep(0.01)
    assert hub.intro.closed and hub.state() != "withdrawn" and float(hub.attributes("-alpha")) == 1.0
    hub.destroy()
    print("PASS-DEAD: v1.6 startup screen process: slower reveal, hold, cross-fade into the window, done; dead splash -> window shown.")
    sys.exit(0)
shots = os.environ.get("SPLASH_SHOTS")
t0 = time.monotonic()
hub = app.Hub(enable_ai=False)
intro = hub.intro
assert isinstance(intro, rt_splash_client.QtIntro), type(intro)
assert intro.ready_at is not None and hub.state() == "withdrawn"
alphas, shown_at, k = [], None, 0
end = time.monotonic() + 15
while not intro.closed and time.monotonic() < end:
    hub.update(); time.sleep(0.01)
    if intro.shown and shown_at is None:
        shown_at = time.monotonic()
    a = float(hub.attributes("-alpha")); alphas.append(a)
    if shots and k < 8 and time.monotonic() - t0 > 0.6 * k:
        from PIL import ImageGrab
        ImageGrab.grab((0, 0, 1600, 1000)).save(f"{shots}/qt_splash_{k}.png"); k += 1
assert intro.closed, "splash never finished"
assert shown_at is not None and shown_at - intro.t0 >= 2.0, shown_at - intro.t0    # slower reveal (~2.4 s) + hold
assert float(hub.attributes("-alpha")) == 1.0 and hub.state() != "withdrawn"
assert any(0.05 < a < 0.95 for a in alphas), "no cross-fade"
assert intro.proc.wait(5) == 0
print(f"  splash: window shown {shown_at - intro.t0:.2f}s after start, fade steps {len(set(alphas))}")
hub.destroy()

import subprocess
r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "linux_shim.py"), os.path.abspath(__file__), "--dead"],
                   capture_output=True, text=True, timeout=120)
assert "PASS-DEAD" in r.stdout, r.stdout[-800:] + r.stderr[-1500:]
print("PASS: v1.6 startup screen process: slower reveal, hold, cross-fade into the window, done; dead splash -> window shown.")
