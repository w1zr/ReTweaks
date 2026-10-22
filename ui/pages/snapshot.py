# ui/pages/snapshot.py
"""Performance snapshots (replaces the old 'A/B Benchmarking' page).

Records what the PC is actually doing for a set time (load, clocks, temps) and keeps the
averages, so you can compare before and after a tweak. It measures; it doesn't score.
"""

from datetime import datetime

from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem)

from ui.widgets.common import Card, Page, label, set_role

COLUMNS = ["Name", "Time", "Length", "CPU load avg / max", "CPU clock avg", "CPU temp max",
           "GPU load avg / max", "GPU temp max", "RAM avg"]


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _max(xs):
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def _f(v, unit="", digits=0):
    return "Unavailable" if v is None else f"{v:.{digits}f}{unit}"


class SnapshotPage(Page):
    title = "Performance snapshots"
    subtitle = ("Start your game or task, then record a snapshot. Change a tweak and record another "
                "to compare. Snapshots measure what your PC is doing; they don't measure FPS.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.recording = None
        self.samples = []

        card = Card("New snapshot")
        row = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name, e.g. “Before Game Mode”")
        self.length = QComboBox()
        self.length.addItems(["15 seconds", "30 seconds", "60 seconds", "120 seconds"])
        self.length.setCurrentIndex(1)
        self.btn = set_role(QPushButton("Record"), "primary")
        self.btn.clicked.connect(self.toggle)
        row.addWidget(self.name, 1)
        row.addWidget(self.length)
        row.addWidget(self.btn)
        card.body.addLayout(row)
        self.progress = label("", "cardLine")
        card.body.addWidget(self.progress)
        self.content.addWidget(card)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(260)
        self.content.addWidget(self.table)
        b_clear = QPushButton("Clear list")
        b_clear.clicked.connect(lambda: self.table.setRowCount(0))
        self.content.addWidget(b_clear)
        self.finish()

    def toggle(self):
        if self.recording:
            self._finish()
            return
        seconds = int(self.length.currentText().split()[0])
        self.recording = {"seconds": seconds, "start": datetime.now(),
                          "name": self.name.text().strip() or f"Snapshot {self.table.rowCount() + 1}"}
        self.samples = []
        self.btn.setText("Stop")
        self.progress.setText(f"Recording… 0 / {seconds} s")

    def on_telemetry(self, s):
        if not self.recording:
            return
        self.samples.append(s)
        elapsed = int((datetime.now() - self.recording["start"]).total_seconds())
        total = self.recording["seconds"]
        self.progress.setText(f"Recording… {min(elapsed, total)} / {total} s")
        if elapsed >= total:
            self._finish()

    def _finish(self):
        rec, samples = self.recording, self.samples
        self.recording = None
        self.btn.setText("Record")
        if not samples:
            self.progress.setText("Stopped before any data was recorded.")
            return
        cpu_load = [x["cpu"]["load"] for x in samples]
        gpu_load = [x["gpus"][0]["load"] if x["gpus"] else None for x in samples]
        gpu_temp = [x["gpus"][0]["temp_c"] if x["gpus"] else None for x in samples]
        values = [
            rec["name"], rec["start"].strftime("%H:%M:%S"), f"{len(samples)} s",
            f"{_f(_avg(cpu_load), '%')} / {_f(_max(cpu_load), '%')}",
            _f(_avg([x["cpu"]["mhz"] for x in samples]), " MHz"),
            _f(_max([x["cpu"]["temp_c"] for x in samples]), " °C"),
            f"{_f(_avg(gpu_load), '%')} / {_f(_max(gpu_load), '%')}",
            _f(_max(gpu_temp), " °C"),
            _f(_avg([x["ram"]["percent"] for x in samples]), "%"),
        ]
        length = int((datetime.now() - rec["start"]).total_seconds())
        values[2] = f"{length} s"
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, v in enumerate(values):
            self.table.setItem(r, c, QTableWidgetItem(v))
        self.progress.setText(f"Saved “{rec['name']}”. GPU columns use GPU 1.")
        self.name.clear()
