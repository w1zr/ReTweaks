# ui/pages/rules.py
"""Program rules (choose your own .exe) and auto game mode."""

import os

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QMessageBox,
                               QPushButton, QTextEdit)

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
