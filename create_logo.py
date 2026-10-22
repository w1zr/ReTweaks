# create_logo.py
"""Builds assets/icon.ico (the chip logo) at every Windows icon size.

Run: python create_logo.py   (works on any OS; only PySide6 is needed)

Each size is drawn separately instead of shrinking one big image, so the small
sizes stay crisp: at 16-24 px the pins are dropped and the lines get thicker.
The .ico stores PNG images, which Windows Vista and newer read at every size.
"""

import os
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ui.widgets.brand import paint_chip  # noqa: E402

SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
BACKGROUND = "#0b0d10"


def _small_chip(p, size):
    """16-48 px: the chip redrawn for the pixel grid instead of shrunk.

    The outline stays fully inside the tile, line widths are whole-ish pixels, and the R is
    centered in the chip, so nothing gets cut off or smeared (the old version zoomed the big
    logo, which pushed the outline past the edge at 16-24 px).
    """
    from PySide6.QtGui import QPen
    from ui.widgets.brand import LOGO_COLOR, r_path
    color = QColor(LOGO_COLOR)
    w = 1.5 if size <= 24 else (2.0 if size <= 40 else 2.5)   # crisp, never blobby
    pins = size >= 32
    margin = size * (0.22 if pins else 0.13)          # leave room for the pins at 32 px and up
    half = w / 2
    box = QRectF(margin + half, margin + half, size - 2 * margin - w, size - 2 * margin - w)
    pen = QPen(color, w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(box, box.width() * 0.2, box.width() * 0.2)
    if pins:
        pin_pen = QPen(color, 1.5 if size <= 40 else 2.0)
        pin_pen.setCapStyle(Qt.RoundCap)
        p.setPen(pin_pen)
        inner = box.width()
        for k in (0.25, 0.5, 0.75):
            c = box.left() + inner * k
            d = box.top() + inner * k
            p.drawLine(QPointF(c, box.top() - half - 1), QPointF(c, max(1.0, box.top() - margin * 0.75)))
            p.drawLine(QPointF(c, box.bottom() + half + 1), QPointF(c, min(size - 1.0, box.bottom() + margin * 0.75)))
            p.drawLine(QPointF(box.left() - half - 1, d), QPointF(max(1.0, box.left() - margin * 0.75), d))
            p.drawLine(QPointF(box.right() + half + 1, d), QPointF(min(size - 1.0, box.right() + margin * 0.75), d))
    # The R: the logo's own path (48..73 x 42..78 in the 120 grid), fitted inside the chip
    r = r_path()
    rb = QRectF(48, 42, 25, 36)
    pad_r = max(w * 1.6, box.width() * 0.2)
    room = box.adjusted(pad_r, pad_r, -pad_r, -pad_r)
    scale = min(room.width() / rb.width(), room.height() / rb.height())
    p.save()
    p.translate(room.center().x() - rb.center().x() * scale, room.center().y() - rb.center().y() * scale)
    p.scale(scale, scale)
    r_pen = QPen(color, w / scale)
    r_pen.setCapStyle(Qt.RoundCap)
    r_pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(r_pen)
    p.drawPath(r)
    p.restore()


def render_taskbar(size):
    """Window + taskbar icon. 24 px and up: the v1.4 drawing the owner prefers on the taskbar
    (chip zoomed to fill the tile). 16 and 20 px (the window title bar): the crisp pixel-grid
    drawing, because the zoomed one cuts the chip outline off at those sizes (owner report)."""
    if size < 24:
        return render(size)
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(BACKGROUND))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    if size <= 24:
        grow = size * 0.42
        paint_chip(p, QRectF(-grow, -grow, size + 2 * grow, size + 2 * grow), pins=[0] * 12,
                   stroke_scale=1.15 if size > 16 else 1.05)
    elif size <= 48:
        grow = size * 0.12
        paint_chip(p, QRectF(-grow, -grow, size + 2 * grow, size + 2 * grow), stroke_scale=1.2)
    else:
        pad = size * 0.04
        paint_chip(p, QRectF(pad, pad, size - 2 * pad, size - 2 * pad))
    p.end()
    return img


def render(size):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(BACKGROUND))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    if size <= 48:
        _small_chip(p, size)
    else:
        pad = size * 0.04
        paint_chip(p, QRectF(pad, pad, size - 2 * pad, size - 2 * pad))
    p.end()
    return img


def png_bytes(img):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(data)


def write_ico(path, sizes=SIZES, renderer=None):
    renderer = renderer or render
    images = [(s, png_bytes(renderer(s))) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for s, png in images:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blobs += png
    with open(path, "wb") as f:
        f.write(header + entries + blobs)
    return path


def generate_icon():
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    os.makedirs("assets", exist_ok=True)
    out = write_ico(os.path.join("assets", "icon.ico"))
    print(f"Chip icon (.exe, Explorer, shortcuts) saved to {out} ({', '.join(str(s) for s in SIZES)} px)")
    out = write_ico(os.path.join("assets", "taskbar.ico"), renderer=render_taskbar)
    print(f"Taskbar/window icon saved to {out}")


if __name__ == "__main__":
    generate_icon()
