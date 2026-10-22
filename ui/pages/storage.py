# ui/pages/storage.py
"""Drives (with real health), a simple file browser, and temp-file cleanup."""

import os

from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLineEdit, QMessageBox, QProgressBar,
                               QPushButton, QTableWidget, QTableWidgetItem)

from core.storage_manager import browse_directory, cleanup_temp_files_safe, get_disk_drives
from ui.widgets.common import Card, Page, label, set_role
from ui.workers import TaskWorker


class StoragePage(Page):
    title = "Storage & cleanup"
    subtitle = "Your drives, their health as reported by Windows, and safe temp-file cleanup."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._worker = None
        self._loaded = False
        self.path = os.path.splitdrive(os.path.expanduser("~"))[0] + "\\" if os.name == "nt" else "/"

        self.drives = QTableWidget(0, 6)
        self.drives.setHorizontalHeaderLabels(["Drive", "Disk", "Health", "Size", "Free", "Used"])
        self.drives.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.drives.verticalHeader().setVisible(False)
        self.drives.setMaximumHeight(200)
        self.content.addWidget(self.drives)

        clean = Card("Temp files")
        clean.body.addWidget(label(
            "Deletes files in your Temp folder and Windows\\Temp. Files that are in use are skipped. "
            "Your documents, downloads and Recycle Bin are never touched.", "cardLine", wrap=True))
        row = QHBoxLayout()
        self.btn_clean = set_role(QPushButton("Clean temp files"), "primary")
        self.btn_clean.clicked.connect(self.run_cleanup)
        row.addWidget(self.btn_clean)
        self.clean_result = label("", "cardLine")
        row.addWidget(self.clean_result, 1)
        clean.body.addLayout(row)
        self.content.addWidget(clean)

        browser = Card("Browse files")
        nav = QHBoxLayout()
        self.path_input = QLineEdit(self.path)
        self.path_input.returnPressed.connect(lambda: self.load_directory(self.path_input.text()))
        up = QPushButton("Up")
        up.clicked.connect(lambda: self.load_directory(os.path.dirname(self.path.rstrip("\\/")) or self.path))
        go = QPushButton("Go")
        go.clicked.connect(lambda: self.load_directory(self.path_input.text()))
        nav.addWidget(self.path_input, 1)
        nav.addWidget(up)
        nav.addWidget(go)
        browser.body.addLayout(nav)
        self.files = QTableWidget(0, 3)
        self.files.setHorizontalHeaderLabels(["Name", "Size", "Type"])
        self.files.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.files.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.files.verticalHeader().setVisible(False)
        self.files.setMinimumHeight(320)
        self.files.cellDoubleClicked.connect(self.open_item)
        browser.body.addWidget(self.files)
        self.content.addWidget(browser)

    def on_shown(self):
        if not self._loaded:
            self._loaded = True
            self.load_drives()
            self.load_directory(self.path)

    def on_static(self, data):
        if self._loaded:
            self.load_drives()

    def load_drives(self):
        # Map drive letters to the physical disk's name and health from the hardware scan
        by_letter = {}
        for d in (self.ctx.static or {}).get("disks", []):
            for letter in d.get("letters", []):
                by_letter[letter.upper()] = d
        self.drives.setRowCount(0)
        for d in get_disk_drives():
            r = self.drives.rowCount()
            self.drives.insertRow(r)
            letter = d["device"].rstrip("\\").upper()
            disk = by_letter.get(letter, {})
            self.drives.setItem(r, 0, QTableWidgetItem(f"{d['device']}  ({d['fstype']})"))
            self.drives.setItem(r, 1, QTableWidgetItem(disk.get("name") or "—"))
            self.drives.setItem(r, 2, QTableWidgetItem(disk.get("health") or "Not available"))
            self.drives.setItem(r, 3, QTableWidgetItem(d["total"]))
            self.drives.setItem(r, 4, QTableWidgetItem(d["free"]))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(d["percent"]))
            bar.setToolTip(f"{d['percent']}% used")
            self.drives.setCellWidget(r, 5, bar)

    def load_directory(self, path):
        if not os.path.isdir(path):
            QMessageBox.warning(self, "Browse", f"Folder not found:\n{path}")
            return
        self.path = path
        self.path_input.setText(path)
        self.files.setRowCount(0)
        for item in browse_directory(path):
            r = self.files.rowCount()
            self.files.insertRow(r)
            name = QTableWidgetItem(item["name"])
            if not item["icon"].isNull():
                name.setIcon(item["icon"])
            name.setData(256, item["path"])  # Qt.UserRole
            self.files.setItem(r, 0, name)
            self.files.setItem(r, 1, QTableWidgetItem(item["size"]))
            self.files.setItem(r, 2, QTableWidgetItem(item["type"]))

    def open_item(self, row, _col):
        item = self.files.item(row, 0)
        if not item:
            return
        path = item.data(256)
        if os.path.isdir(path):
            self.load_directory(path)
        else:
            try:
                os.startfile(path)
            except Exception as e:
                QMessageBox.warning(self, "Open", str(e))

    def run_cleanup(self):
        if QMessageBox.question(self, "Clean temp files", "Delete temporary files now?") != QMessageBox.Yes:
            return
        self.btn_clean.setEnabled(False)
        self.clean_result.setText("Cleaning…")
        self._worker = TaskWorker(cleanup_temp_files_safe)

        def done(result):
            self.btn_clean.setEnabled(True)
            text = result if isinstance(result, str) else f"Failed: {result[1]}"
            self.clean_result.setText(text)
            self.ctx.log_action("Temp cleanup", "Clean", "Success" if isinstance(result, str) else "Failed",
                                "" if isinstance(result, str) else text)
            self.load_drives()

        self._worker.done.connect(done)
        self._worker.start()
