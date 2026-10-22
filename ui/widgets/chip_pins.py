# ui/widgets/chip_pins.py
"""The RYTWEAKS chip logo with one pin per Health Check result."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

# Pin geometry from assets/brand/logo-chip.svg (120 x 120 viewBox), 12 pins:
_P = (42, 60, 78)
PINS = ([((x, 12), (x, 22)) for x in _P] + [((98, y), (108, y)) for y in _P] +
        [((x, 108), (x, 98)) for x in reversed(_P)] + [((22, y), (12, y)) for y in reversed(_P)])


class ChipPins(QWidget):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self._status = [None] * len(PINS)      # None = not run yet (muted)
        self._shown = [None] * len(PINS)       # color currently drawn
        self._anims = []
        self.setFixedSize(160, 160)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def sizeHint(self):
        return QSize(160, 160)

    def set_theme(self, theme):
        self.theme = theme
        self._shown = [self._color(s) for s in self._status]
        self.update()

    def _color(self, status):
        key = {"good": "good", "warn": "warn", "bad": "bad"}.get(status, "muted")
        return QColor(self.theme[key])

    def set_results(self, statuses):
        """statuses: list of 'good'|'warn'|'bad'|'unavailable'|None. Only pins whose result
        changed fade to the new color (~120 ms)."""
        new = (list(statuses) + [None] * len(PINS))[:len(PINS)]
        for i, s in enumerate(new):
            if s == self._status[i]:
                continue
            self._status[i] = s
            self._fade(i, self._color(s))

    def _fade(self, i, target):
        start = self._shown[i] or QColor(self.theme["muted"])
        anim = QVariantAnimation(self)
        anim.setDuration(120)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.valueChanged.connect(lambda c, i=i: self._set_shown(i, c))
        anim.finished.connect(lambda a=anim: self._anims.remove(a) if a in self._anims else None)
        self._anims.append(anim)
        anim.start()

    def _set_shown(self, i, color):
        self._shown[i] = QColor(color)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        p.translate((self.width() - side) / 2, (self.height() - side) / 2)
        p.scale(side / 120.0, side / 120.0)
        text = QColor(self.theme["text"])
        for i, (a, b) in enumerate(PINS):
            c = QColor(self._shown[i] or QColor(self.theme["muted"]))
            pen = QPen(c, 4, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(*a), QPointF(*b))
        pen = QPen(text, 5)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(26, 26, 68, 68), 14, 14)
        path = QPainterPath()
        path.moveTo(48, 78)
        path.lineTo(48, 42)
        path.lineTo(62, 42)
        path.quadTo(72, 42, 72, 52)
        path.quadTo(72, 61, 62, 61)
        path.lineTo(48, 61)
        path.moveTo(60, 61)
        path.lineTo(73, 78)
        p.setPen(QPen(text, 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.end()
