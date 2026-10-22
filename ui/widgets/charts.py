# ui/widgets/charts.py
"""Live line graph and metric card, drawn with QPainter (no chart library needed)."""

from collections import deque

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QSizePolicy, QWidget

from ui.widgets.common import Card, label, NA, NA_TIP

HISTORY_SECONDS = 60


class Sparkline(QWidget):
    """Rolling line graph of the last 60 values (one per second)."""

    def __init__(self, maximum=100.0, parent=None):
        super().__init__(parent)
        self.values = deque(maxlen=HISTORY_SECONDS)
        self.maximum = maximum      # None = auto-scale (network/disk speeds)
        self.color = QColor("#8b95a5")
        self.grid_color = QColor("#262b33")
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(64)

    def set_colors(self, line, grid):
        self.color, self.grid_color = QColor(line), QColor(grid)
        self.update()

    def add(self, value):
        self.values.append(value)  # None leaves a gap
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 4, -1, -2)

        p.setPen(QPen(self.grid_color, 1, Qt.DashLine))
        for frac in (0.0, 0.5, 1.0):
            y = r.top() + r.height() * frac
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))

        nums = [v for v in self.values if v is not None]
        if not nums:
            return
        top = self.maximum or max(max(nums) * 1.2, 1.0)
        step = r.width() / max(HISTORY_SECONDS - 1, 1)
        offset = HISTORY_SECONDS - len(self.values)

        def pt(i, v):
            v = max(0.0, min(v, top))
            return QPointF(r.left() + (offset + i) * step, r.bottom() - (v / top) * r.height())

        # Split into segments at gaps (None)
        segments, cur = [], []
        for i, v in enumerate(self.values):
            if v is None:
                if cur:
                    segments.append(cur)
                cur = []
            else:
                cur.append(pt(i, v))
        if cur:
            segments.append(cur)

        fill_top = QColor(self.color)
        fill_top.setAlpha(70)
        fill_bottom = QColor(self.color)
        fill_bottom.setAlpha(0)
        grad = QLinearGradient(0, r.top(), 0, r.bottom())
        grad.setColorAt(0, fill_top)
        grad.setColorAt(1, fill_bottom)

        for seg in segments:
            line = QPainterPath(seg[0])
            for q in seg[1:]:
                line.lineTo(q)
            area = QPainterPath(line)
            area.lineTo(seg[-1].x(), r.bottom())
            area.lineTo(seg[0].x(), r.bottom())
            area.closeSubpath()
            p.fillPath(area, grad)
            p.setPen(QPen(self.color, 2))
            p.drawPath(line)


class MetricCard(Card):
    """Dashboard card: title, big number, a bar, a 60 s graph and detail lines."""

    def __init__(self, title, maximum=100.0, show_bar=True, parent=None):
        super().__init__(title, parent)
        top = QHBoxLayout()
        self.value = label("…", "bigValue")
        self.side = label("", "cardLine")
        self.side.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.value)
        top.addStretch()
        top.addWidget(self.side)
        self.body.addLayout(top)

        self.bar = None
        if show_bar:
            self.bar = QProgressBar()
            self.bar.setRange(0, 100)
            self.bar.setTextVisible(False)
            self.bar.setFixedHeight(6)
            self.body.addWidget(self.bar)

        self.graph = Sparkline(maximum)
        self.body.addWidget(self.graph)
        self.lines = label("", "cardLine")
        self.lines.setTextFormat(Qt.PlainText)
        self.body.addWidget(self.lines)

    def set_value(self, number, text=None, graph_value="same"):
        """number drives the bar (0-100); text is what's printed. None = not available."""
        if number is None and text is None:
            self.value.setText(NA)
            self.value.setToolTip(NA_TIP)
        else:
            self.value.setText(text if text is not None else f"{number:.0f}%")
            self.value.setToolTip("")
        if self.bar is not None:
            self.bar.setValue(int(round(number)) if number is not None else 0)
        self.graph.add(number if graph_value == "same" else graph_value)

    def set_lines(self, lines):
        self.lines.setText("\n".join(lines))

    def set_theme(self, theme):
        self.graph.set_colors(theme["accent"], theme["border"])
