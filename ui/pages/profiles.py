# ui/pages/profiles.py
"""Presets: each one sets a list of individual tweaks On or Off (plus a power plan). Shows exactly what
each changes, reads the current state before applying, and every change has its own Undo."""

from PySide6.QtWidgets import QGridLayout, QPushButton

from core.profiles import PRESETS, PROFILES
from ui.widgets import preset_apply
from ui.widgets.common import Card, Page, label, set_role


class ProfilesPage(Page):
    title = "Profiles"
    subtitle = ("Pick a preset to turn a set of individual tweaks on or off in one click. You see exactly "
                "what changes before anything happens, and each tweak can be undone on the Tweaks page.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.buttons = []
        self.last = label("", "muted")
        self.content.addWidget(self.last)
        grid = QGridLayout()
        grid.setSpacing(16)
        for i, (name, prof) in enumerate(PROFILES.items()):
            card = Card(name)
            card.body.addWidget(label(prof["description"], "cardLine", wrap=True))
            p = PRESETS.get(name)
            if p:
                from core.tweaks import BY_ID
                on = [BY_ID[t].name for t, v in p["tweaks"].items() if v]
                off = [BY_ID[t].name for t, v in p["tweaks"].items() if not v]
                if p.get("power"):
                    on.insert(0, "Ultimate Performance power plan" if p["power"] == "ultimate"
                              else "Balanced power plan")
                if on:
                    card.body.addWidget(label("Turns on: " + ", ".join(on), "cardLine", wrap=True))
                if off:
                    card.body.addWidget(label("Turns off: " + ", ".join(off), "muted", wrap=True))
            else:
                card.body.addWidget(label("Changes:", "muted"))
                for step_name, _ in prof["steps"]:
                    card.body.addWidget(label(f"•  {step_name}", "cardLine", wrap=True))
            card.body.addStretch()
            b = set_role(QPushButton(f"Apply {name}"), "primary")
            b.clicked.connect(lambda _=False, n=name: self.apply(n))
            card.body.addWidget(b)
            self.buttons.append(b)
            grid.addWidget(card, *divmod(i, 3))
        for c in range(3):
            grid.setColumnStretch(c, 1)
        self.content.addLayout(grid)

        self.result_card = Card("Last result")
        self.result = label("No preset applied yet.", "cardLine", wrap=True)
        self.result_card.body.addWidget(self.result)
        self.content.addWidget(self.result_card)
        self._show_last()
        self.finish()

    def _show_last(self):
        name = self.ctx.settings.get("last_preset") if isinstance(getattr(self.ctx, "settings", None), dict) else None
        self.last.setText(f"Last preset applied: {name}" if name else "")
        self.last.setVisible(bool(name))

    def apply(self, name):
        for b in self.buttons:
            b.setEnabled(False)

        def finished(_results):
            for b in self.buttons:
                b.setEnabled(True)
            self._show_last()

        preset_apply.start(self, name, self.result.setText, finished)
