# ui/widgets/banners.py
"""Animated banner across the top of the Dashboard.

Styles: off, cores (live per-thread load), circuit (decorative), galaxy (decorative),
wave (live total CPU load, last 60 s). One QTimer runs only while the banner is visible
and the window is not minimized.
"""

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

BANNER_STYLES = ("off", "cores", "circuit", "galaxy", "wave")
DEFAULT_STYLE = "cores"
WAVE_SECONDS = 60.0
BANNER_HEIGHT = 118


# ---------- pure logic (tested) ----------

def normalize_style(style):
    """Unknown or non-string values fall back to 'cores'."""
    s = str(style).strip().lower() if isinstance(style, str) else ""
    return s if s in BANNER_STYLES else DEFAULT_STYLE


def tile_grid(n):
    """(rows, cols) for n thread tiles: 2 rows, or 3 when n > 32. n <= 0 -> (0, 0)."""
    if not isinstance(n, int) or n <= 0:
        return 0, 0
    rows = 3 if n > 32 else 2
    rows = min(rows, n)
    return rows, -(-n // rows)


def smooth_step(current, target, factor=0.25):
    """Move current toward target by factor; snap when within 0.2."""
    if target is None:
        return current
    d = target - current
    if abs(d) < 0.2:
        return float(target)
    return current + d * factor


def trim_wave(samples, now, seconds=WAVE_SECONDS):
    """Keep only (timestamp, value) pairs from the last `seconds`."""
    return [(t, v) for (t, v) in samples if now - t <= seconds]


def extract_total_load(sample):
    """Total CPU load from a telemetry sample, or None."""
    try:
        v = sample["cpu"]["load"]
    except (KeyError, TypeError):
        return None
    return float(v) if isinstance(v, (int, float)) else None


def extract_per_core(sample):
    """Per-thread load list from a telemetry sample, or None."""
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


# ---------- widget ----------

def _c(hex_or_color, alpha=None):
    c = QColor(hex_or_color)
    if alpha is not None:
        c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


class DashboardBanner(QWidget):
    def __init__(self, ctx, style=DEFAULT_STYLE, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._theme = dict(getattr(ctx, "theme", None) or {})
        self._style = normalize_style(style)
        self._stars = make_stars()
        self._phase = 0.0
        self._t0 = time.monotonic()
        self._cores = []          # smoothed fill per thread (0..100)
        self._targets = []        # latest real values
        self._thread_count = 0
        self._wave = []           # (timestamp, load)
        self._percpu_primed = False
        self._have_core_data = False
        self.setFixedHeight(BANNER_HEIGHT)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self._anim = QTimer(self)
        self._anim.setInterval(33)
        self._anim.timeout.connect(self._tick_anim)
        self._data = QTimer(self)
        self._data.setInterval(1000)
        self._data.timeout.connect(self._tick_data)
        self._sync_timers()

    # --- API ---
    def style(self):
        return self._style

    def set_style(self, style):
        self._style = normalize_style(style)
        self._sync_timers()
        self.update()

    def apply_theme(self, theme):
        self._theme = dict(theme or {})
        self.update()

    def feed_sample(self, sample):
        now = time.monotonic()
        total = extract_total_load(sample)
        if total is not None:
            self._wave.append((now, total))
            self._wave = trim_wave(self._wave, now)
        pc = extract_per_core(sample)
        if pc is not None:
            self._have_core_data = True
            self._set_targets(pc)

    # --- timers: only while visible and window not minimized ---
    def _active(self):
        if self._style == "off" or not self.isVisible():
            return False
        w = self.window()
        return not (w is not None and w.isMinimized())

    def _sync_timers(self):
        if self._active():
            if self._style in ("circuit", "galaxy", "cores", "wave"):
                self._anim.start()
            if self._style == "cores" and not self._have_core_data:
                self._data.start()
            else:
                self._data.stop()
        else:
            self._anim.stop()
            self._data.stop()

    def showEvent(self, e):
        super().showEvent(e)
        self._sync_timers()

    def hideEvent(self, e):
        self._anim.stop()
        self._data.stop()
        super().hideEvent(e)

    def _set_targets(self, values):
        n = len(values)
        if n != self._thread_count:
            self._thread_count = n
            self._cores = [0.0] * n
        self._targets = list(values)

    def _tick_data(self):
        # Fallback when telemetry carries no per-thread list: non-blocking psutil call.
        if self._style != "cores" or self._have_core_data:
            return
        try:
            import psutil
            vals = psutil.cpu_percent(interval=None, percpu=True)
        except Exception:
            return
        if not self._percpu_primed:
            self._percpu_primed = True   # first call returns zeros; don't show them
            return
        self._set_targets(vals)

    def _tick_anim(self):
        if not self._active():
            self._sync_timers()
            return
        self._phase = time.monotonic() - self._t0
        if self._style == "cores":
            for i, t in enumerate(self._targets[:len(self._cores)]):
                self._cores[i] = smooth_step(self._cores[i], t)
        self.update()

    # --- painting ---
    def _col(self, key, default):
        return self._theme.get(key) or default

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 12, 12)
        galaxy = self._style == "galaxy"
        bg = _c("#0c0a1d") if galaxy else _c(self._col("card", "#13161b"))
        p.fillPath(clip, bg)
        p.setClipPath(clip)
        {"cores": self._paint_cores, "circuit": self._paint_circuit,
         "galaxy": self._paint_galaxy, "wave": self._paint_wave}.get(self._style, lambda *_: None)(p)
        p.setClipping(False)
        p.setPen(QPen(_c(self._col("border", "#262b33")), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 12, 12)
        p.end()

    def _wordmark(self, p, x, sub):
        galaxy = self._style == "galaxy"
        f = QFont(self.font())
        f.setPixelSize(26)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 5)
        p.setFont(f)
        p.setPen(_c("#f4f1ff") if galaxy else _c(self._col("text", "#e8eaed")))
        p.drawText(QPointF(x, 56), "RYTWEAKS")
        f2 = QFont(self.font())
        f2.setPixelSize(12)
        p.setFont(f2)
        p.setPen(_c("#a9a3c9") if galaxy else _c(self._col("subtext", "#9aa0a6")))
        p.drawText(QPointF(x, 78), sub)

    def _paint_cores(self, p):
        n = self._thread_count
        measuring = n == 0 or (not self._have_core_data and not self._percpu_primed) \
            or (not self._targets)
        if measuring:
            try:
                import psutil
                n = psutil.cpu_count(logical=True) or 0
            except Exception:
                n = 0
        sub = "measuring…" if not self._targets else f"{n} threads · live load per thread"
        self._wordmark(p, 26, sub)
        rows, cols = tile_grid(n)
        if not rows:
            return
        gap, avail_w = 6.0, self.width() - 330 - 26
        size = min(22.0, (avail_w - gap * (cols - 1)) / cols, (BANNER_HEIGHT - 28 - gap * (rows - 1)) / rows)
        size = max(size, 6.0)
        gw, gh = cols * size + (cols - 1) * gap, rows * size + (rows - 1) * gap
        x0, y0 = self.width() - 26 - gw, (BANNER_HEIGHT - gh) / 2
        tile_bg, tile_bd = _c(self._col("input", "#1b1f26")), _c(self._col("border", "#2a3039"))
        accent = _c(self._col("accent", "#4da3ff"), 0.85)
        for i in range(n):
            r, c = i % rows, i // rows
            tr = QRectF(x0 + c * (size + gap), y0 + r * (size + gap), size, size)
            path = QPainterPath()
            path.addRoundedRect(tr, 5, 5)
            p.fillPath(path, tile_bg)
            if self._targets and i < len(self._cores):
                h = size * max(0.0, min(100.0, self._cores[i])) / 100.0
                if h > 0.5:
                    p.save()
                    p.setClipPath(path)
                    p.fillRect(QRectF(tr.x(), tr.bottom() - h, size, h), accent)
                    p.restore()
            p.setPen(QPen(tile_bd, 1))
            p.drawRoundedRect(tr, 5, 5)

    def _paint_circuit(self, p):
        w, h = float(self.width()), float(BANNER_HEIGHT)
        line, accent = _c(self._col("border", "#2a3039")), _c(self._col("accent", "#4da3ff"))
        s = w / 1280.0
        # polylines (in 1280-wide design coords), each ending at the chip
        routes = [
            [(1280, 30), (980, 30), (950, 59), (760, 59)],
            [(1280, 88), (1010, 88), (980, 59), (760, 59)],
            [(760, 59), (600, 59), (570, 30), (420, 30)][::-1],
            [(760, 59), (600, 59), (570, 88), (380, 88)][::-1],
        ]
        # chip sits at x=760 design coords; pulses flow toward it
        cx = 760 * s
        pls = []
        for r in routes:
            pts = [QPointF(x * s, y * (h / 118.0)) for x, y in r]
            pls.append(pts)
        lens = []
        for pts in pls:
            path = QPainterPath(pts[0])
            for q in pts[1:]:
                path.lineTo(q)
            p.setPen(QPen(line, 2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            lens.append(path)
        # routes 0,1 run far end -> chip; routes 2,3 were stored chip-first reversed, so they end at the chip too
        for i, path in enumerate(lens):
            for k in range(2):
                t = ((self._phase / 3.0) + i * 0.27 + k * 0.5) % 1.0
                pos = path.pointAtPercent(t)
                g = QRadialGradient(pos, 9)
                g.setColorAt(0, _c(accent, 0.9))
                g.setColorAt(1, _c(accent, 0.0))
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawEllipse(pos, 9, 9)
                p.setBrush(accent)
                p.drawEllipse(pos, 2.2, 2.2)
        from ui.widgets.brand import paint_chip
        chip_sz = 64
        p.setBrush(_c(self._col("card", "#13161b")))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(cx - chip_sz / 2 + 4, h / 2 - chip_sz / 2 + 4, chip_sz - 8, chip_sz - 8))
        paint_chip(p, QRectF(cx - chip_sz / 2, h / 2 - chip_sz / 2, chip_sz, chip_sz), self._col("logo", "#e8eaed"))
        self._wordmark(p, 26, "Windows PC diagnostics and optimization")

    def _paint_galaxy(self, p):
        w, h = float(self.width()), float(BANNER_HEIGHT)
        pulse = 0.8 + 0.2 * math.sin(self._phase / 6.0 * math.pi)
        for (cx, cy, rx, ry, col, a) in ((w * 0.78, h * 0.4, 300, 110, "#7c3aed", 0.27),
                                          (w * 0.30, h * 0.8, 260, 100, "#06b6d4", 0.17)):
            p.save()
            p.translate(cx, cy)
            p.scale(1.0, ry / rx)
            g = QRadialGradient(QPointF(0, 0), rx)
            g.setColorAt(0, _c(col, a * pulse))
            g.setColorAt(1, _c(col, 0.0))
            p.setBrush(g)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(0, 0), rx, rx)
            p.restore()
        shift = (self._phase * 11.0)
        p.setPen(Qt.NoPen)
        cols = {"w": "#ffffff", "v": "#c4b5fd", "c": "#a5f3fc"}
        for (sx, sy, r, a, k) in self._stars:
            x = (sx * w - shift * (0.4 + r / 2.0)) % w
            p.setBrush(_c(cols[k], a))
            p.drawEllipse(QPointF(x, sy * h), r / 2 + 0.2, r / 2 + 0.2)
        self._wordmark(p, 26, "Windows PC diagnostics and optimization")

    def _paint_wave(self, p):
        w, h = float(self.width()), float(BANNER_HEIGHT)
        now = time.monotonic()
        pts = trim_wave(self._wave, now)
        self._wordmark(p, 26, "CPU load · last 60 s" if pts else "CPU load · Unavailable")
        if len(pts) < 2:
            if not pts:
                f = QFont(self.font())
                f.setPixelSize(13)
                p.setFont(f)
                p.setPen(_c(self._col("subtext", "#9aa0a6")))
                p.drawText(QRectF(w * 0.4, 0, w * 0.55, h), Qt.AlignRight | Qt.AlignVCenter, "Unavailable")
            return
        x0, x1 = w * 0.38, w - 16
        top, bot = 14.0, h - 14.0
        def pos(t, v):
            x = x1 - (now - t) / WAVE_SECONDS * (x1 - x0)
            y = bot - (max(0.0, min(100.0, v)) / 100.0) * (bot - top)
            return QPointF(x, y)
        P = [pos(t, v) for t, v in pts]
        path = QPainterPath(P[0])
        for a, b in zip(P, P[1:]):
            mx = (a.x() + b.x()) / 2
            path.cubicTo(QPointF(mx, a.y()), QPointF(mx, b.y()), b)
        accent = _c(self._col("accent", "#4da3ff"))
        area = QPainterPath(path)
        area.lineTo(P[-1].x(), h)
        area.lineTo(P[0].x(), h)
        area.closeSubpath()
        g = QLinearGradient(0, top, 0, h)
        g.setColorAt(0, _c(accent, 0.28))
        g.setColorAt(1, _c(accent, 0.02))
        p.fillPath(area, g)
        p.setPen(QPen(_c(accent, 0.95), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
