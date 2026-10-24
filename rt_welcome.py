"""First-run welcome tour (owner request 2026-10-22).

"make a intro screen where it explains how everything in retweaks works and asks if you want to make a
retweaks desktop shortcut. ask if it wants to be preferred in Celsius or Fahrenheit, and ask for the
language wanted, also ask for auto updates, and if they want retweaks showing up in the tray. make
animations for every different question and a good ui. make this only apply for the users first time using
this version/all versions ahead"

Owner answers: shown ONCE to everyone who opens v2.0 or later for the first time (people upgrading from
earlier versions included), never again after that; Settings has "Show the welcome tour
again". Auto updates ON = check at start, download, verify SHA-256, ask to restart (rt_autoupdate).

How it behaves (honest and reversible):
- A full-window overlay inside the main window: Welcome, How RETWEAKS works, Temperature unit, Language,
  Auto updates, Tray, Desktop shortcut, Done. Each page has its own small animation; pages slide/fade in
  (about 0.3 s, time-based, no added waiting).
- Nothing changes until you press Next on a question: that question's choice is applied right then
  (Back never applies anything). Skip ends the tour and keeps what was applied so far.
- Settings keys: welcome_done_version (set when the tour ends or is skipped), temp_unit (via
  settings_store.set_temp_unit), language (via rt_i18n.set_language when available), auto_update,
  tray_on_close (via the shell's set_tray, which starts/stops the tray icon). The desktop shortcut is a real
  .lnk made with first_run.create_desktop_shortcut (only in RETWEAKS.exe), recorded in first_run.json so
  The base app's old one-question shortcut prompt doesn't appear as well.
Only touched from the Tk thread; the shortcut is created on a worker thread and reported back via a queue.
"""
import json
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

from core.version import BRAND, __version__ as VERSION

MARK = "welcome_done_version"
ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"
FALLBACK_LANGS = {"en": "English", "es": "Español", "fr": "Français", "de": "Deutsch", "pt-BR": "Português (Brasil)"}
GREETINGS = {"en": "Hello", "es": "Hola", "fr": "Bonjour", "de": "Hallo", "pt-BR": "Olá"}
COL_W, ANIM_H = 700, 210
STEP_IN = 0.32                     # seconds for a page to slide/fade in


# ---------------------------------------------------------------- hooks used by retweaks.py / Settings
def needed(settings):
    return not (settings or {}).get(MARK)


def _settings_root():
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "RETWEAKS"


def _first_run_state():
    try:
        data = json.loads((_settings_root() / "first_run.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_first_run(**values):
    root = _settings_root()
    state = _first_run_state()
    state.update(values)
    try:
        root.mkdir(parents=True, exist_ok=True)
        tmp = root / "first_run.json.tmp"
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, root / "first_run.json")
        return True
    except OSError:
        return False


def prepare():
    """Called before the window is built. When the tour will run, the base app's separate desktop-shortcut
    question is marked as asked, because the tour asks it instead (one question, not two)."""
    try:
        from rt_pages import settings_store
        if needed(settings_store.load()) and _first_run_state().get("desktop_shortcut_prompted") is not True:
            _write_first_run(desktop_shortcut_prompted=True, asked_by="welcome tour")
    except Exception:
        pass


def maybe_show(hub, interval=200):
    """Shows the tour once the startup screen has finished and the window is really on screen (a start
    with --minimized waits until the window is first opened)."""
    if not needed(getattr(hub, "settings", {})):
        return

    def check():
        try:
            if not hub.winfo_exists() or getattr(hub, "_quitting", False):
                return
            intro = getattr(hub, "intro", None)
            reopen = getattr(hub, "_reopen_intro", None)
            busy = (intro is not None and not getattr(intro, "closed", True)) or \
                   (reopen is not None and not getattr(reopen, "closed", True))
            visible = hub.state() not in ("withdrawn", "iconic")
            if not busy and visible:
                try:
                    alpha = float(hub.attributes("-alpha"))
                except (tk.TclError, ValueError):
                    alpha = 1.0
                if alpha >= 0.99:
                    show(hub)
                    return
        except tk.TclError:
            return
        hub.after(interval, check)
    hub.after(interval, check)


def show(hub, replay=False):
    cur = getattr(hub, "_welcome", None)
    if cur is not None and not cur.closed:
        return cur
    hub._welcome = Welcome(hub, replay=replay)
    return hub._welcome


# ---------------------------------------------------------------- small helpers
def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def blend(a, b, k):
    k = max(0.0, min(1.0, k))
    a, b = _hex(a), _hex(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * k) for x, y in zip(a, b))


def ease(p):
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def rr(x0, y0, x1, y1, r):
    """Rounded rectangle as sampled circular corners (same method as retweaks.rr), so corners really are round:
    the earlier 12-point outline only looked square once Tk smoothed it. Drawn with smooth=False."""
    import math
    r = max(1, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = []
    for cx, cy, start in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for step in range(9):
            a = math.radians(start + step * 90 / 8)
            pts.extend((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _tr(text):
    """Translated text when the translations module offers one, else the English text."""
    try:
        import rt_i18n
        f = getattr(rt_i18n, "tr", None) or getattr(rt_i18n, "t", None)
        if callable(f):
            out = f(text)
            if isinstance(out, str) and out:
                return out
    except Exception:
        pass
    return text


def _languages():
    try:
        import rt_i18n
        langs = getattr(rt_i18n, "LANGUAGES", None)
        if isinstance(langs, dict) and langs:
            return dict(langs)
    except Exception:
        pass
    return dict(FALLBACK_LANGS)


def _packaged():
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def _desktop_dir():
    home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return home / "Desktop"


def _create_shortcut():
    """Real .lnk to the running RETWEAKS.exe on the Desktop (the base app's verified creation code)."""
    from first_run import create_desktop_shortcut
    return create_desktop_shortcut(sys.executable)


# Tests swap these.
CREATE_SHORTCUT = _create_shortcut
IS_PACKAGED = _packaged


# ---------------------------------------------------------------- widgets
class Pill(tk.Canvas):
    """Rounded button drawn with the theme colours (primary = filled accent, else outlined)."""

    def __init__(self, parent, g, text, command, primary=False, width=None, height=40, outer=None):
        import tkinter.font as tkfont
        self.g, self.text, self.command, self.primary = g, text, command, primary
        self.font = (g["UI"], 10, "bold")
        w = width or (tkfont.Font(font=self.font).measure(text) + 44)
        super().__init__(parent, width=w, height=height, bg=outer or g["BG"], highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=0)
        self.w, self.h, self.hover, self.enabled = w, height, False, True
        self.bind("<Enter>", lambda e: self._set(True))
        self.bind("<Leave>", lambda e: self._set(False))
        self.bind("<ButtonRelease-1>", lambda e: self.enabled and self.command and self.command())
        self.draw()

    def _set(self, hover):
        self.hover = hover
        self.draw()

    def set_text(self, text):
        self.text = text
        self.draw()

    def set_enabled(self, flag):
        self.enabled = bool(flag)
        self.configure(cursor="hand2" if flag else "arrow")
        self.draw()

    def draw(self):
        g = self.g
        self.delete("all")
        if self.primary:
            fill = g["FG"] if (self.hover and self.enabled) else blend(g["FG"], g["BG"], 0.08)
            fg, edge = g["BG"], fill
        else:
            fill = g["PANEL2"] if self.hover and self.enabled else g["PANEL"]
            fg, edge = g["FG"], blend(g["LINE"], g["FG"], 0.25 if self.hover else 0)
        if not self.enabled:
            fill, fg, edge = g["PANEL"], g["MUTED"], g["LINE"]
        self.create_polygon(rr(1, 1, self.w - 1, self.h - 1, self.h / 2), smooth=False, fill=fill, outline=edge)
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill=fg, font=self.font)


class OptionCard(tk.Canvas):
    def __init__(self, parent, g, title, subtitle, on_pick, width, height=78):
        super().__init__(parent, width=width, height=height, bg=g["BG"], highlightthickness=0, bd=0,
                         cursor="hand2", takefocus=0)
        self.g, self.title, self.subtitle, self.on_pick = g, title, subtitle, on_pick
        self.w, self.h, self.hover, self.selected, self.fade = width, height, False, False, 1.0
        self.disabled = False
        self.bind("<Enter>", lambda e: self._hov(True))
        self.bind("<Leave>", lambda e: self._hov(False))
        self.bind("<ButtonRelease-1>", lambda e: (not self.disabled) and self.on_pick())
        self.draw()

    def _hov(self, v):
        self.hover = v
        self.draw()

    def draw(self):
        g, k = self.g, self.fade
        self.delete("all")
        base = g["PANEL2"] if (self.hover and not self.disabled) else g["PANEL"]
        edge = g["FG"] if self.selected else (blend(g["LINE"], g["FG"], 0.2) if self.hover else g["LINE"])
        self.create_polygon(rr(1, 1, self.w - 1, self.h - 1, 14), smooth=False, fill=blend(g["BG"], base, k),
                            outline=blend(g["BG"], edge, k), width=2 if self.selected else 1)
        tcol = g["MUTED"] if self.disabled else g["FG"]
        self.create_text(18, 26, text=self.title, anchor="w", fill=blend(g["BG"], tcol, k),
                         font=(g["UI"], 11, "bold"))
        if self.subtitle:
            self.create_text(18, 50, text=self.subtitle, anchor="w", fill=blend(g["BG"], g["MUTED"], k),
                             font=(g["UI"], 9), width=self.w - 50)
        # selection mark
        cx, cy = self.w - 22, 24
        if self.selected:
            self.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, fill=blend(g["BG"], g["FG"], k), outline="")
            self.create_line(cx - 4, cy, cx - 1, cy + 3, cx + 4, cy - 3, fill=g["BG"], width=2)
        else:
            self.create_oval(cx - 8, cy - 8, cx + 8, cy + 8, outline=blend(g["BG"], g["LINE"], k), width=1)


# ---------------------------------------------------------------- the tour
class Welcome:
    def __init__(self, hub, replay=False):
        self.hub, self.replay = hub, replay
        self.g = g = getattr(hub, "_g", None) or {}
        self.closed = False
        self.results = queue.Queue()
        self.shortcut_result = None            # None = not asked / str message
        self.applied = {}
        self.values = self._initial_values()
        self.steps = self._steps()
        self.i = 0
        self.t0 = time.monotonic()
        self.dir = 1
        self.knob = 0.0                         # °C/°F toggle knob position (animated)
        self.tray_scale = 1.0 if self.values["tray"] else 0.0
        self.lang_focus = None                  # (code, time) when a language card was clicked
        self._images = {}
        self.job = None

        self.root = tk.Frame(hub, bg=g["BG"], takefocus=1)
        self.root.place(x=0, y=0, relwidth=1, relheight=1)
        self.root.lift()
        self._build_frame()
        for key, fn in (("<Return>", lambda e: self.next()), ("<Right>", lambda e: self.next()),
                        ("<Left>", lambda e: self.back()), ("<Escape>", lambda e: self.skip())):
            self.root.bind(key, fn)
        self.render()
        self.root.focus_set()
        self._tick()

    # ------------------------------------------------------------ data
    def _initial_values(self):
        s = self.hub.settings
        lang = s.get("language") or "en"
        if lang not in _languages():
            lang = "en"
        lnk = _desktop_dir() / "RETWEAKS.lnk"
        return {
            "unit": "F" if str(s.get("temp_unit", "C")).upper().startswith("F") else "C",
            "language": lang,
            "auto_update": True if "auto_update" not in s else bool(s.get("auto_update")),   # owner: preselect On
            "tray": bool(s.get("tray_on_close", True)),
            "shortcut": IS_PACKAGED() and not lnk.exists(),
        }

    def _steps(self):
        return [
            dict(key="welcome", anim=self.anim_welcome,
                 title="Welcome to ReTweaks",
                 body="Real readings, real tweaks you can undo, and handy tools for gaming. This short tour shows "
                      "how it's laid out and asks five quick questions. You can change every answer later in "
                      "Settings."),
            dict(key="how", anim=self.anim_how, title="How RETWEAKS works",
                 body="Choose a page in the sidebar. Some pages have categories or sections at the top: switch between them to find related tools. Every tweak shows what it "
                      "changes before you apply it, and can be undone."),
            dict(key="unit", anim=self.anim_unit, title="Celsius or Fahrenheit?",
                 body="Used for every temperature in RETWEAKS: Dashboard, Hardware, Temperatures and fan curves.",
                 choices=[("C", "Celsius (°C)", "e.g. 45 °C"), ("F", "Fahrenheit (°F)", "e.g. 113 °F")],
                 value="unit", apply=self.apply_unit),
            dict(key="language", anim=self.anim_language, title="Choose your language",
                 body="Menus, pages and messages switch to this language.",
                 choices=[(c, n, "") for c, n in _languages().items()], value="language", apply=self.apply_language),
            dict(key="update", anim=self.anim_update, title="Automatic updates",
                 body="When this is on, RETWEAKS checks GitHub when it starts. A new version is downloaded, "
                      "checked against its SHA-256 fingerprint, and you're asked before it restarts. When it's "
                      "off you only get an Update now bar.",
                 choices=[(True, "On", "Download and ask to restart"), (False, "Off", "Just show the update bar")],
                 value="auto_update", apply=self.apply_update),
            dict(key="tray", anim=self.anim_tray, title="Keep RETWEAKS in the tray?",
                 body="With the tray on, closing the window keeps RETWEAKS running next to the clock, so volume "
                      "lock, fan curves, the crosshair and auto game mode keep working. Right-click the icon "
                      "to open or quit.",
                 choices=[(True, "Yes, keep it in the tray", "Close hides the window"),
                          (False, "No", "Close quits RETWEAKS")], value="tray", apply=self.apply_tray),
            dict(key="shortcut", anim=self.anim_shortcut, title="Add a desktop shortcut?",
                 body=("Puts a RETWEAKS icon on your desktop." if IS_PACKAGED() else
                       "Desktop shortcuts can only be made by RETWEAKS.exe (this copy is running from source)."),
                 choices=[(True, "Yes, add it", "RETWEAKS.lnk on your desktop"), (False, "No thanks", "")],
                 value="shortcut", apply=self.apply_shortcut),
            dict(key="done", anim=self.anim_done, title="You're all set",
                 body="Here's what you chose. Change any of it in Settings, or see this tour again from there."),
        ]

    # ------------------------------------------------------------ layout
    def _img(self, name, size=None):
        key = (name, size)
        if key not in self._images:
            try:
                from PIL import Image, ImageTk
                im = Image.open(ASSETS / name).convert("RGBA")
                if size:
                    im = im.resize((size, size), Image.LANCZOS)
                self._images[key] = ImageTk.PhotoImage(im, master=self.root)
            except Exception:
                self._images[key] = None
        return self._images[key]

    def _splash_frames(self):
        if "splash" not in self._images:
            frames = []
            folder = ASSETS / "splash"
            try:
                n = len([f for f in os.listdir(folder) if f.startswith("reveal-")])
                frames = [tk.PhotoImage(master=self.root, file=str(folder / f"reveal-{i:03d}.png")) for i in range(n)]
            except (OSError, tk.TclError):
                frames = []
            self._images["splash"] = frames
        return self._images["splash"]

    def _build_frame(self):
        g = self.g
        top = tk.Frame(self.root, bg=g["BG"])
        top.pack(fill="x", padx=28, pady=(22, 0))
        logo = self._img("chip-32.png", 24)
        if logo is not None:
            tk.Label(top, image=logo, bg=g["BG"]).pack(side="left", padx=(0, 8))
        tk.Label(top, text=BRAND, bg=g["BG"], fg=g["FG"], font=(g["UI"], 13, "bold")).pack(side="left")
        self.step_lbl = tk.Label(top, text="", bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 9))
        self.step_lbl.pack(side="left", padx=14)
        self.skip_lbl = tk.Label(top, text="", bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 9, "underline"),
                                 cursor="hand2")
        self.skip_lbl.pack(side="right")
        self.skip_lbl.bind("<ButtonRelease-1>", lambda e: self.skip())

        self.col = tk.Frame(self.root, bg=g["BG"], width=COL_W)
        self.col.place(relx=0.5, rely=0.46, anchor="center", width=COL_W)
        self.canvas = tk.Canvas(self.col, width=COL_W, height=ANIM_H, bg=g["BG"], highlightthickness=0, bd=0)
        self.canvas.pack()
        self.title = tk.Label(self.col, text="", bg=g["BG"], fg=g["FG"], font=(g["UI"], 24, "bold"))
        self.title.pack(pady=(6, 6))
        self.body = tk.Label(self.col, text="", bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 10),
                             wraplength=COL_W - 40, justify="center")
        self.body.pack()
        self.choices = tk.Frame(self.col, bg=g["BG"])
        self.choices.pack(pady=(18, 0))
        self.status = tk.Label(self.col, text="", bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 9))
        self.status.pack(pady=(10, 0))

        foot = tk.Frame(self.root, bg=g["BG"])
        foot.pack(side="bottom", fill="x", padx=28, pady=24)
        self.back_btn = Pill(foot, g, _tr("Back"), self.back, width=110)
        self.back_btn.pack(side="left")
        self.next_btn = Pill(foot, g, _tr("Next"), self.next, primary=True, width=150)
        self.next_btn.pack(side="right")
        self.dots = tk.Canvas(foot, width=200, height=16, bg=g["BG"], highlightthickness=0, bd=0)
        self.dots.pack(side="top", pady=12)

    # ------------------------------------------------------------ rendering a step
    def render(self):
        g, st = self.g, self.steps[self.i]
        self.t0 = time.monotonic()
        self.step_lbl.configure(text=_tr("Step {n} of {total}").replace("{n}", str(self.i + 1))
                                .replace("{total}", str(len(self.steps))))
        self.skip_lbl.configure(text="" if st["key"] == "done" else _tr("Skip tour"))
        self.title.configure(text=_tr(st["title"]))
        self.body.configure(text=_tr(st["body"]))
        self.status.configure(text="")
        for w in self.choices.winfo_children():
            w.destroy()
        self.cards = []
        if st["key"] == "how":
            self._render_how()
        elif st["key"] == "done":
            self._render_done()
        elif "choices" in st:
            self._render_choices(st)
        self.back_btn.set_enabled(self.i > 0 and st["key"] != "done")
        self.back_btn.set_text(_tr("Back"))
        self.next_btn.set_text(_tr("Open Dashboard") if st["key"] == "done" else
                               (_tr("Let's go") if st["key"] == "welcome" else _tr("Next")))
        self._fade(0.0)

    def _render_choices(self, st):
        g = self.g
        opts = st["choices"]
        per_row = 3 if len(opts) > 3 else len(opts)
        pad = 8 if per_row == 3 else 12
        width = (COL_W - per_row * 2 * pad) // per_row
        for idx, (val, title, sub) in enumerate(opts):
            r, c = divmod(idx, per_row)
            card = OptionCard(self.choices, g, _tr(title), _tr(sub) if sub else "",
                              lambda v=val, k=st["value"]: self.pick(k, v), width,
                              height=78 if sub or len(opts) <= 3 else 60)
            card.grid(row=r, column=c, padx=pad, pady=8)
            card.value = val
            if st["key"] == "shortcut" and val is True and not IS_PACKAGED():
                card.disabled = True
            card.selected = (self.values[st["value"]] == val)
            self.cards.append(card)

    def _render_how(self):
        g = self.g
        items = [("Monitor", "Live Dashboard, Hardware, Temperatures, FPS overlay and Health Check."),
                 ("Optimize", "Presets and single tweaks with undo, game settings with backups, network, "
                              "startup apps."),
                 ("Tools", "Browser, storage cleanup, audio mixer, fans and RGB, crosshair, auto clicker, AI."),
                 ("Search & tray", "Press Ctrl+K to find any page, setting or tweak. Closing can keep "
                                   "RETWEAKS in the tray.")]
        w = (COL_W - 4 * 10) // 4
        for idx, (title, sub) in enumerate(items):
            card = tk.Canvas(self.choices, width=w, height=104, bg=g["BG"], highlightthickness=0, bd=0)
            card.grid(row=0, column=idx, padx=5)
            card.info = (_tr(title), _tr(sub))
            self.cards.append(card)

    def _draw_how_cards(self, active, k):
        g = self.g
        for idx, card in enumerate(self.cards):
            w, h = int(card["width"]), int(card["height"])
            card.delete("all")
            on = idx == active
            card.create_polygon(rr(1, 1, w - 1, h - 1, 14), smooth=False,
                                fill=blend(g["BG"], g["PANEL2"] if on else g["PANEL"], k),
                                outline=blend(g["BG"], g["FG"] if on else g["LINE"], k), width=2 if on else 1)
            title, sub = card.info
            card.create_text(14, 20, text=title, anchor="w", fill=blend(g["BG"], g["FG"], k), font=(g["UI"], 10, "bold"))
            card.create_text(14, 34, text=sub, anchor="nw", width=w - 24, fill=blend(g["BG"], g["MUTED"], k),
                             font=(g["UI"], 8))

    def _summary(self):
        langs = _languages()
        sc = self.shortcut_result
        if sc is None:
            sc = _tr("Not added") if self.applied.get("shortcut") is False or not self.values["shortcut"] else _tr("Adding…")
        return [
            (_tr("Temperature"), "°F" if self.values["unit"] == "F" else "°C"),
            (_tr("Language"), langs.get(self.values["language"], self.values["language"])),
            (_tr("Automatic updates"), _tr("On") if self.values["auto_update"] else _tr("Off")),
            (_tr("Tray"), _tr("On") if self.values["tray"] else _tr("Off")),
            (_tr("Desktop shortcut"), sc),
        ]

    def _render_done(self):
        g = self.g
        self.summary_rows = []
        for idx, (k, v) in enumerate(self._summary()):
            row = tk.Frame(self.choices, bg=g["BG"])
            row.pack(fill="x", pady=2)
            tick = tk.Label(row, text="", bg=g["BG"], fg=g["GREEN"], font=(g["UI"], 11, "bold"), width=2)
            tick.pack(side="left")
            a = tk.Label(row, text=k, bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 10), width=18, anchor="w")
            a.pack(side="left")
            b = tk.Label(row, text=v, bg=g["BG"], fg=g["FG"], font=(g["UI"], 10, "bold"), anchor="w")
            b.pack(side="left")
            self.summary_rows.append((tick, a, b))

    def _fade(self, p):
        """Slide + fade-in of the page text and cards (p 0..1)."""
        g, k = self.g, ease(p)
        self.col.place_configure(x=int(48 * self.dir * (1 - k)))
        self.title.configure(fg=blend(g["BG"], g["FG"], k))
        self.body.configure(fg=blend(g["BG"], g["MUTED"], k))
        for card in self.cards:
            if isinstance(card, OptionCard):
                card.fade = k
                card.draw()
        self._draw_dots(k)

    def _draw_dots(self, k):
        g = self.g
        c = self.dots
        c.delete("all")
        n = len(self.steps)
        widths = [6 + 14 * k if i == self.i else 6 for i in range(n)]
        gap = 8
        x = (200 - (sum(widths) + gap * (n - 1))) / 2
        for i, wdt in enumerate(widths):
            if i == self.i:
                c.create_polygon(rr(x, 5, x + wdt, 11, 3), smooth=False, fill=g["FG"], outline="")
            else:
                c.create_oval(x, 5, x + 6, 11, fill=g["FG"] if i < self.i else g["LINE"], outline="")
            x += wdt + gap

    # ------------------------------------------------------------ input
    def pick(self, key, value):
        self.values[key] = value
        for card in self.cards:
            if isinstance(card, OptionCard):
                card.selected = (card.value == value)
                card.draw()
        if key == "language":
            self.lang_focus = (value, time.monotonic())
        self.root.focus_set()

    def next(self):
        if self.closed:
            return
        st = self.steps[self.i]
        if st["key"] == "done":
            self.finish()
            return
        if "apply" in st:
            ok, msg = st["apply"](self.values[st["value"]])
            self.applied[st["key"]] = self.values[st["value"]]
            if not ok:
                self.status.configure(text=msg, fg=self.g["RED"])
                return
        self.dir = 1
        self.i += 1
        self.render()
        self.root.focus_set()

    def back(self):
        if self.closed or self.i == 0 or self.steps[self.i]["key"] == "done":
            return
        self.dir = -1
        self.i -= 1
        self.render()
        self.root.focus_set()

    def skip(self):
        if not self.closed:
            self.finish(open_dashboard=False)

    def finish(self, open_dashboard=True):
        hub = self.hub
        hub.settings[MARK] = VERSION
        try:
            hub.save_settings()
        except Exception:
            pass
        self.close()
        if open_dashboard:
            tab = getattr(hub, "rt_tabs", {}).get("Dashboard")
            if tab is not None:
                try:
                    hub.show_tab(tab)
                except tk.TclError:
                    pass

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.job:
            try:
                self.root.after_cancel(self.job)
            except tk.TclError:
                pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ applying choices
    def _sync_settings_page(self):
        """Keep Settings' own checkboxes showing the same values the tour just saved."""
        page = getattr(self.hub, "rt_pages", {}).get("Settings")
        if page is None:
            return
        s = self.hub.settings
        for attr, key in (("tray", "tray_on_close"), ("auto_update", "auto_update"), ("auto_check", "check_updates")):
            var = getattr(page, attr, None)
            if isinstance(var, tk.Variable) and key in s:
                try:
                    var.set(bool(s[key]))
                except tk.TclError:
                    pass

    def apply_unit(self, unit):
        from rt_pages import settings_store
        settings_store.set_temp_unit(self.hub, unit)
        return True, ""

    def apply_language(self, code):
        try:
            import rt_i18n
            fn = getattr(rt_i18n, "set_language", None)
            if callable(fn):
                fn(self.hub, code)
                return True, ""
        except Exception:
            pass
        self.hub.settings["language"] = code
        self.hub.save_settings()
        return True, ""

    def apply_update(self, on):
        self.hub.settings["auto_update"] = bool(on)
        if on:
            self.hub.settings["check_updates"] = True
        self.hub.save_settings()
        self._sync_settings_page()
        if on:
            try:
                import rt_autoupdate
                rt_autoupdate.start(self.hub)
            except Exception:
                pass
        return True, ""

    def apply_tray(self, on):
        shell = getattr(self.hub, "shell", None)
        if shell is not None and hasattr(shell, "set_tray"):
            shell.set_tray(bool(on))   # saves tray_on_close; a failed icon is logged by the shell
        else:
            self.hub.settings["tray_on_close"] = bool(on)
            self.hub.save_settings()
        self._sync_settings_page()
        return True, ""

    def apply_shortcut(self, yes):
        if not yes:
            _write_first_run(desktop_shortcut_prompted=True, desktop_shortcut_created=False)
            self.shortcut_result = _tr("Not added")
            return True, ""
        if not IS_PACKAGED():
            self.shortcut_result = _tr("Only RETWEAKS.exe can add one")
            return True, ""
        self.shortcut_result = None

        def work():
            try:
                path = CREATE_SHORTCUT()
                self.results.put(("shortcut", True, str(path)))
            except Exception as e:
                self.results.put(("shortcut", False, str(e) or type(e).__name__))
        threading.Thread(target=work, daemon=True, name="RetweaksShortcut").start()
        return True, ""

    def _drain(self):
        try:
            while True:
                kind, ok, msg = self.results.get_nowait()
                if kind == "shortcut":
                    _write_first_run(desktop_shortcut_prompted=True, desktop_shortcut_created=bool(ok))
                    self.shortcut_result = _tr("Added to your desktop") if ok else _tr("Couldn't add it") + ": " + msg
                    try:
                        self.hub.log_action("Welcome tour", "Desktop shortcut", "Success" if ok else "Failed",
                                            "" if ok else msg)
                    except Exception:
                        pass
                    if self.steps[self.i]["key"] == "done":
                        for (tick, a, b), (_, v) in zip(self.summary_rows, self._summary()):
                            b.configure(text=v)
        except queue.Empty:
            pass

    # ------------------------------------------------------------ animation loop
    def _tick(self):
        self.job = None
        if self.closed:
            return
        try:
            t = time.monotonic() - self.t0
            if t <= STEP_IN + 0.05:
                self._fade(t / STEP_IN)
            self._drain()
            c = self.canvas
            c.delete("all")
            self.steps[self.i]["anim"](c, t)
            self.job = self.root.after(16, self._tick)
        except tk.TclError:
            self.closed = True

    # each animation draws on a COL_W x ANIM_H canvas
    def anim_welcome(self, c, t):
        g = self.g
        frames = self._splash_frames()
        cx, cy = COL_W / 2, ANIM_H / 2
        if frames:
            idx = min(len(frames) - 1, int(t * 40))
            c.create_image(cx, cy, image=frames[idx])
        else:
            img = self._img("chip-96.png")
            if img is not None:
                c.create_image(cx, cy, image=img)
        if t > 2.4:   # soft halo once the chip is drawn
            p = ((t - 2.4) % 2.2) / 2.2
            r = 64 + 40 * p
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=blend(g["BG"], g["LINE"], 1 - p), width=1)

    def anim_how(self, c, t):
        g = self.g
        k = ease(min(1.0, t / STEP_IN))
        period = 1.7
        active = int(t / period) % 4
        # mini window
        x0, y0, x1, y1 = 120, 14, COL_W - 120, ANIM_H - 10
        c.create_polygon(rr(x0, y0, x1, y1, 14), smooth=False, fill=g["PANEL"], outline=g["LINE"])
        sx1 = x0 + 140
        c.create_line(sx1, y0 + 8, sx1, y1 - 8, fill=g["LINE"])
        # top search pill
        hi = active == 3
        c.create_polygon(rr(sx1 + 40, y0 + 12, x1 - 40, y0 + 38, 13), smooth=False,
                         fill=g["PANEL2"] if hi else g["BG"], outline=g["FG"] if hi else g["LINE"])
        c.create_text(sx1 + 56, y0 + 25, text=_tr("Search pages, settings and tweaks") + "   Ctrl+K", anchor="w",
                      fill=g["FG"] if hi else g["MUTED"], font=(g["UI"], 8))
        # sidebar sections
        sections = [("MONITOR", 3), ("OPTIMIZE", 3), ("TOOLS", 3)]
        y = y0 + 16
        targets = []
        for si, (name, n) in enumerate(sections):
            on = active == si
            c.create_text(x0 + 18, y, text=name, anchor="w", fill=g["FG"] if on else g["MUTED"],
                          font=(g["UI"], 7, "bold"))
            top = y + 10
            for r in range(n):
                yy = y + 14 + r * 12
                c.create_oval(x0 + 18, yy - 3, x0 + 24, yy + 3, outline=g["MUTED"])
                c.create_line(x0 + 32, yy, x0 + 32 + (70 - 12 * r), yy,
                              fill=blend(g["LINE"], g["FG"], 0.8 if on else 0.15), width=3, capstyle="round")
            targets.append((top, y + 14 + (n - 1) * 12 + 6))
            y += 14 + n * 12 + 6
        # sliding accent bar (eases between sections)
        if active < 3:
            top, bottom = targets[active]
            c.create_line(x0 + 8, top + 2, x0 + 8, bottom, fill=g["FG"], width=3, capstyle="round")
        # content placeholder lines (a page)
        for r in range(4):
            yy = y0 + 60 + r * 26
            c.create_polygon(rr(sx1 + 24, yy, x1 - 24 - r * 40, yy + 14, 7), smooth=False, fill=g["PANEL2"], outline="")
        self._draw_how_cards(active, k)

    def anim_unit(self, c, t):
        g = self.g
        unit = self.values["unit"]
        target = 1.0 if unit == "F" else 0.0
        self.knob += (target - self.knob) * 0.18
        # thermometer
        tx, top, bot = 250, 26, 160
        c.create_polygon(rr(tx - 12, top, tx + 12, bot + 6, 12), smooth=False, fill=g["PANEL"], outline=g["LINE"])
        c.create_oval(tx - 24, bot - 8, tx + 24, bot + 40, fill=g["PANEL"], outline=g["LINE"])
        level = 0.45 + 0.18 * math.sin(t * 1.3)
        celsius = 30 + 40 * level
        red = g["RED"]
        c.create_oval(tx - 16, bot, tx + 16, bot + 32, fill=red, outline="")
        mtop = bot - (bot - top - 10) * level
        c.create_polygon(rr(tx - 5, mtop, tx + 5, bot + 10, 5), smooth=False, fill=red, outline="")
        for i in range(5):
            yy = top + 12 + i * 26
            c.create_line(tx + 16, yy, tx + 24, yy, fill=g["MUTED"])
        value = celsius * 9 / 5 + 32 if unit == "F" else celsius
        c.create_text(430, 82, text=f"{value:.0f}°{unit}", fill=g["FG"], font=(g["UI"], 40, "bold"))
        # toggle
        x0, y0, w, h = 370, 140, 120, 34
        c.create_polygon(rr(x0, y0, x0 + w, y0 + h, h / 2), smooth=False, fill=g["PANEL"], outline=g["LINE"])
        kx = x0 + 4 + self.knob * (w / 2 - 4)
        c.create_polygon(rr(kx, y0 + 4, kx + w / 2 - 4, y0 + h - 4, (h - 8) / 2), smooth=False, fill=g["FG"], outline="")
        c.create_text(x0 + w / 4 + 2, y0 + h / 2, text="°C", font=(g["UI"], 10, "bold"),
                      fill=g["BG"] if self.knob < 0.5 else g["MUTED"])
        c.create_text(x0 + 3 * w / 4, y0 + h / 2, text="°F", font=(g["UI"], 10, "bold"),
                      fill=g["BG"] if self.knob >= 0.5 else g["MUTED"])

    def anim_language(self, c, t):
        g = self.g
        codes = list(_languages().keys())
        if self.lang_focus and time.monotonic() - self.lang_focus[1] < 2.2:
            code, p = self.lang_focus[0], 1.0
            fade = min(1.0, (time.monotonic() - self.lang_focus[1]) / 0.25)
        else:
            period = 1.2
            n = int(t / period)
            code = codes[n % len(codes)]
            p = (t % period) / period
            fade = min(1.0, p / 0.25, (1 - p) / 0.25)
        word = GREETINGS.get(code, GREETINGS.get(code.split("-")[0], "Hello"))
        cy = ANIM_H / 2 - 12
        c.create_text(COL_W / 2, cy + 8 * (1 - fade), text=word, fill=blend(g["BG"], g["FG"], fade),
                      font=(g["UI"], 44, "bold"))
        # little row of language codes, current one highlighted
        x = COL_W / 2 - (len(codes) - 1) * 34
        for cd in codes:
            on = cd == code
            c.create_polygon(rr(x - 26, cy + 50, x + 26, cy + 72, 11), smooth=False,
                             fill=g["PANEL2"] if on else g["BG"], outline=g["FG"] if on else g["LINE"])
            c.create_text(x, cy + 61, text=cd.upper(), fill=g["FG"] if on else g["MUTED"], font=(g["UI"], 8, "bold"))
            x += 68

    def anim_update(self, c, t):
        g = self.g
        on = self.values["auto_update"]
        cx = COL_W / 2
        # app box
        bx0, by0, bx1, by1 = cx - 90, 110, cx + 90, 176
        c.create_polygon(rr(bx0, by0, bx1, by1, 14), smooth=False, fill=g["PANEL"], outline=g["LINE"])
        logo = self._img("chip-32.png", 28)
        if logo is not None:
            c.create_image(bx0 + 30, (by0 + by1) / 2, image=logo)
        c.create_text(bx0 + 54, (by0 + by1) / 2, text="RETWEAKS.exe", anchor="w", fill=g["FG"], font=(g["UI"], 10, "bold"))
        if on:
            period = 1.6
            p = (t % period) / period
            y = 18 + (by0 - 40) * ease(min(1.0, p / 0.6))
            alpha = 1.0 if p < 0.6 else max(0.0, 1 - (p - 0.6) / 0.15)
            col = blend(g["BG"], g["FG"], alpha)
            c.create_line(cx, y - 34, cx, y, fill=col, width=4, capstyle="round")
            c.create_line(cx - 14, y - 14, cx, y, cx + 14, y - 14, fill=col, width=4, capstyle="round",
                          joinstyle="round")
            if p > 0.62:
                q = min(1.0, (p - 0.62) / 0.15)
                gx, gy = bx1 - 22, by0
                c.create_oval(gx - 11 * q, gy - 11 * q, gx + 11 * q, gy + 11 * q, fill=g["GREEN"], outline="")
                if q > 0.6:
                    c.create_line(gx - 5, gy, gx - 1, gy + 4, gx + 6, gy - 4, fill=g["BG"], width=2)
            c.create_text(cx, 196, text=_tr("SHA-256 checked before it installs"), fill=g["MUTED"], font=(g["UI"], 8))
        else:
            c.create_polygon(rr(cx - 150, 40, cx + 150, 76, 12), smooth=False, fill=g["PANEL"], outline=g["LINE"])
            c.create_text(cx - 136, 58, text=_tr("A new version is available."), anchor="w", fill=g["MUTED"],
                          font=(g["UI"], 9))
            c.create_polygon(rr(cx + 50, 47, cx + 142, 69, 11), smooth=False, fill=g["FG"], outline="")
            c.create_text(cx + 96, 58, text=_tr("Update now"), fill=g["BG"], font=(g["UI"], 8, "bold"))

    def anim_tray(self, c, t):
        g = self.g
        on = self.values["tray"]
        target = 1.0 if on else 0.0
        self.tray_scale += (target - self.tray_scale) * 0.16
        s = self.tray_scale
        cx = COL_W / 2
        # taskbar strip
        y0, y1 = 150, 186
        c.create_polygon(rr(cx - 230, y0, cx + 230, y1, 10), smooth=False, fill=g["PANEL"], outline=g["LINE"])
        for i in range(3):   # other (generic) tray icons
            x = cx + 70 + i * 26
            c.create_polygon(rr(x - 7, 161, x + 7, 175, 3), smooth=False, fill=g["PANEL2"], outline="")
        ix, iy = cx + 40, 168
        # pop with a little overshoot
        bounce = s + 0.18 * math.sin(min(1.0, s) * math.pi) if on else s
        size = max(0, int(22 * bounce))
        if size >= 4:
            img = self._img("chip-32.png", max(4, min(32, size)))
            if img is not None:
                c.create_image(ix, iy, image=img)
        if on and s > 0.85:
            # the RETWEAKS tray menu (rounded, themed) above the icon
            q = min(1.0, (s - 0.85) / 0.12)
            mx0, my0 = ix - 70, 40
            c.create_polygon(rr(mx0, my0, mx0 + 140, my0 + 96, 12), smooth=False,
                             fill=blend(g["BG"], g["PANEL"], q), outline=blend(g["BG"], g["LINE"], q))
            for r, label in enumerate((_tr("Open RETWEAKS"), _tr("Settings"), _tr("Quit RETWEAKS"))):
                c.create_text(mx0 + 16, my0 + 20 + r * 28, text=label, anchor="w",
                              fill=blend(g["BG"], g["FG"], q), font=(g["UI"], 9))
        if not on:
            c.create_text(cx, 90, text=_tr("Closing the window quits RETWEAKS"), fill=g["MUTED"], font=(g["UI"], 10))

    def anim_shortcut(self, c, t):
        g = self.g
        on = bool(self.values["shortcut"])
        cx = COL_W / 2
        x0, y0, x1, y1 = cx - 200, 10, cx + 200, ANIM_H - 8
        c.create_polygon(rr(x0, y0, x1, y1, 16), smooth=False, fill=blend(g["BG"], g["PANEL"], 0.7), outline=g["LINE"])
        for i in range(2):   # generic desktop items
            ix, iy = x0 + 50, y0 + 46 + i * 70
            c.create_polygon(rr(ix - 18, iy - 18, ix + 18, iy + 18, 6), smooth=False, fill=g["PANEL2"], outline="")
            c.create_line(ix - 16, iy + 30, ix + 16, iy + 30, fill=g["LINE"], width=4, capstyle="round")
        tx, ty = cx, (y0 + y1) / 2 - 6
        if on:
            p = min(1.0, t / 0.7)
            # drop with a bounce
            if p < 0.7:
                y = y0 - 30 + (ty - y0 + 30) * (p / 0.7) ** 2
            else:
                q = (p - 0.7) / 0.3
                y = ty - 12 * math.sin(q * math.pi) * (1 - q)
            img = self._img("chip-48.png")
            if img is not None:
                c.create_image(tx, y, image=img)
            if p >= 1.0:
                c.create_text(tx, ty + 40, text="RETWEAKS", fill=g["FG"], font=(g["UI"], 9, "bold"))
        else:
            c.create_polygon(rr(tx - 26, ty - 26, tx + 26, ty + 26, 10), smooth=False, fill="", outline=g["LINE"],
                             dash=(4, 4))

    def anim_done(self, c, t):
        g = self.g
        cx, cy = COL_W / 2, ANIM_H / 2
        p = (t % 1.8) / 1.8
        for off in (0.0, 0.5):
            q = (p + off) % 1.0
            r = 50 + 60 * q
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=blend(g["BG"], g["LINE"], 1 - q), width=1)
        img = self._img("chip-96.png")
        if img is not None:
            c.create_image(cx, cy, image=img)
        # ticks appear one after another
        for i, (tick, a, b) in enumerate(getattr(self, "summary_rows", [])):
            if t > 0.25 + i * 0.12 and not tick.cget("text"):
                tick.configure(text="✔")
