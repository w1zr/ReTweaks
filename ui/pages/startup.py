# ui/pages/startup.py
"""Startup apps manager (moved from the old main_window.py; behavior unchanged)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem)

from core.startup_manager import (SCHED_SOURCE, TASK_ID_PREFIX, TASK_WARNING, disable_scheduled_tasks,
                                  disable_startup_entry, enable_scheduled_tasks, enable_startup_entry,
                                  extract_icon)
from ui.widgets.common import Page, label, set_role


def _list_startup_apps(include_windows_tasks=False):
    from core.startup_manager import list_startup_apps
    return list_startup_apps(include_windows_tasks)


def _batch_disable(entries):
    """Registry and Startup-folder entries are instant; scheduled tasks go in one PowerShell run."""
    tasks = [e for e in entries if e.get("source") == SCHED_SOURCE]
    others = [(e, *disable_startup_entry(e)) for e in entries if e.get("source") != SCHED_SOURCE]
    return others + (disable_scheduled_tasks(tasks) if tasks else [])


def _batch_enable(ids):
    tasks = [i for i in ids if str(i).startswith(TASK_ID_PREFIX)]
    others = [(i, *enable_startup_entry(i)) for i in ids if i not in tasks]
    return others + (enable_scheduled_tasks(tasks) if tasks else [])


class StartupPage(Page):
    title = "Startup apps"
    subtitle = ("Apps that start with Windows. Disabling them makes boot faster. "
                "RETWEAKS keeps a backup, so you can turn them back on here.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.entries = []
        self._loaded = False

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name, publisher or path…")
        self.search.textChanged.connect(self.filter_table)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All apps", "Enabled", "Disabled", "Current user", "All users",
                                    "Registry", "Startup folder", "Scheduled tasks"])
        self.filter_combo.currentIndexChanged.connect(self.filter_table)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.filter_combo)
        self.win_tasks = QCheckBox("Show Windows tasks")
        self.win_tasks.setToolTip("Include scheduled tasks under \\Microsoft\\ (Windows' own). Leave them alone unless you know what they do.")
        self.win_tasks.setChecked(bool(self.ctx.settings.get("startup_show_windows_tasks", False)))
        self.win_tasks.toggled.connect(self._win_tasks_toggled)
        tools.addWidget(self.win_tasks)
        self.content.addLayout(tools)

        sel = QHBoxLayout()
        for text, fn in (("Select all", lambda: self.set_all(True)), ("Select none", lambda: self.set_all(False)),
                         ("Invert", self.invert)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            sel.addWidget(b)
        sel.addStretch()
        self.count_lbl = label("Selected: 0", "muted")
        sel.addWidget(self.count_lbl)
        self.content.addLayout(sel)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Application", "Publisher", "Source", "Status", "Scope"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(380)
        self.table.itemChanged.connect(lambda item: item.column() == 0 and self.update_count())
        self.content.addWidget(self.table, 1)

        btns = QHBoxLayout()
        b_refresh = QPushButton("Refresh")
        b_refresh.clicked.connect(self.load)
        b_disable = set_role(QPushButton("Disable selected"), "primary")
        b_disable.clicked.connect(self.disable_selected)
        b_enable = QPushButton("Enable selected")
        b_enable.clicked.connect(self.enable_selected)
        for b in (b_refresh, b_disable, b_enable):
            btns.addWidget(b)
        btns.addStretch()
        self.content.addLayout(btns)

    def on_shown(self):
        if not self._loaded:
            self.load()

    def load(self, force=False, quiet=False):
        """quiet=True re-checks in the background and keeps the current list on screen meanwhile."""
        if self.busy() and not force:
            return  # a load is already running
        self._loaded = True
        if not quiet:
            self.table.setRowCount(0)
            self.count_lbl.setText("Loading…")
        self._load_gen = getattr(self, "_load_gen", 0) + 1
        gen = self._load_gen
        self.run_task(_list_startup_apps, self.win_tasks.isChecked(),
                      on_done=lambda entries, g=gen: self._loaded_entries(entries) if g == self._load_gen else None)

    def _win_tasks_toggled(self, on):
        self.ctx.set_setting("startup_show_windows_tasks", bool(on))
        self.load(force=True)

    def _loaded_entries(self, entries):
        self.entries = entries if isinstance(entries, list) else []
        self.filter_table()

    def filter_table(self):
        text = self.search.text().lower()
        mode = self.filter_combo.currentText()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for e in self.entries:
            status, scope, source = e.get("status", "Enabled"), e.get("scope", ""), e.get("source", "")
            hay = " ".join((e.get("name", ""), e.get("publisher", ""), e.get("path", ""))).lower()
            if text and text not in hay:
                continue
            if (mode == "Enabled" and status != "Enabled") or (mode == "Disabled" and status != "Disabled") \
                    or (mode == "Current user" and scope != "Current User") \
                    or (mode == "All users" and scope != "All Users") \
                    or (mode == "Registry" and "Registry" not in source) \
                    or (mode == "Startup folder" and "Startup Folder" not in source) \
                    or (mode == "Scheduled tasks" and source != SCHED_SOURCE):
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            item = QTableWidgetItem(e["name"])
            managed = bool(e.get("managed"))
            if managed:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)   # not toggled here
                item.setToolTip("RETWEAKS's own start-with-Windows task. Change it in Settings.")
            else:
                item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setCheckState(Qt.Unchecked)
                item.setData(Qt.UserRole, e["id"])
                if source == SCHED_SOURCE:
                    item.setToolTip(f"Task: {e.get('task_path', '')}{e.get('task_name', '')}\n"
                                    f"Runs: {e.get('path', '')}\nTriggers: {', '.join(e.get('triggers', []))}\n"
                                    f"State: {e.get('task_state', '')}\n\n{TASK_WARNING}")
            icon = extract_icon(e.get("path", ""))
            if not icon.isNull():
                item.setIcon(icon)
            self.table.setItem(r, 0, item)
            self.table.setItem(r, 1, QTableWidgetItem(e.get("publisher", "Unknown")))
            self.table.setItem(r, 2, QTableWidgetItem(source))
            st = QTableWidgetItem("Managed in Settings" if managed else status)
            st.setForeground(QColor(self.ctx.theme["bad"] if status == "Disabled" else self.ctx.theme["good"]))
            self.table.setItem(r, 3, st)
            self.table.setItem(r, 4, QTableWidgetItem(scope))
        self.table.blockSignals(False)
        self.update_count()

    def _checked_ids(self):
        ids = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.checkState() == Qt.Checked and it.data(Qt.UserRole):
                ids.append(it.data(Qt.UserRole))
        return ids

    def update_count(self):
        self.count_lbl.setText(f"Selected: {len(self._checked_ids())}")

    def set_all(self, checked):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.table.blockSignals(False)
        self.update_count()

    def invert(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)
        self.table.blockSignals(False)
        self.update_count()

    def disable_selected(self):
        ids = self._checked_ids()
        if not ids:
            QMessageBox.information(self, "Startup apps", "Tick at least one app first.")
            return
        chosen = [e for e in (next((x for x in self.entries if x["id"] == i), None) for i in ids)
                  if e and e.get("status") == "Enabled" and not e.get("managed")]
        text = f"Disable {len(ids)} app(s) from starting with Windows?"
        if any(e.get("source") == SCHED_SOURCE for e in chosen):
            text += "\n\n" + TASK_WARNING
        if QMessageBox.question(self, "Disable startup apps", text) != QMessageBox.Yes:
            return
        self.count_lbl.setText("Working…")
        self.run_task(_batch_disable, chosen, on_done=lambda res, n=len(ids): self._disabled(res, n))

    def _disabled(self, res, total):
        if not isinstance(res, list):
            QMessageBox.warning(self, "Startup apps", f"Failed: {res[1] if isinstance(res, tuple) else res}")
            self.load(force=True)
            return
        done = 0
        for e, ok, msg in res:
            done += bool(ok)
            self.ctx.log_action("Startup apps", f"Disable {e['name']}", "Success" if ok else "Failed",
                                "" if ok else msg)
        self._apply_status({e["id"] for e, ok, _ in res if ok}, "Disabled")
        QMessageBox.information(self, "Startup apps", f"Disabled {done} of {total} app(s)."
                                + "".join(f"\n{e['name']}: {msg}" for e, ok, msg in res if not ok))
        self.load(force=True, quiet=True)   # re-check with Windows in the background

    def enable_selected(self):
        ids = self._checked_ids()
        if not ids:
            QMessageBox.information(self, "Startup apps", "Tick at least one app first.")
            return
        self.count_lbl.setText("Working…")
        self.run_task(_batch_enable, ids, on_done=lambda res, n=len(ids): self._enabled(res, n))

    def _enabled(self, res, total):
        if not isinstance(res, list):
            QMessageBox.warning(self, "Startup apps", f"Failed: {res[1] if isinstance(res, tuple) else res}")
            self.load(force=True)
            return
        done = 0
        for entry_id, ok, msg in res:
            done += bool(ok)
            self.ctx.log_action("Startup apps", f"Enable {entry_id}", "Success" if ok else "Failed", "" if ok else msg)
        self._apply_status({i for i, ok, _ in res if ok}, "Enabled")
        QMessageBox.information(self, "Startup apps", f"Enabled {done} of {total} app(s)."
                                + "".join(f"\n{i}: {msg}" for i, ok, msg in res if not ok))
        self.load(force=True, quiet=True)   # re-check with Windows in the background

    def _apply_status(self, ids, status):
        """Show the verified result right away instead of waiting for a full re-scan."""
        for e in self.entries:
            if e.get("id") in ids:
                e["status"] = status
        self.filter_table()
