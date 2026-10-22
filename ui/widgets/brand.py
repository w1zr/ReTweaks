# ui/widgets/brand.py
"""The RYTWEAKS chip logo, drawn with QPainter so it stays sharp at every size.

Geometry matches assets/brand/logo-chip.svg (a 120 x 120 viewBox): a rounded chip outline,
12 pins (3 per side) and a stylized R. The logo is always grey/white, whatever the theme
(owner decision 2026-10-21).
"""

import math

from PySide6.QtCore import QEasingCurve, QElapsedTimer, QPointF, QRectF, Qt, QTimer, Property, QPropertyAnimation
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

LOGO_COLOR = "#e8eaed"
_current = {"logo": LOGO_COLOR}


def set_logo_color(color):
    """Called by MainWindow when the theme changes (dark on the Light theme, grey/white otherwise)."""
    _current["logo"] = color or LOGO_COLOR


def logo_color():
    return _current["logo"]

# Pins: (x1, y1, x2, y2) in viewBox units; order = top L→R, right T→B, bottom R→L, left B→T
PINS = [
    (42, 12, 42, 22), (60, 12, 60, 22), (78, 12, 78, 22),
    (98, 42, 108, 42), (98, 60, 108, 60), (98, 78, 108, 78),
    (78, 98, 78, 108), (60, 98, 60, 108), (42, 98, 42, 108),
    (12, 78, 22, 78), (12, 60, 22, 60), (12, 42, 22, 42),
]


def chip_outline_path():
    p = QPainterPath()
    p.addRoundedRect(QRectF(26, 26, 68, 68), 14, 14)
    return p


def r_path():
    """M 48 78 L 48 42 L 62 42 Q 72 42 72 52 Q 72 61 62 61 L 48 61 M 60 61 L 73 78"""
    p = QPainterPath()
    p.moveTo(48, 78)
    p.lineTo(48, 42)
    p.lineTo(62, 42)
    p.quadTo(72, 42, 72, 52)
    p.quadTo(72, 61, 62, 61)
    p.lineTo(48, 61)
    p.moveTo(60, 61)
    p.lineTo(73, 78)
    return p


def partial_path(path, fraction):
    """The first `fraction` (0..1) of a path's length, for the 'drawing' effect."""
    if fraction >= 1:
        return path
    if fraction <= 0:
        return QPainterPath()
    out = QPainterPath()
    total = path.length()
    target = total * fraction
    steps = max(8, int(160 * fraction))
    # moveTo gaps (the R's leg) count as zero length, so sample points and break on jumps
    last = None
    for s in range(steps + 1):
        length = target * s / steps
        pt = path.pointAtPercent(path.percentAtLength(length))
        if last is None or math.hypot(pt.x() - last.x(), pt.y() - last.y()) > 6:
            out.moveTo(pt)
        else:
            out.lineTo(pt)
        last = pt
    return out


def paint_chip(painter, rect, color=LOGO_COLOR, chip=1.0, pins=None, r=1.0, scan=None,
               stroke_scale=1.0, pin_colors=None):
    """Draw the chip logo into rect (square-ish).

    chip: 0..1 how much of the outline is drawn. pins: list of 12 opacities (None = all 1).
    r: 0..1 how much of the R is traced. scan: None or 0..1 vertical scan-line position.
    pin_colors: optional list of 12 QColor/hex to color pins individually (Health Check).
    """
    size = min(rect.width(), rect.height())
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(rect.x() + (rect.width() - size) / 2, rect.y() + (rect.height() - size) / 2)
    painter.scale(size / 120.0, size / 120.0)
    base = QColor(color)

    def pen(width, c=base, alpha=1.0):
        c = QColor(c)
        c.setAlphaF(max(0.0, min(1.0, alpha)) * c.alphaF())
        p = QPen(c, width * stroke_scale)
        p.setCapStyle(Qt.RoundCap)
        p.setJoinStyle(Qt.RoundJoin)
        return p

    painter.setBrush(Qt.NoBrush)
    if chip > 0:
        painter.setPen(pen(5))
        painter.drawPath(partial_path(chip_outline_path(), chip))
    for i, (x1, y1, x2, y2) in enumerate(PINS):
        a = 1.0 if pins is None else pins[i]
        if a <= 0:
            continue
        c = base if not pin_colors else QColor(pin_colors[i])
        painter.setPen(pen(4, c, a))
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    if scan is not None and 0 <= scan <= 1:
        y = 32 + 56 * scan
        painter.setPen(pen(2, base, 0.9))
        painter.drawLine(QPointF(32, y), QPointF(88, y))
    if r > 0:
        painter.setPen(pen(6))
        painter.drawPath(partial_path(r_path(), r))
    painter.restore()


def chip_pixmap(size, background=None, dpr=1.0):
    """A finished logo as a pixmap (About page, empty states, icon generation)."""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    if background:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(background))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    pad = size * 0.04 if background else 0
    paint_chip(p, QRectF(pad, pad, size - 2 * pad, size - 2 * pad))
    p.end()
    return pm


class ChipLogo(QWidget):
    """Static logo widget. color=None follows the theme's logo color."""

    def __init__(self, size=96, color=None, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        paint_chip(p, QRectF(self.rect()), self._color or logo_color())
        p.end()


class ChipLoader(QWidget):
    """Mini chip with a looping scan line. Only show it while real work is running:
    call start() when the work begins and stop() when the real result arrives."""

    def __init__(self, size=22, parent=None, color=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = color
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self.update)
        self.hide()

    def start(self):
        self._clock.restart()
        self._timer.start()
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def is_running(self):
        return self._timer.isActive()

    def paintEvent(self, _):
        p = QPainter(self)
        t = (self._clock.elapsed() % 1100) / 1100.0 if self._clock.isValid() else 0
        scan = 0.5 - 0.5 * math.cos(t * 2 * math.pi)
        paint_chip(p, QRectF(self.rect()), self._color or logo_color(), r=0.0, scan=scan, stroke_scale=1.6,
                   pins=[0.35 + 0.65 * (abs(((i / 12) - t + 1) % 1 - 0.5) < 0.12) for i in range(12)])
        p.end()


class EmptyState(QWidget):
    """A faint chip outline and one helpful line, for lists with nothing in them yet."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 24)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignCenter)
        self.logo = _FaintChip()
        lay.addWidget(self.logo, 0, Qt.AlignCenter)
        self.text = QLabel(text)
        self.text.setObjectName("muted")
        self.text.setAlignment(Qt.AlignCenter)
        self.text.setWordWrap(True)
        lay.addWidget(self.text)

    def set_text(self, text):
        self.text.setText(text)


class _FaintChip(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(56, 56)

    def paintEvent(self, _):
        p = QPainter(self)
        c = QColor(logo_color())
        c.setAlphaF(0.22)
        paint_chip(p, QRectF(self.rect()), c, r=0.0, stroke_scale=0.8)
        p.end()


# ------------------------------------------------------------------ thin-line nav icons

def _icon_paths():
    """24 x 24 line icons for the sidebar pages, keyed by page label."""
    def P():
        return QPainterPath()

    icons = {}

    p = P()  # Dashboard: 4 tiles
    for r in ((3, 3, 8, 8), (13, 3, 8, 5), (13, 10, 8, 11), (3, 13, 8, 8)):
        p.addRoundedRect(QRectF(*r), 2, 2)
    icons["Dashboard"] = p

    p = P()  # Hardware: small chip
    p.addRoundedRect(QRectF(6, 6, 12, 12), 3, 3)
    for x in (9, 12, 15):
        p.moveTo(x, 3); p.lineTo(x, 6); p.moveTo(x, 18); p.lineTo(x, 21)
        p.moveTo(3, x); p.lineTo(6, x); p.moveTo(18, x); p.lineTo(21, x)
    icons["Hardware"] = p

    p = P()  # Health Check: pulse line
    p.moveTo(2, 12); p.lineTo(7, 12); p.lineTo(9, 7); p.lineTo(13, 17); p.lineTo(15, 12); p.lineTo(22, 12)
    icons["Health Check"] = p

    p = P()  # FPS test: gauge
    p.arcMoveTo(QRectF(3, 5, 18, 18), 180); p.arcTo(QRectF(3, 5, 18, 18), 180, -180)
    p.moveTo(12, 14); p.lineTo(16.5, 9.5)
    icons["FPS test"] = p

    p = P()  # Display & drivers: monitor
    p.addRoundedRect(QRectF(3, 4, 18, 12), 2, 2)
    p.moveTo(9, 20); p.lineTo(15, 20); p.moveTo(12, 16); p.lineTo(12, 20)
    icons["Display & drivers"] = p

    p = P()  # Tweaks: sliders
    p.moveTo(4, 7); p.lineTo(13.8, 7); p.moveTo(18.2, 7); p.lineTo(20, 7)
    p.addEllipse(QPointF(16, 7), 2.2, 2.2)
    p.moveTo(4, 17); p.lineTo(7.8, 17); p.moveTo(12.2, 17); p.lineTo(20, 17)
    p.addEllipse(QPointF(10, 17), 2.2, 2.2)
    icons["Tweaks"] = p

    p = P()  # Profiles: stacked layers
    p.moveTo(12, 3); p.lineTo(21, 8); p.lineTo(12, 13); p.lineTo(3, 8); p.closeSubpath()
    p.moveTo(3, 12.5); p.lineTo(12, 17.5); p.lineTo(21, 12.5)
    p.moveTo(3, 16.5); p.lineTo(12, 21.5); p.lineTo(21, 16.5)
    icons["Profiles"] = p

    p = P()  # Game presets: controller
    p.addRoundedRect(QRectF(2.5, 7, 19, 11), 5.5, 5.5)
    p.moveTo(7, 10.5); p.lineTo(7, 14.5); p.moveTo(5, 12.5); p.lineTo(9, 12.5)
    p.addEllipse(QPointF(16, 11.5), 0.9, 0.9); p.addEllipse(QPointF(18, 13.5), 0.9, 0.9)
    icons["Game presets"] = p

    p = P()  # Program rules: list with checks
    for y in (6, 12, 18):
        p.moveTo(4, y); p.lineTo(5.5, y + 1.5); p.lineTo(8, y - 1.5)
        p.moveTo(11, y); p.lineTo(20, y)
    icons["Program rules"] = p

    p = P()  # Startup apps: power
    p.arcMoveTo(QRectF(4, 5, 16, 16), 55); p.arcTo(QRectF(4, 5, 16, 16), 55, 290)
    p.moveTo(12, 3); p.lineTo(12, 11)
    icons["Startup apps"] = p

    p = P()  # Network: globe-ish signal bars
    for i, h in enumerate((5, 9, 13, 17)):
        x = 5 + i * 4.5
        p.moveTo(x, 20); p.lineTo(x, 20 - h)
    icons["Network"] = p

    p = P()  # Storage: drive
    p.addRoundedRect(QRectF(3, 6, 18, 12), 3, 3)
    p.moveTo(3, 12); p.lineTo(21, 12)
    p.addEllipse(QPointF(17, 15), 0.8, 0.8)
    icons["Storage & cleanup"] = p

    p = P()  # Audio mixer: speaker
    p.moveTo(4, 9.5); p.lineTo(8, 9.5); p.lineTo(12.5, 5.5); p.lineTo(12.5, 18.5); p.lineTo(8, 14.5)
    p.lineTo(4, 14.5); p.closeSubpath()
    p.arcMoveTo(QRectF(12, 8, 8, 8), 60); p.arcTo(QRectF(12, 8, 8, 8), 60, -120)
    icons["Audio mixer"] = p

    p = P()  # Auto clicker: cursor
    p.moveTo(6, 4); p.lineTo(6, 19); p.lineTo(10, 15); p.lineTo(13, 21); p.lineTo(15.5, 20)
    p.lineTo(12.5, 14); p.lineTo(18, 14); p.closeSubpath()
    icons["Auto clicker"] = p

    p = P()  # AI Assistant: chat bubble
    p.addRoundedRect(QRectF(3, 4, 18, 13), 4, 4)
    p.moveTo(8, 17); p.lineTo(7, 21); p.lineTo(12, 17)
    icons["AI Assistant"] = p

    p = P()  # Snapshots: camera
    p.addRoundedRect(QRectF(3, 7, 18, 13), 3, 3)
    p.moveTo(8, 7); p.lineTo(9.5, 4.5); p.lineTo(14.5, 4.5); p.lineTo(16, 7)
    p.addEllipse(QPointF(12, 13.5), 3.5, 3.5)
    icons["Snapshots"] = p

    p = P()  # Fun tools: star-ish sparkle
    p.moveTo(12, 3); p.lineTo(12, 21); p.moveTo(3, 12); p.lineTo(21, 12)
    p.moveTo(6, 6); p.lineTo(18, 18); p.moveTo(18, 6); p.lineTo(6, 18)
    icons["Fun tools"] = p

    p = P()  # Logs: document
    p.addRoundedRect(QRectF(5, 3, 14, 18), 2.5, 2.5)
    for y in (8, 12, 16):
        p.moveTo(8, y); p.lineTo(16, y)
    icons["Logs"] = p

    p = P()  # About: info circle
    p.addEllipse(QPointF(12, 12), 9, 9)
    p.moveTo(12, 11); p.lineTo(12, 16.5)
    p.addEllipse(QPointF(12, 7.8), 0.6, 0.6)
    icons["About"] = p

    p = P()  # Settings: gear (circle + spokes)
    p.addEllipse(QPointF(12, 12), 3.2, 3.2)
    for k in range(8):
        a = k * math.pi / 4
        p.moveTo(12 + 6 * math.cos(a), 12 + 6 * math.sin(a))
        p.lineTo(12 + 9 * math.cos(a), 12 + 9 * math.sin(a))
    p.addEllipse(QPointF(12, 12), 6, 6)
    icons["Settings"] = p
    return icons


_ICONS = None


def nav_icon(name, color, size=18, dpr=2.0):
    """A thin-line monochrome QIcon for a sidebar page (None if there's no drawing for it)."""
    global _ICONS
    if _ICONS is None:
        _ICONS = _icon_paths()
    path = _ICONS.get(name)
    if path is None:
        return None
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(size / 24.0, size / 24.0)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


def nav_icon_names():
    global _ICONS
    if _ICONS is None:
        _ICONS = _icon_paths()
    return list(_ICONS)


def galaxy_backdrop_path():
    """A starfield tile for the Galaxy theme, generated once (fixed seed, so it's always the same)."""
    import os
    import random
    from pathlib import Path
    from PySide6.QtGui import QImage, QRadialGradient
    folder = Path(os.getenv("APPDATA") or Path.home()) / "RYTWEAKS"
    path = folder / "galaxy_backdrop_v1.png"
    if path.exists():
        return str(path)
    folder.mkdir(parents=True, exist_ok=True)
    w, h = 1200, 800
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(QColor("#0c0a1d"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    for cx, cy, rx, col, a in ((0.85, 0.05, 520, "#7c3aed", 0.22), (0.05, 0.95, 460, "#06b6d4", 0.12)):
        g = QRadialGradient(QPointF(w * cx, h * cy), rx)
        c = QColor(col)
        c.setAlphaF(a)
        g.setColorAt(0, c)
        c2 = QColor(col)
        c2.setAlphaF(0)
        g.setColorAt(1, c2)
        p.fillRect(img.rect(), g)
    rnd = random.Random(1404)
    p.setPen(Qt.NoPen)
    for _ in range(170):
        c = QColor(rnd.choice(["#ffffff", "#ffffff", "#c4b5fd", "#a5f3fc"]))
        c.setAlphaF(rnd.uniform(0.25, 0.8))
        p.setBrush(c)
        r = rnd.choice([0.6, 0.8, 1.0, 1.3])
        p.drawEllipse(QPointF(rnd.uniform(0, w), rnd.uniform(0, h)), r, r)
    p.end()
    img.save(str(path), "PNG")
    return str(path)
