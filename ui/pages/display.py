# ui/pages/display.py
"""Display refresh rate check and GPU driver age."""

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout)

from core import display as dsp
from ui.widgets.common import Card, KeyValueGrid, NA, Notice, Page, label, set_role

REVERT_SECONDS = 15


class KeepSettingsDialog(QDialog):
    """'Keep these settings?' with a countdown. Rejecting or timing out means revert."""

    def __init__(self, seconds=REVERT_SECONDS, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keep these display settings?")
        self.left = seconds
        lay = QVBoxLayout(self)
        self.msg = label("", wrap=True)
        lay.addWidget(self.msg)
        row = QHBoxLayout()
        keep = set_role(QPushButton("Keep changes"), "primary")
        revert = QPushButton("Revert")
        keep.clicked.connect(self.accept)
        revert.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(revert)
        row.addWidget(keep)
        lay.addLayout(row)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._update_text()
        self._timer.start(1000)

    def _update_text(self):
        self.msg.setText(f"Keep these settings? Reverting automatically in {self.left} s "
                         "if you do not confirm.")

    def _tick(self):
        self.left -= 1
        if self.left <= 0:
            self._timer.stop()
            self.reject()
        else:
            self._update_text()


class DisplayPage(Page):
    title = "Display & drivers"
    subtitle = ("Checks whether each monitor runs at the highest refresh rate it supports at its "
                "current resolution, and shows how old your graphics driver is.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._loaded = False
        self.mon_box = QVBoxLayout()
        self.drv_box = QVBoxLayout()
        self.content.addLayout(self.mon_box)
        self.content.addLayout(self.drv_box)
        row = QHBoxLayout()
        refresh = QPushButton("Re-check")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        row.addStretch(1)
        self.content.addLayout(row)
        self.finish()

    def on_shown(self):
        if not self._loaded:
            self.refresh()

    def refresh(self):
        self._loaded = True
        self.run_task(dsp.list_displays, on_done=self._show_displays)
        self.run_task(dsp.list_gpu_drivers, on_done=self._show_drivers)

    @staticmethod
    def _clear(box):
        while box.count():
            item = box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ------------------------------------------------------------ monitors

    def _friendly_names(self, count):
        """Names from the hardware scan, only when the count matches the active displays."""
        mons = [m.get("name") for m in ((self.ctx.static or {}).get("monitors") or []) if m.get("name")]
        return mons if len(mons) == count else [None] * count

    def _show_displays(self, displays):
        self._clear(self.mon_box)
        if not displays:
            card = Card("Monitors")
            card.body.addWidget(label(f"Display modes: {NA} (Windows did not list any active display).",
                                      "muted", wrap=True))
            self.mon_box.addWidget(card)
            return
        names = self._friendly_names(len(displays))
        for d, friendly in zip(displays, names):
            self.mon_box.addWidget(self._monitor_card(d, friendly or d.get("monitor") or d["device"]))

    def _monitor_card(self, d, name):
        card = Card(name + (" (primary)" if d.get("primary") else ""))
        grid = KeyValueGrid()
        cur, mx = d.get("hz"), d.get("max_hz")
        grid.set_rows([
            ("Display", d["device"]),
            ("Resolution", f"{d['width']} x {d['height']}"),
            ("Refresh rate", f"{cur} Hz" if cur else NA),
            ("Max at this resolution", f"{mx} Hz" if mx else NA),
            ("Bit depth", f"{d['bpp']}-bit" if d.get("bpp") else NA),
        ])
        card.body.addWidget(grid)
        if cur and mx and cur < mx:
            line = label(f"Running below max refresh: {cur} Hz now, {mx} Hz supported.", "warn", wrap=True)
            card.body.addWidget(line)
            row = QHBoxLayout()
            open_btn = QPushButton("Open Windows display settings")
            open_btn.clicked.connect(self._open_settings)
            apply_btn = set_role(QPushButton(f"Set {mx} Hz"), "primary")
            apply_btn.clicked.connect(lambda _=False, dd=d: self._apply(dd))
            row.addWidget(open_btn)
            row.addWidget(apply_btn)
            row.addStretch(1)
            card.body.addLayout(row)
            card.body.addWidget(label("In Windows: Display, then Advanced display, then choose the "
                                      "refresh rate.", "muted", wrap=True))
        elif cur and mx:
            card.body.addWidget(label("Running at the highest refresh rate this display reports at "
                                      "this resolution.", "good", wrap=True))
        else:
            card.body.addWidget(label("Refresh rate could not be read for this display.", "muted"))
        return card

    def _open_settings(self):
        QDesktopServices.openUrl(QUrl("ms-settings:display"))

    def _apply(self, d):
        mx = d["max_hz"]
        ans = QMessageBox.question(
            self, "Change refresh rate",
            f"Change {d['device']} from {d['hz']} Hz to {mx} Hz at {d['width']} x {d['height']}?\n\n"
            f"The screen may flicker. You will have {REVERT_SECONDS} seconds to confirm, "
            "otherwise the previous setting is restored.")
        if ans != QMessageBox.Yes:
            return
        self.run_task(dsp.set_refresh_rate, d["device"], mx,
                      on_done=lambda res, dd=d: self._after_apply(dd, res))

    def _after_apply(self, d, res):
        ok, msg, previous = res
        what = f"{d['device']}: {d['hz']} Hz -> {d['max_hz']} Hz"
        if not ok:
            self.ctx.log_action("Display", what, "Failed", msg)
            QMessageBox.warning(self, "Refresh rate", msg)
            self.refresh()
            return
        dlg = KeepSettingsDialog(REVERT_SECONDS, self)
        if dlg.exec() == QDialog.Accepted:
            self.ctx.log_action("Display", what, "Success", "Kept after confirmation")
            self.refresh()
            return
        self.run_task(dsp.set_refresh_rate, d["device"], previous,
                      on_done=lambda r2, dd=d, w=what: self._after_revert(dd, w, r2))

    def _after_revert(self, d, what, res):
        ok, msg, _ = res
        self.ctx.log_action("Display", what, "Reverted" if ok else "Revert failed",
                            "Not confirmed in time" if ok else msg)
        if not ok:
            QMessageBox.warning(self, "Refresh rate", "Could not restore the previous refresh rate "
                                f"automatically: {msg}\nUse Windows display settings to fix it.")
        self.refresh()

    # ------------------------------------------------------------ drivers

    def _show_drivers(self, drivers):
        self._clear(self.drv_box)
        if not drivers:
            card = Card("Graphics driver")
            card.body.addWidget(label(f"Driver information: {NA}", "muted"))
            self.drv_box.addWidget(card)
            return
        for g in drivers:
            card = Card(g["name"])
            grid = KeyValueGrid()
            rows = [
                ("Driver version", g.get("version")),
                ("Driver date", g["date"].isoformat() if g.get("date") else None),
                ("Age", dsp.driver_age_text(g.get("age_days"))),
            ]
            if g.get("vendor") == "NVIDIA":
                rows.append(("NVML driver version", g.get("nvml_version")))
            grid.set_rows(rows)
            card.body.addWidget(grid)
            if g.get("url"):
                btn = QPushButton(f"Open {g['vendor']} driver page")
                btn.clicked.connect(lambda _=False, u=g["url"]: QDesktopServices.openUrl(QUrl(u)))
                row = QHBoxLayout()
                row.addWidget(btn)
                row.addStretch(1)
                card.body.addLayout(row)
            self.drv_box.addWidget(card)
        self.drv_box.addWidget(Notice("The age is only the date stamped on the installed driver. "
                                      "It does not mean a newer driver exists or is better for you."))
