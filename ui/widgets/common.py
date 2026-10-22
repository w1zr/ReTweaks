# ui/widgets/common.py
"""Small building blocks shared by every page."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

NA = "Unavailable"
NA_TIP = ("Windows doesn't report this on this PC.\n"
          "Temperatures and fans need LibreHardwareMonitor running (see Settings).")


# ---------------------------------------------------------------- formatting

def fmt(value, unit="", digits=0, na=NA):
    """Format a number with a unit, or return the 'not available' text for None."""
    if value is None or value == "" or value == []:
        return na
    if isinstance(value, (int, float)):
        text = f"{value:.{digits}f}" if digits else f"{round(value):d}"
    else:
        text = str(value)
    return f"{text} {unit}".strip() if unit else text


# Temperature unit chosen in Settings ("C" or "F"); set by MainWindow
TEMP_UNIT = {"unit": "C"}


def temp_text(celsius, digits=0):
    """45.0 -> '45 °C' or '113 °F' depending on Settings. None -> None."""
    if celsius is None:
        return None
    if TEMP_UNIT["unit"] == "F":
        return f"{celsius * 9 / 5 + 32:.{digits}f} °F"
    return f"{celsius:.{digits}f} °C"


def fmt_rate(bps):
    """Bytes per second -> '12.3 MB/s'."""
    if bps is None:
        return NA
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024 or unit == "GB/s":
            return f"{bps:.0f} {unit}" if unit == "B/s" else f"{bps:.1f} {unit}"
        bps /= 1024.0
    return NA


def join(*parts, sep=" "):
    return sep.join(str(p) for p in parts if p not in (None, ""))


def set_role(widget, role):
    widget.setProperty("role", role)
    return widget


def label(text="", name=None, wrap=False, selectable=False):
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lbl


def set_status_style(lbl, state):
    """state: 'good' | 'warn' | 'bad' | None. Re-polishes so the stylesheet updates."""
    lbl.setObjectName(state or "cardLine")
    lbl.style().unpolish(lbl)
    lbl.style().polish(lbl)


# ---------------------------------------------------------------- containers

class Card(QFrame):
    """Rounded panel. Use .body (QVBoxLayout) to add content."""

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        set_role(self, "card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(8)
        self.title_label = None
        if title:
            self.title_label = label(title.upper(), "cardTitle")
            self.body.addWidget(self.title_label)


class Notice(QFrame):
    """Highlighted info box, e.g. 'Install LibreHardwareMonitor to see temperatures'."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setObjectName("notice")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self.text = label(text, "cardLine", wrap=True)
        self.text.setOpenExternalLinks(True)
        self.text.setTextFormat(Qt.RichText)
        lay.addWidget(self.text)


class KeyValueGrid(QWidget):
    """Two-column 'Label   Value' list that can be refilled."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(1, 1)
        self.rows, self._widgets = [], []

    def set_rows(self, rows):
        self.rows = [(k, v if v not in (None, "") else NA) for k, v in rows]
        self._widgets = []
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for r, (key, value) in enumerate(rows):
            k = label(key, "muted")
            k.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            v = label(value if value not in (None, "") else NA, selectable=True, wrap=True)
            if value in (None, "", NA):
                v.setObjectName("muted")
                v.setToolTip(NA_TIP)
            self.grid.addWidget(k, r, 0, Qt.AlignTop)
            self.grid.addWidget(v, r, 1, Qt.AlignTop)
            self._widgets.append((k, v))

    def filter(self, text):
        """Show only rows containing text. Returns how many rows match."""
        text = text.lower().strip()
        shown = 0
        for (key, value), (kw, vw) in zip(self.rows, self._widgets):
            match = not text or text in f"{key} {value}".lower()
            kw.setVisible(match)
            vw.setVisible(match)
            shown += match
        return shown


class Page(QWidget):
    """Base class for every page: a scrollable column with a title.

    Subclasses add widgets to self.content and can override:
      on_static(data)     - hardware scan finished
      on_telemetry(s)     - new live sample (about once a second)
      on_shown()          - user opened this page
      on_theme(theme)     - colors changed
    """

    title = ""
    subtitle = ""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx  # the MainWindow: log_action(), theme, static data, etc.
        self._tasks = []  # running TaskWorkers; kept alive until they finish
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        self.content = QVBoxLayout(inner)
        self.content.setContentsMargins(32, 28, 32, 28)
        self.content.setSpacing(16)
        self.loader = None
        if self.title:
            # Title row with the mini chip loader, shown only while run_task work is running
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(label(self.title, "pageTitle"))
            from ui.widgets.brand import ChipLoader
            self.loader = ChipLoader(20)
            self.loader.setToolTip("Working…")
            row.addWidget(self.loader, 0, Qt.AlignVCenter)
            row.addStretch(1)
            self.content.addLayout(row)
        if self.subtitle:
            sub = label(self.subtitle, "pageSubtitle", wrap=True)
            self.content.addWidget(sub)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def run_task(self, fn, *args, on_done=None):
        """Run fn(*args) on a background thread; on_done(result) runs on the UI thread."""
        from ui.workers import TaskWorker
        w = TaskWorker(fn, *args)
        if on_done:
            w.done.connect(on_done)
        self._tasks.append(w)
        w.finished.connect(lambda: self._task_finished(w))
        if self.loader and not self.loader.is_running():
            self.loader.start()
        w.start()
        return w

    def _task_finished(self, w):
        if w in self._tasks:
            self._tasks.remove(w)
        if self.loader and not any(t.isRunning() for t in self._tasks):
            self.loader.stop()

    def busy(self):
        return any(w.isRunning() for w in self._tasks)

    def wait_for_tasks(self):
        """Called when the app closes: a QThread must not be destroyed while running."""
        for w in list(self._tasks):
            w.wait()

    def finish(self):
        """Call at the end of a subclass __init__ to push content to the top."""
        self.content.addStretch(1)

    def on_static(self, data):
        pass

    def on_telemetry(self, sample):
        pass

    def on_shown(self):
        pass

    def on_theme(self, theme):
        pass


def expanding(widget):
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    return widget
