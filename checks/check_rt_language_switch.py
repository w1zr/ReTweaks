"""v2.0.9 (owner report on Windows: switching language made the sidebar icons vanish and the text stayed in the old
language): the screen switches at once, hidden pages follow in steps while the window stays usable, and the
sidebar keeps its icons."""
import os, tempfile, time
T = tempfile.mkdtemp(prefix="rt_lang_")
os.environ["APPDATA"] = T; os.environ["LOCALAPPDATA"] = T
import retweaks as app, hubplus
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
import rt_i18n
rt_i18n.install(vars(app), code="en")
hub = app.Hub(show_intro=False, enable_ai=False)
import rt_shell
rt_shell.Shell(hub, vars(app), [])
hub.geometry("1500x940+0+0"); hub.deiconify()
pump = lambda s: [hub.update() or time.sleep(0.01) for _ in range(int(s / 0.01))]
pump(1.5)
hub.show_tab(hub.rt_tabs["Settings"]); hub.rt_pages["Settings"].on_shown(); pump(0.5)
nav = hub.sidebar_nav
icons_before = dict(nav._icons)
assert icons_before and all(v is not None for v in icons_before.values())
t = time.perf_counter()
rt_i18n.set_language(hub, "de")
took = time.perf_counter() - t
assert rt_i18n.busy(), "hidden pages should still be switching in the background"
assert nav._icons == icons_before, "sidebar icons were cleared"
heading = next(w for w in rt_i18n._walk(hub) if w.__dict__.get("_i18n_en", {}).get("text") == "Language")
assert heading.cget("text") == "Language" and str(heading.tk.call(heading._w, "cget", "-text")).startswith("Sprache")
end = time.time() + 30
while rt_i18n.busy() and time.time() < end:
    hub.update()
assert not rt_i18n.busy()
hidden = [w for w in rt_i18n._walk(hub) if w.__dict__.get("_i18n_en", {}).get("text") == "Ready to check"]
assert hidden, "no 'Ready to check' widget found, so hidden-page switching was not tested"
for w in hidden:
    assert "Bereit" in str(w.tk.call(w._w, "cget", "-text")), w.tk.call(w._w, "cget", "-text")
# a second switch while one is running takes over cleanly
rt_i18n.set_language(hub, "es"); rt_i18n.set_language(hub, "en")
while rt_i18n.busy():
    hub.update()
assert str(heading.tk.call(heading._w, "cget", "-text")) == "Language"
print(f"PASS: language switch — screen switched in {took:.2f} s, hidden pages followed, sidebar icons kept.")
os._exit(0)
