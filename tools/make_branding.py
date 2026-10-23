"""Builds the RETWEAKS logo images the Tk app uses (assets/chip-*.png, assets/chip-scan-*.png).

The chip is drawn with the same code as the original RETWEAKS app (ui.widgets.brand.paint_chip), so
it matches assets/icon.ico, assets/taskbar.ico and the README banner. Small sizes come straight from
assets/taskbar.ico (drawn on the pixel grid). Needs PySide6 and Pillow; runs offscreen on any OS.
    python tools/make_branding.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image                                                  # noqa: E402
from PySide6.QtCore import QRectF, Qt                                  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter            # noqa: E402

from PySide6.QtCore import QPointF                                     # noqa: E402
from PySide6.QtGui import QColor, QPainterPath, QPen                   # noqa: E402

from ui.widgets import brand                                           # noqa: E402
from ui.widgets.brand import LOGO_COLOR, paint_chip                    # noqa: E402

ASSETS = os.path.join(ROOT, "assets")
FRAMES = 21          # the startup screen steps through chip-scan-0 .. chip-scan-20


def _render(size, **kw):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    paint_chip(p, QRectF(0, 0, size, size), color=LOGO_COLOR, **kw)
    p.end()
    return img


def _ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _extra_icons():
    """Thin-line icons for the original pages, in the same 24x24 style as RETWEAKS' sidebar icons."""
    icons = {}

    def P():
        return QPainterPath()

    p = P()   # Benchmark: bar chart
    for i, h in enumerate((7, 12, 16)):
        x = 5 + i * 6
        p.addRoundedRect(QRectF(x, 20 - h, 3.5, h), 1, 1)
    p.moveTo(3, 21); p.lineTo(21, 21)
    icons["Benchmark"] = p
    p = P()   # Bottleneck: funnel
    p.moveTo(3, 5); p.lineTo(21, 5); p.lineTo(14, 13); p.lineTo(14, 20); p.lineTo(10, 18); p.lineTo(10, 13)
    p.closeSubpath()
    icons["Bottleneck"] = p
    p = P()   # 3D PC Builder: cube
    p.moveTo(12, 3); p.lineTo(20, 7.5); p.lineTo(20, 16.5); p.lineTo(12, 21); p.lineTo(4, 16.5); p.lineTo(4, 7.5)
    p.closeSubpath(); p.moveTo(4, 7.5); p.lineTo(12, 12); p.lineTo(20, 7.5); p.moveTo(12, 12); p.lineTo(12, 21)
    icons["3D PC Builder"] = p
    p = P()   # Windows tweaks: four panes
    for r in ((3, 3, 8.5, 8.5), (12.5, 3, 8.5, 8.5), (3, 12.5, 8.5, 8.5), (12.5, 12.5, 8.5, 8.5)):
        p.addRoundedRect(QRectF(*r), 1.5, 1.5)
    icons["Windows tweaks"] = p
    p = P()   # Drivers: download into tray
    p.moveTo(12, 3); p.lineTo(12, 14); p.moveTo(7.5, 9.5); p.lineTo(12, 14); p.lineTo(16.5, 9.5)
    p.moveTo(4, 15); p.lineTo(4, 20); p.lineTo(20, 20); p.lineTo(20, 15)
    icons["Drivers"] = p
    p = P()   # App Starter: grid of apps
    for x in (4, 10.5, 17):
        for y in (4, 10.5, 17):
            p.addRoundedRect(QRectF(x - 1.5, y - 1.5, 4, 4), 1, 1)
    icons["App Starter"] = p
    p = P()   # PC Value Checker: price tag
    p.moveTo(3, 12); p.lineTo(12, 3); p.lineTo(21, 3); p.lineTo(21, 12); p.lineTo(12, 21); p.closeSubpath()
    p.addEllipse(QPointF(16.5, 7.5), 1.4, 1.4)
    icons["PC Value Checker"] = p
    p = P()   # Daily Tools: wrench
    p.moveTo(14.5, 4); p.arcTo(QRectF(13, 3.5, 7.5, 7.5), 150, -300)
    p.moveTo(14.5, 9.5); p.lineTo(4.5, 19.5)
    icons["Daily Tools"] = p
    p = P()   # Tools: toolbox
    p.addRoundedRect(QRectF(3, 8, 18, 12), 2, 2)
    p.moveTo(9, 8); p.lineTo(9, 5); p.lineTo(15, 5); p.lineTo(15, 8); p.moveTo(3, 13); p.lineTo(21, 13)
    icons["Tools"] = p
    p = P()   # Backups & fixes: circular arrow
    p.arcMoveTo(QRectF(4, 4, 16, 16), 90); p.arcTo(QRectF(4, 4, 16, 16), 90, 280)
    p.moveTo(12, 4); p.lineTo(8.5, 1.5); p.moveTo(12, 4); p.lineTo(8.5, 6.8)
    icons["Backups & fixes"] = p
    p = P()   # Appearance: palette
    p.addEllipse(QPointF(12, 12), 9, 9)
    for (x, y) in ((8, 9), (12, 7), (16, 9), (16.5, 13.5)):
        p.addEllipse(QPointF(x, y), 1.1, 1.1)
    icons["Appearance"] = p
    p = P()   # Help: question mark in circle
    p.addEllipse(QPointF(12, 12), 9, 9)
    p.moveTo(9.3, 9.5); p.arcTo(QRectF(9.3, 6.5, 5.4, 5.4), 180, -220); p.lineTo(12, 13.8)
    p.addEllipse(QPointF(12, 16.8), 0.6, 0.6)
    icons["Help"] = p
    p = P()   # Exact-undo tweaks: undo arrow
    p.moveTo(9, 5); p.lineTo(4, 10); p.lineTo(9, 15)
    p.moveTo(4, 10); p.lineTo(14, 10); p.arcTo(QRectF(8, 10, 12, 10), 90, -180); p.lineTo(10, 20)
    icons["Exact-undo tweaks"] = p
    p = P()   # Cleanup: trash can
    p.moveTo(4, 7); p.lineTo(20, 7); p.moveTo(9, 7); p.lineTo(10, 4); p.lineTo(14, 4); p.lineTo(15, 7)
    p.moveTo(6, 7); p.lineTo(7, 20); p.lineTo(17, 20); p.lineTo(18, 7); p.moveTo(10, 11); p.lineTo(10, 16)
    p.moveTo(14, 11); p.lineTo(14, 16)
    icons["Cleanup"] = p
    p = P()   # Game config files: document with a corner fold
    p.moveTo(6, 3); p.lineTo(14, 3); p.lineTo(19, 8); p.lineTo(19, 21); p.lineTo(6, 21); p.closeSubpath()
    p.moveTo(14, 3); p.lineTo(14, 8); p.lineTo(19, 8); p.moveTo(9, 13); p.lineTo(16, 13); p.moveTo(9, 17); p.lineTo(14, 17)
    icons["Game config files"] = p
    p = P()   # Crosshair: ring with four ticks and a centre dot
    p.addEllipse(QPointF(12, 12), 6.5, 6.5)
    for a, b in (((12, 2), (12, 7)), ((12, 17), (12, 22)), ((2, 12), (7, 12)), ((17, 12), (22, 12))):
        p.moveTo(*a); p.lineTo(*b)
    p.addEllipse(QPointF(12, 12), 0.9, 0.9)
    icons["Crosshair"] = p
    # pages added 2026-10-22
    p = P()   # Temperatures: thermometer
    p.moveTo(10, 15); p.lineTo(10, 5); p.arcTo(QRectF(10, 3, 4, 4), 180, -180); p.lineTo(14, 15)
    p.arcMoveTo(QRectF(7.5, 13.5, 9, 9), 61); p.arcTo(QRectF(7.5, 13.5, 9, 9), 61, 418)
    p.moveTo(12, 9); p.lineTo(12, 16)
    icons["Temperatures"] = p
    p = P()   # Fan control: three blades around a hub
    p.addEllipse(QPointF(12, 12), 2, 2)
    import math as _m
    for k in range(3):
        a0 = _m.radians(k * 120 - 90)
        a1 = a0 + _m.radians(55)
        x0, y0 = 12 + 2.5 * _m.cos(a0), 12 + 2.5 * _m.sin(a0)
        x1, y1 = 12 + 9 * _m.cos(a0 + _m.radians(20)), 12 + 9 * _m.sin(a0 + _m.radians(20))
        x2, y2 = 12 + 3 * _m.cos(a1), 12 + 3 * _m.sin(a1)
        p.moveTo(x0, y0); p.quadTo(12 + 9.5 * _m.cos(a0 - _m.radians(15)), 12 + 9.5 * _m.sin(a0 - _m.radians(15)), x1, y1)
        p.quadTo(12 + 6 * _m.cos(a1), 12 + 6 * _m.sin(a1), x2, y2)
    p.addEllipse(QPointF(12, 12), 10, 10)
    icons["Fan control"] = p
    p = P()   # RGB lighting: three overlapping circles
    for (x, y) in ((12, 8.5), (8.5, 14.5), (15.5, 14.5)):
        p.addEllipse(QPointF(x, y), 5, 5)
    icons["RGB lighting"] = p
    p = P()   # Run: window with a play arrow
    p.addRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
    p.moveTo(3, 8); p.lineTo(21, 8)
    p.moveTo(10, 11); p.lineTo(15, 14); p.lineTo(10, 17); p.closeSubpath()
    icons["Run"] = p
    return icons


ICON_ALIASES = {
    "FPS overlay": "FPS test",            # page renamed 2026-10-22, same gauge icon   # sidebar name in the combined app -> RETWEAKS icon drawing
    "Presets": "Profiles", "Individual tweaks": "Tweaks", "Game profiles": "Game presets",
    "Display": "Display & drivers", "Storage": "Storage & cleanup", "AI assistant": "AI Assistant",
    "Activity": "Logs", "Audio Mixer": "Audio mixer",
    "PC specs": "Hardware", "Quick start": "Dashboard", "CTT library": "Tweaks", "Customize": "Appearance",
    "Advanced tools": "Tools", "Tips": "Help", "Notifications": "Logs",
}


def _save_icon(path, painter_path, size=18, scale=2):
    img = QImage(size * scale, size * scale, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size * scale / 24.0, size * scale / 24.0)
    pen = QPen(QColor("#ffffff"), 1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(painter_path)
    p.end()
    tmp = path + ".tmp.png"
    img.save(tmp)
    Image.open(tmp).resize((size, size), Image.LANCZOS).save(path)    # supersampled: crisp at 18 px
    os.remove(tmp)


def export_nav_icons():
    """assets/nav/<slug>.png: white line icons; the app tints them to the theme's colours."""
    out = os.path.join(ASSETS, "nav")
    os.makedirs(out, exist_ok=True)
    paths = dict(brand._icon_paths())
    paths.update(_extra_icons())
    for alias, src in ICON_ALIASES.items():
        paths[alias] = paths[src]
    for name, pp in paths.items():
        _save_icon(os.path.join(out, slug(name) + ".png"), pp)
    return sorted(paths)


def slug(name):
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


SPLASH_STRETCH = 1.7     # owner request 2026-10-22: the original animation, slower (1.4 s -> 2.4 s reveal)
SPLASH_FPS = 40


def export_splash():
    """assets/splash/reveal-NNN.png and loop-NNN.png: the chip part of the original RETWEAKS splash
    (ui/splash.py paintEvent, same timing curves, slowed down by SPLASH_STRETCH), 120 x 120, transparent.
    The Tk startup screen draws the rounded card, wordmark and status line itself and steps through
    these frames by real time."""
    from ui import splash as sp
    out = os.path.join(ASSETS, "splash")
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        os.remove(os.path.join(out, f))

    def frame(t, loop_k=None):
        pins = [sp._phase(t, (sp.PIN_START + i * sp.PIN_STEP, sp.PIN_START + i * sp.PIN_STEP + sp.PIN_FADE))
                for i in range(12)]
        pins = [0.12 + 0.88 * a for a in pins] if t > 0.05 else [0.0] * 12
        scan = None
        if loop_k is not None:
            scan = loop_k
        elif sp.SCAN[0] <= t <= sp.SCAN[1]:
            scan = sp._phase(t, sp.SCAN)
        return _render(120, chip=sp._phase(t, sp.CHIP), pins=pins, r=sp._phase(t, sp.R_TRACE), scan=scan)

    n = int(sp.REVEAL_END * SPLASH_STRETCH * SPLASH_FPS) + 1
    for i in range(n):
        t = min(sp.REVEAL_END, i / (SPLASH_FPS * SPLASH_STRETCH))
        frame(t).save(os.path.join(out, f"reveal-{i:03d}.png"))
    m = int(2 * sp.SCAN_LOOP * SPLASH_STRETCH * SPLASH_FPS)
    for i in range(m):
        k = (i / m) * 2
        frame(sp.REVEAL_END, k if k <= 1 else 2 - k).save(os.path.join(out, f"loop-{i:03d}.png"))
    import json
    with open(os.path.join(out, "timing.json"), "w") as f:
        json.dump({"fps": SPLASH_FPS, "stretch": SPLASH_STRETCH, "reveal_frames": n, "loop_frames": m,
                   "reveal_end": sp.REVEAL_END * SPLASH_STRETCH,
                   "word": [sp.WORD[0] * SPLASH_STRETCH, sp.WORD[1] * SPLASH_STRETCH],
                   "hold": sp.HOLD, "fade": sp.FADE, "bg": sp.BG, "border": sp.BORDER,
                   "subtext": sp.SUBTEXT, "logo": LOGO_COLOR}, f, indent=1)
    return n, m


def main():
    QGuiApplication.instance() or QGuiApplication([])
    ico = Image.open(os.path.join(ASSETS, "taskbar.ico"))
    for size in (16, 32, 40, 48, 96, 256):
        out = os.path.join(ASSETS, f"chip-{size}.png")
        # owner request 2026-10-22: the logo is transparent (no dark square behind it)
        _render(size).save(out)
    # Startup animation, like the original RETWEAKS splash: the outline draws, the pins light up one
    # after another, a scan line sweeps and the R traces in.
    for i in range(FRAMES):
        t = i / (FRAMES - 1)
        chip = _ease(t / 0.35)
        pins = [_ease((t - 0.25 - k * 0.025) / 0.12) for k in range(12)]
        r = _ease((t - 0.62) / 0.33)
        scan = (t - 0.3) / 0.6 if 0.3 <= t <= 0.9 else None
        _render(112, chip=chip, pins=pins, r=r, scan=scan).save(os.path.join(ASSETS, f"chip-scan-{i}.png"))
    names = export_nav_icons()
    n, m = export_splash()
    print("Splash frames:", n, "reveal +", m, "loop")
    print("Wrote chip-*.png, chip-scan-*.png and", len(names), "sidebar icons to", ASSETS)


if __name__ == "__main__":
    main()
