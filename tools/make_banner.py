"""Builds assets/brand/banner.png (the README banner): the app's own chip logo (same drawing as the
sidebar and splash, ui.widgets.brand.paint_chip) next to the ReTweaks wordmark, centered.
Run: python tools/make_banner.py   (works offscreen, any OS)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt                      # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QImage, QPainter  # noqa: E402

from core.version import BRAND                             # noqa: E402
from ui.widgets.brand import LOGO_COLOR, paint_chip         # noqa: E402

W, H = 2000, 600
BG = "#0b0d10"
CHIP = 380          # logo box size
GAP = 70            # space between logo and wordmark


def build(path):
    app = QGuiApplication.instance() or QGuiApplication([])
    img = QImage(W, H, QImage.Format_ARGB32)
    img.fill(QColor(BG))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    f = QFont("DejaVu Sans")
    f.setPixelSize(176)
    f.setBold(True)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 6)
    fm = QFontMetricsF(f)
    text_w = fm.horizontalAdvance(BRAND)
    total = CHIP + GAP + text_w
    x0 = (W - total) / 2
    paint_chip(p, QRectF(x0, (H - CHIP) / 2, CHIP, CHIP), color=LOGO_COLOR)
    p.setFont(f)
    p.setPen(QColor(LOGO_COLOR))
    # optical centre: put the cap height in the middle of the banner
    cap = fm.capHeight()
    baseline = H / 2 + cap / 2
    p.drawText(int(x0 + CHIP + GAP), int(baseline), BRAND)
    p.end()
    img.save(path)
    return path


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "brand", "banner.png")
    print(build(out))
