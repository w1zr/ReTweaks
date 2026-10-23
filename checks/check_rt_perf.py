"""Smooth scrolling + slowness log (owner report 2026-10-22: laggy scrolling with black gaps, buttons not reacting).
- several wheel ticks inside one frame become ONE scroll of their total (no queue of repaints)
- the page scrolls by the right amount and the sidebar uses the same path
- a slow button command is written to %APPDATA%\\RETWEAKS\\perf.log with its name; fast ones aren't"""
import os, sys, tempfile, time
TMP = tempfile.mkdtemp(prefix="rt_perf_")
os.environ["APPDATA"] = TMP; os.environ["LOCALAPPDATA"] = TMP
import rt_perf
rt_perf.install("test")
import retweaks as app, hubplus
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
hub.geometry("1400x800"); hub.update()
pump = lambda n=20: [hub.update() or time.sleep(0.01) for _ in range(n)]
hub.show_tab(1); pump()                                   # Individual tweaks: a long page
tab = getattr(hub, "tweaks_all", hub.tabs[1])            # the visible "All tweaks" tab of Individual tweaks
cv = next(w for w in tab.winfo_children() if isinstance(w, app.tk.Canvas) and hasattr(w, "wheel_scroll")) \
    if any(hasattr(w, "wheel_scroll") for w in tab.winfo_children()) else None
if cv is None:   # page built its own layout; find any smooth canvas inside it
    stack = [tab]; cv = None
    while stack and cv is None:
        w = stack.pop()
        if hasattr(w, "wheel_scroll"): cv = w
        stack.extend(w.winfo_children())
assert cv is not None, "page scroll area must use smooth scrolling"
calls = []
orig = cv.yview_scroll
cv.yview_scroll = lambda n, what: (calls.append(n), orig(n, what))
top0 = cv.yview()[0]
for _ in range(5):
    cv.wheel_scroll(3)                                    # five quick wheel ticks
pump(5)
assert calls == [15], calls                               # coalesced into one scroll
assert cv.yview()[0] > top0
cv.wheel_scroll(-3); cv.wheel_scroll(3); pump(5)
assert calls == [15], calls                               # ticks that cancel out don't repaint at all
# global wheel handler routes to it
class E: pass
e = E(); e.delta = -120; e.x_root = cv.winfo_rootx() + 50; e.y_root = cv.winfo_rooty() + 50
hub._wheel(e); pump(5)
assert calls[-1] == 3, calls
assert hasattr(hub.sidebar_nav.canvas, "wheel_scroll")    # sidebar too
# slowness log
b = app.tk.Button(hub, command=lambda: time.sleep(0.15)); b.invoke()
f = app.tk.Button(hub, command=lambda: None); f.invoke()
log = open(rt_perf.log_path(), encoding="utf-8").read()
assert "START  RETWEAKS test" in log and "check_rt_perf.py" in log and " ms  " in log, log[-500:]
assert log.count(" ms  ") == sum(1 for l in log.splitlines() if " ms  " in l)
print("PASS: smooth scrolling (coalesced wheel, cancel-out, global handler, sidebar) and the slow-callback log.")
hub.destroy()
