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

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ui.widgets.brand import paint_chip  # noqa: E402

SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
BACKGROUND = None   # transparent chip, no tile behind it (owner choice 2026-10-21); was "#0b0d10"


def render(size):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    if BACKGROUND:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(BACKGROUND))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    if size <= 24:
        # No pins; zoom so the chip outline fills the icon, and thicken the strokes
        grow = size * 0.42
        paint_chip(p, QRectF(-grow, -grow, size + 2 * grow, size + 2 * grow), pins=[0] * 12,
                   stroke_scale=1.3 if size > 16 else 1.2)
    elif size <= 48:
        grow = size * 0.12
        paint_chip(p, QRectF(-grow, -grow, size + 2 * grow, size + 2 * grow), stroke_scale=1.3)
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


def write_ico(path, sizes=SIZES):
    images = [(s, png_bytes(render(s))) for s in sizes]
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
    print(f"Chip icon saved to {out} ({', '.join(str(s) for s in SIZES)} px)")


if __name__ == "__main__":
    generate_icon()
