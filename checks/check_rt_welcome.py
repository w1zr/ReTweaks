"""First-run welcome tour + automatic updates.
- before the window: the base app's separate shortcut question is marked as asked (the tour asks it)
- shown once the window is visible (not while withdrawn = --minimized start), never again after it ends
- every question applies its choice to config.json only on Next; Back never applies; Skip ends the tour
- desktop shortcut via a fake creator (packaged) and honest 'only RETWEAKS.exe' text from source
- Settings: replay button + automatic updates checkbox
- auto_update: check -> download (SHA-256 checked by updater) -> ask -> install + quit (all fakes)"""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APPDATA = tempfile.mkdtemp(); os.environ["APPDATA"] = APPDATA; os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
os.environ["USERPROFILE"] = tempfile.mkdtemp()
import retweaks as app, hubplus, rt_shell, rt_welcome, rt_autoupdate
from rt_pages import settings_store
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
cfg = lambda: json.load(open(os.path.join(APPDATA, "RETWEAKS", "config.json")))
first_run = lambda: json.load(open(os.path.join(APPDATA, "RETWEAKS", "first_run.json")))

# --- before the window: shortcut question handed to the tour
rt_welcome.prepare()
assert first_run()["desktop_shortcut_prompted"] is True

hub = app.Hub(show_intro=False, enable_ai=False)
hub.settings["check_updates"] = False
shell = rt_shell.Shell(hub, vars(app), [])
pump = lambda n=10: [hub.update() or time.sleep(0.02) for _ in range(n)]
assert rt_welcome.needed(hub.settings)

# --- minimized start: waits until the window is opened
hub.withdraw(); pump()
rt_welcome.maybe_show(hub, interval=30); pump(20)
assert getattr(hub, "_welcome", None) is None
hub.deiconify(); pump(20)
w = hub._welcome
assert w is not None and not w.closed and w.root.winfo_ismapped()
keys = [s["key"] for s in w.steps]
assert keys == ["welcome", "how", "unit", "language", "update", "tray", "shortcut", "done"], keys

# packaged + fake shortcut creator
made = []
rt_welcome.IS_PACKAGED = lambda: True
rt_welcome.CREATE_SHORTCUT = lambda: made.append(1) or os.path.join(os.environ["USERPROFILE"], "Desktop", "RETWEAKS.lnk")
started = []
rt_autoupdate.start = lambda hub, delay=0: started.append(1)

w.next(); pump()                                     # welcome -> how
assert w.steps[w.i]["key"] == "how" and len(w.cards) == 4
w.next(); pump()                                     # how -> unit
assert w.steps[w.i]["key"] == "unit"
w.pick("unit", "F"); pump()
assert cfg().get("temp_unit", "C") == "C"            # nothing saved before Next
w.back(); pump(); assert w.steps[w.i]["key"] == "how"
assert cfg().get("temp_unit", "C") == "C"            # Back applied nothing
w.next(); pump(); w.pick("unit", "F"); w.next(); pump()
assert cfg()["temp_unit"] == "F" and settings_store.temp_unit(hub) == "F"
assert w.steps[w.i]["key"] == "language" and len(w.cards) == 5
w.pick("language", "es"); w.next(); pump()
assert cfg()["language"] == "es"
assert w.steps[w.i]["key"] == "update" and w.values["auto_update"] is True      # preselected On
w.next(); pump()
assert cfg()["auto_update"] is True and cfg()["check_updates"] is True and started
assert hub.rt_pages["Settings"].auto_update.get() is True                     # Settings checkbox in sync
w.pick("tray", False); w.next(); pump()
assert cfg()["tray_on_close"] is False and hub.rt_pages["Settings"].tray.get() is False
assert w.steps[w.i]["key"] == "shortcut"
w.pick("shortcut", True); w.next(); pump(20)
assert made and w.steps[w.i]["key"] == "done"
assert first_run()["desktop_shortcut_created"] is True
# the tour switched the UI to Spanish above: compare in the language shown (rt_i18n.tr) by English row name
import rt_i18n
rows = {rt_i18n.english(a.cget("text")): b.cget("text") for _, a, b in w.summary_rows}
on, off = (rt_i18n.tr(x) for x in ("On", "Off"))
assert rows["Temperature"] == "°F" and rows["Automatic updates"] in ("On", on) and rows["Tray"] in ("Off", off), rows
assert rows["Desktop shortcut"] in ("Added to your desktop", rt_i18n.tr("Added to your desktop")), rows
# screenshots of every step are taken by the screenshot script; here: Done -> Open Dashboard
w.next(); pump()
from core.version import __version__
assert w.closed and cfg()[rt_welcome.MARK] == __version__
assert hub.cur_tab == hub.rt_tabs["Dashboard"]
assert not rt_welcome.needed(settings_store.load())  # next start: no tour

# --- second start doesn't show it
hub._welcome = None
rt_welcome.maybe_show(hub, interval=30); pump(20)
assert hub._welcome is None

# --- replay from Settings; Skip keeps everything already applied
hub.rt_pages["Settings"].show_welcome(); pump()
w2 = hub._welcome
assert w2 is not None and not w2.closed
w2.skip(); pump()
assert w2.closed and cfg()["temp_unit"] == "F"

# --- from source: shortcut can't be made, said honestly, nothing created
rt_welcome.IS_PACKAGED = lambda: False
w3 = rt_welcome.show(hub, replay=True)
w3.i = 6; w3.steps = w3._steps(); w3.render(); pump()
yes_card = [c for c in w3.cards if c.value is True][0]
assert yes_card.disabled and "RETWEAKS.exe" in w3.body.cget("text")
w3.close()

# --- keyboard: Enter/Right next, Left back, Esc skip
w4 = rt_welcome.show(hub, replay=True); pump()
w4.root.focus_force(); pump()
w4.root.event_generate("<Return>"); pump(); assert w4.i == 1
w4.root.event_generate("<Left>"); pump(); assert w4.i == 0
w4.root.event_generate("<Escape>"); pump(); assert w4.closed

# --- automatic updates: check -> verified download -> ask -> install + quit (fakes)
import importlib
importlib.reload(rt_autoupdate)
from core import updater
calls = []
hub.settings["auto_update"] = True
hub._autoupdate_started = False
updater.check_for_update = lambda: {"available": True, "version": "9.9", "exe_url": "https://github.com/x/RETWEAKS.exe",
                                    "sha_url": "https://github.com/x/RETWEAKS.exe.sha256", "notes": "", "page": ""}
updater.can_self_update = lambda: True
updater.download_update = lambda info, progress=None: (calls.append("download") or (True, "C:/tmp/new.exe"))
updater.install_and_restart = lambda p: (calls.append(("install", p)) or (True, "ok"))
rt_autoupdate.messagebox.askyesno = lambda *a, **k: calls.append("ask") or True
quit_calls = []
rt_shell.quit_app = lambda h: quit_calls.append(h)
assert rt_autoupdate.start(hub, delay=10)
assert not rt_autoupdate.start(hub, delay=10)          # only once
end = time.time() + 5
while not quit_calls and time.time() < end:
    pump(5)
assert calls == ["download", "ask", ("install", "C:/tmp/new.exe")] and quit_calls, calls
# off -> nothing starts
hub._autoupdate_started = False; hub.settings["auto_update"] = False
assert not rt_autoupdate.start(hub, delay=10)
print("PASS: welcome tour — shortcut prompt handed over, waits for a visible window, 8 steps, choices saved only on "
      "Next (unit/language/updates/tray/shortcut), Back/Skip/keys, Settings in sync + replay, shown once; "
      "auto updates check/download/ask/install once, off does nothing.")
hub.destroy()
