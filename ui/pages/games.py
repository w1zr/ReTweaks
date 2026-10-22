# ui/pages/games.py
"""Game presets: Low / High / Ultra / Ultra Performance / Custom for each game's settings file,
plus presets for any settings file the user picks. Always previews, backs up, and can restore."""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
                               QInputDialog, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from core import game_presets as gp
from ui.widgets.common import Card, Notice, Page, label, set_role


class KeepDialog(QDialog):
    """'Keep this resolution?' with a countdown. No answer = switch back (like Windows' own dialog)."""

    SECONDS = 15

    def __init__(self, parent, w, h):
        super().__init__(None)            # top-level, so it stays visible while the screen mode changes
        self.setWindowTitle("Keep this resolution?")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.left = self.SECONDS
        v = QVBoxLayout(self)
        v.addWidget(label(f"Your screen is now running {w}×{h}, stretched by your NVIDIA card.", "sectionTitle", wrap=True))
        self.text = label("", "cardLine", wrap=True)
        v.addWidget(self.text)
        row = QHBoxLayout()
        keep = set_role(QPushButton("Keep"), "primary")
        keep.clicked.connect(self.accept)
        back = QPushButton("Switch back")
        back.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(back)
        row.addWidget(keep)
        v.addLayout(row)
        from PySide6.QtCore import QTimer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._tick(first=True)

    def _tick(self, first=False):
        if not first:
            self.left -= 1
        if self.left <= 0:
            self.timer.stop()
            self.reject()
            return
        self.text.setText(f"Switching back in {self.left} seconds unless you press Keep.")


class PresetEditor(QDialog):
    """Key/value table for one user preset. Keys can only be ones the engine knows for the game
    (or, for your own file, ones that exist in that file); values are free text."""

    def __init__(self, parent, name, settings, allowed_keys):
        super().__init__(parent)
        self.setWindowTitle(f"Edit preset “{name}”")
        self.resize(520, 480)
        self.allowed = list(allowed_keys)
        v = QVBoxLayout(self)
        v.addWidget(label("Double-click a value to change it. Settings are written only if they already "
                          "exist in the game's file.", "muted", wrap=True))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Setting", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table)
        for k, val in settings.items():
            self._row(k, str(val))
        row = QHBoxLayout()
        b_add = QPushButton("Add a setting…")
        b_add.clicked.connect(self.add_key)
        b_del = QPushButton("Remove selected")
        b_del.clicked.connect(self.remove_selected)
        row.addWidget(b_add)
        row.addWidget(b_del)
        row.addStretch()
        v.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def _row(self, key, value):
        r = self.table.rowCount()
        self.table.insertRow(r)
        k = QTableWidgetItem(key)
        k.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.table.setItem(r, 0, k)
        self.table.setItem(r, 1, QTableWidgetItem(value))

    def keys(self):
        return [self.table.item(r, 0).text() for r in range(self.table.rowCount())]

    def add_key(self):
        free = [k for k in self.allowed if k not in self.keys()]
        if not free:
            QMessageBox.information(self, "Add a setting", "Every setting RYTWEAKS knows for this game is already in the preset.")
            return
        key, ok = QInputDialog.getItem(self, "Add a setting", "Setting:", free, 0, False)
        if ok and key:
            self._row(key, "")
            self.table.editItem(self.table.item(self.table.rowCount() - 1, 1))

    def remove_selected(self):
        for r in sorted({i.row() for i in self.table.selectedItems()}, reverse=True):
            self.table.removeRow(r)

    def result_settings(self, original):
        """Edited values. A value that still equals the old value keeps its original type."""
        out = {}
        for r in range(self.table.rowCount()):
            k, val = self.table.item(r, 0).text(), self.table.item(r, 1).text()
            old = original.get(k)
            out[k] = old if old is not None and str(old) == val else val
        return out


class GamesPage(Page):
    title = "Game presets"
    subtitle = ("Pick a game and a preset. RYTWEAKS shows exactly what will change, backs up the game's "
                "settings file first, and only changes settings that already exist in it. Close the game first.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.path = None
        self.fmt = None
        self.entry_id = None

        top = QHBoxLayout()
        top.addWidget(label("Game:", "cardLine"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(280)
        self.combo.currentIndexChanged.connect(self.select)
        top.addWidget(self.combo)
        b_add = QPushButton("Choose your own file…")
        b_add.setToolTip("Any game's settings file (key=value, key:value or \"key\" \"value\").")
        b_add.clicked.connect(self.add_own_file)
        top.addWidget(b_add)
        self.b_remove = QPushButton("Remove from list")
        self.b_remove.clicked.connect(self.remove_own_file)
        top.addWidget(self.b_remove)
        top.addStretch()
        self.content.addLayout(top)

        # ---- file
        self.file_card = Card("Settings file")
        self.file_lbl = label("", "cardLine", wrap=True, selectable=True)
        self.file_card.body.addWidget(self.file_lbl)
        row = QHBoxLayout()
        self.b_pick = QPushButton("Use a different file…")
        self.b_pick.clicked.connect(self.pick_file)
        self.b_open = QPushButton("Open folder")
        self.b_open.clicked.connect(lambda: self.path and os.startfile(os.path.dirname(self.path)))
        self.b_lock = QPushButton("")
        self.b_lock.clicked.connect(self.toggle_lock)
        for b in (self.b_pick, self.b_open, self.b_lock):
            row.addWidget(b)
        row.addStretch()
        self.file_card.body.addLayout(row)
        self.note = Notice("")
        self.file_card.body.addWidget(self.note)
        self.content.addWidget(self.file_card)

        # ---- presets
        self.preset_card = Card("Presets")
        self.tier_row = QHBoxLayout()
        self.tier_buttons = []
        for tier in gp.TIERS:
            b = set_role(QPushButton(tier), "primary")
            b.clicked.connect(lambda _=False, t=tier: self.apply_tier(t))
            self.tier_row.addWidget(b)
            self.tier_buttons.append(b)
        self.tier_row.addStretch()
        self.preset_card.body.addLayout(self.tier_row)
        self.tier_help = label("Low: weaker PCs · High: balanced · Ultra: best visuals · "
                               "Ultra Performance: competitive, low effects but full resolution. "
                               "FPS caps are never changed by presets (use Custom).", "muted", wrap=True)
        self.preset_card.body.addWidget(self.tier_help)
        row = QHBoxLayout()
        row.addWidget(label("Your presets:", "cardLine"))
        self.user_presets = QComboBox()
        self.user_presets.setMinimumWidth(200)
        row.addWidget(self.user_presets)
        b_apply_user = QPushButton("Apply")
        b_apply_user.clicked.connect(self.apply_user_preset)
        b_del_user = QPushButton("Delete")
        b_del_user.clicked.connect(self.delete_user_preset)
        row.addWidget(b_apply_user)
        row.addWidget(b_del_user)
        row.addStretch()
        self.preset_card.body.addLayout(row)
        row = QHBoxLayout()
        for text, fn, tip in (
                ("Rename…", self.rename_user_preset, "Rename the selected preset of yours."),
                ("Duplicate…", self.duplicate_user_preset, "Make a copy of the selected preset of yours."),
                ("Edit…", self.edit_user_preset, "Change the values in the selected preset."),
                ("Export…", self.export_user_preset, "Save the selected preset to a .json file you can share."),
                ("Import…", self.import_user_preset, "Add a preset from a .json file exported by RYTWEAKS."),
                ("Copy a built-in preset…", self.copy_builtin_preset,
                 "Built-in presets can't be changed, but you can copy one to edit.")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
            if text.startswith("Copy"):
                self.b_copy_builtin = b
        row.addStretch()
        self.preset_card.body.addLayout(row)
        self.content.addWidget(self.preset_card)

        # ---- Fortnite stretched resolution (v1.5)
        self.stretch_card = Card("Stretched resolution (Fortnite)")
        self.stretch_card.body.addWidget(label(
            "Plays Fortnite at a narrower resolution stretched to fill your screen, e.g. 1720×1080 on a "
            "1920×1080 monitor. Characters look wider; you don't see more of the map. Sets Fortnite to "
            "Fullscreen (stretching doesn't work in borderless). A backup is saved first.", "muted", wrap=True))
        srow = QHBoxLayout()
        self.stretch_size = QComboBox()
        for w, h in gp.STRETCH_SIZES:
            self.stretch_size.addItem(f"{w} × {h}", (w, h))
        srow.addWidget(label("Resolution", "cardLine"))
        srow.addWidget(self.stretch_size)
        self.b_stretch = set_role(QPushButton("Apply stretched"), "primary")
        self.b_stretch.clicked.connect(self.apply_stretch)
        self.b_native = QPushButton("Back to native")
        self.b_native.clicked.connect(self.apply_native)
        self.b_nvidia = QPushButton("Set up NVIDIA automatically")
        self.b_nvidia.setToolTip("Adds this resolution to your NVIDIA graphics card, stretched to full screen "
                                 "(same as NVIDIA Control Panel → Create Custom Resolution). Your screen switches "
                                 "for a test; press Keep or it switches back by itself.")
        self.b_nvidia.clicked.connect(self.nvidia_setup)
        srow.addWidget(self.b_stretch)
        srow.addWidget(self.b_native)
        srow.addWidget(self.b_nvidia)
        srow.addStretch()
        self.stretch_card.body.addLayout(srow)
        self.stretch_lock = QCheckBox("Lock the file afterwards so Fortnite doesn't reset it (recommended)")
        self.stretch_lock.setChecked(True)
        self.stretch_card.body.addWidget(self.stretch_lock)
        self.stretch_now = label("", "cardLine")
        self.stretch_card.body.addWidget(self.stretch_now)
        crow = QHBoxLayout()
        self.stretch_check = label("", "cardLine", wrap=True)
        self.b_check_mode = QPushButton("Check again")
        self.b_check_mode.setToolTip("Reads the list of resolutions your graphics driver offers for your main display.")
        self.b_check_mode.clicked.connect(self.check_stretch_mode)
        crow.addWidget(self.stretch_check, 1)
        crow.addWidget(self.b_check_mode, 0, Qt.AlignTop)
        self.stretch_card.body.addLayout(crow)
        self.stretch_size.currentIndexChanged.connect(lambda _i: self.check_stretch_mode())
        self.stretch_card.body.addWidget(label(
            "<b>All three steps are needed:</b><br>"
            "<b>1.</b> Apply stretched here (with Fortnite closed).<br>"
            "<b>2.</b> Your graphics card must offer the resolution and stretch it (once):<br>"
            "&nbsp;&nbsp;• <b>NVIDIA:</b> press <b>Set up NVIDIA automatically</b> above. If that doesn't work on your PC, "
            "do it by hand in <b>NVIDIA Control Panel</b> → Display → Change resolution → Customize → tick “Enable "
            "resolutions not exposed by the display” → Create Custom Resolution: same width × height and your "
            "refresh rate → Test → Yes. Then Adjust desktop size and position → Scaling: <b>Full-screen</b>, "
            "Perform scaling on: <b>GPU</b>, tick <b>Override the scaling mode set by games and programs</b> → Apply.<br>"
            "&nbsp;&nbsp;• <b>AMD Software</b> → Display → GPU Scaling: On, Scaling Mode: <b>Full panel</b>; add the "
            "resolution under Custom Resolutions.<br>"
            "&nbsp;&nbsp;• <b>Intel Graphics Command Center</b> → Display → Scale: <b>Stretch</b>.<br>"
            "<b>3.</b> In Fortnite: Settings → Video → Window Mode: <b>Fullscreen</b>. “Windowed Fullscreen” "
            "always uses your desktop resolution, so stretched can't work there. If the file is locked, Fortnite "
            "can't save menu changes: unlock it, set Fullscreen and the resolution in Fortnite, then lock it again.<br>"
            "Epic locks competitive modes (Arena and tournaments) to 16:9 since April 2019, so stretched only "
            "applies in regular matches. Back to native, or Restore under Backups, undoes it.", "muted", wrap=True))
        self.content.addWidget(self.stretch_card)

        # ---- custom editor
        self.custom_card = Card("Custom")
        self.custom_card.body.addWidget(label(
            "Every setting in the file. Double-click a value to change it, then Apply or save it as one of your presets.",
            "muted", wrap=True))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Setting", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(300)
        self.custom_card.body.addWidget(self.table)
        row = QHBoxLayout()
        b_apply = set_role(QPushButton("Apply changes"), "primary")
        b_apply.clicked.connect(self.apply_custom)
        b_save = QPushButton("Save changes as a preset…")
        b_save.clicked.connect(self.save_user_preset)
        b_reload = QPushButton("Reload from file")
        b_reload.clicked.connect(self.load_table)
        for b in (b_apply, b_save, b_reload):
            row.addWidget(b)
        row.addStretch()
        self.custom_card.body.addLayout(row)
        self.content.addWidget(self.custom_card)

        # ---- backups
        self.backup_card = Card("Backups")
        self.backups = QComboBox()
        row = QHBoxLayout()
        row.addWidget(self.backups, 1)
        b_restore = QPushButton("Restore this backup")
        b_restore.clicked.connect(self.restore)
        row.addWidget(b_restore)
        self.backup_card.body.addLayout(row)
        self.content.addWidget(self.backup_card)

        self.msg = label("", "cardLine", wrap=True)
        self.content.addWidget(self.msg)
        self.finish()
        self.fill_combo()

    # ------------------------------------------------------------ game list
    def fill_combo(self, select_id=None):
        self.combo.blockSignals(True)
        self.combo.clear()
        for g in gp.GAMES:
            self.combo.addItem(g.name, g.id)
        for f in gp.load_custom()["files"]:
            self.combo.addItem(f"{f['name']} (your file)", f["id"])
        self.combo.blockSignals(False)
        idx = self.combo.findData(select_id) if select_id else 0
        self.combo.setCurrentIndex(max(idx, 0))
        self.select()

    def _custom_entry(self, eid):
        return next((f for f in gp.load_custom()["files"] if f["id"] == eid), None)

    def select(self, *_):
        self.entry_id = self.combo.currentData()
        game = gp.BY_ID.get(self.entry_id)
        self.msg.setText("")
        if game:
            saved = gp.load_custom().get("paths", {}).get(game.id)
            files = game.find_files()
            self.path = saved if saved and os.path.isfile(saved) else (files[0] if files else None)
            self.fmt = game.fmt
            self.note.text.setText(game.note)
            self.note.setVisible(bool(game.note))
            self.b_remove.hide()
            self.b_lock.setVisible(game.lockable)
            self.stretch_card.setVisible(game.id == "fortnite")
            if game.id == "fortnite":
                self.check_stretch_mode()
            for b in self.tier_buttons:
                b.show()
            self.tier_help.show()
            self.b_copy_builtin.show()
        else:
            entry = self._custom_entry(self.entry_id) or {}
            self.path, self.fmt = entry.get("path"), entry.get("fmt")
            self.note.text.setText("Your own file: use Custom to change values and save your own presets.")
            self.note.show()
            self.b_remove.show()
            self.b_lock.show()
            self.stretch_card.hide()
            for b in self.tier_buttons:
                b.hide()
            self.tier_help.hide()
            self.b_copy_builtin.hide()
        self.refresh_file()

    def refresh_file(self):
        ok = bool(self.path and os.path.isfile(self.path))
        if ok:
            self.file_lbl.setText(self.path)
        else:
            self.file_lbl.setText("Settings file not found. Start the game once so it creates the file, "
                                  "or use “Use a different file…” to pick it.")
        for b in self.tier_buttons:
            b.setEnabled(ok)
        self.b_open.setEnabled(ok)
        self.b_lock.setEnabled(ok)
        if ok:
            self.b_lock.setText("Unlock file" if gp.is_read_only(self.path) else "Lock file (read-only)")
        self.custom_card.setVisible(ok)
        self.b_stretch.setEnabled(ok)
        self.b_native.setEnabled(ok)
        cur = gp.current_resolution(self.path, self.fmt) if ok and self.entry_id == "fortnite" else None
        nat = self._native_size()
        self.stretch_now.setText((f"Fortnite's resolution now: {cur[0]} × {cur[1]}" if cur else
                                  "Fortnite's resolution: Unavailable (not in the file yet)") +
                                 (f" · Your screen: {nat[0]} × {nat[1]}" if nat else ""))
        self.load_table()
        self.load_user_presets()
        self.load_backups()

    # ------------------------------------------------------------ file selection
    def pick_file(self):
        start = os.path.dirname(self.path) if self.path else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, "Choose the settings file", start,
                                              "Settings files (*.ini *.txt *.cfg *.vcfg *.json);;All files (*)")
        if not path:
            return
        data = gp.load_custom()
        if gp.BY_ID.get(self.entry_id):
            data.setdefault("paths", {})[self.entry_id] = path
        else:
            for f in data["files"]:
                if f["id"] == self.entry_id:
                    f["path"] = path
        gp.save_custom(data)
        self.select()

    def add_own_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a game's settings file", os.path.expanduser("~"),
                                              "Settings files (*.ini *.txt *.cfg *.vcfg);;All files (*)")
        if not path:
            return
        name, ok = QInputDialog.getText(self, "Name", "Name for this file (e.g. the game):",
                                        text=os.path.basename(os.path.dirname(path)) or os.path.basename(path))
        if not ok:
            return
        try:
            entry, msg = gp.add_custom_file(path, name.strip() or None)
        except Exception as e:
            entry, msg = None, str(e)
        if not entry:
            QMessageBox.warning(self, "Choose your own file", msg)
            return
        self.ctx.log_action("Game presets", f"Added file {path}", "Success")
        self.fill_combo(entry["id"])
        self.msg.setText(msg)

    def remove_own_file(self):
        data = gp.load_custom()
        data["files"] = [f for f in data["files"] if f["id"] != self.entry_id]
        gp.save_custom(data)  # presets for it are kept in case it's added again
        self.fill_combo()

    def toggle_lock(self):
        if gp.game_running(self.entry_id):
            QMessageBox.warning(self, "Lock file", "Close the game first.")
            return
        locked = gp.is_read_only(self.path)
        try:
            gp.set_read_only(self.path, not locked)
            self.ctx.log_action("Game presets", f"{'Unlock' if locked else 'Lock'} {self.path}", "Success")
            self.msg.setText("File unlocked: the game can save its own changes again." if locked else
                             "File locked: the game can't overwrite your settings, but changes you make "
                             "in the game's menu won't save until you unlock it.")
        except Exception as e:
            QMessageBox.warning(self, "Lock file", str(e))
        self.refresh_file()

    # ------------------------------------------------------------ apply
    def _confirm_and_apply(self, title, changes, on_ok=None):
        if not changes:
            return
        try:
            rows, missing = gp.preview(self.path, self.fmt, changes)
        except Exception as e:
            QMessageBox.warning(self, title, f"Couldn't read the file: {e}")
            return
        real = [(k, a, b) for k, a, b in rows if a != b]
        if not real:
            self.msg.setText("Nothing to change: the file already has these values.")
            return
        lines = "\n".join(f"{k}:  {a}  →  {b}" for k, a, b in real)
        extra = (f"\n\nNot in your file (skipped): {', '.join(missing)}" if missing else "")
        if QMessageBox.question(self, title, f"These settings will change:\n\n{lines}{extra}\n\n"
                                "A backup is saved first. Continue?") != QMessageBox.Yes:
            return
        game_id = self.entry_id

        def done(result):
            ok, msg, applied, skipped = result if isinstance(result, tuple) and len(result) == 4 \
                else (False, str(result), {}, [])
            self.msg.setText(msg)
            self.ctx.log_action(f"Game presets: {self.combo.currentText()}", title,
                                "Success" if ok else "Failed", "" if ok else msg)
            if not ok:
                QMessageBox.warning(self, title, msg)
            elif on_ok:
                on_ok()
            self.refresh_file()

        self.run_task(gp.apply_changes, game_id, self.path, self.fmt, changes, on_done=done)

    # ------------------------------------------------------------ stretched resolution (v1.5)
    def _native_size(self):
        """The primary screen's resolution in real pixels (what 'native' means)."""
        from PySide6.QtGui import QGuiApplication
        scr = QGuiApplication.primaryScreen()
        if not scr:
            return None
        r = scr.devicePixelRatio()
        return int(round(scr.size().width() * r)), int(round(scr.size().height() * r))

    def check_stretch_mode(self):
        """Is the chosen resolution in the display driver's mode list? (Fortnite only lists those.)"""
        from core import display
        w, h = self.stretch_size.currentData()
        self.stretch_check.setText("Checking your display's resolutions…")

        def done(res):
            if isinstance(res, tuple) and len(res) == 3:
                self.stretch_check.setText(res[2])
            else:
                self.stretch_check.setText("Couldn't read your display's modes.")

        self.run_task(display.stretch_mode_status, w, h, on_done=done)

    def nvidia_setup(self):
        """Adds the chosen resolution to the NVIDIA driver (stretched to full screen), with a timed Keep test."""
        from core import display
        from core import nvidia_display as nvd
        w, h = self.stretch_size.currentData()
        if gp.game_running("fortnite"):
            QMessageBox.warning(self, "Set up NVIDIA", "Close Fortnite first.")
            return
        if QMessageBox.question(
                self, "Set up NVIDIA",
                f"RYTWEAKS will add {w}×{h} to your NVIDIA graphics card, stretched to fill your screen.\n\n"
                "Your screen goes black for a moment and switches to it as a test. Then press Keep within "
                f"{KeepDialog.SECONDS} seconds. If you don't (or can't see the screen), it switches back by "
                "itself.\n\nContinue?") != QMessageBox.Yes:
            return
        what = f"NVIDIA custom resolution {w}×{h}"
        try:
            nv = nvd.NvApi()
            device, nw, nh, hz = nvd.primary_display()
            did = nv.display_id(device)
            timing = nv.timing(did, nw, nh, hz)
            nv.try_custom(did, nvd.build_custom(w, h, timing))
        except Exception as e:
            self.ctx.log_action("Game presets", what, "Failed", str(e))
            QMessageBox.warning(self, "Set up NVIDIA",
                                f"The NVIDIA driver didn't accept it: {e}\n\nNothing was changed. You can still add it "
                                "by hand in NVIDIA Control Panel (step 2 on this page).")
            return
        keep = KeepDialog(self, w, h).exec() == QDialog.Accepted
        try:
            if keep:
                nv.save_custom(did)
                ok, msg = display.restore_saved_mode(device)
                self.ctx.log_action("Game presets", what, "Saved")
                self.msg.setText(f"✔ {w}×{h} was added to your NVIDIA card. {msg} Now start Fortnite and pick "
                                 f"Window Mode: Fullscreen and Resolution: {w}×{h}.")
            else:
                nv.revert_trial(did)
                self.ctx.log_action("Game presets", what, "Reverted")
                self.msg.setText("Switched back. Nothing was saved.")
        except Exception as e:
            ok, msg = display.restore_saved_mode(device)          # always try to get the normal desktop back
            self.ctx.log_action("Game presets", what, "Failed", str(e))
            QMessageBox.warning(self, "Set up NVIDIA", f"{e}\n\n{msg}")
        self.check_stretch_mode()

    def _lock_after(self):
        if self.stretch_lock.isChecked() and self.path and not gp.is_read_only(self.path):
            try:
                gp.set_read_only(self.path, True)
                self.ctx.log_action("Game presets", f"Lock {self.path}", "Success")
                self.msg.setText(self.msg.text() + " The file is locked so Fortnite keeps it; unlock it to "
                                 "save changes you make in Fortnite's menu.")
            except Exception as e:
                self.msg.setText(self.msg.text() + f" Couldn't lock the file: {e}")

    def apply_stretch(self):
        w, h = self.stretch_size.currentData()

        def after():
            self._lock_after()
            self.msg.setText(self.msg.text() + f" Next: make sure your graphics card offers {w}×{h} (step 2), then "
                             "set Window Mode to Fullscreen in Fortnite (step 3).")
            self.check_stretch_mode()

        self._confirm_and_apply(f"Stretched resolution {w}×{h}", gp.resolution_changes(w, h), after)

    def apply_native(self):
        nat = self._native_size()
        if not nat:
            self.msg.setText("Couldn't read your screen's resolution.")
            return
        self._confirm_and_apply(f"Native resolution {nat[0]}×{nat[1]}", gp.resolution_changes(*nat))

    def apply_tier(self, tier):
        game = gp.BY_ID.get(self.entry_id)
        if game:
            self._confirm_and_apply(f"{tier} preset", game.presets[tier])

    def _edited_values(self):
        out = {}
        for r in range(self.table.rowCount()):
            k, v = self.table.item(r, 0), self.table.item(r, 1)
            if k and v and v.text() != v.data(Qt.UserRole):
                out[k.text()] = v.text()
        return out

    def apply_custom(self):
        changes = self._edited_values()
        if not changes:
            self.msg.setText("Change a value in the table first (double-click it).")
            return
        self._confirm_and_apply("Custom changes", changes)

    # ------------------------------------------------------------ custom table + user presets
    def load_table(self):
        self.table.setRowCount(0)
        if not (self.path and os.path.isfile(self.path)):
            return
        try:
            settings = gp.read_settings(self.path, self.fmt)
        except Exception as e:
            self.msg.setText(f"Couldn't read the file: {e}")
            return
        for k, v in settings.items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            key = QTableWidgetItem(k)
            key.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            val = QTableWidgetItem(v)
            val.setData(Qt.UserRole, v)
            self.table.setItem(r, 0, key)
            self.table.setItem(r, 1, val)

    def load_user_presets(self):
        self.user_presets.clear()
        presets = gp.load_custom()["presets"].get(self.entry_id, {})
        self.user_presets.addItems(sorted(presets))

    def _ask_new_name(self, title, text="", exclude=None):
        """Ask for a preset name. If it clashes with one of yours, ask: rename or replace.
        Returns (name, replace) or (None, False)."""
        while True:
            name, ok = QInputDialog.getText(self, title, "Preset name:", text=text)
            if not ok:
                return None, False
            good, name = gp.clean_name(name)
            if not good:
                QMessageBox.warning(self, title, name)
                continue
            if name in gp.user_presets(self.entry_id) and name != exclude:
                box = QMessageBox(QMessageBox.Question, title,
                                  f"You already have a preset called “{name}”.", parent=self)
                b_replace = box.addButton("Replace it", QMessageBox.DestructiveRole)
                b_rename = box.addButton("Choose another name", QMessageBox.AcceptRole)
                box.addButton(QMessageBox.Cancel)
                box.exec()
                if box.clickedButton() is b_replace:
                    return name, True
                if box.clickedButton() is b_rename:
                    text = name
                    continue
                return None, False
            return name, False

    def _selected_user_preset(self):
        name = self.user_presets.currentText()
        if not name:
            self.msg.setText("Pick one of your presets first.")
        return name

    def save_user_preset(self):
        changes = self._edited_values()
        if not changes:
            self.msg.setText("Change some values in the table first, then save them as a preset.")
            return
        name, replace = self._ask_new_name("Save preset")
        if not name:
            return
        status, msg = gp.save_user_preset(self.entry_id, name, changes, replace)
        self.load_user_presets()
        if status == "ok":
            self.user_presets.setCurrentText(name)
            self.msg.setText(f"Saved preset “{name}” ({len(changes)} settings). Use Apply to write it to the file.")
        else:
            QMessageBox.warning(self, "Save preset", msg)

    def rename_user_preset(self):
        old = self._selected_user_preset()
        if not old:
            return
        new, replace = self._ask_new_name("Rename preset", old, exclude=old)
        if not new:
            return
        status, msg = gp.rename_user_preset(self.entry_id, old, new, replace)
        self.msg.setText(msg)
        if status == "error":
            QMessageBox.warning(self, "Rename preset", msg)
        else:
            self.ctx.log_action(f"Game presets: {self.combo.currentText()}", f"Rename preset {old} → {new}", "Success")
        self.load_user_presets()
        self.user_presets.setCurrentText(new)

    def duplicate_user_preset(self):
        src = self._selected_user_preset()
        if not src:
            return
        new, replace = self._ask_new_name("Duplicate preset", f"{src} copy")
        if not new:
            return
        status, msg = gp.duplicate_preset(self.entry_id, src, new, replace)
        self.msg.setText(msg)
        if status == "error":
            QMessageBox.warning(self, "Duplicate preset", msg)
        self.load_user_presets()
        self.user_presets.setCurrentText(new)

    def copy_builtin_preset(self):
        game = gp.BY_ID.get(self.entry_id)
        if not game:
            self.msg.setText("Your own files have no built-in presets.")
            return
        tier, ok = QInputDialog.getItem(self, "Copy a built-in preset", "Built-in preset:", gp.TIERS, 0, False)
        if not ok:
            return
        new, replace = self._ask_new_name("Copy a built-in preset", f"My {tier}")
        if not new:
            return
        status, msg = gp.duplicate_preset(self.entry_id, tier, new, replace)
        self.msg.setText(msg)
        if status == "error":
            QMessageBox.warning(self, "Copy a built-in preset", msg)
        self.load_user_presets()
        self.user_presets.setCurrentText(new)

    def _file_keys(self):
        try:
            return list(gp.read_settings(self.path, self.fmt)) if self.path and os.path.isfile(self.path) else []
        except Exception:
            return []

    def edit_user_preset(self):
        name = self._selected_user_preset()
        if not name:
            return
        original = gp.user_presets(self.entry_id).get(name, {})
        dlg = PresetEditor(self, name, original, gp.known_keys(self.entry_id, self._file_keys()))
        if dlg.exec() != QDialog.Accepted:
            return
        ok, msg = gp.update_user_preset(self.entry_id, name, dlg.result_settings(original), self._file_keys())
        self.msg.setText(msg)
        if ok:
            self.ctx.log_action(f"Game presets: {self.combo.currentText()}", f"Edit preset {name}", "Success")
        else:
            QMessageBox.warning(self, "Edit preset", msg)

    def export_user_preset(self):
        name = self._selected_user_preset()
        if not name:
            return
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip() or "preset"
        path, _ = QFileDialog.getSaveFileName(self, "Export preset", os.path.join(os.path.expanduser("~"), f"{safe}.json"),
                                              "RYTWEAKS preset (*.json)")
        if not path:
            return
        ok, msg = gp.export_preset(self.entry_id, name, path)
        self.msg.setText(msg)
        self.ctx.log_action(f"Game presets: {self.combo.currentText()}", f"Export preset {name}",
                            "Success" if ok else "Failed", "" if ok else msg)
        if not ok:
            QMessageBox.warning(self, "Export preset", msg)

    def import_user_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import preset", os.path.expanduser("~"),
                                              "RYTWEAKS preset (*.json);;All files (*)")
        if not path:
            return
        status, msg, name = gp.import_preset(self.entry_id, path)
        while status == "clash":
            box = QMessageBox(QMessageBox.Question, "Import preset", msg, parent=self)
            b_replace = box.addButton("Replace it", QMessageBox.DestructiveRole)
            b_rename = box.addButton("Import under another name", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is b_replace:
                status, msg, name = gp.import_preset(self.entry_id, path, name, replace=True)
            elif box.clickedButton() is b_rename:
                new, ok = QInputDialog.getText(self, "Import preset", "New name:", text=f"{name} (imported)")
                if not ok:
                    return
                status, msg, name = gp.import_preset(self.entry_id, path, new.strip())
            else:
                self.msg.setText("Import cancelled. Nothing was changed.")
                return
        if status != "ok":
            QMessageBox.warning(self, "Import preset", msg)
            self.msg.setText(msg)
            return
        self.load_user_presets()
        self.user_presets.setCurrentText(name)
        self.msg.setText(msg)
        self.ctx.log_action(f"Game presets: {self.combo.currentText()}", f"Import preset {name}", "Success")

    def apply_user_preset(self):
        name = self.user_presets.currentText()
        preset = gp.load_custom()["presets"].get(self.entry_id, {}).get(name)
        if preset:
            self._confirm_and_apply(f"Preset “{name}”", preset)

    def delete_user_preset(self):
        name = self.user_presets.currentText()
        if not name or QMessageBox.question(self, "Delete preset", f"Delete your preset “{name}”?") != QMessageBox.Yes:
            return
        gp.delete_user_preset(self.entry_id, name)
        self.load_user_presets()

    # ------------------------------------------------------------ backups
    def load_backups(self):
        self.backups.clear()
        self._backup_list = gp.list_backups(self.entry_id) if self.entry_id else []
        for b in self._backup_list:
            self.backups.addItem(f"{b['when']}  ({os.path.basename(b['original'])})")
        if not self._backup_list:
            self.backups.addItem("No backups yet. One is made before every change.")

    def restore(self):
        i = self.backups.currentIndex()
        if not self._backup_list or i < 0:
            return
        b = self._backup_list[i]
        if QMessageBox.question(self, "Restore backup",
                                f"Replace the current settings file with the backup from {b['when']}?\n"
                                "(The current file is backed up first.)") != QMessageBox.Yes:
            return
        ok, msg = gp.restore_backup(self.entry_id, b)
        self.msg.setText(msg)
        self.ctx.log_action(f"Game presets: {self.combo.currentText()}", "Restore backup",
                            "Success" if ok else "Failed", "" if ok else msg)
        self.refresh_file()
