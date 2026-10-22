# ui/pages/logs.py
"""Every change RETWEAKS made this session, with its real result."""

from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from ui.widgets.common import Page

COLUMNS = ["Time", "What", "Action", "Result", "Details"]


class LogsPage(Page):
    title = "Logs"
    subtitle = "Every change made in this session and whether Windows accepted it."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        hh = self.table.horizontalHeader()
        for c in range(4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(420)
        self.content.addWidget(self.table, 1)

    def add(self, entry):
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, key in enumerate(("timestamp", "component", "requested", "result", "error")):
            self.table.setItem(r, c, QTableWidgetItem(str(entry.get(key, ""))))
        self.table.scrollToBottom()
