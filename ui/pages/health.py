# ui/pages/health.py
"""Health Check: one read-only scan with a Fix button where a real fix exists."""

import subprocess

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget

from core import healthcheck as hc
from ui.widgets.chip_pins import ChipPins
from ui.widgets.common import Card, Page, label, set_role, set_status_style

SYMBOL = {hc.GOOD: ("✔", "good"), hc.WARN: ("!", "warn"), hc.BAD: ("✖", "bad"), hc.NA: ("–", "muted")}
# Pins used by the chip, in order (pins 5 and 11 are left unlit; there are 12 pins, 10 checks)
PIN_SLOTS = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10]

FIX_NAV = {"open_startup": "Startup apps", "open_storage": "Storage & cleanup"}


class HealthPage(Page):
    title = "Health Check"
    subtitle = ("A read-only scan of real Windows readings. Nothing is changed unless you click Fix "
                "and confirm. Cleanup always shows its preview on the Storage page.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.checks = list(hc.CHECKS)
        self.results = {}          # check id -> result dict
        self._running = False
        self._ran = False
        self._rows = {}            # check id -> dict of widgets

        top = QHBoxLayout()
        top.setSpacing(24)
        self.chip = ChipPins(ctx.theme)
        top.addWidget(self.chip, 0, Qt.AlignTop)
        side = QVBoxLayout()
        self.summary = label("Not run yet. Click Run Health Check.", "sectionTitle", wrap=True)
        side.addWidget(self.summary)
        self.run_btn = set_role(QPushButton("Run Health Check"), "primary")
        self.run_btn.clicked.connect(self.run_all)
        side.addWidget(self.run_btn, 0, Qt.AlignLeft)
        side.addWidget(label("Each pin on the chip is one check: green is good, amber or red needs a look, "
                             "grey is not run or unavailable.", "muted", wrap=True))
        side.addStretch(1)
        top.addLayout(side, 1)
        self.content.addLayout(top)

        self.card = Card("Checks")
        self.list_lay = QVBoxLayout()
        self.list_lay.setSpacing(10)
        self.card.body.addLayout(self.list_lay)
        self.content.addWidget(self.card)
        for cid, name, _fn in self.checks:
            self._add_row(cid, name)
        self.finish()

    # ------------------------------------------------------------ rows
    def _add_row(self, cid, name):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        sym = label("·", "muted")
        sym.setFixedWidth(20)
        sym.setAlignment(Qt.AlignCenter)
        text = QVBoxLayout()
        text.setSpacing(2)
        nm = label(name)
        detail = label("Not run yet", "muted", wrap=True)
        text.addWidget(nm)
        text.addWidget(detail)
        btn = QPushButton("")
        btn.setVisible(False)
        btn.clicked.connect(lambda _=False, c=cid: self.do_fix(c))
        lay.addWidget(sym, 0, Qt.AlignTop)
        lay.addLayout(text, 1)
        lay.addWidget(btn, 0, Qt.AlignTop)
        self.list_lay.addWidget(row)
        self._rows[cid] = {"sym": sym, "name": nm, "detail": detail, "btn": btn}

    def _show(self, r):
        w = self._rows.get(r["id"])
        if not w:
            return
        self.results[r["id"]] = r
        text, state = SYMBOL[r["status"]]
        w["sym"].setText(text)
        set_status_style(w["sym"], state)
        w["detail"].setText(r["detail"])
        w["detail"].setObjectName("cardLine" if r["status"] != hc.NA else "muted")
        w["detail"].style().unpolish(w["detail"])
        w["detail"].style().polish(w["detail"])
        w["btn"].setText((r.get("fix_label") or "").replace("&", "&&"))
        w["btn"].setVisible(bool(r.get("fix_id")))
        w["btn"].setEnabled(True)
        self._update_summary()

    def _update_summary(self):
        have = [self.results[c] for c, _n, _f in self.checks if c in self.results]
        if have:
            self.summary.setText(hc.summarize(have)["text"])
        stat = [None] * 12
        for i, (cid, _n, _f) in enumerate(self.checks):
            r = self.results.get(cid)
            if r and i < len(PIN_SLOTS):
                stat[PIN_SLOTS[i]] = r["status"]
        self.chip.set_results(stat)

    # ------------------------------------------------------------ running
    def on_shown(self):
        # Read-only, so it is fine to scan the first time the page opens
        if not self._ran and not self._running:
            self.run_all()

    def run_all(self):
        if self._running:
            return
        self._running = self._ran = True
        self.run_btn.setEnabled(False)
        self.results.clear()
        self.chip.set_results([None] * 12)
        self.summary.setText("Checking…")
        for cid, _n, _f in self.checks:
            self._rows[cid]["detail"].setText("Checking…")
            self._rows[cid]["btn"].setVisible(False)
        self._next(0)

    def _next(self, i):
        if i >= len(self.checks):
            self._running = False
            self.run_btn.setEnabled(True)
            self._update_summary()
            return
        cid = self.checks[i][0]
        self.run_task(hc.run_one, cid, on_done=lambda r, i=i: self._got(r, i))

    def _got(self, r, i):
        if not isinstance(r, dict) or "id" not in r:      # worker-level failure
            cid, name, _f = self.checks[i]
            r = hc.result(cid, name, hc.NA, f"Could not be read: {r[1] if isinstance(r, tuple) else r}")
        self._show(r)
        self._next(i + 1)

    # ------------------------------------------------------------ fixes
    def do_fix(self, cid):
        r = self.results.get(cid)
        fix = r.get("fix_id") if r else None
        if not fix:
            return
        if fix in FIX_NAV:
            if hasattr(self.ctx, "go_to_page"):
                self.ctx.go_to_page(FIX_NAV[fix])
            return
        if fix == "open_display":
            try:
                subprocess.Popen(["explorer.exe", "ms-settings:display"])
            except Exception as e:
                QMessageBox.warning(self, "Health Check", f"Could not open Windows display settings: {e}")
            return
        if fix == "power_high":
            ok = QMessageBox.question(
                self, "Switch power plan",
                "Switch to the Windows High performance power plan?\n\n"
                "RYTWEAKS saves your current plan first, so you can restore it from the Tweaks page. "
                "Laptops use more battery on this plan.")
            if ok != QMessageBox.Yes:
                return
            self._rows[cid]["btn"].setEnabled(False)
            self.run_task(hc.apply_power_high, on_done=lambda res, c=cid: self._fix_done(c, res))

    def _fix_done(self, cid, res):
        ok, msg = res if isinstance(res, tuple) and len(res) == 2 else (False, str(res))
        self.ctx.log_action("Health Check: power plan", "Switch to High performance", msg if ok else "Failed",
                            "" if ok else msg)
        if not ok:
            QMessageBox.warning(self, "Health Check", msg)
        # Show the real new state
        self.run_task(hc.run_one, cid, on_done=self._show)

    def on_theme(self, theme):
        self.chip.set_theme(theme)
