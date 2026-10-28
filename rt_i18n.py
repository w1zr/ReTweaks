"""RETWEAKS translations (owner decision 2026-10-22: the whole app in Spanish, French, German and Portuguese
(Brazil), English stays the default). Translations are machine-made; corrections are welcome.

How it works, without touching every page: install() hooks the few places Tk receives display text —
widget `text` options (labels, buttons, check/radio buttons, label frames, ttk widgets), canvas text items
(which is how RETWEAKS' own rounded buttons, checkboxes, dropdowns, the sidebar and the top bar draw their
labels), menu labels, window titles, read-only Text inserts and message boxes — and translates English to the
chosen language on the way in. The English original is remembered on each widget/canvas item and is what the
code gets back from cget('text') / itemcget(..., 'text'), so program logic that compares labels keeps working,
and switching language later re-labels everything live. Values used as settings or IDs (theme names,
dropdown values, setting keys) are never changed: only what's drawn on screen is.

Catalogs: i18n/<code>.json = {"strings": {english: translation}, "templates": {"Loading {0}…": "..."}};
templates cover text built at run time (f-strings). Text with no translation stays English.
"""
import json
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox

LANGUAGES = {"en": "English", "es": "Español", "fr": "Français", "de": "Deutsch", "pt-BR": "Português (Brasil)"}
DEFAULT = "en"
NOTE = "Translations are machine-made; corrections welcome."

_lang = DEFAULT
_strings = {}          # english -> translation (current language)
_reverse = {}          # translation -> english, for every language (to recover English from shown text)
_templates = []        # (compiled regex, english template, translated template)
_cache = {}
_upper = {}            # "PROCESSOR" -> "PROZESSOR" (labels drawn in capitals from catalog text)
_prefixes = []         # catalog keys that are the start of a longer text ("Live · updated ")
_suffixes = []         # catalog keys that end a longer text (" (limit reached)")
_installed = False
_g = None              # retweaks module globals (text_w measuring)


def _folder():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "i18n")


def _load_catalog(code):
    try:
        with open(os.path.join(_folder(), code + ".json"), encoding="utf-8") as f:
            data = json.load(f)
        s = data.get("strings", {}) if isinstance(data, dict) else {}
        t = data.get("templates", {}) if isinstance(data, dict) else {}
        return ({k: v for k, v in s.items() if isinstance(k, str) and isinstance(v, str) and v},
                {k: v for k, v in t.items() if isinstance(k, str) and isinstance(v, str) and v})
    except (OSError, ValueError):
        return {}, {}


def _compile(tpl):
    """'Loading {0}…' -> regex with one group per placeholder (non-greedy, whole string)."""
    parts = re.split(r"(\{\d+\})", tpl.replace("{{", "\x00").replace("}}", "\x01"))
    rx, order = "", []
    for p in parts:
        m = re.fullmatch(r"\{(\d+)\}", p)
        if m:
            order.append(int(m.group(1)))
            rx += "(.+?)" if len(order) > 0 else "(.*)"
        else:
            rx += re.escape(p.replace("\x00", "{").replace("\x01", "}"))
    try:
        return re.compile(r"\A" + rx + r"\Z", re.S), order
    except re.error:
        return None, order


def _fill(tpl, args):
    out = tpl.replace("{{", "\x00").replace("}}", "\x01")
    for i, a in enumerate(args):
        out = out.replace("{%d}" % i, a)
    return out.replace("\x00", "{").replace("\x01", "}")


def _build_reverse():
    cats = [_load_catalog(code)[0] for code in LANGUAGES if code != "en"]
    english_keys = set().union(*[set(s) for s in cats]) if cats else set()
    rev = {}
    for s in cats:
        for en, tr_ in s.items():
            # never map text that is itself English (e.g. German "Info" for "About" vs the English "Info")
            if tr_ != en and tr_ not in english_keys:
                rev.setdefault(tr_, en)
    return rev


def load(code):
    """Make `code` the active language (no UI update; see set_language)."""
    global _lang, _strings, _templates, _cache, _reverse, _upper, _prefixes, _suffixes
    code = code if code in LANGUAGES else DEFAULT
    _lang = code
    _cache = {}
    if not _reverse:
        _reverse = _build_reverse()
    if code == "en":
        _strings, _templates, _upper, _prefixes, _suffixes = {}, [], {}, [], []
        return code
    s, t = _load_catalog(code)
    _strings = s
    _upper = {}
    for en, tr_ in s.items():
        if re.search(r"[a-z]", en) and en.upper() not in s:
            _upper.setdefault(en.upper(), tr_.upper())
    _prefixes = sorted((k for k in s if len(k) >= 4 and k[-1] in " :\n" and k.strip()), key=len, reverse=True)
    _suffixes = sorted((k for k in s if len(k) >= 4 and k[0] in " \n" and k.strip()), key=len, reverse=True)
    tpls = []
    for en, tr_ in t.items():
        rx, order = _compile(en)
        if rx is not None:
            tpls.append((rx, en, tr_, len(re.sub(r"\{\d+\}", "", en))))
    tpls.sort(key=lambda x: -x[3])           # most specific (longest literal text) first
    _templates = tpls
    return code


def language():
    return _lang


# ---------------------------------------------------------------- lookup
_EDGE = re.compile(r"\A([\s•●·\-–—:✓✔✖→←↗↘▾▸►|*]*)(.*?)([\s•●·:.…!?,;|*]*)\Z", re.S)


def tr(text):
    """English text -> current language (unchanged if no translation is known)."""
    if _lang == "en" or not isinstance(text, str) or not text or not re.search(r"[A-Za-z]", text):
        return text
    hit = _cache.get(text)
    if hit is not None:
        return hit
    out = _tr(text)
    if len(_cache) > 20000:
        _cache.clear()
    _cache[text] = out
    return out


def _tr(text, depth=0):
    s = _strings.get(text)
    if s is not None:
        return s
    for rx, en, tr_, _n in _templates:
        m = rx.match(text)
        if m and "\n" not in en and any("\n" in a for a in m.groups()):
            m = None                                 # a one-line pattern must not swallow a multi-line text
        if m:
            return _fill(tr_, [_tr(a, depth + 1) if depth < 4 else a for a in m.groups()])
    if text.isupper():                               # "PROCESSOR" drawn from "Processor".upper()
        s = _upper.get(text)
        if s is not None:
            return s
    for key in _prefixes:                            # "Live · updated " + time
        if text.startswith(key) and len(text) > len(key):
            return _strings[key] + (_tr(text[len(key):], depth + 1) if depth < 3 else text[len(key):])
    for key in _suffixes:                            # name + " (limit reached)"
        if text.endswith(key) and len(text) > len(key):
            return (_tr(text[:-len(key)], depth + 1) if depth < 3 else text[:-len(key)]) + _strings[key]
    if depth < 3:
        for sep in ("\n\n", "\n", "  |  ", " · ", " • ", " — ", ": "):
            if sep in text:
                if sep == ": ":                      # "Trade-off: Off: you can still …" -> head + translated rest
                    head, rest = text.split(sep, 1)
                    done = [_tr(head, depth + 1), _tr(rest, depth + 1)]
                    if done[1] != rest:
                        return sep.join(done)
                parts = text.split(sep)
                done = [_tr(p, depth + 1) for p in parts]
                if done != parts:
                    return sep.join(done)
                break
    m = _EDGE.match(text)
    if m and (m.group(1) or m.group(3)):
        core = m.group(2)
        for cand in (core + m.group(3).strip(), core):
            if cand and cand != text:
                s = _strings.get(cand)
                if s is not None:
                    tail = m.group(3) if cand == core else m.group(3)[len(m.group(3).strip()):]
                    return m.group(1) + s + tail
        if core and core != text and depth < 3:
            inner = _tr(core, depth + 1)
            if inner != core:
                return m.group(1) + inner + m.group(3)
    return text


def english(text):
    """Shown text (in any language) -> its English original, when known."""
    if not isinstance(text, str):
        return text
    return _reverse.get(text, text)


# ---------------------------------------------------------------- Tk hooks
_orig = {}


def _translated_cnf(widget, cnf, kw, keys):
    """Copy of the option dicts with display keys translated; remembers the English on the widget."""
    if _lang == "en" and not getattr(widget, "_i18n_seen", False):
        # still remember English for widgets that might be re-labelled later
        pass
    merged = {}
    if cnf:
        if isinstance(cnf, dict):
            merged.update(cnf)
        else:
            return cnf, kw
    if kw:
        merged.update(kw)
    hit = [k for k in keys if k in merged and isinstance(merged[k], str)]
    if not hit:
        return cnf, kw
    for k in hit:
        en = english(merged[k])
        try:
            store = widget.__dict__.setdefault("_i18n_en", {})
            store[k] = en
        except Exception:
            pass
        merged[k] = tr(en)
    return merged, None


def _hook_options():
    orig = tk.Misc._options

    def _options(self, cnf, kw=None):
        if isinstance(self, tk.Canvas) and not getattr(self, "_i18n_widget_call", False):
            # canvas item create/itemconfigure: translate 'text'; ids are recorded by the canvas hooks
            if (isinstance(cnf, dict) and "text" in cnf) or (kw and "text" in kw):
                merged = dict(cnf) if isinstance(cnf, dict) else {}
                if kw:
                    merged.update(kw)
                if isinstance(merged.get("text"), str):
                    en = english(merged["text"])
                    self.__dict__["_i18n_last"] = en
                    merged["text"] = tr(en)
                    return orig(self, merged)
            return orig(self, cnf, kw)
        keys = ("label",) if isinstance(self, tk.Menu) else ("text",)
        if isinstance(self, tk.Menu):
            return orig(self, cnf, kw)          # menu entries: handled in Menu.add hook
        c2, k2 = _translated_cnf(self, cnf, kw, keys)
        return orig(self, c2, k2)
    tk.Misc._options = _options
    _orig["_options"] = orig

    ocget = tk.Misc.cget

    def cget(self, key):
        if key == "text":
            store = self.__dict__.get("_i18n_en")
            if store and "text" in store:
                return store["text"]
        return ocget(self, key)
    tk.Misc.cget = cget
    tk.Misc.__getitem__ = cget
    _orig["cget"] = ocget


def _hook_canvas():
    ocreate = tk.Canvas.create_text

    def create_text(self, *args, **kw):
        self.__dict__.pop("_i18n_last", None)
        item = ocreate(self, *args, **kw)
        en = self.__dict__.pop("_i18n_last", None)
        if en is not None:
            self.__dict__.setdefault("_i18n_items", {})[item] = en
        return item
    tk.Canvas.create_text = create_text

    oitemconfigure = tk.Canvas.itemconfigure

    def itemconfigure(self, tagOrId, cnf=None, **kw):
        self.__dict__.pop("_i18n_last", None)
        r = oitemconfigure(self, tagOrId, cnf, **kw)
        en = self.__dict__.pop("_i18n_last", None)
        if en is not None:
            items = self.__dict__.setdefault("_i18n_items", {})
            try:
                ids = self.find_withtag(tagOrId) if not isinstance(tagOrId, int) else (tagOrId,)
            except tk.TclError:
                ids = ()
            for i in ids:
                items[i] = en
        return r
    tk.Canvas.itemconfigure = itemconfigure
    tk.Canvas.itemconfig = itemconfigure

    oitemcget = tk.Canvas.itemcget

    def itemcget(self, tagOrId, option):
        if option == "text":
            items = self.__dict__.get("_i18n_items")
            if items:
                try:
                    i = tagOrId if isinstance(tagOrId, int) else (self.find_withtag(tagOrId) or (None,))[0]
                except tk.TclError:
                    i = None
                if i in items:
                    return items[i]
        return oitemcget(self, tagOrId, option)
    tk.Canvas.itemcget = itemcget

    odelete = tk.Canvas.delete

    def delete(self, *args):
        items = self.__dict__.get("_i18n_items")
        if items:
            if "all" in args:
                items.clear()
            else:
                for a in args:
                    if isinstance(a, int):
                        items.pop(a, None)
        return odelete(self, *args)
    tk.Canvas.delete = delete


def _hook_menu():
    oadd = tk.Menu.add

    def add(self, itemType, cnf={}, **kw):
        if "label" in kw and isinstance(kw["label"], str):
            kw["label"] = tr(english(kw["label"]))
        elif isinstance(cnf, dict) and isinstance(cnf.get("label"), str):
            cnf = dict(cnf)
            cnf["label"] = tr(english(cnf["label"]))
        return oadd(self, itemType, cnf, **kw)
    tk.Menu.add = add


def _hook_title():
    otitle = tk.Wm.wm_title

    def wm_title(self, string=None):
        if string is None:
            en = self.__dict__.get("_i18n_title")
            return en if en is not None else otitle(self)
        self.__dict__["_i18n_title"] = english(string)
        return otitle(self, tr(english(string)))
    tk.Wm.wm_title = wm_title
    tk.Wm.title = wm_title


def _hook_text():
    oinsert = tk.Text.insert

    def insert(self, index, chars, *args):
        if isinstance(chars, str) and _lang != "en":
            t = tr(chars)
            if t != chars:
                chars = t
        return oinsert(self, index, chars, *args)
    tk.Text.insert = insert


def _hook_messagebox():
    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askyesnocancel",
                 "askquestion", "askretrycancel"):
        f = getattr(messagebox, name, None)
        if f is None or getattr(f, "_i18n", False):
            continue

        def wrap(f=f):
            def inner(title=None, message=None, **options):
                if "detail" in options and isinstance(options["detail"], str):
                    options["detail"] = tr(options["detail"])
                return f(tr(title) if isinstance(title, str) else title,
                         tr(message) if isinstance(message, str) else message, **options)
            inner._i18n = True
            return inner
        setattr(messagebox, name, wrap())


def _hook_ttk():
    try:
        from tkinter import ttk
    except Exception:
        return
    oheading = ttk.Treeview.heading

    def heading(self, column, option=None, **kw):
        if isinstance(kw.get("text"), str):
            en = english(kw["text"])
            self.__dict__.setdefault("_i18n_heads", {})[column] = en
            kw["text"] = tr(en)
        if option == "text":
            heads = self.__dict__.get("_i18n_heads", {})
            if column in heads:
                return heads[column]
        return oheading(self, column, option, **kw)
    ttk.Treeview.heading = heading


def _hook_measure(g):
    """RETWEAKS' rounded widgets size themselves from text_w(font, text): measure the translated text."""
    if not g or "text_w" not in g or getattr(g["text_w"], "_i18n", False):
        return
    otw = g["text_w"]

    def text_w(spec, text):
        return otw(spec, tr(text) if isinstance(text, str) else text)
    text_w._i18n = True
    text_w._orig = otw
    g["text_w"] = text_w


def install(g=None, code=None):
    """Hook Tk once (before the window is built) and load the saved language."""
    global _installed, _g
    if code is None:
        try:
            from rt_pages import settings_store
            code = settings_store.load().get("language", DEFAULT)
        except Exception:
            code = DEFAULT
    load(code)
    if g is not None:
        _g = g
        _hook_measure(g)
    if _installed:
        return _lang
    _installed = True
    _hook_options()
    _hook_canvas()
    _hook_menu()
    _hook_title()
    _hook_text()
    _hook_messagebox()
    _hook_ttk()
    return _lang


# ---------------------------------------------------------------- live switching
def _walk(w):
    yield w
    try:
        kids = w.winfo_children()
    except tk.TclError:
        return
    for c in kids:
        yield from _walk(c)


# RETWEAKS' own canvas widgets that draw their label in a redraw method (safe to call: drawing only)
_REDRAW = {"RButton": "_draw", "RCheck": "_draw", "RSelect": "_draw", "NavItem": "_draw", "NavButton": "draw",
           "CoolingSelect": None}


def relabel(root):
    """Re-apply the current language to every widget under root (all toplevels of the app)."""
    _relabel_widgets(list(_walk(root)))


def _relabel_widgets(widgets):
    tw = (_g or {}).get("text_w")
    measure = getattr(tw, "_orig", None)
    for w in widgets:
        try:
            store = w.__dict__.get("_i18n_en")
            if store and "text" in store and not isinstance(w, tk.Canvas):
                w.configure(text=store["text"])
            items = w.__dict__.get("_i18n_items")
            if items:
                for i, en in list(items.items()):
                    try:
                        w.itemconfigure(i, text=en)
                    except tk.TclError:
                        items.pop(i, None)
            heads = w.__dict__.get("_i18n_heads")
            if heads:
                for col, en in list(heads.items()):
                    try:
                        w.heading(col, text=en)
                    except tk.TclError:
                        pass
            t = w.__dict__.get("_i18n_title")
            if t is not None and isinstance(w, (tk.Tk, tk.Toplevel)):
                w.title(t)
            cls = type(w).__name__
            if cls == "RButton" and measure is not None:
                auto = w.__dict__.get("_i18n_auto")
                if auto is None:
                    auto = abs(int(float(w.cget("width"))) - (measure(w.font, w.label) + 36)) <= 2 or \
                        abs(int(float(w.cget("width"))) - (tw(w.font, w.label) + 36)) <= 2
                    w.__dict__["_i18n_auto"] = auto
                if auto:
                    w.set_text(w.label)
            elif cls == "RCheck" and measure is not None:
                w.configure(width=tw(w.cb_font, w.cb_text) + 34)
            redraw = _REDRAW.get(cls)
            if redraw and callable(getattr(w, redraw, None)):
                try:
                    getattr(w, redraw)()
                except Exception:
                    pass
        except Exception:
            continue


_switch = {"gen": 0, "busy": False}
BATCH = 250            # widgets re-labelled per step of a background switch


def busy():
    """True while a language switch is still re-labelling hidden pages."""
    return _switch["busy"]


def _viewable(w):
    try:
        return bool(w.winfo_viewable())
    except tk.TclError:
        return False


def set_language(hub, code, sync=False):
    """Switch the whole app and save the choice (config key `language`).

    v2.0.9 (owner report: on Windows the sidebar icons vanished and the text stayed in the old language): the switch
    re-labels ~6,000 widgets, which froze the window for many seconds on Windows. Now what's on screen (sidebar, top bar,
    the open page) switches first, and the hidden pages follow in small steps, so the window stays responsive. Pass
    sync=True to do everything at once."""
    code = code if code in LANGUAGES else DEFAULT
    load(code)
    try:
        hub.settings["language"] = code
        from rt_pages import settings_store
        settings_store.save(hub.settings)
    except Exception:
        pass
    for page in list((getattr(hub, "rt_pages", {}) or {}).values()):
        fn = getattr(page, "relabel", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
    roots = [hub] + [w for w in hub.winfo_children() if isinstance(w, tk.Toplevel)]
    widgets = [w for r in roots for w in _walk(r)]
    shown = [w for w in widgets if _viewable(w)]
    hidden = [w for w in widgets if not _viewable(w)] if not sync else []
    _relabel_widgets(widgets if sync else shown)
    for extra, method in (("chrome", "refresh"), ("sidebar_nav", "relabel")):
        obj = getattr(hub, extra, None)
        fn = getattr(obj, method, None) or getattr(obj, "refresh", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass
    _switch["gen"] += 1
    gen = _switch["gen"]

    def finished():
        _switch["busy"] = False
        try:
            hub.event_generate("<<LanguageChanged>>")
        except tk.TclError:
            pass

    if not hidden:
        finished()
        return code
    _switch["busy"] = True

    def step(i=0):
        if gen != _switch["gen"]:
            return                                   # a newer switch took over
        _relabel_widgets(hidden[i:i + BATCH])
        if i + BATCH < len(hidden):
            try:
                hub.after(1, lambda: step(i + BATCH))
            except tk.TclError:
                _switch["busy"] = False
            return
        finished()
    try:
        hub.update_idletasks()                       # draw the switched screen before the rest continues
        hub.after(1, step)
    except tk.TclError:
        _relabel_widgets(hidden)
        finished()
    return code
