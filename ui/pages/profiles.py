# ui/pages/profiles.py
"""Performance profiles: apply several real tweaks at once and show each step's result."""

from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton

from core.profiles import PROFILES, apply_profile
from ui.widgets.common import Card, Page, label, set_role
from ui.workers import TaskWorker


class ProfilesPage(Page):
    title = "Profiles"
    subtitle = ("Apply a group of tweaks in one click. You can see exactly what each profile "
                "changes, and switch back with “Windows Default”.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._worker = None
        self.buttons = []
        row = QHBoxLayout()
        row.setSpacing(16)
        for name, prof in PROFILES.items():
            card = Card(name)
            card.body.addWidget(label(prof["description"], "cardLine", wrap=True))
            card.body.addWidget(label("Changes:", "muted"))
            for step_name, _ in prof["steps"]:
                card.body.addWidget(label(f"•  {step_name}", "cardLine"))
            card.body.addStretch()
            b = set_role(QPushButton(f"Apply {name}"), "primary")
            b.clicked.connect(lambda _=False, n=name: self.apply(n))
            card.body.addWidget(b)
            self.buttons.append(b)
            row.addWidget(card, 1)
        self.content.addLayout(row)

        self.result_card = Card("Last result")
        self.result = label("No profile applied yet.", "cardLine", wrap=True)
        self.result_card.body.addWidget(self.result)
        self.content.addWidget(self.result_card)
        self.finish()

    def apply(self, name):
        steps = "\n".join(f"• {s}" for s, _ in PROFILES[name]["steps"])
        if QMessageBox.question(self, f"Apply {name}?", f"This will:\n{steps}") != QMessageBox.Yes:
            return
        for b in self.buttons:
            b.setEnabled(False)
        self.result.setText(f"Applying {name}…")
        self._worker = TaskWorker(apply_profile, name)
        self._worker.done.connect(lambda results: self._done(name, results))
        self._worker.start()

    def _done(self, name, results):
        for b in self.buttons:
            b.setEnabled(True)
        if isinstance(results, tuple):  # the worker itself failed
            results = [("Profile", False, results[1])]
        lines = []
        for step, ok, msg in results:
            lines.append(f"{'✔' if ok else '✖'}  {step}: {msg}")
            self.ctx.log_action(f"Profile: {name}", step, "Success" if ok else "Failed", "" if ok else msg)
        failed = sum(1 for _, ok, _ in results if not ok)
        header = f"{name}: {len(results) - failed} of {len(results)} steps succeeded."
        self.result.setText(header + "\n\n" + "\n".join(lines))
