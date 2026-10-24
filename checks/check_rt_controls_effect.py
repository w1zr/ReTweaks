"""Settings controls really do something AND survive a restart (owner report 2026-10-22: "a lot of buttons
dont work, some settings dont change like temperature").

Phase 1 (this process): fresh temporary APPDATA, change every Settings control the way a click does, and check
the visible/real effect at once. Phase 2 (a new process, like reopening RETWEAKS): the same APPDATA, check every
choice came back. Linux: xvfb-run -a -s "-screen 0 1600x1000x24" python3.12 tools/linux_shim.py <this file>"""
import json, os, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PHASE = "verify" if "--verify" in sys.argv else "change"
TMP = sys.argv[sys.argv.index("--verify") + 1] if PHASE == "verify" else tempfile.mkdtemp(prefix="rt_effect_")
os.environ["APPDATA"] = TMP
os.environ["LOCALAPPDATA"] = TMP

import webbrowser
from unittest.mock import Mock
import retweaks as app
import hubplus
import automation
import rt_shell


class Hotkeys:
    def __init__(self, *a): self.thread = Mock()
    def update(self, *a): pass
    def close(self): pass


class FakeTray:
    def __init__(self, hub): self.icon = None; self.error = None
    def start(self): self.icon = object(); return True
    def stop(self): self.icon = None
    def notify(self, *a): pass


automation.Hotkeys = Hotkeys
rt_shell.Tray = FakeTray
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
opened = []
webbrowser.open = lambda url, *a, **k: opened.append(url) or True

hub = app.Hub(show_intro=False, enable_ai=False)
hub.settings["check_updates"] = False if PHASE == "change" else hub.settings.get("check_updates")
shell = rt_shell.Shell(hub, vars(app), [])
hub.update()
page = hub.rt_pages["Settings"]
dash = hub.rt_pages["Dashboard"]
cfg = lambda: json.load(open(os.path.join(TMP, "RETWEAKS", "config.json"), encoding="utf-8"))
pump = lambda n=5: [hub.update() for _ in range(n)]


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


def texts(w):
    out = []
    for c in walk(w):
        try:
            out.append(str(c.cget("text")))
        except Exception:
            pass
    return " | ".join(out)


def button(label):
    for c in walk(page.tab if hasattr(page, "tab") else hub.tabs[hub.rt_tabs["Settings"]]):
        if getattr(c, "label", None) == label and hasattr(c, "command"):
            return c
    raise AssertionError(f"button {label!r} not found")


def check(var):
    for c in walk(hub.tabs[hub.rt_tabs["Settings"]]):
        if getattr(c, "var", None) is var and hasattr(c, "_click"):
            return c
    raise AssertionError("checkbox not found")


# a fake live sample, as the telemetry service delivers it
SAMPLE = {"cpu": {"load": 20, "mhz": 3000, "temp_c": 50.0, "per_core": [20, 20]},
          "ram": {"percent": 40, "used_gb": 6.0, "total_gb": 16.0},
          "io": {"disk_read_bps": 0, "disk_write_bps": 0, "net_down_bps": 0, "net_up_bps": 0},
          "gpus": [{"load": 10, "vram_used_gb": 1.0, "vram_total_gb": 8.0, "temp_c": 60.0, "engine": "3D",
                    "core_mhz": None, "power_w": None, "fan_pct": None, "name": "Test GPU"}],
          "sensors": {}, "fans": []}

if PHASE == "change":
    hub.show_tab(hub.rt_tabs["Settings"]); pump()
    # ---- theme (writes appearance.json)
    page.theme._pick("Ocean"); pump()
    assert hub.theme_name == "Ocean"
    # ---- custom accent
    page.hex.set("#3b82f6"); assert page.apply_hex() is True
    assert cfg()["custom_accent"] == "#3b82f6"
    # ---- sidebar header
    page.header._pick("Wordmark only"); pump()
    assert cfg()["header_style"] == "wordmark" and not hub.sidebar_nav.header_chip.winfo_ismapped()
    # ---- dashboard banner
    page.banner._pick("Load wave (live)"); pump()
    assert cfg()["banner_style"] == "wave" and dash.banner.style == "wave"
    # ---- background accent (appearance.json)
    hub.animation_selector._pick("Fireflies"); pump()
    assert hub.animation == "Fireflies"
    # ---- refresh interval: the live service and the Dashboard text follow it
    page.interval._pick("Every 5 seconds"); pump()
    assert cfg()["interval"] == 5.0 and dash.svc.interval() == 5.0
    assert "every 5 seconds" in dash.sub_label.cget("text"), dash.sub_label.cget("text")
    # ---- temperature unit: Dashboard redraws at once, the setting is saved
    hub.rt_last_sample = SAMPLE
    dash.on_telemetry(SAMPLE, feed_banner=False); pump()
    assert "50 °C" in texts(dash.grid), texts(dash.grid)
    page.unit.event_generate("<ButtonRelease-1>", x=80, y=16); pump()       # real click on the °F side
    assert cfg()["temp_unit"] == "F" and page.unit.get() == "°F"
    assert "122 °F" in texts(dash.grid) and "140 °F" in texts(dash.grid), texts(dash.grid)
    # changed somewhere else (e.g. the Temperatures page) -> the Settings selector follows
    from rt_pages.settings_store import set_temp_unit
    set_temp_unit(hub, "C"); pump()
    assert page.unit.get() == "°C" and "50 °C" in texts(dash.grid)
    set_temp_unit(hub, "F"); pump()
    # ---- open on: the list holds every sidebar page
    assert "Network" in page.start_page.values and "Crosshair" in page.start_page.values, page.start_page.values
    assert len(page.start_page.values) == len(hub.sidebar_nav.targets)
    page.start_page._pick("Network"); pump()
    assert cfg()["startup_page"] == "Network"
    # ---- start minimized / tray / update check / Discord (checkbox clicks)
    check(page.minimized)._click(None); assert cfg()["start_minimized"] is False
    check(page.tray)._click(None); pump()
    assert cfg()["tray_on_close"] is False
    before = bool(page.auto_check.get())
    check(page.auto_check)._click(None); assert cfg()["check_updates"] is (not before)
    if before is False:
        check(page.auto_check)._click(None)
    check(page.auto_check)._click(None) if cfg()["check_updates"] else None
    assert cfg()["check_updates"] is False
    before = bool(page.discord_on.get())
    check(page.discord_on)._click(None); assert cfg()["discord_status"] is (not before)
    if not page.discord_on.get():
        check(page.discord_on)._click(None)
    assert cfg()["discord_status"] is True
    # ---- buttons that open pages
    button("PawnIO download page ↗").command(); assert any("pawnio" in u.lower() or "PawnIO" in u for u in opened), opened
    button("Download LibreHardwareMonitor").command(); assert any("LibreHardwareMonitor" in u for u in opened)
    button("Open on GitHub").command(); assert any(u.startswith("https://github.com/") for u in opened)
    n = len(opened)
    button("Report a problem").command(); pump()
    assert len(opened) == n + 1 and "/issues/new" in opened[-1] and hub.clipboard_get()
    if "Temperatures" in hub.rt_tabs:
        button("Open Temperatures").command(); pump(); assert hub.cur_tab == hub.rt_tabs["Temperatures"]
    hub.show_tab(hub.rt_tabs["Settings"]); pump()
    button("About RETWEAKS").command(); pump(); assert hub.cur_tab == hub.rt_tabs["About"]
    hub.destroy()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "linux_shim.py"), os.path.abspath(__file__),
                        "--verify", TMP], capture_output=True, text=True, timeout=180)
    assert "VERIFIED" in r.stdout, r.stdout[-1500:] + r.stderr[-3000:]
    print("PASS: Settings controls — theme, accent, header, banner, background accent, refresh interval (service + "
          "text), °C/°F (Dashboard redraw, selector sync, saved), Open on (all pages), start minimized, tray, update "
          "check, Discord, PawnIO/LHM/GitHub/Report/Temperatures/About buttons; every choice survives a restart.")
else:
    pump()
    s = cfg()
    assert hub.theme_name == "Ocean", hub.theme_name
    assert s["custom_accent"] == "#3b82f6" and s["header_style"] == "wordmark"
    assert not hub.sidebar_nav.header_chip.winfo_ismapped()
    assert dash.banner.style == "wave" and hub.animation == "Fireflies"
    assert dash.svc.interval() == 5.0 and "every 5 seconds" in dash.sub_label.cget("text")
    assert hub.cur_tab == hub.rt_tabs["Network"], hub.cur_tab                    # Open on
    hub.show_tab(hub.rt_tabs["Settings"]); pump()
    assert page.unit.get() == "°F" and page.start_page.get() == "Network"
    assert page.minimized.get() is False and page.tray.get() is False and page.auto_check.get() is False
    assert page.discord_on.get() is True
    dash.on_telemetry(SAMPLE, feed_banner=False); pump()
    assert "122 °F" in texts(dash.grid)
    print("VERIFIED")
    hub.destroy()
