# ui/pages/storage.py
"""Drives (with real health), the Storage Explorer, the disk space analyzer and temp-file cleanup."""

import os
import subprocess
import sys

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFileIconProvider, QFrame, QHBoxLayout,
                               QHeaderView, QLineEdit, QMenu, QMessageBox, QProgressBar, QPushButton,
                               QScrollArea, QTableWidget, QTableWidgetItem, QWidget)

from core.storage_manager import (BackgroundJob, ScanState, browse_directory, cleanup_temp_files_safe,  # noqa: F401
                                  format_mtime, get_disk_drives, human_size, list_directory, preview_temp_files,
                                  scan_tree, search_files, sort_items, split_breadcrumbs)
from ui.widgets.common import Card, Notice, Page, label, set_role

SORT_KEYS = {"Name": "name", "Size": "size", "Date modified": "modified", "Type": "type"}


class StoragePage(Page):
    title = "Storage & cleanup"
    subtitle = "Your drives, their health as reported by Windows, and safe temp-file cleanup."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
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
        # breadcrumbs: clickable path segments
        self.crumb_host = QWidget()
        self.crumb_lay = QHBoxLayout(self.crumb_host)
        self.crumb_lay.setContentsMargins(0, 0, 0, 0)
        self.crumb_lay.setSpacing(2)
        self.crumb_scroll = QScrollArea()
        self.crumb_scroll.setWidget(self.crumb_host)
        self.crumb_scroll.setWidgetResizable(True)
        self.crumb_scroll.setFrameShape(QFrame.NoFrame)
        self.crumb_scroll.setFixedHeight(46)
        self.crumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        browser.body.addWidget(self.crumb_scroll)

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

        opts = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search in this folder…")
        self.search_input.returnPressed.connect(self.start_search)
        self.search_sub = QCheckBox("Include subfolders")
        self.btn_search = QPushButton("Search")
        self.btn_search.clicked.connect(self.start_search)
        self.btn_search_cancel = QPushButton("Cancel search")
        self.btn_search_cancel.setEnabled(False)
        self.btn_search_cancel.clicked.connect(self.cancel_search)
        self.btn_search_clear = QPushButton("Clear")
        self.btn_search_clear.clicked.connect(self.clear_search)
        for w in (self.search_input, self.search_sub, self.btn_search, self.btn_search_cancel, self.btn_search_clear):
            opts.addWidget(w, 1 if w is self.search_input else 0)
        browser.body.addLayout(opts)

        opts2 = QHBoxLayout()
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(list(SORT_KEYS))
        self.sort_desc = QCheckBox("Descending")
        self.show_hidden = QCheckBox("Show hidden items")
        self.show_hidden.setChecked(bool(self.ctx.settings.get("storage_show_hidden", True)))
        self.sort_combo.currentIndexChanged.connect(self.resort)
        self.sort_desc.toggled.connect(self.resort)
        self.show_hidden.toggled.connect(self._hidden_toggled)
        b_open = QPushButton("Open")
        b_open.clicked.connect(self.open_selected)
        b_show = QPushButton("Show in Explorer")
        b_show.clicked.connect(self.show_selected_in_explorer)
        b_copy = QPushButton("Copy path")
        b_copy.clicked.connect(self.copy_selected_path)
        opts2.addWidget(label("Sort by", "muted"))
        for w in (self.sort_combo, self.sort_desc, self.show_hidden):
            opts2.addWidget(w)
        opts2.addStretch()
        for w in (b_open, b_show, b_copy):
            opts2.addWidget(w)
        browser.body.addLayout(opts2)

        self.browse_status = label("", "muted")
        browser.body.addWidget(self.browse_status)
        self.files = QTableWidget(0, 4)
        self.files.setHorizontalHeaderLabels(["Name", "Size", "Date modified", "Type"])
        self.files.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            self.files.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.files.verticalHeader().setVisible(False)
        self.files.setEditTriggers(QTableWidget.NoEditTriggers)
        self.files.setSelectionBehavior(QTableWidget.SelectRows)
        self.files.setMinimumHeight(320)
        self.files.cellDoubleClicked.connect(self.open_item)
        self.files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._file_menu)
        browser.body.addWidget(self.files)
        self.content.addWidget(browser)

        # ---------------------------------------------------------------- disk usage analyzer
        usage = Card("Disk usage breakdown")
        usage.body.addWidget(label(
            "Scans a drive or folder in the background and shows where the space goes. Nothing is "
            "deleted here. Symlinks and junctions are not followed.", "cardLine", wrap=True))
        row = QHBoxLayout()
        self.scan_target = QComboBox()
        self.scan_target.setEditable(True)
        self.scan_target.setMinimumWidth(260)
        b_choose = QPushButton("Choose folder…")
        b_choose.clicked.connect(self.choose_scan_folder)
        self.btn_scan = set_role(QPushButton("Scan"), "primary")
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_scan_cancel = QPushButton("Cancel")
        self.btn_scan_cancel.setEnabled(False)
        self.btn_scan_cancel.clicked.connect(self.cancel_scan)
        row.addWidget(self.scan_target, 1)
        for w in (b_choose, self.btn_scan, self.btn_scan_cancel):
            row.addWidget(w)
        usage.body.addLayout(row)
        self.scan_status = label("", "cardLine", wrap=True)
        usage.body.addWidget(self.scan_status)
        self.scan_notice = Notice("")
        self.scan_notice.setVisible(False)
        usage.body.addWidget(self.scan_notice)

        usage.body.addWidget(label("TOP-LEVEL BREAKDOWN", "sectionTitle"))
        self.tbl_children = QTableWidget(0, 3)
        self.tbl_children.setHorizontalHeaderLabels(["Name", "Size", "Share of scanned space"])
        usage.body.addWidget(self._prep_table(self.tbl_children, 2, 220))
        usage.body.addWidget(label("LARGEST FOLDERS (2-3 levels down)", "sectionTitle"))
        self.tbl_folders = QTableWidget(0, 2)
        self.tbl_folders.setHorizontalHeaderLabels(["Folder", "Size"])
        usage.body.addWidget(self._prep_table(self.tbl_folders, 0, 200))
        usage.body.addWidget(label("LARGEST FILES", "sectionTitle"))
        self.tbl_files = QTableWidget(0, 2)
        self.tbl_files.setHorizontalHeaderLabels(["File", "Size"])
        usage.body.addWidget(self._prep_table(self.tbl_files, 0, 240))
        self.content.addWidget(usage)
        self.finish()

        # jobs (all background; the UI only reads their shared state from this timer)
        self._list_gen = 0
        self._items = []
        self._searching = False
        self._size_job = None
        self._size_state = None
        self._size_paths = []
        self._search_job = None
        self._search_state = None
        self._scan_job = None
        self._scan_state = None
        self._poll = QTimer(self)
        self._poll.setInterval(200)
        self._poll.timeout.connect(self._poll_jobs)

    def _prep_table(self, tbl, stretch_col, height):
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        hh = tbl.horizontalHeader()
        for c in range(tbl.columnCount()):
            hh.setSectionResizeMode(c, QHeaderView.Stretch if c == stretch_col else QHeaderView.ResizeToContents)
        tbl.setMinimumHeight(height)
        tbl.setContextMenuPolicy(Qt.CustomContextMenu)
        tbl.customContextMenuRequested.connect(lambda pos, t=tbl: self._generic_menu(t, pos))
        return tbl

    def on_shown(self):
        if not self._loaded:
            self._loaded = True
            self.load_drives()
            self._fill_scan_targets()
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
            self.drives.setItem(r, 2, QTableWidgetItem(disk.get("health") or "Unavailable"))
            self.drives.setItem(r, 3, QTableWidgetItem(d["total"]))
            self.drives.setItem(r, 4, QTableWidgetItem(d["free"]))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(d["percent"]))
            bar.setToolTip(f"{d['percent']}% used")
            self.drives.setCellWidget(r, 5, bar)

    # ---------------------------------------------------------------- explorer
    def _icon(self, is_dir):
        if not hasattr(self, "_icons"):
            prov = QFileIconProvider()
            self._icons = {True: prov.icon(QFileIconProvider.Folder), False: prov.icon(QFileIconProvider.File)}
        return self._icons[is_dir]

    def _stop_browse_jobs(self):
        for job in (self._size_job, self._search_job):
            if job:
                job.cancel()
        self._size_job = self._search_job = None
        self.btn_search_cancel.setEnabled(False)

    def _rebuild_crumbs(self):
        while self.crumb_lay.count():
            it = self.crumb_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        crumbs = split_breadcrumbs(self.path)
        for i, (text, full) in enumerate(crumbs):
            b = QPushButton(text)
            b.setFlat(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(full)
            b.clicked.connect(lambda _=False, p=full: self.load_directory(p))
            self.crumb_lay.addWidget(b)
            if i < len(crumbs) - 1:
                self.crumb_lay.addWidget(label("›", "muted"))
        self.crumb_lay.addStretch()

    def load_directory(self, path):
        path = (path or "").strip().strip('"')
        if not os.path.isdir(path):
            QMessageBox.warning(self, "Browse", f"Folder not found or drive not connected:\n{path}")
            return
        self._stop_browse_jobs()          # leaving the folder cancels size calculations and searches
        self._searching = False
        self.path = path
        self.path_input.setText(path)
        self._rebuild_crumbs()
        self.files.setRowCount(0)
        self._items = []
        self.browse_status.setText("Loading…")
        self._list_gen += 1
        gen = self._list_gen
        hidden = self.show_hidden.isChecked()
        self.run_task(list_directory, path, hidden, on_done=lambda res, g=gen: self._listed(g, res))

    def _listed(self, gen, res):
        if gen != self._list_gen:
            return   # the user already moved on
        if not isinstance(res, list):
            msg = res[1] if isinstance(res, tuple) and len(res) == 2 else "unknown error"
            self.browse_status.setText(f"This folder can't be read: {msg}")
            return
        self._items = res
        self.browse_status.setText(f"{len(res)} item(s)")
        self._start_folder_sizes()
        self._fill_table()

    def _fill_table(self):
        key = SORT_KEYS.get(self.sort_combo.currentText(), "name")
        items = sort_items(self._items, key, self.sort_desc.isChecked())
        self.files.setUpdatesEnabled(False)
        self.files.setRowCount(len(items))
        for r, it in enumerate(items):
            name = QTableWidgetItem(it["name"] + ("  (link, not followed)" if it.get("is_link") else ""))
            name.setIcon(self._icon(it["is_dir"]))
            name.setData(Qt.UserRole, it["path"])
            name.setData(Qt.UserRole + 1, it["is_dir"])
            self.files.setItem(r, 0, name)
            if it["is_dir"]:
                txt = "-" if it.get("is_link") else self._folder_size_text(it["path"])
            else:
                txt = human_size(it["size"]) if it["size"] is not None else "Unavailable"
            self.files.setItem(r, 1, QTableWidgetItem(txt))
            self.files.setItem(r, 2, QTableWidgetItem(format_mtime(it["mtime"])))
            self.files.setItem(r, 3, QTableWidgetItem(it["type"]))
        self.files.setUpdatesEnabled(True)

    def _folder_size_text(self, path):
        sizes = self._size_state.sizes if self._size_state else {}
        if path in sizes:
            v = sizes[path]
            return human_size(v) if v is not None else "Unavailable"
        return "calculating…" if self._size_job else "-"

    def _start_folder_sizes(self):
        dirs = [i["path"] for i in self._items if i["is_dir"] and not i.get("is_link")]
        if not dirs or self._searching:
            return
        state = ScanState()
        state.sizes = {}
        self._size_state = state

        def work(stop):
            for d in dirs:
                if stop.is_set():
                    return
                r = scan_tree(d, stop, track_depth=0, top_files=0)
                if stop.is_set():
                    return    # partial totals are never shown
                state.sizes[d] = None if r["error"] else r["total"]
        self._size_job = BackgroundJob(work).start()
        self._poll.start()

    def resort(self, *_):
        if self._searching:
            self._fill_search_results()
        elif self._items:
            self._fill_table()

    def _hidden_toggled(self, on):
        self.ctx.set_setting("storage_show_hidden", bool(on))
        if self._searching:
            return
        self.load_directory(self.path)

    def _selected_paths(self, table=None):
        table = table or self.files
        rows = sorted({i.row() for i in table.selectedItems()})
        out = []
        for r in rows:
            it = table.item(r, 0)
            if it and it.data(Qt.UserRole):
                out.append((it.data(Qt.UserRole), bool(it.data(Qt.UserRole + 1))))
        return out

    def open_path(self, path, is_dir=None):
        if is_dir is None:
            is_dir = os.path.isdir(path)
        if is_dir:
            self.load_directory(path)
            return
        try:
            os.startfile(path)   # opens with the default Windows app
        except AttributeError:
            QMessageBox.information(self, "Open", "Opening files with the default app only works on Windows.")
        except Exception as e:
            QMessageBox.warning(self, "Open", str(e))

    def open_item(self, row, _col):
        item = self.files.item(row, 0)
        if item:
            self.open_path(item.data(Qt.UserRole), bool(item.data(Qt.UserRole + 1)))

    def open_selected(self):
        sel = self._selected_paths()
        if sel:
            self.open_path(*sel[0])

    def reveal(self, path):
        """Open the containing folder in Windows Explorer with the item selected."""
        try:
            if sys.platform == "win32":
                if os.path.isdir(path):
                    subprocess.Popen(["explorer", os.path.normpath(path)])
                else:
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            else:
                QMessageBox.information(self, "Show in Explorer", "This only works on Windows.")
        except Exception as e:
            QMessageBox.warning(self, "Show in Explorer", str(e))

    def show_selected_in_explorer(self):
        sel = self._selected_paths()
        self.reveal(sel[0][0] if sel else self.path)

    def copy_path(self, path):
        QGuiApplication.clipboard().setText(path)
        self.browse_status.setText(f"Copied: {path}")

    def copy_selected_path(self):
        sel = self._selected_paths()
        self.copy_path(sel[0][0] if sel else self.path)

    def _menu_for(self, table, pos, open_fn):
        sel = self._selected_paths(table)
        if not sel:
            return
        path, is_dir = sel[0]
        m = QMenu(self)
        a_open = m.addAction("Open" if not is_dir else "Open folder")
        a_show = m.addAction("Show in Explorer")
        a_copy = m.addAction("Copy path")
        act = m.exec(table.viewport().mapToGlobal(pos))
        if act is a_open:
            open_fn(path, is_dir)
        elif act is a_show:
            self.reveal(path)
        elif act is a_copy:
            self.copy_path(path)

    def _file_menu(self, pos):
        self._menu_for(self.files, pos, self.open_path)

    def _generic_menu(self, table, pos):
        self._menu_for(table, pos, self.open_path)

    # ---------------------------------------------------------------- search
    def start_search(self):
        q = self.search_input.text().strip()
        if not q:
            self.clear_search()
            return
        self._stop_browse_jobs()
        self._searching = True
        state = ScanState()
        state.results = []
        self._search_state = state
        root, recursive, hidden = self.path, self.search_sub.isChecked(), self.show_hidden.isChecked()
        self.files.setRowCount(0)
        self.btn_search_cancel.setEnabled(True)
        self._search_job = BackgroundJob(
            lambda stop: search_files(root, q, recursive, stop, state, hidden)).start()
        self._poll.start()

    def cancel_search(self):
        if self._search_job:
            self._search_job.cancel()
            self.browse_status.setText("Search cancelled. Showing what was found so far.")
            self.btn_search_cancel.setEnabled(False)

    def clear_search(self):
        self.search_input.clear()
        if self._searching:
            self.load_directory(self.path)

    def _fill_search_results(self):
        key = SORT_KEYS.get(self.sort_combo.currentText(), "name")
        items = sort_items(list(self._search_state.results), key, self.sort_desc.isChecked())
        self.files.setUpdatesEnabled(False)
        self.files.setRowCount(len(items))
        for r, it in enumerate(items):
            rel = os.path.relpath(it["path"], self.path) if self.path else it["path"]
            name = QTableWidgetItem(rel)
            name.setIcon(self._icon(it["is_dir"]))
            name.setData(Qt.UserRole, it["path"])
            name.setData(Qt.UserRole + 1, it["is_dir"])
            name.setToolTip(it["path"])
            self.files.setItem(r, 0, name)
            self.files.setItem(r, 1, QTableWidgetItem("-" if it["is_dir"] else human_size(it["size"])))
            self.files.setItem(r, 2, QTableWidgetItem(format_mtime(it["mtime"])))
            self.files.setItem(r, 3, QTableWidgetItem(it["type"]))
        self.files.setUpdatesEnabled(True)

    # ---------------------------------------------------------------- disk usage analyzer
    def _fill_scan_targets(self):
        cur = self.scan_target.currentText()
        self.scan_target.clear()
        for d in get_disk_drives():
            self.scan_target.addItem(d["mountpoint"])
        if cur:
            self.scan_target.setEditText(cur)

    def choose_scan_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Choose a folder to analyze", self.path)
        if d:
            self.scan_target.setEditText(os.path.normpath(d))

    def start_scan(self):
        if self._scan_job and not self._scan_job.done:
            return
        root = self.scan_target.currentText().strip().strip('"')
        if not root or not os.path.isdir(root):
            self.scan_status.setText(f"Can't scan: '{root}' was not found. If it is a drive, it may be disconnected.")
            return
        for t in (self.tbl_children, self.tbl_folders, self.tbl_files):
            t.setRowCount(0)
        self.scan_notice.setVisible(False)
        state = ScanState()
        self._scan_state = state
        self._scan_root = root

        def work(stop):
            try:
                state.result = scan_tree(root, stop, state)
            finally:
                state.done = True
        self._scan_job = BackgroundJob(work).start()
        self.btn_scan.setEnabled(False)
        self.btn_scan_cancel.setEnabled(True)
        self.scan_status.setText("Starting…")
        self._poll.start()

    def cancel_scan(self):
        if self._scan_job:
            self._scan_job.cancel()
            self.scan_status.setText("Cancelling…")

    def _show_scan_result(self, r, state):
        self.btn_scan.setEnabled(True)
        self.btn_scan_cancel.setEnabled(False)
        if self._scan_job and self._scan_job.error:
            self.scan_status.setText(f"Scan failed: {self._scan_job.error}")
            return
        if r is None:
            self.scan_status.setText("Scan failed.")
            return
        if r["error"]:
            self.scan_status.setText(f"Can't read {r['root']}: {r['error']}")
            return
        head = "Scan cancelled. Partial results" if r["cancelled"] else "Scan finished"
        self.scan_status.setText(
            f"{head}: {human_size(r['total'])} in {r['files']:,} files and {r['folders']:,} folders under {r['root']}.")
        notes = []
        if r["skipped"]:
            notes.append(f"{r['skipped']:,} folders couldn't be read (access denied or removed during the scan); "
                         "their size is not included.")
        if r["link_count"]:
            notes.append(f"{r['link_count']:,} symlinks/junctions were not followed and are counted as 0.")
        if r["cancelled"]:
            notes.append("The scan was cancelled, so totals are incomplete.")
        if notes:
            self.scan_notice.text.setText("<br>".join(notes))
            self.scan_notice.setVisible(True)
        total = max(r["total"], 1)
        kids = r["children"]
        self.tbl_children.setRowCount(len(kids))
        for i, c in enumerate(kids):
            it = QTableWidgetItem(c["name"] + ("  (link, not followed)" if c["is_link"] else ""))
            it.setIcon(self._icon(c["is_dir"]))
            it.setData(Qt.UserRole, c["path"])
            it.setData(Qt.UserRole + 1, c["is_dir"])
            self.tbl_children.setItem(i, 0, it)
            self.tbl_children.setItem(i, 1, QTableWidgetItem(human_size(c["size"])))
            pct = c["size"] * 100.0 / total
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(int(pct * 10))
            bar.setFormat(f"{pct:.1f}%")
            bar.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.tbl_children.setCellWidget(i, 2, bar)
        self.tbl_folders.setRowCount(len(r["top_folders"]))
        for i, (p, sz) in enumerate(r["top_folders"]):
            it = QTableWidgetItem(os.path.relpath(p, r["root"]))
            it.setData(Qt.UserRole, p)
            it.setData(Qt.UserRole + 1, True)
            it.setToolTip(p)
            self.tbl_folders.setItem(i, 0, it)
            self.tbl_folders.setItem(i, 1, QTableWidgetItem(human_size(sz)))
        self.tbl_files.setRowCount(len(r["top_files"]))
        for i, (sz, p) in enumerate(r["top_files"]):
            it = QTableWidgetItem(os.path.relpath(p, r["root"]))
            it.setData(Qt.UserRole, p)
            it.setData(Qt.UserRole + 1, False)
            it.setToolTip(p)
            self.tbl_files.setItem(i, 0, it)
            self.tbl_files.setItem(i, 1, QTableWidgetItem(human_size(sz)))

    # ---------------------------------------------------------------- polling (UI thread)
    def _poll_jobs(self):
        active = False
        if self._scan_job:
            st = self._scan_state
            if self._scan_job.done and (st.done or self._scan_job.error):
                job, self._scan_job = self._scan_job, None
                self._show_scan_result(st.result, st)
                self._scan_job = None
            else:
                active = True
                cur = st.current
                cur = cur if len(cur) < 80 else "…" + cur[-77:]
                self.scan_status.setText(f"Scanning… {st.items:,} items, {human_size(st.bytes)} so far. Now in: {cur}")
        if self._size_job:
            if self._size_job.done:
                self._size_job = None
                if not self._searching:
                    self._update_size_cells()
                    if SORT_KEYS.get(self.sort_combo.currentText()) == "size":
                        self._fill_table()
            else:
                active = True
                self._update_size_cells()
        if self._search_job:
            st = self._search_state
            if self._search_job.done:
                self._search_job = None
                self.btn_search_cancel.setEnabled(False)
                if self._searching:
                    self.browse_status.setText(f"{len(st.results)} match(es) for '{self.search_input.text().strip()}'"
                                               + (" (limit reached)" if len(st.results) >= 1000 else ""))
            else:
                active = True
                self.browse_status.setText(f"Searching… {st.items:,} items checked, {len(st.results)} found")
            if self._searching:
                self._fill_search_results()
        if not active:
            self._poll.stop()

    def _update_size_cells(self):
        if not self._size_state:
            return
        sizes = self._size_state.sizes
        for r in range(self.files.rowCount()):
            it = self.files.item(r, 0)
            if it and it.data(Qt.UserRole + 1) and it.data(Qt.UserRole) in sizes:
                v = sizes[it.data(Qt.UserRole)]
                cell = self.files.item(r, 1)
                if cell:
                    cell.setText(human_size(v) if v is not None else "Unavailable")

    def wait_for_tasks(self):
        for job in (self._scan_job, self._size_job, self._search_job):
            if job:
                job.cancel()
        for job in (self._scan_job, self._size_job, self._search_job):
            if job:
                job.join()
        if hasattr(self, "_poll"):
            self._poll.stop()
        return super().wait_for_tasks()

    def run_cleanup(self):
        # Preview first (CLAUDE.md: never delete without showing what will go)
        self.btn_clean.setEnabled(False)
        self.clean_result.setText("Checking temp folders…")
        self.run_task(preview_temp_files, on_done=self._confirm_cleanup)

    def _confirm_cleanup(self, result):
        self.btn_clean.setEnabled(True)
        if not isinstance(result, tuple) or len(result) != 2 or isinstance(result[0], bool):
            self.clean_result.setText("Could not check the temp folders.")
            return
        items, size = result
        self.clean_result.setText("")
        if items == 0:
            self.clean_result.setText("Temp folders are already empty.")
            return
        msg = (f"Found {items} item(s), about {size / 1024 ** 2:.1f} MB, in your Temp folder and Windows\\Temp.\n\n"
               "Delete them? Files that are in use will be skipped.")
        if QMessageBox.question(self, "Clean temp files", msg) != QMessageBox.Yes:
            return
        self.btn_clean.setEnabled(False)
        self.clean_result.setText("Cleaning…")
        def done(result):
            self.btn_clean.setEnabled(True)
            text = result if isinstance(result, str) else f"Failed: {result[1]}"
            self.clean_result.setText(text)
            self.ctx.log_action("Temp cleanup", "Clean", "Success" if isinstance(result, str) else "Failed",
                                "" if isinstance(result, str) else text)
            self.load_drives()

        self.run_task(cleanup_temp_files_safe, on_done=done)
