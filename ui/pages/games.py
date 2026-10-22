# ui/pages/games.py
"""Game presets: Low / High / Ultra / Ultra Performance / Custom for each game's settings file,
plus presets for any settings file the user picks. Always previews, backs up, and can restore."""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem)

from core import game_presets as gp
from ui.widgets.common import Card, Notice, Page, label, set_role


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
        self.content.addWidget(self.preset_card)

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
            for b in self.tier_buttons:
                b.show()
            self.tier_help.show()
        else:
            entry = self._custom_entry(self.entry_id) or {}
            self.path, self.fmt = entry.get("path"), entry.get("fmt")
            self.note.text.setText("Your own file: use Custom to change values and save your own presets.")
            self.note.show()
            self.b_remove.show()
            self.b_lock.show()
            for b in self.tier_buttons:
                b.hide()
            self.tier_help.hide()
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
    def _confirm_and_apply(self, title, changes):
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
            self.refresh_file()

        self.run_task(gp.apply_changes, game_id, self.path, self.fmt, changes, on_done=done)

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

    def save_user_preset(self):
        changes = self._edited_values()
        if not changes:
            self.msg.setText("Change some values in the table first, then save them as a preset.")
            return
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name:")
        if not ok or not name.strip():
            return
        data = gp.load_custom()
        data["presets"].setdefault(self.entry_id, {})[name.strip()] = changes
        gp.save_custom(data)
        self.load_user_presets()
        self.user_presets.setCurrentText(name.strip())
        self.msg.setText(f"Saved preset “{name.strip()}” ({len(changes)} settings). Use Apply to write it to the file.")

    def apply_user_preset(self):
        name = self.user_presets.currentText()
        preset = gp.load_custom()["presets"].get(self.entry_id, {}).get(name)
        if preset:
            self._confirm_and_apply(f"Preset “{name}”", preset)

    def delete_user_preset(self):
        name = self.user_presets.currentText()
        if not name or QMessageBox.question(self, "Delete preset", f"Delete your preset “{name}”?") != QMessageBox.Yes:
            return
        data = gp.load_custom()
        data["presets"].get(self.entry_id, {}).pop(name, None)
        gp.save_custom(data)
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
