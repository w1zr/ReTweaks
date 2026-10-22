# ui/pages/rules.py
"""Program rules (choose your own .exe) and auto game mode."""

import os

import psutil
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog,
                               QListWidget, QMessageBox, QPushButton, QTextEdit)

from core import app_rules as R
from ui.widgets.common import Card, Page, label, set_role


class RuleCard(Card):
    def __init__(self, page, rule):
        super().__init__(rule["name"])
        self.page, self.rule = page, rule
        self.body.addWidget(label(rule["exe"], "muted", selectable=True))

        row = QHBoxLayout()
        row.addWidget(label("Graphics card:", "cardLine"))
        self.gpu = QComboBox()
        self.gpu.addItems(list(R.GPU_CHOICES))
        self.gpu.setToolTip("Same setting as Windows Settings → System → Display → Graphics.")
        row.addWidget(self.gpu)
        row.addSpacing(16)
        row.addWidget(label("CPU priority while running:", "cardLine"))
        self.prio = QComboBox()
        self.prio.addItems(R.PRIORITY_CHOICES)
        self.prio.setCurrentText(rule.get("priority") or R.PRIORITY_CHOICES[0])
        self.prio.setToolTip("Applied when the program starts, while RYTWEAKS is open. "
                             "“High” can make other apps less responsive.")
        row.addWidget(self.prio)
        row.addStretch()
        self.body.addLayout(row)

        self.fso = QCheckBox("Disable fullscreen optimizations (same as the .exe's Compatibility tab)")
        self.boost = QCheckBox("Auto game mode: switch to the Ultimate Performance power plan while it runs, "
                               "then switch back")
        self.boost.setChecked(bool(rule.get("boost")))
        self.body.addWidget(self.fso)
        self.body.addWidget(self.boost)

        row = QHBoxLayout()
        b_remove = set_role(QPushButton("Remove rule and restore settings"), "danger")
        b_remove.clicked.connect(lambda: page.remove(self))
        row.addWidget(b_remove)
        row.addStretch()
        self.body.addLayout(row)

        self.refresh()
        self.gpu.currentTextChanged.connect(lambda t: page.change(self, "gpu", t))
        self.prio.currentTextChanged.connect(lambda t: page.change(self, "priority", t))
        self.fso.toggled.connect(lambda v: page.change(self, "fso_off", v))
        self.boost.toggled.connect(lambda v: page.change(self, "boost", v))

    def refresh(self):
        """Show the real current Windows values."""
        for w in (self.gpu, self.fso):
            w.blockSignals(True)
        self.gpu.setCurrentText(R.get_gpu(self.rule) or "Let Windows decide")
        self.fso.setChecked(R.get_fso_off(self.rule))
        for w in (self.gpu, self.fso):
            w.blockSignals(False)


class RulesPage(Page):
    title = "Program rules"
    subtitle = ("Pick any game or program (.exe) and choose how Windows should run it. Graphics card and "
                "fullscreen settings are saved in Windows. Priority and auto game mode work while "
                "RYTWEAKS is open (Settings → start with Windows, minimized).")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        top = QHBoxLayout()
        b_add = set_role(QPushButton("Add a program (.exe)…"), "primary")
        b_add.clicked.connect(self.add)
        top.addWidget(b_add)
        top.addStretch()
        self.content.addLayout(top)
        self.msg = label("", "cardLine", wrap=True)
        self.content.addWidget(self.msg)
        self.cards = []
        self.empty = label("No programs yet. Add a game's .exe to set its rules.", "muted")
        self.content.addWidget(self.empty)
        self._insert_at = self.content.count()

        self._build_calm_card()

        log_card = Card("Auto game mode activity")
        self.activity = QTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumHeight(140)
        self.activity.setPlaceholderText("When a program with auto game mode starts or closes, it shows here.")
        log_card.body.addWidget(self.activity)
        self.content.addWidget(log_card)
        self.finish()
        for rule in R.load_rules():
            self._add_card(rule)

    # ------------------------------------------------------------ background calming
    def _build_calm_card(self):
        cfg = R.load_calm_config()
        enabled = bool(self.ctx.settings.get("calm_enabled", False))
        cfg["enabled"] = enabled
        R.save_calm_config(cfg)          # the background worker reads this copy
        self.calm_cfg = cfg
        card = Card("Background calming")
        card.body.addWidget(label(
            "While a game from the list above is running (one with auto game mode or a CPU priority set), "
            "temporarily lower the CPU priority of only the programs you pick here, then put it back when the "
            "game closes (or RYTWEAKS closes). If you change a program's priority yourself in the meantime, "
            "RYTWEAKS leaves it alone. System-critical programs, anti-cheat services, programs that have their "
            "own rule above and RYTWEAKS itself are never lowered. This never closes or pauses anything.",
            "muted", wrap=True))
        self.calm_switch = QCheckBox("Enable background calming")
        self.calm_switch.setChecked(enabled)
        self.calm_switch.toggled.connect(self._calm_enabled)
        card.body.addWidget(self.calm_switch)
        row = QHBoxLayout()
        row.addWidget(label("Priority to use:", "cardLine"))
        self.calm_level = QComboBox()
        self.calm_level.addItems(list(R.CALM_LEVELS))
        self.calm_level.setCurrentText(cfg["priority"])
        self.calm_level.setToolTip("Below normal is gentle. Idle only gives the program CPU time nobody else wants.")
        self.calm_level.currentTextChanged.connect(self._calm_level)
        row.addWidget(self.calm_level)
        row.addStretch()
        card.body.addLayout(row)
        self.calm_list = QListWidget()
        self.calm_list.setMaximumHeight(130)
        card.body.addWidget(self.calm_list)
        row = QHBoxLayout()
        b_run = QPushButton("Add from running programs…")
        b_run.clicked.connect(self._calm_add_running)
        b_type = QPushButton("Type a name…")
        b_type.clicked.connect(self._calm_add_typed)
        b_del = QPushButton("Remove selected")
        b_del.clicked.connect(self._calm_remove)
        for b in (b_run, b_type, b_del):
            row.addWidget(b)
        row.addStretch()
        card.body.addLayout(row)
        self.calm_status = label("", "cardLine", wrap=True)
        card.body.addWidget(self.calm_status)
        self.content.addWidget(card)
        self._fill_calm_list()
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._refresh_calm_status)
        self._timer.start()
        self._refresh_calm_status()

    def _fill_calm_list(self):
        self.calm_list.clear()
        self.calm_list.addItems(self.calm_cfg["apps"])

    def _calm_save(self):
        R.save_calm_config(self.calm_cfg)

    def _calm_enabled(self, on):
        self.ctx.set_setting("calm_enabled", bool(on))
        self.calm_cfg["enabled"] = bool(on)
        self._calm_save()
        self.msg.setText("Background calming " + ("on. It starts the next time a game from the list runs."
                                                  if on else "off. Anything already lowered is restored within a few seconds."))
        self.ctx.log_action("Background calming", "Enabled" if on else "Disabled", "Success")
        self._refresh_calm_status()

    def _calm_level(self, level):
        self.calm_cfg["priority"] = level
        self._calm_save()
        self.ctx.log_action("Background calming", f"Priority set to {level}", "Success")

    def _calm_add(self, name):
        ok, result = R.validate_calm_name(name)
        if not ok:
            QMessageBox.warning(self, "Background calming", result)
            return
        if result in self.calm_cfg["apps"]:
            self.msg.setText(f"{result} is already in the list.")
            return
        self.calm_cfg["apps"].append(result)
        self._calm_save()
        self._fill_calm_list()
        self.ctx.log_action("Background calming", f"Added {result}", "Success")

    def _calm_add_typed(self):
        name, ok = QInputDialog.getText(self, "Add a program", "Program name (for example discord or chrome):")
        if ok and name.strip():
            self._calm_add(name)

    def _calm_add_running(self):
        names = set()
        for p in psutil.process_iter(["name"]):
            n = R.normalize_name(p.info.get("name") or "")
            if n and n not in R.PROTECTED:
                names.add(n)
        if not names:
            QMessageBox.information(self, "Background calming", "Unavailable: no running programs could be listed.")
            return
        name, ok = QInputDialog.getItem(self, "Add a running program", "Program:", sorted(names), 0, False)
        if ok and name:
            self._calm_add(name)

    def _calm_remove(self):
        item = self.calm_list.currentItem()
        if not item:
            return
        self.calm_cfg["apps"].remove(item.text())
        self._calm_save()
        self._fill_calm_list()
        self.ctx.log_action("Background calming", f"Removed {item.text()}", "Success")

    def _refresh_calm_status(self):
        recs = R.load_calm_records()
        if recs:
            self.calm_status.setText("Calmed right now: " + ", ".join(
                f"{r['name']} (PID {r['pid']})" for r in recs))
        elif self.calm_cfg["enabled"]:
            self.calm_status.setText("Nothing is calmed right now. Waiting for a game from the list above to run.")
        else:
            self.calm_status.setText("Off.")

    def _add_card(self, rule):
        card = RuleCard(self, rule)
        self.content.insertWidget(self._insert_at + len(self.cards), card)
        self.cards.append(card)
        self.empty.setVisible(not self.cards)

    def _save(self):
        R.save_rules([c.rule for c in self.cards])

    def add(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a program", os.path.expanduser("~"),
                                              "Programs (*.exe)")
        if not path:
            return
        norm = os.path.normcase(os.path.normpath(path))
        if any(os.path.normcase(c.rule["exe"]) == norm for c in self.cards):
            self.msg.setText("That program already has a rule.")
            return
        rule = R.new_rule(path)
        self._add_card(rule)
        self._save()
        self.ctx.log_action("Program rules", f"Added {path}", "Success")

    def change(self, card, field, value):
        rule = card.rule
        if field == "gpu":
            ok, msg = R.set_gpu(rule, value)
        elif field == "fso_off":
            ok, msg = R.set_fso(rule, value)
        else:
            rule[field] = value
            ok, msg = True, (f"{rule['name']}: {'auto game mode on' if value else 'auto game mode off'}."
                             if field == "boost" else f"{rule['name']}: CPU priority {value}.")
        self._save()
        self.msg.setText(msg)
        self.ctx.log_action("Program rules", f"{rule['name']}: {field} = {value}",
                            "Success" if ok else "Failed", "" if ok else msg)
        if not ok:
            QMessageBox.warning(self, "Program rules", msg)
        card.refresh()

    def remove(self, card):
        if QMessageBox.question(self, "Remove rule",
                                f"Remove the rule for {card.rule['name']} and put its Windows settings back?") \
                != QMessageBox.Yes:
            return
        ok, msg = R.remove_rule_settings(card.rule)
        if not ok:
            QMessageBox.warning(self, "Remove rule", msg)
            return
        self.cards.remove(card)
        card.setParent(None)
        card.deleteLater()
        self._save()
        self.empty.setVisible(not self.cards)
        self.msg.setText(msg)
        self.ctx.log_action("Program rules", f"Removed {card.rule['name']}", "Success")

    def on_auto_event(self, text):
        self.activity.append(text)
        self.ctx.log_action("Auto game mode", text, "Info")
