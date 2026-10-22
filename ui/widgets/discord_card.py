# ui/widgets/discord_card.py
"""Settings card for the Discord status (Rich Presence)."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox

from core.discord_rpc import status_text
from ui.widgets.common import Card, label


class DiscordCard(Card):
    def __init__(self, ctx, presence, parent=None):
        super().__init__("Discord status", parent)
        self.ctx = ctx
        self.presence = presence
        s = ctx.settings
        self.enable = QCheckBox("Show RYTWEAKS on my Discord status")
        self.enable.setChecked(bool(s.get("discord_status", False)))
        self.show_game = QCheckBox("Show which game I'm playing")
        self.show_game.setChecked(bool(s.get("discord_show_game", True)))
        self.show_game.setEnabled(self.enable.isChecked())
        self.status_line = label("", "cardLine", wrap=True)
        note = label("Your Discord friends can see this. RYTWEAKS only talks to the Discord app on this PC.",
                     "muted", wrap=True)
        for w in (self.enable, self.show_game, self.status_line, note):
            self.body.addWidget(w)
        self.enable.toggled.connect(self._changed)
        self.show_game.toggled.connect(self._changed)
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh_status)
        self.refresh_status()

    def _changed(self, _checked=None):
        on, show = self.enable.isChecked(), self.show_game.isChecked()
        self.show_game.setEnabled(on)
        self.ctx.set_setting("discord_status", on)
        self.ctx.set_setting("discord_show_game", show)
        self.presence.configure(on, show)
        if on:
            self.presence.start()
        self.refresh_status()

    def refresh_status(self):
        self.status_line.setText("Status: " + status_text(self.presence.status))

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh_status()
        self.timer.start()

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)
