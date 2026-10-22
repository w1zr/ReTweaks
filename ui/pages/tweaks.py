# ui/pages/tweaks.py
"""System tweaks. Each row shows the setting's REAL current state, read from Windows."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core.optimizer import WindowsOptimizer as W
from core.winutil import is_admin
from ui.widgets.common import Card, Notice, Page, label, set_status_style


class TweakRow(QWidget):
    """Name + description on the left, live status and action buttons on the right."""

    def __init__(self, page, name, description, get_status, actions, restart_note=False):
        super().__init__()
        self.page, self.name, self.get_status = page, name, get_status
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 8)
        text = QVBoxLayout()
        text.addWidget(label(name, "sectionTitle"))
        d = label(description + ("  Takes effect after a restart." if restart_note else ""), "cardLine", wrap=True)
        text.addWidget(d)
        lay.addLayout(text, 1)
        self.status = label("Checking…", "cardLine")
        self.status.setMinimumWidth(170)
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.status)
        self.buttons = []
        for text_, fn in actions:
            b = QPushButton(text_)
            b.clicked.connect(lambda _=False, f=fn, t=text_: self.page.run(self, t, f))
            lay.addWidget(b)
            self.buttons.append(b)

    def set_busy(self, busy):
        for b in self.buttons:
            b.setEnabled(not busy)
        if busy:
            self.status.setText("Working…")

    def show_status(self, value):
        self.status.setText(value)
        v = value.lower()
        set_status_style(self.status, "good" if v.startswith(("enabled", "active")) else None)


class TweaksPage(Page):
    title = "Tweaks"
    subtitle = ("Windows settings that can help in games. Status is read from Windows, "
                "and every change is written to Logs.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        if not is_admin():
            self.content.addWidget(Notice(
                "RyTweaks isn't running as administrator, so some tweaks (like HAGS) will fail. "
                "Right-click RYTWEAKS.exe → Run as administrator."))

        card = Card()
        self.rows = [
            TweakRow(self, "Game Mode",
                     "Windows gives the game you're playing priority over background apps.",
                     W.get_game_mode,
                     [("Turn on", lambda: W.set_game_mode(True)), ("Turn off", lambda: W.set_game_mode(False))]),
            TweakRow(self, "Power plan",
                     "Ultimate Performance stops the CPU from saving power, so it ramps up faster. "
                     "Uses more electricity; on laptops it drains the battery and runs warmer.",
                     W.get_active_power_plan,
                     [("Ultimate Performance", W.enable_ultimate_power_plan), ("Balanced", W.set_balanced_power_plan)]),
            TweakRow(self, "Hardware-accelerated GPU scheduling (HAGS)",
                     "Lets the GPU manage its own memory. Can lower latency on newer GPUs; "
                     "on some PCs it makes no difference. Needs administrator rights.",
                     W.get_hags_status,
                     [("Turn on", lambda: W.set_hags(True)), ("Turn off", lambda: W.set_hags(False))],
                     restart_note=True),
            TweakRow(self, "Xbox Game Bar background recording",
                     "Game Bar can record the last few minutes of gameplay in the background, which costs "
                     "some performance. Turning it off stops that recording.",
                     W.get_xbox_captures,
                     [("Allow", lambda: W.set_xbox_captures(False)), ("Stop", lambda: W.set_xbox_captures(True))]),
        ]
        for i, row in enumerate(self.rows):
            if i:
                sep = QWidget()
                sep.setFixedHeight(1)
                sep.setStyleSheet("background-color: rgba(128,128,128,0.18);")
                card.body.addWidget(sep)
            card.body.addWidget(row)
        self.content.addWidget(card)
        self.finish()

    def on_shown(self):
        self.refresh_all()

    def refresh_all(self):
        for row in self.rows:
            self._refresh(row)

    def _refresh(self, row):
        self.run_task(row.get_status, on_done=row.show_status)

    def run(self, row, action_text, fn):
        row.set_busy(True)

        def done(result):
            ok, msg = result
            row.set_busy(False)
            self.ctx.log_action(row.name, action_text, "Success" if ok else "Failed", "" if ok else msg)
            if not ok:
                QMessageBox.warning(self, row.name, msg)
            self._refresh(row)

        self.run_task(fn, on_done=done)
