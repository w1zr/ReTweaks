"""Translations (rt_i18n) — Linux via tools/linux_shim.py, temporary APPDATA (the real config is never touched).

Checks: every language switches live and back; sample widgets on several pages show translated text while
cget() still returns English; Settings → Language card (first card, one click per language, names never
translated, heading contains "Language" in every language, switching to German and back to English using
only the card); search finds the language card by "language"/"idioma"/"langue"/"sprache"/"lingua" in every
UI language; the setting persists across a restart; values still work (theme in German, temperature unit
in French); no Tcl errors. Optional argv[1]: folder for German screenshots of Dashboard and Settings."""
import json
import os
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="rt_i18n_")
os.environ["APPDATA"] = TMP
os.environ["LOCALAPPDATA"] = TMP
os.makedirs(os.path.join(TMP, "RETWEAKS"), exist_ok=True)
json.dump({"theme": "Midnight", "first_run_done": True}, open(os.path.join(TMP, "RETWEAKS", "config.json"), "w"))

import tkinter as tk
from unittest.mock import Mock

import retweaks as app
import hubplus
import automation
import rt_shell
import rt_i18n

SHOTS = sys.argv[1] if len(sys.argv) > 1 else None
tcl_errors = []


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
hubplus.write_json = lambda *a: None
hubplus.install(vars(app))
assert rt_i18n.install(vars(app)) == "en", "default language must be English"

hub = app.Hub(show_intro=False, enable_ai=False)
hub.report_callback_exception = lambda *a: tcl_errors.append(a)
hub.settings["check_updates"] = False
rt_shell.Shell(hub, vars(app), [])
hub.geometry("1500x940+0+0")


def pump(n=8):
    for _ in range(n):
        hub.update()
        time.sleep(0.02)


def disk():
    return json.load(open(os.path.join(TMP, "RETWEAKS", "config.json")))


def shown(w):
    """The text Tk really displays (bypasses the cget hook, which returns the English original)."""
    return str(w.tk.call(w._w, "cget", "-text"))


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def labels_with(english, root=hub):
    return [w for w in walk(root) if isinstance(w, tk.Label) and w.__dict__.get("_i18n_en", {}).get("text") == english]


pump(20)
side = hub.sidebar_nav
settings = hub.rt_pages["Settings"]
assert settings is not None, "Settings page failed to load"
card = settings.language_card

# ---- the language card is the first card on Settings, shows each language in its own name
heads = labels_with("Language")
assert heads, "Language card heading not found"
head = heads[0]
order = [w.__dict__["_i18n_en"]["text"] for w in walk(settings.theme.winfo_toplevel())
         if isinstance(w, tk.Label) and w.__dict__.get("_i18n_en", {}).get("text") in ("Language", "Appearance")]
assert order[:2] == ["Language", "Appearance"], order
assert [b.label for b in card.buttons.values()] == list(rt_i18n.LANGUAGES.values())
assert card.buttons["en"].kind == "primary" and card.buttons["de"].kind == "ghost"


def click(button):
    """Press and release on the button, like a mouse click (the card is the only way languages change here)."""
    button._press(None)
    ev = tk.Event()
    ev.x, ev.y = 5, 5
    button._release(ev)
    pump(4)
    end = time.time() + 30
    while rt_i18n.busy() and time.time() < end:     # v2.0.9: hidden pages switch in steps
        pump(2)


# ---- every language: switch live via the card, check pages, heading keeps "Language", names untranslated
samples = {  # (page key in rt_pages, English label text that the page shows)
    "Settings": "Appearance",
    "About": "Good to know",
}
for code in ["es", "fr", "de", "pt-BR"]:
    click(card.buttons[code])
    assert rt_i18n.language() == code, code
    assert disk().get("language") == code, "language not saved"
    assert card.buttons[code].kind == "primary", code
    assert all(card.buttons[c].kind == "ghost" for c in card.buttons if c != code)
    h = shown(head)
    assert "Language" in h and h != "Language", (code, h)
    for b in card.buttons.values():
        drawn = [str(b.tk.call(b._w, "itemcget", i, "-text")) for i in b.find_all() if b.type(i) == "text"]
        assert drawn == [b.label] and b.label in rt_i18n.LANGUAGES.values(), (code, drawn)
    for page, en in samples.items():
        ws = labels_with(en)
        assert ws, (page, en)
        assert shown(ws[0]) == rt_i18n.tr(en) != en, (code, page, shown(ws[0]))
        assert ws[0].cget("text") == en, "cget must return English"
    # sidebar entries (canvas text) are translated too
    nav_txt = [t for it in side.buttons.values() if hasattr(it, "find_all")
               for t in [str(it.tk.call(it._w, "itemcget", i, "-text")) for i in it.find_all() if it.type(i) == "text"] if t]
    # since 2.0.4 the sidebar shows group names (Temperatures is a section inside Hardware & cooling)
    for entry in ("Settings", "Hardware & cooling", "Tweaks & presets", "File Transfers", "Windows backgrounds"):
        assert rt_i18n.tr(entry) != entry and rt_i18n.tr(entry) in nav_txt, (code, entry, nav_txt[:8])
    # global search finds the language card with any of the words, in this UI language
    gs = getattr(hub, "global_search", None)
    for word in ("language", "idioma", "langue", "sprache", "lingua"):
        hits = side.matches(word)
        assert "Settings" in hits, (code, word, hits)
        if gs is not None:
            assert any(t == "Settings" for t, _d, _a in gs.search(word)), (code, word)
    # searching by the page name shown in this language finds the page
    word = rt_i18n.tr("Hardware & cooling").split()[0].lower()
    assert "Hardware & cooling" in side.matches(word), (code, word, side.matches(word))
    print(code, "ok:", h)

# ---- values keep working in another language: theme in German, temperature unit in French
click(card.buttons["de"])
import appearance as ap
names = ap.theme_names()
other = next(n for n in names if n != hub.theme_name)
settings.theme.set(other)
settings.theme.command(other)
pump(4)
assert hub.theme_name == other, (hub.theme_name, other)
assert disk().get("theme") in (other, hub.settings.get("theme")), disk().get("theme")
assert rt_i18n.language() == "de"
assert shown(labels_with("Appearance")[0]) == rt_i18n.tr("Appearance") != "Appearance", "theme change lost German"
click(card.buttons["fr"])
settings.set_unit("°F")
pump(2)
assert hub.settings.get("temp_unit") == "F" and disk().get("temp_unit") == "F", hub.settings.get("temp_unit")
settings.set_unit("°C")
assert hub.settings.get("temp_unit") == "C"

# ---- German screenshots (Dashboard, Settings) for a visual check
click(card.buttons["de"])
if SHOTS:
    try:
        from PIL import ImageGrab
        os.makedirs(SHOTS, exist_ok=True)
        hub.deiconify()
        for name in ("Dashboard", "Settings"):
            if name in side.targets:
                side.open(name, side.targets[name])
                pump(25)
                ImageGrab.grab((0, 0, 1500, 940)).save(os.path.join(SHOTS, f"de_{name.lower()}.png"))
        print("screenshots in", SHOTS)
    except Exception as e:
        print("screenshots skipped:", e)

# ---- back to English using only the card: every sample shows English again
click(card.buttons["en"])
assert rt_i18n.language() == "en" and disk().get("language") == "en"
assert shown(head) == "Language"
for page, en in samples.items():
    assert shown(labels_with(en)[0]) == en, (page, en)
assert rt_i18n.tr("Appearance") == "Appearance"

# ---- persists across restart: the saved language is loaded by install() with no code given
click(card.buttons["pt-BR"])
assert disk()["language"] == "pt-BR"
rt_i18n.load("en")
assert rt_i18n.install(vars(app)) == "pt-BR", "saved language not restored"
assert rt_i18n.tr("Settings") != "Settings"
rt_i18n.set_language(hub, "en")
pump(2)

# ---- catalogs: placeholders kept, no empty values
for code in ["es", "fr", "de", "pt-BR"]:
    cat = json.load(open(os.path.join(os.path.dirname(rt_i18n.__file__), "i18n", code + ".json"), encoding="utf-8"))
    import re
    for en, t in list(cat["strings"].items()) + list(cat["templates"].items()):
        assert t, (code, en)
        assert set(re.findall(r"\{\d+\}", t)) <= set(re.findall(r"\{\d+\}", en)), (code, en, t)

assert not tcl_errors, tcl_errors
hub.destroy()
print("check_rt_i18n: all passed")
