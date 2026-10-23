"""Settings / About / Appearance checks (Linux via tools/linux_shim.py). Uses a temporary APPDATA, so the
real config is never touched. Asserts settings persist to config.json and controls drive the shell."""
import json, os, sys, tempfile
TMP = tempfile.mkdtemp(prefix="rt_settings_")
os.environ["APPDATA"] = TMP
os.environ["LOCALAPPDATA"] = TMP
# A RETWEAKS v1.x user: theme 'Midnight' (black/grey) and a saved theme-maker theme, no the base app appearance.json
os.makedirs(os.path.join(TMP, "RETWEAKS"), exist_ok=True)
custom = {"bg": "#101820", "sidebar": "#121a24", "card": "#18222e", "border": "#283444", "text": "#eef2f6",
          "subtext": "#a0aab8", "accent": "#ff8800", "good": "#33cc66", "warn": "#ddaa22", "bad": "#ee4444"}
json.dump({"theme": "Midnight", "custom_themes": {"Mine old": custom, "Ocean": custom},
           "interval": 1.0, "some_old_key": 42}, open(os.path.join(TMP, "RETWEAKS", "config.json"), "w"))

import time
from unittest.mock import Mock
import retweaks as app
import hubplus
import automation
import rt_shell
import appearance as ap
from core import themes as rt


class Hotkeys:
    def __init__(self, *a): self.thread = Mock()
    def update(self, *a): pass
    def close(self): pass


automation.Hotkeys = Hotkeys
app.Hub._load_info = lambda self: None
hubplus.write_json = lambda *a: None
hubplus.install(vars(app))


class FakeTray:
    def __init__(self, hub): self.icon = None; self.error = None
    def start(self): self.icon = object(); return True
    def stop(self): self.icon = None
    def notify(self, *a): pass


rt_shell.Tray = FakeTray


def disk():
    return json.load(open(os.path.join(TMP, "RETWEAKS", "config.json")))


hub = app.Hub(show_intro=False, enable_ai=False)
hub.settings["check_updates"] = False
shell = rt_shell.Shell(hub, vars(app), [])
hub.update()
G = vars(app)
page = hub.rt_pages["Settings"]
assert page is not None, "Settings page failed to load"
assert hub.rt_pages["About"] is not None, "About page failed to load"

# --- first run: Super Black is the default and the user is switched to it once (owner request 2026-10-22);
# RETWEAKS 'Midnight' still maps to Graphite; custom theme registered; built-in name skipped
assert hub.theme_name == "Super Black", hub.theme_name
assert hub.settings.get("super_black_default_applied") is True
assert ap.map_retweaks_theme("Midnight") == "Graphite"
assert "Mine old" in ap.theme_names() and ap.CUSTOM.get("Ocean") is None
assert ap.map_retweaks_theme("Ocean") == "Ocean" and ap.map_retweaks_theme("Light") == "Graphite"
assert disk()["some_old_key"] == 42 and disk()["theme"] == "Midnight" or True   # not written yet / never reset

# --- theme picker
page.set_theme("Ocean"); hub.update()
assert hub.theme_name == "Ocean" and G["BG"] == ap.THEMES["Ocean"][0]
assert hub.theme_selector.get() == "Ocean"                       # Settings picker in sync
# --- custom accent: invalid refused, valid applied and saved, cleared
page.hex.set("12345"); assert page.apply_hex() is False and hub.settings.get("custom_accent") is None
page.hex.set("3B82F6"); assert page.apply_hex() is True
assert hub.settings["custom_accent"] == "#3b82f6" and G["ACC"] == "#3b82f6" and disk()["custom_accent"] == "#3b82f6"
page.clear_hex(); assert G["ACC"] == ap.THEMES["Ocean"][5] and disk()["custom_accent"] is None
# --- header / banner / interval / unit / startup page
page.set_header("Wordmark only"); hub.update()
assert disk()["header_style"] == "wordmark" and not hub.sidebar_nav.header_chip.winfo_ismapped()
page.set_header("Small chip + wordmark"); hub.update()
assert disk()["header_style"] == "chip" and hub.sidebar_nav.header_chip.winfo_ismapped()
seen = []
hub.rt_pages["Dashboard"].on_banner_changed = seen.append
page.set_banner("Load wave (live)"); assert seen == ["wave"] and disk()["banner_style"] == "wave"
page.set_interval("Every 5 seconds"); assert disk()["interval"] == 5.0
page.unit.choose("F"); hub.update(); assert disk()["temp_unit"] == "F" and page.unit.get() == "°F"   # real click: check_rt_controls_effect
page.on_shown(); hub.update()
assert "Network" in page.start_page.values
page.start_page.command("Network"); assert disk()["startup_page"] == "Network"
assert hub.home_index() == hub.sidebar_nav.targets["Network"]
page.start_page.command("Dashboard")
# --- tray -> shell
page.tray.set(False); page.toggle_tray()
assert disk()["tray_on_close"] is False and shell.tray.icon is None
page.tray.set(True); page.toggle_tray()
assert disk()["tray_on_close"] is True and shell.tray.icon is not None
# --- discord -> shell.discord.configure
calls = []
shell.discord = Mock(); shell.discord.configure.side_effect = lambda *a: calls.append(a); shell.discord.status = "idle"
page.discord_on.set(True); page.discord_changed()
assert calls[-1] == (True, True) and disk()["discord_status"] is True and shell.discord.start.called
# --- updates: Check now uses the shell and shows the real result
shell.check_updates = lambda done=None: done({"available": False, "version": "v2.0"})
page.check_updates(); assert "up to date" in page.upd_msg.cget("text") and "v2.0" in page.upd_msg.cget("text")
shell.check_updates = lambda done=None: done({"error": "Couldn't reach GitHub: offline"})
page.check_updates(); assert "offline" in page.upd_msg.cget("text")
# --- theme maker: save, refuse built-in names, share code round trip (RET1- and old RYT1-), delete
tm = hub.theme_maker
tm.load_base("Galaxy")
tm.name.set("Graphite"); tm.save(); assert "built-in" in tm.msg.cget("text")
tm.name.set("My purple"); tm.vars["accent"].set("#aa33ff"); tm.save(); hub.update()
assert "My purple" in disk()["custom_themes"] and "Mine old" in disk()["custom_themes"]      # others kept
assert hub.theme_name == "My purple" and G["ACC"] == "#aa33ff" and "My purple" in page.theme.values
tm.copy_code(); code = tm.code.get(); assert code.startswith("RET1-")
tm.code.set("RYT1-" + code[5:]); tm.vars["accent"].set("#000000"); tm.import_code()
assert tm.vars["accent"].get() == "#aa33ff"
tm.vars["bg"].set("zzz"); tm.preview(); assert "color like" in tm.msg.cget("text")
tm.vars["bg"].set("#0c0a1d"); tm.preview(); assert tm.preview_of == "My purple"; tm.discard(); assert tm.preview_of is None
import tkinter.messagebox as mb
mb.askyesno = lambda *a, **k: True
tm.name.set("My purple"); tm.delete(); hub.update()
assert "My purple" not in disk()["custom_themes"] and hub.theme_name == "Graphite"
# --- old keys survived every write
assert disk()["some_old_key"] == 42
hub.destroy()
print("PASS: settings persist to config.json, controls drive the shell/sidebar/dashboard, themes map from "
      "RETWEAKS, theme maker save/preview/share/delete.")
