# ui/pages/fps.py
"""FPS test: real average FPS and 1% / 0.1% lows measured with Intel PresentMon."""

import os
import subprocess
import sys
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
                               QLineEdit, QListWidget, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem)

from core import fps
from ui.widgets.common import Card, KeyValueGrid, Notice, Page, label, set_role

SETTING_PATH = "fps_presentmon_path"


class FpsPage(Page):
    title = "FPS test"
    subtitle = ("Measures real frame times of a running program with Intel PresentMon: average "
                "FPS and 1% / 0.1% lows. Nothing here is estimated, and no result is credited "
                "to a tweak automatically.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.capture = None
        self.capture_game = None
        self.current_runs = []
        self._loaded = False

        # ---- PresentMon location
        c = Card("PresentMon")
        c.body.addWidget(Notice(
            "RYTWEAKS does not include PresentMon. Download the PresentMon console app from the "
            f"<a href=\"{fps.RELEASES_URL}\">official releases page</a> and select PresentMon.exe "
            "below. It needs administrator rights."))
        row = QHBoxLayout()
        self.path_edit = QLineEdit(ctx.settings.get(SETTING_PATH, "") or "")
        self.path_edit.setPlaceholderText("Path to PresentMon.exe")
        self.path_edit.editingFinished.connect(self._path_typed)
        b_browse = QPushButton("Browse…")
        b_browse.clicked.connect(self.browse)
        row.addWidget(self.path_edit, 1)
        row.addWidget(b_browse)
        c.body.addLayout(row)
        self.path_status = label("", "cardLine", wrap=True)
        c.body.addWidget(self.path_status)
        self.content.addWidget(c)

        # ---- run
        r = Card("Run a test")
        r.body.addWidget(label(
            "Start the game first and get to the scene you want to test. Use the same scene, "
            "settings and duration every time you compare.", "muted", wrap=True))
        srow = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search running programs")
        self.search.textChanged.connect(self._filter_procs)
        b_ref = QPushButton("Refresh list")
        b_ref.clicked.connect(self.refresh_processes)
        srow.addWidget(self.search, 1)
        srow.addWidget(b_ref)
        r.body.addLayout(srow)
        self.proc_list = QListWidget()
        self.proc_list.setMinimumHeight(150)
        self.proc_list.setMaximumHeight(220)
        r.body.addWidget(self.proc_list)
        self.proc_hint = label("", "muted", wrap=True)
        r.body.addWidget(self.proc_hint)
        drow = QHBoxLayout()
        self.duration = QComboBox()
        for d in fps.DURATIONS:
            self.duration.addItem(f"{d} seconds", d)
        self.duration.setCurrentIndex(1)
        self.btn_start = set_role(QPushButton("Start test"), "primary")
        self.btn_start.clicked.connect(self.start)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel)
        drow.addWidget(label("Duration"))
        drow.addWidget(self.duration)
        drow.addStretch(1)
        drow.addWidget(self.btn_start)
        drow.addWidget(self.btn_cancel)
        r.body.addLayout(drow)
        self.status = label("", "cardLine", wrap=True, selectable=True)
        r.body.addWidget(self.status)
        self.content.addWidget(r)

        # ---- result
        self.result_card = Card("Result")
        self.result_grid = KeyValueGrid()
        self.result_card.body.addWidget(self.result_grid)
        self.result_card.body.addWidget(label(fps.METHOD_TEXT, "muted", wrap=True))
        self.result_card.setVisible(False)
        self.content.addWidget(self.result_card)

        # ---- saved runs
        s = Card("Saved runs")
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Program", "Date", "Length", "Avg FPS", "1% low",
                                              "0.1% low", "Notes"])
        hh = self.table.horizontalHeader()
        for i in range(6):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(180)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        s.body.addWidget(self.table)
        nrow = QHBoxLayout()
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Notes for the selected run (e.g. “Game Mode off, 1080p low”)")
        self.btn_notes = QPushButton("Save notes")
        self.btn_notes.clicked.connect(self.save_notes)
        nrow.addWidget(self.notes, 1)
        nrow.addWidget(self.btn_notes)
        s.body.addLayout(nrow)
        brow = QHBoxLayout()
        self.btn_compare = set_role(QPushButton("Compare selected two"), "primary")
        self.btn_compare.clicked.connect(self.compare)
        self.btn_delete = QPushButton("Delete selected run")
        self.btn_delete.clicked.connect(self.delete)
        brow.addWidget(self.btn_compare)
        brow.addWidget(self.btn_delete)
        brow.addStretch(1)
        s.body.addLayout(brow)
        self.saved_hint = label("Select one run to edit its notes, or two runs to compare them.",
                                "muted", wrap=True)
        s.body.addWidget(self.saved_hint)
        self.content.addWidget(s)

        self.compare_card = Card("Comparison")
        self.compare_warn = label("", "warn", wrap=True)
        self.compare_card.body.addWidget(self.compare_warn)
        self.compare_table = QTableWidget(0, 5)
        self.compare_table.setHorizontalHeaderLabels(["Metric", "Run A", "Run B", "Difference (B − A)", "Change"])
        self.compare_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.compare_table.verticalHeader().setVisible(False)
        self.compare_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.compare_table.setMinimumHeight(330)
        self.compare_card.body.addWidget(self.compare_table)
        self.compare_card.body.addWidget(label(
            "A difference is a measurement, not proof that a setting caused it. Run-to-run "
            "variation is normal; repeat each test before drawing conclusions.", "muted", wrap=True))
        self.compare_card.setVisible(False)
        self.content.addWidget(self.compare_card)

        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._tick)
        self.finish()

        if not self.path_edit.text():
            found = fps.find_presentmon_near_exe()
            if found:
                self.path_edit.setText(found)
                ctx.set_setting(SETTING_PATH, found)
        self._check_path()
        self._selection_changed()

    # ---------------------------------------------------------------- lifecycle
    def on_shown(self):
        if not self._loaded:
            self._loaded = True
            self.refresh_processes()
            self.reload_runs()

    def wait_for_tasks(self):
        self.timer.stop()
        if self.capture:
            self.capture.cancel()
            self.capture.cleanup()
            self.capture = None
        super().wait_for_tasks()

    # ---------------------------------------------------------------- PresentMon path
    def browse(self):
        start = self.path_edit.text() or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Select PresentMon.exe", start,
                                              "Programs (*.exe);;All files (*)")
        if path:
            self.path_edit.setText(path)
            self._path_typed()

    def _path_typed(self):
        self.ctx.set_setting(SETTING_PATH, self.path_edit.text().strip())
        self._check_path()

    def _check_path(self):
        ok, msg = fps.validate_presentmon_path(self.path_edit.text().strip())
        self.path_status.setText("PresentMon found." if ok else msg)
        self.path_status.setObjectName("good" if ok else "muted")
        self.path_status.style().unpolish(self.path_status)
        self.path_status.style().polish(self.path_status)
        return ok

    # ---------------------------------------------------------------- processes
    def refresh_processes(self):
        self.proc_hint.setText("Reading running programs…")
        self.run_task(fps.list_processes, on_done=self._procs_loaded)

    def _procs_loaded(self, result):
        self.procs = result if isinstance(result, list) else []
        if not self.procs:
            self.proc_hint.setText("Could not read the list of running programs.")
        else:
            self.proc_hint.setText("Programs with a visible window." if sys.platform == "win32"
                                   else "All running processes.")
        self._filter_procs()

    def _filter_procs(self):
        text = self.search.text().lower().strip()
        keep = None
        cur = self.proc_list.currentItem()
        if cur:
            keep = cur.data(256)
        self.proc_list.clear()
        for name, title in getattr(self, "procs", []):
            if text and text not in name.lower() and text not in title.lower():
                continue
            from PySide6.QtWidgets import QListWidgetItem
            it = QListWidgetItem(f"{name}   {title}" if title else name)
            it.setData(256, name)
            self.proc_list.addItem(it)
            if name == keep:
                self.proc_list.setCurrentItem(it)

    # ---------------------------------------------------------------- running
    def _set_busy(self, busy):
        self.btn_start.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)
        self.duration.setEnabled(not busy)
        self.proc_list.setEnabled(not busy)

    def start(self):
        if self.capture:
            return
        if not self._check_path():
            self.status.setText("Select PresentMon.exe first.")
            return
        item = self.proc_list.currentItem()
        if not item:
            self.status.setText("Pick the running program to measure.")
            return
        name = item.data(256)
        seconds = self.duration.currentData()
        cap = fps.Capture(self.path_edit.text().strip(), name, seconds)
        try:
            cap.start()
        except (OSError, ValueError) as e:
            cap.cleanup()
            msg = str(e)
            if getattr(e, "winerror", None) == 740:
                msg = "Windows needs administrator rights to start PresentMon. " + fps.ADMIN_HINT
            self.status.setText(f"Could not start PresentMon: {msg}")
            self.ctx.log_action("FPS test", f"PresentMon on {name}", "Failed", msg)
            return
        self.capture, self.capture_game = cap, name
        self._set_busy(True)
        self.result_card.setVisible(False)
        self.status.setText(f"Measuring {name}… 0 / {seconds} s")
        self.timer.start()

    def cancel(self):
        if self.capture:
            self.timer.stop()
            self.capture.cancel()
            self.capture.cleanup()
            self.capture = None
            self._set_busy(False)
            self.status.setText("Cancelled. Nothing was saved.")

    def _tick(self):
        cap = self.capture
        if not cap:
            self.timer.stop()
            return
        if cap.running():
            if cap.overdue():
                cap.terminate()   # finish() below handles whatever was written
            else:
                self.status.setText(f"Measuring {self.capture_game}… "
                                    f"{min(int(cap.elapsed()), cap.seconds)} / {cap.seconds} s")
                return
        self.timer.stop()
        self.status.setText("Reading the results…")
        self.run_task(cap.finish, on_done=lambda res, c=cap, g=self.capture_game, s=cap.seconds:
                      self._finished(res, c, g, s))

    def _finished(self, result, cap, game, seconds):
        cap.cleanup()
        self.capture = None
        self._set_busy(False)
        if not (isinstance(result, tuple) and len(result) == 2):
            self.status.setText(f"Unexpected error: {result}")
            return
        frames, err = result
        if err:
            self.status.setText(err)
            self.ctx.log_action("FPS test", f"PresentMon on {game}", "Failed", err.splitlines()[0])
            return
        metrics = fps.compute_metrics(frames)
        run = fps.make_run(game, seconds, metrics)
        try:
            fps.add_run(run)
            saved = "Saved to your run list."
        except OSError as e:
            saved = f"The result could not be saved ({e})."
        self.ctx.log_action("FPS test", f"PresentMon on {game}, {seconds} s",
                            f"{metrics['avg_fps']:.1f} FPS average, {metrics['frames']} frames")
        self.status.setText(f"Done. {saved}")
        self._show_result(run)
        self.reload_runs()

    def _show_result(self, run):
        self.result_grid.set_rows(
            [("Program", run["game"])] +
            [(lbl, fps.format_metric(key, run.get(key))) for key, lbl, _u in fps.METRIC_ROWS])
        self.result_card.setVisible(True)

    # ---------------------------------------------------------------- saved runs
    def reload_runs(self):
        self.current_runs = fps.load_runs()
        self.table.setRowCount(0)
        for run in reversed(self.current_runs):
            r = self.table.rowCount()
            self.table.insertRow(r)
            try:
                date = datetime.fromisoformat(run.get("date", "")).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                date = run.get("date", "") or "Unavailable"
            vals = [run.get("game", ""), date, f"{run.get('seconds', '?')} s",
                    fps.format_metric("avg_fps", run.get("avg_fps")) if run.get("avg_fps") is not None else "Unavailable",
                    fps.format_metric("low1_fps", run.get("low1_fps")),
                    fps.format_metric("low01_fps", run.get("low01_fps")),
                    run.get("notes", "")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setData(256, run["id"])
                self.table.setItem(r, c, it)
        self._selection_changed()

    def _selected_ids(self):
        rows = sorted({i.row() for i in self.table.selectedItems()})
        return [self.table.item(r, 0).data(256) for r in rows]

    def _run_by_id(self, rid):
        return next((r for r in self.current_runs if r.get("id") == rid), None)

    def _selection_changed(self):
        ids = self._selected_ids()
        self.btn_compare.setEnabled(len(ids) == 2)
        self.btn_delete.setEnabled(len(ids) == 1)
        self.btn_notes.setEnabled(len(ids) == 1)
        self.notes.setEnabled(len(ids) == 1)
        if len(ids) == 1:
            run = self._run_by_id(ids[0])
            self.notes.setText(run.get("notes", "") if run else "")
            if run:
                self._show_result(run)
        else:
            self.notes.clear()

    def save_notes(self):
        ids = self._selected_ids()
        if len(ids) == 1:
            try:
                fps.update_notes(ids[0], self.notes.text().strip())
            except OSError as e:
                self.saved_hint.setText(f"Could not save notes: {e}")
                return
            self.reload_runs()
            self.saved_hint.setText("Notes saved.")

    def delete(self):
        ids = self._selected_ids()
        if len(ids) != 1:
            return
        run = self._run_by_id(ids[0])
        if QMessageBox.question(self, "Delete run",
                                f"Delete the saved run for {run.get('game', '')} "
                                f"({run.get('date', '')})? This cannot be undone.") != QMessageBox.Yes:
            return
        try:
            fps.delete_run(ids[0])
        except OSError as e:
            self.saved_hint.setText(f"Could not delete: {e}")
            return
        self.compare_card.setVisible(False)
        self.reload_runs()

    def compare(self):
        ids = self._selected_ids()
        if len(ids) != 2:
            return
        a, b = (self._run_by_id(i) for i in ids)
        if not a or not b:
            return
        if a.get("date", "") > b.get("date", ""):
            a, b = b, a   # A = older run
        self.compare_warn.setText("\n".join("• " + w for w in fps.comparison_warnings(a, b)))
        rows = fps.compare_runs(a, b)
        self.compare_table.setRowCount(0)
        for key, lbl, va, vb, diff, pct in rows:
            r = self.compare_table.rowCount()
            self.compare_table.insertRow(r)
            unit = "ms" if key.endswith("_ms") else ("s" if key == "duration_s" else "")
            if diff is None:
                d, p = "Unavailable", "Unavailable"
            else:
                digits = 0 if key == "frames" else (2 if unit == "ms" else 1)
                d = f"{diff:+.{digits}f} {unit or ('FPS' if key.endswith('_fps') else '')}".strip()
                p = f"{pct:+.1f}%" if pct is not None else "Unavailable"
            for c, v in enumerate([lbl, fps.format_metric(key, va), fps.format_metric(key, vb), d, p]):
                self.compare_table.setItem(r, c, QTableWidgetItem(v))
        self.compare_card.title_label.setText(
            f"COMPARISON: A = {a.get('game')} {a.get('date', '')[:16]}   B = {b.get('game')} {b.get('date', '')[:16]}")
        self.compare_card.setVisible(True)
