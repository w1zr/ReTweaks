"""Browser page check (the base app's v1.5 browser as its own program, RETWEAKS branding) with a fake browser
program instead of ai/EmbeddedBrowser.exe (no WebView2 needed).
Linux:   xvfb-run -a python3.12 tools/linux_shim.py checks/check_rt_browser.py
Windows: py checks/check_rt_browser.py
Exercises: the browser starts only when the page is opened, inside this page's window (window id passed),
handshake with theme colours + RETWEAKS data (search engines incl. a custom one, the user's engine,
bookmarks, history, download settings); first-run merge of RETWEAKS bookmarks + the base app shortcuts (once);
visibility on page switch; theme changes; bookmarks / visits / titles / clear history / settings reported by
the browser are saved to browser.json and config.json (bad values refused); a browser crash never closes
RETWEAKS (restarts once by itself, then offers Restart browser); a browser that can't start shows an honest
message + Restart + WebView2 link; close on Quit; nothing loads pythonnet/WebView2 into RETWEAKS itself."""
import json
import os
import sys
import tempfile
import time
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="rt-browser-check-")
os.environ["APPDATA"] = os.path.join(TMP, "roaming")
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "local")
os.environ["USERPROFILE"] = TMP
LOG = os.path.join(TMP, "fake-browser.log")

FAKE = os.path.join(TMP, "fake_browser.py")
with open(FAKE, "w", encoding="utf-8") as f:
    f.write(r'''
import json, sys
log = open(sys.argv[1], "a", encoding="utf-8")
def out(d):
    sys.stdout.write(json.dumps(d) + "\n"); sys.stdout.flush()
first = json.loads(sys.stdin.readline())
log.write(json.dumps({"argv": sys.argv[2:], "first": first}) + "\n"); log.flush()
if first.get("data", {}).get("engine") == "FAIL":
    out({"type": "error", "message": "Browser unavailable. Install Microsoft Edge WebView2 Runtime and retry."}); sys.exit(1)
out({"type": "ready", "embedded": True}); out({"type": "loaded", "message": "RETWEAKS Browser ready."})
for raw in sys.stdin:
    d = json.loads(raw)
    log.write(json.dumps(d) + "\n"); log.flush()
    op = d.get("op")
    if op == "close":
        sys.exit(0)
    if op == "crash":
        sys.exit(3)
    if op == "emit":
        out(d["event"])
''')
os.environ["RETWEAKS_BROWSER_CMD"] = f"{sys.executable}|{FAKE}|{LOG}"

import retweaks as app                                    # noqa: E402  (widgets + colours)
from core import browser_data as bd                       # noqa: E402
from rt_pages import browser as bp                        # noqa: E402


class Hub(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = {"browser_search_engine": "DuckDuckGo"}
        self.saved = 0
        self.actions = []

    def save_settings(self):
        self.saved += 1
        return True

    def log_action(self, *a):
        self.actions.append(a)


def pump(sec=0.4):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        hub.update()
        time.sleep(0.01)


def wait(cond, sec=8, what="condition"):
    end = time.monotonic() + sec
    while time.monotonic() < end:
        hub.update()
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError("timed out waiting for " + what)


def log():
    try:
        return [json.loads(l) for l in open(LOG, encoding="utf-8") if l.strip()]
    except OSError:
        return []


def ops():
    return [e.get("op") for e in log() if "op" in e]


# existing data: one RETWEAKS bookmark + a base app v1.5 shortcut copied in by the base app migration
data0 = bd.BrowserData()
data0.add_bookmark("Old bookmark", "https://old.example/")
data0.add_history("Earlier page", "https://earlier.example/")
prof = os.path.join(os.environ["LOCALAPPDATA"], "RETWEAKS", "Browser")
os.makedirs(prof, exist_ok=True)
with open(os.path.join(prof, "shortcuts.json"), "w", encoding="utf-8") as f:
    json.dump([{"name": "the base app tile", "url": "https://tile.example/"}, {"name": "bad", "url": "javascript:x"}], f)

hub = Hub()
hub.geometry("1400x860")
g = vars(app)
tab = tk.Frame(hub, bg=g["BG"])
tab.pack(fill="both", expand=True, padx=(26, 12), pady=(20, 12))   # how the app packs a page
errors = []
hub.report_callback_exception = lambda *a: errors.append(a)

# 1) built, nothing started yet (the browser starts the first time the page is opened)
page = bp.BrowserPage(hub, tab, g)
pump(0.2)
assert page.bridge is None and not log()
assert hub.settings.get("browser_v15_merged") is True
assert [b["url"] for b in page.data.bookmarks] == ["https://old.example/", "https://tile.example/"]
page._migrate_once()                                         # repeat-safe
assert len(page.data.bookmarks) == 2

# 2) opened: full size, its own program in this page's window, handshake with theme + RETWEAKS data
page.on_shown()
wait(lambda: log() and not page.overlay_shown(), what="browser ready")
assert tab.pack_info()["padx"] in (0, "0")
first = log()[0]
assert first["argv"] == [str(page.frame.winfo_id())]
assert first["first"]["op"] == "theme" and first["first"]["BG"] == g["BG"]
d = first["first"]["data"]
assert d["engine"] == "DuckDuckGo" and [e["name"] for e in d["engines"]] == list(bd.SEARCH_ENGINES)
assert [b["url"] for b in d["bookmarks"]] == ["https://old.example/", "https://tile.example/"]
assert d["history"][-1]["url"] == "https://earlier.example/" and d["downloadPrompt"] is False
assert "clr" not in sys.modules and "core.browser_engine" not in sys.modules     # no in-process engine

# 3) page switches -> visibility; theme change -> theme
page.on_hidden(); page.on_shown(); pump(0.5)
vis = [e for e in log() if e.get("op") == "visibility"]
assert vis and vis[-1]["visible"] is True and any(e["visible"] is False for e in vis), vis
assert any(e.get("op") == "data" for e in log())
old_bg = g["BG"]
g["BG"] = "#123456"
pump(0.5)
assert any(e.get("op") == "theme" and e.get("BG") == "#123456" for e in log())
g["BG"] = old_bg
pump(0.3)

# 4) what the browser reports is saved by RETWEAKS
def emit(event):
    page.bridge.send({"op": "emit", "event": event})

emit({"type": "bookmarks", "items": [{"name": "Tile", "url": "https://tile.example/"},
                                     {"name": "New", "url": "https://new.example/"}]})
emit({"type": "visit", "url": "https://visited.example/a", "title": ""})
emit({"type": "title", "url": "https://visited.example/a", "title": "Visited page"})
emit({"type": "setting", "key": "browser_search_engine", "value": "Bing"})
emit({"type": "setting", "key": "browser_search_engine", "value": "Evil"})              # refused
emit({"type": "setting", "key": "browser_custom_search", "value": "http://insecure/?q={q}"})   # refused
emit({"type": "setting", "key": "browser_ask_download", "value": True})
emit({"type": "setting", "key": "theme", "value": "x"})                                 # not a browser key
wait(lambda: hub.settings.get("browser_ask_download") is True, what="settings saved")
saved = bd.BrowserData()
assert [b["url"] for b in saved.bookmarks] == ["https://tile.example/", "https://new.example/"]
assert [b["title"] for b in saved.bookmarks] == ["Tile", "New"]
assert saved.history[-1]["url"] == "https://visited.example/a" and saved.history[-1]["title"] == "Visited page"
assert hub.settings["browser_search_engine"] == "Bing" and "browser_custom_search" not in hub.settings
assert "theme" not in hub.settings and hub.saved >= 2
emit({"type": "setting", "key": "browser_custom_search", "value": "https://kagi.com/search?q={q}"})
emit({"type": "setting", "key": "browser_search_engine", "value": "Custom"})
emit({"type": "clear-history"})
wait(lambda: hub.settings.get("browser_search_engine") == "Custom", what="custom engine")
assert bd.BrowserData().history == []
assert page.settings_payload()["engines"][-1] == {"name": "Custom", "template": "https://kagi.com/search?q={q}"}

# 5) the browser crashes: RETWEAKS stays up, restarts it once by itself...
starts = len([e for e in log() if "argv" in e])
page.bridge.send({"op": "crash"})
wait(lambda: len([e for e in log() if "argv" in e]) == starts + 1 and not page.overlay_shown(), what="auto restart")
assert page.bridge.running() and hub.winfo_exists()
# ...a second crash soon after asks instead (Restart browser)
page.bridge.send({"op": "crash"})
wait(lambda: page.overlay_shown() and page.o_title.cget("text") == "The browser stopped", what="stopped state")
assert page.b_restart.winfo_manager()
page.b_restart.invoke() if hasattr(page.b_restart, "invoke") else page.restart()
wait(lambda: page.bridge.running() and not page.overlay_shown(), what="manual restart")

# 6) close (Quit / app close): the browser program is told to close and exits
proc = page.bridge.process
page.close()
wait(lambda: proc.poll() is not None, what="browser exit")
assert "close" in ops() and page.closed
tab.destroy()

# 7) a browser that can't start: honest message, Restart browser + WebView2 link, no crash
hub.settings["browser_search_engine"] = "Google"
tab2 = tk.Frame(hub, bg=g["BG"]); tab2.pack(fill="both", expand=True)
page2 = bp.BrowserPage(hub, tab2, g)
page2.settings_payload = lambda: {"engine": "FAIL", "engines": []}
page2.payload = page2.settings_payload
page2.bridge = None
page2.on_shown()
wait(lambda: page2.o_title.cget("text") == "The browser can't start", what="error state")
assert page2.b_restart.winfo_manager() and page2.b_runtime.winfo_manager()
assert any(a[1] == "Start the browser" and a[2] == "Failed" for a in hub.actions)
page2.close()
tab2.destroy()

# 8) program missing from the build
os.environ["RETWEAKS_BROWSER_CMD"] = os.path.join(TMP, "no-such-program")
tab3 = tk.Frame(hub, bg=g["BG"]); tab3.pack(fill="both", expand=True)
page3 = bp.BrowserPage(hub, tab3, g)
page3.on_shown()
wait(lambda: page3.o_title.cget("text") == "The browser can't start", what="start failure")
page3.close()

assert not errors, errors
hub.destroy()
print("PASS: browser page (own program, fake): starts on first open inside the page, theme + RETWEAKS data "
      "handshake, first-run bookmark merge (once), visibility, theme changes, bookmarks/history/settings saved "
      "(bad values refused), crash -> auto restart -> Restart browser, start failure message, close on Quit, "
      "no in-process engine.")
