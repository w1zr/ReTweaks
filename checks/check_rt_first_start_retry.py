"""v2.1.2 (owner reports): on the first launch on a new PC the Browser and AI assistant failed and waited for a
manual retry; the selected sidebar row lost its icon; Startup apps had no app icons.
Checks: WebView2 registry detection, automatic start retries (Browser, AI), the AI tab in WebView2 auto-setup,
sidebar icons survive their Tk image being deleted, Startup apps row pictures (tick + icon).
Windows: py checks/check_rt_first_start_retry.py  (throwaway settings; no real settings are changed)."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
T = tempfile.mkdtemp(prefix="rt_retry_")
os.environ["APPDATA"] = T; os.environ["LOCALAPPDATA"] = T
import retweaks as app, hubplus
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
import rt_i18n
rt_i18n.install(vars(app), code="en")
from core import dependencies as deps
import rt_dependencies

# WebView2: Microsoft's registry value counts even when the folder check finds nothing
v = deps.webview2_registry_version()
print("WebView2 registry version:", v or "(none)")
if v:
    real = deps.Path
    class _NoFolder(type(real())):
        def is_dir(self): return False
    deps.Path = _NoFolder
    try:
        assert deps.available("webview2"), "registry-installed WebView2 not detected"
    finally:
        deps.Path = real

hub = app.Hub(show_intro=False, enable_ai=False)
import rt_shell
rt_shell.Shell(hub, vars(app), [])
hub.geometry("1400x900+0+0"); hub.deiconify()
pump = lambda s: [hub.update() or time.sleep(0.01) for _ in range(int(s / 0.01))]
pump(1.0)

# AI: a start error retries twice on its own, then shows the message; a key error never retries
retries = []
hub.retry_ai = lambda: retries.append(time.monotonic())
hub.handle_ai_event({"type": "error", "message": "WebView2 failed"})
assert "first start" in hub.ai_status.cget("text"), hub.ai_status.cget("text")
pump(3.3); assert len(retries) == 1, retries
hub.handle_ai_event({"type": "error", "message": "WebView2 failed"})
pump(8.3); assert len(retries) == 2, retries
hub.handle_ai_event({"type": "error", "message": "WebView2 failed"})
pump(0.3); assert hub.ai_status.cget("text") == "WebView2 failed" and len(retries) == 2
hub.handle_ai_event({"type": "ready"}) if False else None
hub.ai_start_retries = 0
from rt_pages import ai_key
key_msg = next((m for m in ("API key not valid", "API_KEY_INVALID", "key expired") if ai_key.is_key_error(m)), None)
if key_msg:
    hub.handle_ai_event({"type": "error", "message": key_msg}); pump(3.5)
    assert len(retries) == 2, "a key error must not retry"

# AI tab is part of the WebView2 auto-setup
called = []
rt_dependencies.deps.enabled = lambda h: True
rt_dependencies.deps.available = lambda k: k != "webview2"
rt_dependencies.ensure = lambda h, k, done=None: called.append((k, done))
rt_dependencies.on_page(hub, 20)
assert called and called[0][0] == "webview2"
hub.enable_ai = True
called[0][1](); assert len(retries) == 3, "AI should reload after WebView2 setup"
hub.enable_ai = False

# Browser: a start error retries twice on its own before showing the error
page = hub.rt_pages["Browser"]
restarts = []
page.restart = lambda: restarts.append(1)
page.handle({"type": "error", "message": "boom"})
assert page.failed and not restarts
pump(3.3); assert restarts == [1]
page.handle({"type": "stopped"}); pump(0.2); assert restarts == [1], "stale stop must not restart again"
page.handle({"type": "error", "message": "boom"}); pump(8.3); assert restarts == [1, 1]
page.handle({"type": "error", "message": "boom"}); pump(0.5); assert restarts == [1, 1]
page.handle({"type": "ready"}); assert page.start_retries == 0
page.handle({"type": "error", "message": "x", "reason": "missing_component"}); pump(0.3); assert restarts == [1, 1]

# Sidebar: a deleted icon image is made again instead of drawing nothing
nav = hub.sidebar_nav
b = nav.buttons["Network"]
b._set(active=True); pump(0.2)
img = b._img
hub.tk.call("image", "delete", str(img))
b.draw(); pump(0.2)
items = [b.itemcget(i, "image") for i in b.find_all() if b.type(i) == "image"]
assert items and items[0] in hub.tk.call("image", "names"), "sidebar icon not recreated"

# Startup apps: tick + icon picture
from rt_pages import startup
from PIL import Image
pic = startup.row_picture(Image.new("RGBA", (16, 16), (255, 0, 0, 255)), True, "#ffffff")
assert pic.size == startup.ROW_PIC and pic.getpixel((30, 9))[0] == 255 and pic.getpixel((5, 10))[3] > 0
assert startup.row_picture(None, False, "#ffffff").getextrema()[3] == (0, 0)
from file_icons import exe_from_command, app_icon
assert exe_from_command('"C:\\A B\\x.exe" --min') == "C:\\A B\\x.exe"
assert exe_from_command("%windir%\\system32\\notepad.exe /a").lower().endswith("system32\\notepad.exe")
assert app_icon("%windir%\\system32\\notepad.exe") is not None
print("PASS: WebView2 registry detection, Browser/AI start retries, AI in WebView2 setup, sidebar icon self-repair, "
      "Startup apps icons.")
os._exit(0)
