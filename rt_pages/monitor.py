"""Dashboard (home screen): the RETWEAKS live overview, ported from ui/pages/dashboard.py and
ui/widgets/banners.py to Tk.

CPU (per-thread load, live clock), RAM, every GPU (load from the Windows GPU counters, VRAM, NVIDIA
extras), disk and network speed, each with a 60-second graph; temperatures and fans come from
LibreHardwareMonitor when it runs. All readings come from core.telemetry on a background thread that
only runs while the Dashboard or Hardware page is on screen. The animated banner (setting
`banner_style`: cores / wave / circuit / galaxy / off) only animates while visible.
Banner colour (v2.0.6, setting `banner_color`: original / mono / accent / custom + `banner_custom_color`):
`banner_palette` picks the galaxy background, nebula and star colours and the accent the live styles draw with.

Also shared with the Hardware page: TelemetryService (live samples + data sources) and the one-time
static hardware scan (core.hardware.scan_static), kept on the hub as hub.rt_static / hub.rt_last_sample
/ hub.rt_sources for the hardware report.
"""
import math
import queue
import random
import threading
import time
import tkinter as tk
import traceback

from rt_pages.common import NA, run_bg

BANNER_STYLES = ("off", "cores", "circuit", "galaxy", "wave")
DEFAULT_STYLE = "cores"
WAVE_SECONDS = 60.0
BANNER_HEIGHT = 118
GRAPH_POINTS = 60


# ---------------------------------------------------------------- formatting (same as RETWEAKS ui)

def fmt(value, unit="", digits=0, na=NA):
    if value is None or value == "" or value == []:
        return na
    if isinstance(value, (int, float)):
        text = f"{value:.{digits}f}" if digits else f"{round(value):d}"
    else:
        text = str(value)
    return f"{text} {unit}".strip() if unit else text


def fmt_rate(bps):
    if bps is None:
        return NA
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024 or unit == "GB/s":
            return f"{bps:.0f} {unit}" if unit == "B/s" else f"{bps:.1f} {unit}"
        bps /= 1024.0
    return NA


# Model names some PC makers leave unset (Windows reports the placeholder text as the model)
PLACEHOLDER_MODELS = {"to be filled by o.e.m.", "system product name", "default string", "not applicable",
                      "none", "o.e.m.", "oem", "to be filled by oem", "undefined"}


def _norm(text):
    return " ".join(str(text or "").casefold().split())


def pc_label(computer, cpu_name=None):
    """Maker + model for the Dashboard summary. Drops placeholder models and a model that just repeats the CPU
    name (some prebuilt PCs, e.g. iBUYPOWER, report the CPU as the model), so the CPU isn't shown twice."""
    maker = str((computer or {}).get("manufacturer") or "").strip()
    model = str((computer or {}).get("model") or "").strip()
    m, cpu = _norm(model), _norm(cpu_name)
    if m in PLACEHOLDER_MODELS or (cpu and (m == cpu or cpu in m)):
        model = ""
    elif maker and _norm(model).startswith(_norm(maker)):
        maker = ""                                   # model already starts with the maker's name
    if _norm(maker) in PLACEHOLDER_MODELS:
        maker = ""
    return join(maker, model) or None


def join(*parts, sep=" "):
    return sep.join(str(p) for p in parts if p not in (None, ""))


def temp_text(celsius, unit="C", digits=0):
    if celsius is None:
        return None
    if str(unit).upper() == "F":
        return f"{celsius * 9 / 5 + 32:.{digits}f} °F"
    return f"{celsius:.{digits}f} °C"


def ghz(mhz):
    return f"{mhz / 1000:.2f} GHz" if mhz else None


def interval_seconds(value):
    """The `interval` setting. The original app stored seconds (1.0); values above 30 are treated as
    milliseconds. Clamped to 0.5–10 s; bad values fall back to 1 s."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 1.0
    if v > 30:
        v /= 1000.0
    return max(0.5, min(10.0, v)) if v > 0 else 1.0


# ---------------------------------------------------------------- banner logic (from banners.py)

def normalize_style(style):
    s = str(style).strip().lower() if isinstance(style, str) else ""
    return s if s in BANNER_STYLES else DEFAULT_STYLE


def tile_grid(n):
    if not isinstance(n, int) or n <= 0:
        return 0, 0
    rows = min(3 if n > 32 else 2, n)
    return rows, -(-n // rows)


def smooth_step(current, target, factor=0.25):
    if target is None:
        return current
    d = target - current
    if abs(d) < 0.2:
        return float(target)
    return current + d * factor


def trim_wave(samples, now, seconds=WAVE_SECONDS):
    return [(t, v) for (t, v) in samples if now - t <= seconds]


def extract_total_load(sample):
    try:
        v = sample["cpu"]["load"]
    except (KeyError, TypeError):
        return None
    return float(v) if isinstance(v, (int, float)) else None


def extract_per_core(sample):
    try:
        pc = sample["cpu"]["per_core"]
    except (KeyError, TypeError):
        return None
    if isinstance(pc, (list, tuple)) and pc and all(isinstance(x, (int, float)) for x in pc):
        return [max(0.0, min(100.0, float(x))) for x in pc]
    return None


def make_stars(count=120, seed=7):
    rnd = random.Random(seed)
    return [(rnd.random(), rnd.random(), rnd.uniform(0.6, 1.7), rnd.uniform(0.2, 1.0),
             rnd.choice(("w", "w", "w", "v", "c"))) for _ in range(count)]


def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


BANNER_COLORS = ("original", "mono", "accent", "custom")
DEFAULT_COLOR = "original"


def normalize_color(mode):
    m = str(mode).strip().lower() if isinstance(mode, str) else ""
    return m if m in BANNER_COLORS else DEFAULT_COLOR


def valid_hex(text):
    t = str(text or "").strip()
    return len(t) == 7 and t[0] == "#" and all(ch in "0123456789abcdefABCDEF" for ch in t[1:])


def banner_palette(mode, accent, custom=None):
    """Colours for the banner. original = the purple galaxy + theme accent (unchanged default);
    mono = black and white; accent = the theme's accent colour; custom = the user's HEX colour."""
    mode = normalize_color(mode)
    if mode == "custom" and not valid_hex(custom):
        mode = "accent"
    if mode == "mono":
        return {"mode": mode, "space": "#030303", "nebula": ("#9a9a9a", "#d6d6d6"),
                "stars": {"w": "#ffffff", "v": "#bdbdbd", "c": "#e2e2e2"},
                "title": "#ffffff", "sub": "#a3a3a3", "accent": "#e6e6e6"}
    if mode in ("accent", "custom"):
        col = custom if mode == "custom" else (accent if valid_hex(accent) else "#7c3aed")
        return {"mode": mode, "space": blend("#050505", col, 0.07), "nebula": (col, blend(col, "#ffffff", 0.45)),
                "stars": {"w": "#ffffff", "v": blend(col, "#ffffff", 0.55), "c": blend(col, "#ffffff", 0.8)},
                "title": "#f5f5f5", "sub": blend("#a3a3a3", col, 0.25), "accent": col}
    return {"mode": "original", "space": "#0c0a1d", "nebula": ("#7c3aed", "#06b6d4"),
            "stars": {"w": "#ffffff", "v": "#c4b5fd", "c": "#a5f3fc"},
            "title": "#f4f1ff", "sub": "#a9a3c9", "accent": accent}


def blend(c1, c2, t):
    """Colour between c1 and c2 (Tk has no alpha: used for glows and fades)."""
    t = max(0.0, min(1.0, t))
    try:
        a, b = _rgb(c1), _rgb(c2)
    except (ValueError, AttributeError):
        return c2
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def rounded(x1, y1, x2, y2, r):
    """Points for a smooth rounded rectangle polygon."""
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
            x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


# ---------------------------------------------------------------- shared static scan

def request_static(hub, force=False):
    """Starts the one-time hardware scan (1-5 s) in the background. Listeners in
    hub.rt_static_listeners get the dict (or {} if the scan failed)."""
    if not hasattr(hub, "rt_static_listeners"):
        hub.rt_static_listeners = []
    if getattr(hub, "rt_static_busy", False):
        return
    if getattr(hub, "rt_static", None) is not None and not force:
        for fn in list(hub.rt_static_listeners):
            fn(hub.rt_static)
        return
    hub.rt_static_busy = True

    def scan():
        from core.hardware import scan_static
        data = scan_static()
        try:
            from core.display import list_displays
            data["display_modes"] = list_displays()
        except Exception:
            data["display_modes"] = []
        return data

    def done(res):
        hub.rt_static_busy = False
        hub.rt_static = res if isinstance(res, dict) else {}
        for fn in list(hub.rt_static_listeners):
            try:
                fn(hub.rt_static)
            except tk.TclError:
                pass
            except Exception:
                traceback.print_exc()
    run_bg(hub, scan, done)


def on_static(hub, fn):
    if not hasattr(hub, "rt_static_listeners"):
        hub.rt_static_listeners = []
    hub.rt_static_listeners.append(fn)


# ---------------------------------------------------------------- shared telemetry thread

class TelemetryService:
    """One background thread with core.telemetry.Telemetry (created on that thread, so COM/WMI objects
    stay there). Runs while at least one page holds it (acquire/release), samples every `interval`."""

    def __init__(self, hub):
        self.hub = hub
        self.listeners = []
        self.source_listeners = []
        self.holders = set()
        self.q = queue.Queue()
        self.thread = None
        self.stop_flag = threading.Event()
        self.error = None
        self._polling = False

    def interval(self):
        return interval_seconds((getattr(self.hub, "settings", None) or {}).get("interval", 1.0))

    def acquire(self, who):
        self.holders.add(who)
        if self.thread is None or not self.thread.is_alive() or self.stop_flag.is_set():
            self.stop_flag = threading.Event()
            self.thread = threading.Thread(target=self._run, args=(self.stop_flag,), daemon=True,
                                           name="RetweaksTelemetry")
            self.thread.start()
        if not self._polling:
            self._polling = True
            self.hub.after(100, self._pump)

    def release(self, who):
        self.holders.discard(who)
        if not self.holders:
            self.stop_flag.set()

    def running(self):
        return self.thread is not None and self.thread.is_alive() and not self.stop_flag.is_set()

    def _run(self, stop):
        try:
            from core.telemetry import Telemetry
            telemetry = Telemetry()
        except Exception as e:
            self.q.put(("error", f"{type(e).__name__}: {e}"))
            return
        last_sources = None
        if stop.wait(1.0):        # counters need time between two readings
            return
        while not stop.is_set():
            started = time.monotonic()
            try:
                self.q.put(("sample", telemetry.sample()))
                src = telemetry.sources()
                if src != last_sources:
                    last_sources = src
                    self.q.put(("sources", src))
            except Exception as e:
                self.q.put(("error", f"{type(e).__name__}: {e}"))
            stop.wait(max(0.05, self.interval() - (time.monotonic() - started)))

    def _pump(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "sample":
                    self.error = None
                    self.hub.rt_last_sample = data
                    for fn in list(self.listeners):
                        try:
                            fn(data)
                        except tk.TclError:
                            pass
                        except Exception:
                            traceback.print_exc()
                elif kind == "sources":
                    self.hub.rt_sources = data
                    for fn in list(self.source_listeners):
                        try:
                            fn(data)
                        except Exception:
                            traceback.print_exc()
                else:
                    self.error = data
        except queue.Empty:
            pass
        if self.holders or not self.q.empty():
            try:
                self.hub.after(150, self._pump)
            except tk.TclError:
                self._polling = False
        else:
            self._polling = False


def telemetry_service(hub):
    svc = getattr(hub, "rt_telemetry", None)
    if svc is None:
        svc = hub.rt_telemetry = TelemetryService(hub)
    return svc


# ---------------------------------------------------------------- widgets

class MetricCard:
    """Tk version of the RETWEAKS dashboard card: title, big value, side text, bar, 60 s graph, lines."""

    def __init__(self, parent, g, title, maximum=100.0, show_bar=True):
        self.g, self.maximum, self.points = g, maximum, []
        self.card = g["Card"](parent)
        b = self.card.body
        self.title = tk.Label(b, text=title.upper(), bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9, "bold"),
                              anchor="w")
        self.title.pack(fill="x", padx=16, pady=(12, 0))
        top = tk.Frame(b, bg=b.cget("bg"))
        top.pack(fill="x", padx=16)
        self.value = tk.Label(top, text="…", bg=b.cget("bg"), fg=g["FG"], font=(g["UI"], 22, "bold"), anchor="w")
        self.value.pack(side="left")
        self.side = tk.Label(top, text="", bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9), anchor="e")
        self.side.pack(side="right")
        self.bar = None
        if show_bar:
            self.bar = tk.Canvas(b, height=6, bg=b.cget("bg"), highlightthickness=0, bd=0)
            self.bar.pack(fill="x", padx=16, pady=(2, 4))
            self.bar.bind("<Configure>", lambda e: self._draw_bar())
            self.frac = 0.0
        self.graph = tk.Canvas(b, height=70, bg=b.cget("bg"), highlightthickness=0, bd=0)
        self.graph.pack(fill="x", padx=16, pady=(4, 2))
        self.graph.bind("<Configure>", lambda e: self._draw_graph())
        self.lines = tk.Label(b, text="", bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9), anchor="w",
                              justify="left")
        self.lines.pack(fill="x", padx=16, pady=(2, 12))

    def set_value(self, number, text=None, graph_value="same"):
        if number is None and text is None:
            self.value.config(text=NA)
        else:
            self.value.config(text=text if text is not None else f"{number:.0f}%")
        if self.bar is not None:
            self.frac = max(0.0, min(1.0, (number or 0) / 100.0))
            self._draw_bar()
        v = number if graph_value == "same" else graph_value
        self.points.append(v)
        self.points = self.points[-GRAPH_POINTS:]
        self._draw_graph()

    def set_lines(self, lines):
        self.lines.config(text="\n".join(lines))

    def _draw_bar(self):
        c, g = self.bar, self.g
        w = c.winfo_width()
        c.delete("all")
        if w < 4:
            return
        c.create_polygon(rounded(0, 0, w - 1, 5, 3), smooth=True, fill=g.get("PANEL2", g["LINE"]), outline="")
        if self.frac > 0:
            c.create_polygon(rounded(0, 0, max(6, (w - 1) * self.frac), 5, 3), smooth=True, fill=g["ACC"],
                             outline="")

    def _draw_graph(self):
        c, g = self.graph, self.g
        w, h = c.winfo_width(), c.winfo_height()
        c.delete("all")
        if w < 10:
            return
        for k in range(1, 4):
            y = h * k / 4
            c.create_line(0, y, w, y, fill=g["LINE"], dash=(2, 4))
        vals = [v for v in self.points if v is not None]
        if len(vals) < 2:
            return
        top = self.maximum if self.maximum else max(max(vals) * 1.15, 1.0)
        step = w / (GRAPH_POINTS - 1)
        x0 = w - step * (len(self.points) - 1)
        pts = []
        for i, v in enumerate(self.points):
            if v is None:
                continue
            pts += [x0 + i * step, h - 2 - (max(0.0, min(top, v)) / top) * (h - 6)]
        if len(pts) >= 4:
            area = pts + [pts[-2], h, pts[0], h]
            c.create_polygon(area, fill=blend(c.cget("bg"), g["ACC"], 0.16), outline="")
            c.create_line(*pts, fill=g["ACC"], width=2, smooth=True, capstyle="round", joinstyle="round")


class Banner:
    """Animated banner (styles from the original RETWEAKS dashboard) on a tk.Canvas."""

    def __init__(self, parent, hub, g, style):
        self.hub, self.g = hub, g
        self.style = normalize_style(style)
        self.canvas = tk.Canvas(parent, height=BANNER_HEIGHT, bg=g["BG"], highlightthickness=0, bd=0)
        self.stars = make_stars()
        self.phase, self.t0 = 0.0, time.monotonic()
        self.cores, self.targets, self.thread_count = [], [], 0
        self.wave = []
        self.visible = False
        self.job = None
        self._chip = None
        self._watch_job = None

    # API
    def set_style(self, style):
        self.style = normalize_style(style)
        self.sync()

    def feed_sample(self, sample):
        now = time.monotonic()
        total = extract_total_load(sample)
        if total is not None:
            self.wave = trim_wave(self.wave + [(now, total)], now)
        pc = extract_per_core(sample)
        if pc is not None:
            if len(pc) != self.thread_count:
                self.thread_count = len(pc)
                self.cores = [0.0] * len(pc)
            self.targets = pc

    def set_visible(self, flag):
        self.visible = flag
        self.sync()

    def active(self):
        if self.style == "off" or not self.visible:
            return False
        try:
            return self.hub.state() not in ("iconic", "withdrawn")
        except tk.TclError:
            return False

    def sync(self):
        if self.active():
            if self.job is None:
                self.job = self.hub.after(33, self._tick)
            return
        if self.job is not None:
            try:
                self.hub.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        self._watch_window()

    def _watch_window(self):
        """Owner report 2026-10-24: on first launch the Dashboard is shown while the main window is still hidden
        behind the startup screen, so the banner drew one still frame and never started; it only moved after
        switching tabs. While the banner should animate but the window is hidden or minimized, check again
        twice a second (cheap: no drawing) and start as soon as the window is on screen."""
        if getattr(self, "_watch_job", None) is not None:
            return
        if self.style == "off" or not self.visible:
            return

        def check():
            self._watch_job = None
            if self.style == "off" or not self.visible:
                return
            if self.active():
                self.sync()
            else:
                self._watch_window()
        try:
            self._watch_job = self.hub.after(500, check)
        except tk.TclError:
            self._watch_job = None

    def _tick(self):
        self.job = None
        if not self.active():
            self._watch_window()       # minimized / hidden: resume by itself when the window is back
            return
        self.phase = time.monotonic() - self.t0
        if self.style == "cores":
            for i, t in enumerate(self.targets[:len(self.cores)]):
                self.cores[i] = smooth_step(self.cores[i], t)
        self.draw()
        self.job = self.hub.after(33, self._tick)

    # painting
    def palette(self):
        s = getattr(self.hub, "settings", None) or {}
        return banner_palette(s.get("banner_color", DEFAULT_COLOR), self.g["ACC"], s.get("banner_custom_color"))

    def col(self, key):
        g = self.g
        if key == "accent":
            return self.palette()["accent"]
        return {"card": g["PANEL"], "border": g["LINE"], "input": g.get("PANEL2", g["LINE"]),
                "text": g["FG"], "subtext": g["MUTED"]}[key]

    def draw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), BANNER_HEIGHT
        if w < 50:
            return
        galaxy = self.style == "galaxy"
        bg = self.palette()["space"] if galaxy else self.col("card")
        c.configure(bg=self.g["BG"])
        c.create_polygon(rounded(1, 1, w - 2, h - 2, 12), smooth=True, fill=bg, outline="")
        getattr(self, "_paint_" + self.style, lambda *a: None)(c, w, h, bg)
        c.create_polygon(rounded(1, 1, w - 2, h - 2, 12), smooth=True, fill="", outline=self.col("border"))

    def _wordmark(self, c, x, sub, bg):
        from core.version import BRAND
        galaxy = self.style == "galaxy"
        pal = self.palette()
        c.create_text(x, 44, text=BRAND, anchor="w", fill=pal["title"] if galaxy else self.col("text"),
                      font=(self.g["UI"], 19, "bold"))
        c.create_text(x, 74, text=sub, anchor="w", fill=pal["sub"] if galaxy else self.col("subtext"),
                      font=(self.g["UI"], 9))

    def _paint_cores(self, c, w, h, bg):
        n = self.thread_count
        if not self.targets:
            try:
                import psutil
                n = psutil.cpu_count(logical=True) or 0
            except Exception:
                n = 0
        self._wordmark(c, 26, "measuring…" if not self.targets else f"{n} threads · live load per thread", bg)
        rows, cols = tile_grid(n)
        if not rows:
            return
        gap, avail_w = 6.0, w - 330 - 26
        size = max(6.0, min(22.0, (avail_w - gap * (cols - 1)) / cols, (h - 28 - gap * (rows - 1)) / rows))
        gw, gh = cols * size + (cols - 1) * gap, rows * size + (rows - 1) * gap
        x0, y0 = w - 26 - gw, (h - gh) / 2
        tile_bg, tile_bd, acc = self.col("input"), self.col("border"), blend(bg, self.col("accent"), 0.85)
        for i in range(n):
            r, col = i % rows, i // rows
            x, y = x0 + col * (size + gap), y0 + r * (size + gap)
            c.create_polygon(rounded(x, y, x + size, y + size, 5), smooth=True, fill=tile_bg, outline="")
            if self.targets and i < len(self.cores):
                fh = size * max(0.0, min(100.0, self.cores[i])) / 100.0
                if fh > 0.5:
                    c.create_polygon(rounded(x, y + size - fh, x + size, y + size, min(5, fh / 2)), smooth=True,
                                     fill=acc, outline="")
            c.create_polygon(rounded(x, y, x + size, y + size, 5), smooth=True, fill="", outline=tile_bd)

    def _paint_circuit(self, c, w, h, bg):
        s = w / 1280.0
        routes = [
            [(1280, 30), (980, 30), (950, 59), (760, 59)],
            [(1280, 88), (1010, 88), (980, 59), (760, 59)],
            [(420, 30), (570, 30), (600, 59), (760, 59)],
            [(380, 88), (570, 88), (600, 59), (760, 59)],
        ]
        acc = self.col("accent")
        for i, r in enumerate(routes):
            pts = [(min(x * s, w - 3), y * h / 118.0) for x, y in r]
            c.create_line(*[v for p in pts for v in p], fill=self.col("border"), width=2)
            segs = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
            total = sum(segs) or 1.0
            for k in range(2):
                t = ((self.phase / 3.0) + i * 0.27 + k * 0.5) % 1.0
                d = t * total
                for (a, b), L in zip(zip(pts, pts[1:]), segs):
                    if d <= L or (a, b) == (pts[-2], pts[-1]):
                        f = d / L if L else 0
                        x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
                        break
                    d -= L
                for rad, a_ in ((9, 0.18), (6, 0.35), (2.2, 1.0)):
                    col = blend(bg, acc, a_)
                    c.create_oval(x - rad, y - rad, x + rad, y + rad, fill=col, outline="")
        cx = 760 * s
        if self._chip is None:
            try:
                from branding import logo
                self._chip = logo(c, 96 if h > 100 else 48)
            except Exception:
                self._chip = False
        c.create_rectangle(cx - 28, h / 2 - 28, cx + 28, h / 2 + 28, fill=self.col("card"), outline="")
        if self._chip:
            c.create_image(cx, h / 2, image=self._chip)
        self._wordmark(c, 26, "Windows PC diagnostics and optimization", bg)

    def _galaxy_frames(self, w, h, bg):
        """Nebula glow as images (Tk can't draw transparency): 8 pulse levels, rendered once per size,
        with the banner's rounded corners masked to the page colour."""
        neb = self.palette()["nebula"]
        key = (w, h, bg, self.g["BG"], neb)
        if getattr(self, "_gal_key", None) == key:
            return self._gal_frames
        try:
            from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk
        except Exception:
            self._gal_key, self._gal_frames = key, []
            return []
        frames = []
        base_rgb = _rgb(bg)
        for k in range(8):
            pulse = 0.8 + 0.2 * math.sin(k / 8 * 2 * math.pi)
            img = Image.new("RGB", (w, h), base_rgb)
            for (cx, cy, rx, ry, col, a) in ((w * 0.78, h * 0.4, 300, 110, neb[0], 0.27),
                                              (w * 0.30, h * 0.8, 260, 100, neb[1], 0.17)):
                layer = Image.new("L", (w, h), 0)
                ImageDraw.Draw(layer).ellipse((cx - rx * 0.7, cy - ry * 0.7, cx + rx * 0.7, cy + ry * 0.7),
                                              fill=int(255 * a * pulse))
                layer = layer.filter(ImageFilter.GaussianBlur(min(rx, ry) * 0.45))
                img = Image.composite(Image.new("RGB", (w, h), _rgb(col)), img, layer)
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle((1, 1, w - 2, h - 2), 12, fill=255)
            out = Image.composite(img, Image.new("RGB", (w, h), _rgb(self.g["BG"])), mask)
            frames.append(ImageTk.PhotoImage(out, master=self.canvas))
        self._gal_key, self._gal_frames = key, frames
        return frames

    def _paint_galaxy(self, c, w, h, bg):
        frames = self._galaxy_frames(w, h, bg)
        if frames:
            c.create_image(0, 0, anchor="nw", image=frames[int(self.phase / 6.0 * 8) % len(frames)])
        shift = self.phase * 11.0
        cols = self.palette()["stars"]
        for (sx, sy, r, a, k) in self.stars:
            x = 4 + (sx * w - shift * (0.4 + r / 2.0)) % (w - 8)
            y = 4 + sy * (h - 8)
            rr_ = r / 2 + 0.2
            c.create_oval(x - rr_, y - rr_, x + rr_, y + rr_, fill=blend(bg, cols[k], a), outline="")
        self._wordmark(c, 26, "Windows PC diagnostics and optimization", bg)

    def _paint_wave(self, c, w, h, bg):
        now = time.monotonic()
        pts = trim_wave(self.wave, now)
        self._wordmark(c, 26, "CPU load · last 60 s" if pts else "CPU load · Unavailable", bg)
        if len(pts) < 2:
            if not pts:
                c.create_text(w - 30, h / 2, text=NA, anchor="e", fill=self.col("subtext"), font=(self.g["UI"], 10))
            return
        x0, x1, top, bot = w * 0.38, w - 16, 14.0, h - 14.0
        P = []
        for t, v in pts:
            P += [x1 - (now - t) / WAVE_SECONDS * (x1 - x0), bot - (max(0.0, min(100.0, v)) / 100.0) * (bot - top)]
        acc = self.col("accent")
        c.create_polygon(P + [P[-2], h - 3, P[0], h - 3], fill=blend(bg, acc, 0.18), outline="")
        c.create_line(*P, fill=acc, width=2, smooth=True, capstyle="round", joinstyle="round")


# ---------------------------------------------------------------- page

def _descendants(w):
    for c in w.winfo_children():
        yield c
        yield from _descendants(c)


class MonitorPage:
    title = "Dashboard"
    subtitle = "Live view of your PC. Updates every second."

    def __init__(self, hub, tab, g):
        self.hub, self.g, self.tab = hub, g, tab
        self.svc = telemetry_service(hub)
        head = g["page_header"](tab, "RETWEAKS", self.title, self.subtitle)
        self.sub_label = next((w for w in _descendants(head) if isinstance(w, tk.Label)
                               and w.cget("text") == self.subtitle), None)
        self._update_subtitle()
        body = hub._scroll_area(tab)
        self.body = body
        style = normalize_style((hub.settings or {}).get("banner_style", DEFAULT_STYLE))
        self.banner = Banner(body, hub, g, style)
        if style != "off":
            self.banner.canvas.pack(fill="x", pady=(0, 10), padx=(0, 12))
        self.banner.canvas.bind("<Configure>", lambda e: self.banner.draw())

        self.summary = tk.Label(body, text="Scanning hardware…", bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 10),
                                anchor="w", justify="left", wraplength=900)
        self.summary.pack(fill="x", pady=(0, 8))

        # Quick Start actions share the live overview instead of a second dashboard.
        actions = tk.Frame(body, bg=g['BG'])
        actions.pack(fill='x', pady=(4, 10), padx=(0, 12))
        for column, (title, description, caption, target) in enumerate((
            ('Tune your PC', 'Review a preset or choose individual settings.', 'Browse presets', 15),
            ('Drivers', 'Find official drivers for your hardware.', 'Find drivers', 22),
            ('Set up apps', 'Install the apps you choose in one place.', 'Open App Starter', 23),
        )):
            actions.columnconfigure(column, weight=1, uniform='quick')
            tile=g['Card'](actions)
            tile.grid(row=0,column=column,sticky='nsew',padx=(0,8))
            from rt_pages.common import label
            label(tile.body,title,g,14,bold=True,pady=(12,3))
            label(tile.body,description,g,9,g['MUTED'],wrap=260)
            g['RButton'](tile.body,caption,lambda i=target:hub.show_tab(i)).pack(anchor='w',padx=16,pady=(6,12))

        self.notice = g["Card"](body)
        tk.Label(self.notice.body, text=(
            "CPU temperature and fan speeds aren't available yet. Windows needs a hardware driver for those. "
            "RETWEAKS has LibreHardwareMonitor built in; it reads CPU and motherboard sensors once the free "
            "PawnIO driver is installed (see Hardware & cooling → Temperatures). A separately running LibreHardwareMonitor "
            "with its web server on also works."), bg=self.notice.body.cget("bg"), fg=g["FG"],
            font=(g["UI"], 9), justify="left", anchor="w", wraplength=880).pack(fill="x", padx=16, pady=10)
        self.notice_shown = False

        self.grid = tk.Frame(body, bg=g["BG"])
        self.grid.pack(fill="x", padx=(0, 12))
        self.grid.columnconfigure(0, weight=1, uniform="c")
        self.grid.columnconfigure(1, weight=1, uniform="c")
        self.cpu = MetricCard(self.grid, g, "Processor")
        self.ram = MetricCard(self.grid, g, "Memory")
        self.disk = MetricCard(self.grid, g, "Disk activity", maximum=None, show_bar=False)
        self.net = MetricCard(self.grid, g, "Network", maximum=None, show_bar=False)
        self.gpu_cards = []
        self.fans = g["Card"](self.grid)
        tk.Label(self.fans.body, text="FANS", bg=self.fans.body.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9, "bold"),
                 anchor="w").pack(fill="x", padx=16, pady=(12, 0))
        self.fans_label = tk.Label(self.fans.body, text="", bg=self.fans.body.cget("bg"), fg=g["FG"],
                                   font=(g["UI"], 10), anchor="w", justify="left", wraplength=880)
        self.fans_label.pack(fill="x", padx=16, pady=(2, 12))
        self.fans_shown = False
        self.status = tk.Label(body, text="", bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 9), anchor="w")
        self.status.pack(fill="x", pady=(6, 0))
        self._layout_cards()

        from rt_pages.common import card, label, button_row
        activity=card(body,g,'Game Mode & recommendations',
                      'Review changes before applying. Live readings above show current performance.')
        hub.game_status=label(activity,hub.game_mode_status(),g,10)
        hub.detected=label(activity,'Detected game ... Scanning...',g,9,g['MUTED'])
        row=button_row(activity,g)
        for caption,command in (
            ('Toggle Windows Game Mode',hub.toggle_game_mode),
            ('Game profiles',lambda:hub.show_tab(3)),
            ('Individual tweaks',lambda:hub.show_tab(1)),
            ('Backups & fixes',lambda:hub.show_tab(11)),
        ):
            g['RButton'](row,caption,command).pack(side='left',padx=(0,8))
        hub.rec_lbl=label(activity,'Scanning hardware for a suitable preset...',g,10,g['MUTED'])
        hub.rec_btn=g['RButton'](activity,'Review recommendation',lambda:hub.open_preset(hub.rec_key))
        hub.rec_btn.pack(anchor='w',padx=16,pady=(4,12))
        hub.rec_btn.set_enabled(False)

        self.svc.listeners.append(self.on_telemetry)
        on_static(hub, self.on_static)
        request_static(hub)

    # lifecycle
    def on_shown(self):
        self.svc.acquire(self)
        self.banner.set_visible(True)
        if not self.svc.running() and self.svc.error:
            self.status.config(text=f"Live readings unavailable: {self.svc.error}")

    def on_hidden(self):
        self.banner.set_visible(False)
        self.svc.release(self)

    def close(self):
        self.on_hidden()

    # settings hooks (called by the Settings page / settings_store.set_temp_unit)
    def _update_subtitle(self):
        if self.sub_label is None:
            return
        sec = interval_seconds((self.hub.settings or {}).get("interval", 1.0))
        every = "every second" if sec == 1 else f"every {sec:g} seconds"
        try:
            self.sub_label.config(text=f"Live view of your PC. Updates {every}.")
        except tk.TclError:
            pass

    def on_interval_changed(self, seconds):
        self._update_subtitle()

    def on_temp_unit(self, unit):
        """Redraw the last reading in the new unit right away (no waiting for the next sample)."""
        sample = getattr(self.hub, "rt_last_sample", None)
        if sample:
            try:
                self.on_telemetry(sample, feed_banner=False)
            except Exception:
                pass

    def on_banner_color_changed(self):
        """Settings changed `banner_color` / `banner_custom_color`: redraw now (the galaxy glow re-renders)."""
        self.banner.draw()

    def on_banner_changed(self, style):
        style = normalize_style(style)
        self.banner.set_style(style)
        if style == "off":
            self.banner.canvas.pack_forget()
        elif not self.banner.canvas.winfo_ismapped():
            self.banner.canvas.pack(fill="x", pady=(0, 10), padx=(0, 12), before=self.summary)
        self.banner.draw()

    # layout
    def _all_cards(self):
        return [self.cpu, self.ram, *self.gpu_cards, self.disk, self.net]

    def _layout_cards(self):
        for i, card in enumerate(self._all_cards()):
            card.card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 8) if i % 2 == 0 else (8, 0), pady=6)
        rows = (len(self._all_cards()) + 1) // 2
        if self.fans_shown:
            self.fans.grid(row=rows, column=0, columnspan=2, sticky="ew", pady=6)
        else:
            self.fans.grid_forget()

    # data
    def on_static(self, data):
        if not data:
            self.summary.config(text="The hardware scan failed. Open Hardware and click Rescan to try again.")
            return
        cpu, gpus, ram, comp = data.get("cpu", {}), data.get("gpus", []), data.get("ram", {}), data.get("computer", {})
        pc = pc_label(comp, cpu.get("name"))
        parts = [pc, cpu.get("name"), *(gp.get("name") for gp in gpus),
                 join(fmt(ram.get("installed_gb") or ram.get("total_gb"), "GB"), ram.get("type"))]
        seen, shown = set(), []
        for p in parts:
            key = _norm(p)
            if key and key not in seen:
                seen.add(key)
                shown.append(p)
        self.summary.config(text=" · ".join(shown))

    def on_telemetry(self, s, feed_banner=True):
        if feed_banner:
            try:
                self.banner.feed_sample(s)
            except Exception:
                pass   # a decorative banner must never break the live cards
        unit = (self.hub.settings or {}).get("temp_unit", "C")
        tt = lambda c: temp_text(c, unit)
        cpu, ram, io, sensors = s["cpu"], s["ram"], s["io"], s.get("sensors")
        static = getattr(self.hub, "rt_static", None) or {}
        scpu = static.get("cpu", {})

        self.cpu.set_value(cpu["load"])
        self.cpu.side.config(text=join(ghz(cpu["mhz"]), tt(cpu["temp_c"]), sep="  ·  "))
        self.cpu.set_lines([scpu.get("name") or "",
                            f"Clock: {ghz(cpu['mhz']) or NA}   Temperature: {tt(cpu['temp_c']) or NA}",
                            f"{fmt(scpu.get('cores'))} cores / {fmt(scpu.get('threads'))} threads"])

        self.ram.set_value(ram["percent"])
        self.ram.side.config(text=f"{ram['used_gb']:.1f} / {ram['total_gb']:.1f} GB")
        sram = static.get("ram", {})
        speed = f"{sram['running_mts']} MT/s" if sram.get("running_mts") else None
        self.ram.set_lines([join(sram.get("type"), speed, sep=" · ") or "Memory in use"])

        gpus = s["gpus"]
        if len(gpus) != len(self.gpu_cards):
            for c in self.gpu_cards:
                c.card.destroy()
            self.gpu_cards = [MetricCard(self.grid, self.g, f"GPU {i + 1}" if len(gpus) > 1 else "Graphics")
                              for i in range(len(gpus))]
            self._layout_cards()
        for card, gp in zip(self.gpu_cards, gpus):
            card.set_value(gp["load"])
            if gp["vram_used_gb"] is not None and gp["vram_total_gb"]:
                vram = f"{gp['vram_used_gb']:.1f} / {gp['vram_total_gb']:.1f} GB"
            else:
                vram = fmt(gp["vram_total_gb"], "GB", 1)
            card.side.config(text=join(tt(gp["temp_c"]), gp["engine"], sep="  ·  "))
            extra = join(fmt(gp["core_mhz"], "MHz", na=""), fmt(gp["power_w"], "W", 0, na=""),
                         f"Fan {gp['fan_pct']}%" if gp["fan_pct"] is not None else "", sep="   ")
            lines = [gp["name"], f"VRAM: {vram}   Temperature: {tt(gp['temp_c']) or NA}"]
            if extra:
                lines.append(extra)
            card.set_lines(lines)

        r, w = io["disk_read_bps"], io["disk_write_bps"]
        total = (r or 0) + (w or 0) if r is not None else None
        self.disk.set_value(None, fmt_rate(total) if total is not None else "…", graph_value=total)
        self.disk.set_lines([f"Read {fmt_rate(r)}   Write {fmt_rate(w)}"])
        d, u = io["net_down_bps"], io["net_up_bps"]
        self.net.set_value(None, fmt_rate(d) if d is not None else "…", graph_value=d)
        self.net.side.config(text=f"↑ {fmt_rate(u)}" if u is not None else "")
        self.net.set_lines([f"Download {fmt_rate(d)}   Upload {fmt_rate(u)}"])

        show_notice = sensors is None
        if show_notice != self.notice_shown:
            self.notice_shown = show_notice
            if show_notice:
                self.notice.pack(fill="x", pady=(0, 8), padx=(0, 12), before=self.grid)
            else:
                self.notice.pack_forget()
        fans = (sensors or {}).get("fans") or []
        if fans:
            self.fans_label.config(text="    ".join(f"{f['name']}: {f['rpm']:.0f} RPM" for f in fans))
        if bool(fans) != self.fans_shown:
            self.fans_shown = bool(fans)
            self._layout_cards()
        self.status.config(text="Live · updated " + time.strftime("%H:%M:%S"))
