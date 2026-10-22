# ui/pages/display.py
"""Display refresh rate check, stretched resolution (v1.5) and GPU driver age."""

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout)

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
                "current resolution, sets a stretched resolution, and shows how old your graphics driver is.")

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
        if not isinstance(displays, list):    # the task raised: (False, message)
            displays = []
        if not displays:
            card = Card("Monitors")
            card.body.addWidget(label(f"Display modes: {NA} (Windows did not list any active display).",
                                      "muted", wrap=True))
            self.mon_box.addWidget(card)
            return
        for d in displays:
            # The monitor's own name comes from Windows per display (v1.5). The hardware scan's list is
            # in a different order, so it's only used when there is a single monitor.
            fallback = self._friendly_names(1)[0] if len(displays) == 1 else None
            self.mon_box.addWidget(self._monitor_card(d, d.get("name") or fallback or d.get("monitor") or d["device"]))

    def _monitor_card(self, d, name):
        card = Card(name + (" (primary)" if d.get("primary") else ""))
        grid = KeyValueGrid()
        cur, mx = d.get("hz"), d.get("max_hz")
        grid.set_rows([
            ("Display", d["device"]),
            ("Resolution", f"{d['width']} x {d['height']}" + (" (rotated)" if d.get("rotated") else "")),
            ("Native resolution", "{} x {}".format(*d["native"]) if d.get("native") else NA),
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
        self._stretch_section(card, d)
        return card

    # ------------------------------------------------------------ stretched resolution (v1.5)

    def _stretch_section(self, card, d):
        """Global stretched resolution for this monitor, like NVIDIA Control Panel: the desktop runs at
        a narrower resolution stretched to fill the screen, so games in Windowed Fullscreen are too."""
        if d.get("rotated"):
            card.body.addWidget(label("Stretched resolution isn't offered for a rotated (portrait) screen.",
                                      "muted", wrap=True))
            return
        choices = dsp.stretch_choices(d)
        nw, nh = dsp.native_size(d)
        if not choices or not nw:
            return
        card.body.addWidget(label("Stretched resolution", "sectionTitle"))
        stretched = (d["width"], d["height"]) != (nw, nh)
        card.body.addWidget(label(
            (f"Now running {d['width']}×{d['height']} on a {nw}×{nh} screen." if stretched else
             f"Runs the whole screen at a narrower resolution stretched to fill it (native: {nw}×{nh}). "
             "Games in Windowed Fullscreen, like Fortnite, use it automatically. Characters look wider; "
             "you don't see more of the map. Fortnite's Arena and tournaments stay 16:9 (Epic's rule)."),
            "muted", wrap=True))
        row = QHBoxLayout()
        combo = QComboBox()
        for w, h, hz in choices:
            combo.addItem(f"{w} × {h}" + (f"  ({hz} Hz)" if hz else "  (not on your graphics card yet)"), (w, h, hz))
        apply_btn = set_role(QPushButton("Apply stretched"), "primary")
        apply_btn.clicked.connect(lambda _=False, dd=d, c=combo: self._stretch(dd, *c.currentData()))
        native_btn = QPushButton(f"Back to native ({nw}×{nh})")
        native_btn.setEnabled(stretched)
        native_btn.clicked.connect(lambda _=False, dd=d: self._native(dd))
        row.addWidget(combo)
        row.addWidget(apply_btn)
        row.addWidget(native_btn)
        row.addStretch(1)
        card.body.addLayout(row)
        card.body.addWidget(label(
            "If a resolution isn't on your graphics card yet, RETWEAKS adds it on NVIDIA cards (NVIDIA's own "
            "NVAPI, like Control Panel → Create Custom Resolution). On AMD or Intel add it once in AMD Software "
            "or Intel Graphics Command Center. If you see black bars instead of a stretched picture, set "
            "scaling to Full-screen (NVIDIA Control Panel → Adjust desktop size and position) or Full panel "
            "(AMD GPU Scaling).", "muted", wrap=True))

    def _stretch(self, d, w, h, hz):
        if not hz:
            if not self._nvidia_add(d, w, h):
                return
            d = next((x for x in dsp.list_displays() if x["device"] == d["device"]), d)
            hz = dsp.max_refresh_at(d.get("modes") or [], w, h, d.get("bpp"))
            if not hz:
                QMessageBox.warning(self, "Stretched resolution", f"{w}×{h} still isn't on the graphics card's list.")
                self.refresh()
                return
        if QMessageBox.question(
                self, "Stretched resolution",
                f"Switch {d['device']} to {w}×{h} at {hz} Hz, stretched to fill the screen?\n\n"
                f"The screen goes black for a moment. You'll have {REVERT_SECONDS} seconds to keep it, "
                "otherwise it switches back.") != QMessageBox.Yes:
            return
        what = f"{d['device']}: stretched {w}×{h}"
        ok, msg = dsp.set_resolution(d["device"], w, h, hz, stretch=True, persist=False)
        if not ok:
            self.ctx.log_action("Display", what, "Failed", msg)
            QMessageBox.warning(self, "Stretched resolution", msg)
            self.refresh()
            return
        if KeepSettingsDialog(REVERT_SECONDS, None).exec() == QDialog.Accepted:
            ok, msg = dsp.set_resolution(d["device"], w, h, hz, stretch=True, persist=True)   # save it
            self.ctx.log_action("Display", what, "Success" if ok else "Failed", "" if ok else msg)
            if not ok:
                QMessageBox.warning(self, "Stretched resolution", msg)
        else:
            ok, msg = dsp.restore_saved_mode(d["device"])
            self.ctx.log_action("Display", what, "Reverted" if ok else "Revert failed", "" if ok else msg)
            if not ok:
                QMessageBox.warning(self, "Stretched resolution", msg + " Use Windows display settings to fix it.")
        self.refresh()

    def _native(self, d):
        nw, nh = dsp.native_size(d)
        hz = dsp.max_refresh_at(d.get("modes") or [], nw, nh, d.get("bpp"))
        ok, msg = dsp.set_resolution(d["device"], nw, nh, hz, stretch=False, persist=True)
        self.ctx.log_action("Display", f"{d['device']}: back to native {nw}×{nh}", "Success" if ok else "Failed",
                            "" if ok else msg)
        if not ok:
            QMessageBox.warning(self, "Stretched resolution", msg)
        self.refresh()

    def _nvidia_add(self, d, w, h):
        """Adds w×h to the NVIDIA driver for this monitor (source w×h, native timing = GPU stretches),
        with NVIDIA's own Try → Keep/Revert. Returns True when saved."""
        from core import nvidia_display as nvd
        if QMessageBox.question(
                self, "Add to graphics card",
                f"{w}×{h} isn't on your graphics card's list yet. Add it now (NVIDIA cards)?\n\n"
                "The screen switches to it for a test; press Keep within "
                f"{REVERT_SECONDS} seconds or it switches back by itself.") != QMessageBox.Yes:
            return False
        what = f"{d['device']}: NVIDIA custom resolution {w}×{h}"
        nw, nh = dsp.native_size(d)
        try:
            nv = nvd.NvApi()
            did = nv.display_id(d["device"])
            timing = nv.timing(did, nw, nh, d.get("max_hz") or d.get("hz") or 60)
            nv.try_custom(did, nvd.build_custom(w, h, timing))
        except Exception as e:
            self.ctx.log_action("Display", what, "Failed", str(e))
            QMessageBox.warning(self, "Add to graphics card",
                                f"The graphics driver didn't accept it: {e}\n\nNothing was changed. Add it by "
                                "hand: NVIDIA Control Panel → Change resolution → Customize → Create Custom "
                                "Resolution; AMD Software → Display → Custom Resolutions.")
            return False
        keep = KeepSettingsDialog(REVERT_SECONDS, None).exec() == QDialog.Accepted
        try:
            if keep:
                nv.save_custom(did)
                dsp.restore_saved_mode(d["device"])
                self.ctx.log_action("Display", what, "Saved")
                return True
            nv.revert_trial(did)
            self.ctx.log_action("Display", what, "Reverted")
        except Exception as e:
            ok, msg = dsp.restore_saved_mode(d["device"])
            self.ctx.log_action("Display", what, "Failed", str(e))
            QMessageBox.warning(self, "Add to graphics card", f"{e}\n\n{msg}")
        return False

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
        if not isinstance(drivers, list):     # the task raised: (False, message)
            drivers = []
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
