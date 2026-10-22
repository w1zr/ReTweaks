# ui/pages/tweaks.py
"""Individual tweaks, split into Standard and Advanced. Each row shows the setting's REAL
current state, its trade-off, and has its own Undo. Plus restore point and Undo everything."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core import tweaks as T
from core.optimizer import WindowsOptimizer as W
from core.winutil import is_admin
from ui.widgets.common import Card, Notice, Page, label, set_role, set_status_style


class TweakRow(QWidget):
    """Name, description and trade-off on the left; live status and buttons on the right."""

    def __init__(self, page, name, description, tradeoff, get_status, actions, badges=()):
        super().__init__()
        self.page, self.name, self.get_status = page, name, get_status
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 8)
        text = QVBoxLayout()
        title = name + ("   " + "  ·  ".join(badges) if badges else "")
        text.addWidget(label(title, "sectionTitle"))
        text.addWidget(label(description, "cardLine", wrap=True))
        if tradeoff:
            text.addWidget(label("Trade-off: " + tradeoff, "muted", wrap=True))
        lay.addLayout(text, 1)
        self.status = label("Checking…", "cardLine")
        self.status.setMinimumWidth(150)
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
        value = value if isinstance(value, str) else "Unknown"
        self.status.setText(value)
        set_status_style(self.status, "good" if value.lower().startswith(("on", "enabled", "active")) else None)


def _sep():
    s = QWidget()
    s.setFixedHeight(1)
    s.setStyleSheet("background-color: rgba(128,128,128,0.18);")
    return s


class TweaksPage(Page):
    title = "Tweaks"
    subtitle = ("Apply tweaks one at a time. Status is read from Windows, every change is written to "
                "Logs, and RYTWEAKS saves the original setting so Undo puts it back exactly.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        if not is_admin():
            self.content.addWidget(Notice(
                "RYTWEAKS isn't running as administrator, so tweaks marked “Admin” will fail. "
                "Right-click RYTWEAKS.exe → Run as administrator."))

        top = QHBoxLayout()
        self.b_restore = QPushButton("Create restore point")
        self.b_restore.setToolTip("Windows System Restore point, so you can roll back the whole PC.")
        self.b_restore.clicked.connect(self.restore_point)
        self.b_undo_all = set_role(QPushButton("Undo everything RYTWEAKS changed"), "danger")
        self.b_undo_all.clicked.connect(self.undo_everything)
        top.addWidget(self.b_restore)
        top.addWidget(self.b_undo_all)
        top.addStretch()
        self.top_msg = label("", "muted", wrap=True)
        self.content.addLayout(top)
        self.content.addWidget(self.top_msg)

        self.rows = []
        for level, intro in ((T.STANDARD, "Safe, everyday settings. Easy to switch back."),
                             (T.ADVANCED, "Change how Windows starts or uses hardware. Read the trade-off first.")):
            card = Card(level)
            card.body.addWidget(label(intro, "muted"))
            first = True
            if level == T.STANDARD:
                row = TweakRow(self, "Power plan",
                               "Ultimate Performance stops the CPU from saving power, so it ramps up faster.",
                               "Uses more electricity; laptops drain faster and run warmer. Your current plan "
                               "is saved first, so “Restore previous” switches back.",
                               W.get_active_power_plan,
                               [("Ultimate Performance", W.enable_ultimate_power_plan),
                                ("Balanced", W.set_balanced_power_plan),
                                ("Restore previous", W.restore_previous_power_plan)])
                card.body.addWidget(row)
                self.rows.append(row)
                first = False
            for t in [t for t in T.TWEAKS if t.level == level]:
                if not first:
                    card.body.addWidget(_sep())
                first = False
                badges = (["Admin"] if t.admin else []) + \
                         (["Restart needed"] if t.restart == "restart" else []) + \
                         (["Sign out needed"] if t.restart == "signout" else [])
                row = TweakRow(self, t.name, t.description, t.tradeoff, t.get_state,
                               [("On", lambda t=t: t.apply(True)), ("Off", lambda t=t: t.apply(False)),
                                ("Undo", t.undo)], badges)
                card.body.addWidget(row)
                self.rows.append(row)
            self.content.addWidget(card)
        self.finish()

    def on_shown(self):
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
            self.top_msg.setText(msg)
            if not ok:
                QMessageBox.warning(self, row.name, msg)
            self._refresh(row)

        self.run_task(fn, on_done=done)

    def restore_point(self):
        self.b_restore.setEnabled(False)
        self.top_msg.setText("Creating a restore point… (can take a minute)")

        def done(result):
            ok, msg = result
            self.b_restore.setEnabled(True)
            self.top_msg.setText(msg)
            self.ctx.log_action("Restore point", "Create", "Success" if ok else "Failed", "" if ok else msg)

        self.run_task(T.create_restore_point, on_done=done)

    def undo_everything(self):
        names = [t.name for t in T.changed_tweaks()]
        listing = "\n".join(f"• {n}" for n in names) or "• (no individual tweaks)"
        if QMessageBox.question(
                self, "Undo everything",
                "Put these back to how they were before RYTWEAKS changed them?\n\n"
                f"{listing}\n• Power plan and DNS, if RYTWEAKS saved them") != QMessageBox.Yes:
            return
        self.b_undo_all.setEnabled(False)
        self.top_msg.setText("Restoring…")

        def done(results):
            self.b_undo_all.setEnabled(True)
            if isinstance(results, tuple):
                results = [("Undo everything", False, results[1])]
            if not results:
                self.top_msg.setText("Nothing to undo: RYTWEAKS hasn't changed anything yet.")
            else:
                ok_count = sum(1 for _, ok, _ in results if ok)
                lines = [f"{'✔' if ok else '✖'} {name}: {msg}" for name, ok, msg in results]
                self.top_msg.setText(f"Restored {ok_count} of {len(results)}.\n" + "\n".join(lines))
                for name, ok, msg in results:
                    self.ctx.log_action(name, "Undo", "Success" if ok else "Failed", "" if ok else msg)
            self.on_shown()

        self.run_task(T.undo_everything, on_done=done)
