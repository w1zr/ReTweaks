"""Health Check (from RETWEAKS): one read-only scan of real Windows readings, with a Fix button where
a real fix exists. The chip logo shows one pin per check (green good, amber/red look at, grey not
run or unavailable). Logic lives in core/healthcheck.py, unchanged."""
import math
import subprocess
import sys
import tkinter as tk

from core import healthcheck as hc
from rt_pages.common import card, confirm, info, label, run_bg

SYMBOL = {hc.GOOD: ("✔", "good"), hc.WARN: ("!", "warn"), hc.BAD: ("✖", "bad"), hc.NA: ("–", "muted")}
# Pins used by the chip, in order (pins 5 and 11 stay unlit; 12 pins, 10 checks)
PIN_SLOTS = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10]
# Fixes that open another page of the combined app (RETWEAKS page keys in hub.rt_tabs)
FIX_NAV = {"open_startup": "Startup apps", "open_storage": "Cleanup"}

# Pin geometry from assets/brand/logo-chip.svg (120 x 120 viewBox), same order as ui/widgets/chip_pins.py
_P = (42, 60, 78)
PINS = ([((x, 12), (x, 22)) for x in _P] + [((98, y), (108, y)) for y in _P] +
        [((x, 108), (x, 98)) for x in reversed(_P)] + [((22, y), (12, y)) for y in reversed(_P)])


def status_color(g, status):
    """Theme colour for a check status (read live so theme changes apply)."""
    risk = g.get("RISKCOL", {})
    return {hc.GOOD: g["GREEN"], hc.WARN: risk.get("Medium", "#ffb020"),
            hc.BAD: risk.get("Advanced", "#ff5c5c")}.get(status, g["MUTED"])


class ChipPinsCanvas(tk.Canvas):
    """The RETWEAKS chip with one coloured pin per Health Check result (Tk version of ChipPins)."""

    def __init__(self, parent, g, size=160):
        super().__init__(parent, width=size, height=size, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.g, self.size = g, size
        self.status = [None] * len(PINS)
        self.draw()

    def set_results(self, statuses):
        self.status = (list(statuses) + [None] * len(PINS))[:len(PINS)]
        self.draw()

    def draw(self):
        s = self.size / 120.0
        self.delete("all")
        for i, ((x1, y1), (x2, y2)) in enumerate(PINS):
            self.create_line(x1 * s, y1 * s, x2 * s, y2 * s, fill=status_color(self.g, self.status[i]),
                             width=max(2, 4 * s), capstyle="round", tags=f"pin{i}")
        text = self.g["FG"]
        r = 14 * s
        x0, y0, x1, y1 = 26 * s, 26 * s, 94 * s, 94 * s
        w = max(2, 5 * s)
        # rounded square outline
        self.create_arc(x0, y0, x0 + 2 * r, y0 + 2 * r, start=90, extent=90, style="arc", outline=text, width=w)
        self.create_arc(x1 - 2 * r, y0, x1, y0 + 2 * r, start=0, extent=90, style="arc", outline=text, width=w)
        self.create_arc(x0, y1 - 2 * r, x0 + 2 * r, y1, start=180, extent=90, style="arc", outline=text, width=w)
        self.create_arc(x1 - 2 * r, y1 - 2 * r, x1, y1, start=270, extent=90, style="arc", outline=text, width=w)
        for a, b in (((x0 + r, y0), (x1 - r, y0)), ((x0 + r, y1), (x1 - r, y1)),
                     ((x0, y0 + r), (x0, y1 - r)), ((x1, y0 + r), (x1, y1 - r))):
            self.create_line(*a, *b, fill=text, width=w)
        # the R (same path as the logo: stem, bowl, leg)
        rw = max(2, 6 * s)
        bowl = ([(48, 42), (62, 42)] +
                [(62 + 10 * math.sin(k / 10 * math.pi), 51.5 - 9.5 * math.cos(k / 10 * math.pi)) for k in range(1, 10)] +
                [(62, 61), (48, 61)])
        self.create_line(48 * s, 78 * s, 48 * s, 42 * s, fill=text, width=rw, capstyle="round")
        self.create_line(*[c * s for p in bowl for c in p], fill=text, width=rw, capstyle="round",
                         joinstyle="round", smooth=True)
        self.create_line(60 * s, 61 * s, 73 * s, 78 * s, fill=text, width=rw, capstyle="round")


class HealthPage:
    TITLE = "Health Check"
    SUB = ("A read-only scan of real Windows readings. Nothing is changed unless you click Fix and confirm. "
           "Cleanup always shows its preview first.")

    def __init__(self, hub, tab, g):
        self.hub, self.tab, self.g = hub, tab, g
        self.checks = list(hc.CHECKS)
        self.results = {}
        self._running = False
        self._ran = False
        self._rows = {}
        g["page_header"](tab, "RETWEAKS", self.TITLE, self.SUB)
        body = hub._scroll_area(tab)
        self.body = body

        top = card(body, g)
        row = tk.Frame(top, bg=top.cget("bg"))
        row.pack(fill="x", padx=16, pady=12)
        self.chip = ChipPinsCanvas(row, g)
        self.chip.pack(side="left", anchor="n")
        side = tk.Frame(row, bg=row.cget("bg"))
        side.pack(side="left", fill="both", expand=True, padx=(24, 0))
        self.summary = tk.Label(side, text="Not run yet. Click Run Health Check.", bg=side.cget("bg"), fg=g["FG"],
                                font=(g["UI"], 14, "bold"), anchor="w", justify="left", wraplength=560)
        self.summary.pack(fill="x", pady=(4, 8))
        self.run_btn = g["RButton"](side, "Run Health Check", self.run_all, kind="primary")
        self.run_btn.pack(anchor="w")
        tk.Label(side, text="Each pin on the chip is one check: green is good, amber or red needs a look, "
                            "grey is not run or unavailable.", bg=side.cget("bg"), fg=g["MUTED"],
                 font=(g["UI"], 9), anchor="w", justify="left", wraplength=560).pack(fill="x", pady=(10, 0))

        self.list = card(body, g, "Checks")
        for cid, name, _fn in self.checks:
            self._add_row(cid, name)

    # ------------------------------------------------------------ rows
    def _add_row(self, cid, name):
        g = self.g
        bg = self.list.cget("bg")
        row = tk.Frame(self.list, bg=bg)
        row.pack(fill="x", padx=16, pady=5)
        sym = tk.Label(row, text="·", bg=bg, fg=g["MUTED"], font=(g["UI"], 13, "bold"), width=2, anchor="n")
        sym.pack(side="left", anchor="n")
        text = tk.Frame(row, bg=bg)
        text.pack(side="left", fill="x", expand=True)
        nm = tk.Label(text, text=name, bg=bg, fg=g["FG"], font=(g["UI"], 10, "bold"), anchor="w")
        nm.pack(fill="x")
        detail = tk.Label(text, text="Not run yet", bg=bg, fg=g["MUTED"], font=(g["UI"], 9), anchor="w",
                          justify="left", wraplength=640)
        detail.pack(fill="x")
        btn_holder = tk.Frame(row, bg=bg)
        btn_holder.pack(side="right", anchor="n")
        self._rows[cid] = {"sym": sym, "name": nm, "detail": detail, "holder": btn_holder, "btn": None}

    def _set_fix(self, cid, text):
        w = self._rows[cid]
        if w["btn"] is not None:
            w["btn"].destroy()
            w["btn"] = None
        if text:
            w["btn"] = self.g["RButton"](w["holder"], text, lambda c=cid: self.do_fix(c), kind="default", height=30)
            w["btn"].pack()

    def _show(self, r):
        if not isinstance(r, dict) or "id" not in r:
            return
        w = self._rows.get(r["id"])
        if not w:
            return
        self.results[r["id"]] = r
        sym, state = SYMBOL.get(r["status"], ("–", "muted"))
        w["sym"].configure(text=sym, fg=status_color(self.g, r["status"]))
        w["detail"].configure(text=r.get("detail") or "", fg=self.g["FG"] if r["status"] != hc.NA else self.g["MUTED"])
        fix = r.get("fix_id")
        text = f"Open {FIX_NAV[fix]}" if fix in FIX_NAV else (r.get("fix_label") or "")
        self._set_fix(r["id"], text if fix else "")
        self._update_summary()

    def _update_summary(self):
        have = [self.results[c] for c, _n, _f in self.checks if c in self.results]
        if have:
            self.summary.configure(text=hc.summarize(have)["text"])
        stat = [None] * 12
        for i, (cid, _n, _f) in enumerate(self.checks):
            r = self.results.get(cid)
            if r and i < len(PIN_SLOTS):
                stat[PIN_SLOTS[i]] = r["status"]
        self.chip.set_results(stat)

    # ------------------------------------------------------------ running
    def on_shown(self):
        self.chip.draw()                          # follow theme changes
        if not self._ran and not self._running:   # read-only, fine to scan the first time it opens
            self.run_all()

    def run_all(self):
        if self._running:
            return
        self._running = self._ran = True
        self.run_btn.set_enabled(False)
        self.results.clear()
        self.chip.set_results([None] * 12)
        self.summary.configure(text="Checking…")
        for cid, _n, _f in self.checks:
            self._rows[cid]["detail"].configure(text="Checking…", fg=self.g["MUTED"])
            self._rows[cid]["sym"].configure(text="·", fg=self.g["MUTED"])
            self._set_fix(cid, "")
        self._next(0)

    def _next(self, i):
        if i >= len(self.checks):
            self._running = False
            self.run_btn.set_enabled(True)
            self._update_summary()
            return
        cid = self.checks[i][0]
        run_bg(self.hub, hc.run_one, lambda r, i=i: self._got(r, i), cid)

    def _got(self, r, i):
        if not isinstance(r, dict) or "id" not in r:       # worker-level failure
            cid, name, _f = self.checks[i]
            r = hc.result(cid, name, hc.NA, f"Could not be read: {r}")
        self._show(r)
        self._next(i + 1)

    # ------------------------------------------------------------ fixes
    def do_fix(self, cid):
        r = self.results.get(cid)
        fix = r.get("fix_id") if r else None
        if not fix:
            return
        if fix in FIX_NAV:
            idx = getattr(self.hub, "rt_tabs", {}).get(FIX_NAV[fix])
            if idx is not None:
                self.hub.show_tab(idx)
            else:
                info(self.tab, "Health Check", f"The {FIX_NAV[fix]} page isn't available.", error=True)
            return
        if fix == "open_display":
            try:
                if sys.platform == "win32":
                    subprocess.Popen(["explorer.exe", "ms-settings:display"])
                else:
                    raise OSError("Windows display settings only exist on Windows")
            except Exception as e:
                info(self.tab, "Health Check", f"Could not open Windows display settings: {e}", error=True)
            return
        if fix == "power_high":
            if not confirm(self.tab, "Switch power plan",
                           "Switch to the Windows High performance power plan?\n\n"
                           "RETWEAKS saves your current plan first, so it can be restored. "
                           "Laptops use more battery on this plan."):
                return
            if self._rows[cid]["btn"] is not None:
                self._rows[cid]["btn"].set_enabled(False)
            run_bg(self.hub, hc.apply_power_high, lambda res, c=cid: self._fix_done(c, res))

    def _fix_done(self, cid, res):
        ok, msg = res if isinstance(res, tuple) and len(res) == 2 else (False, str(res))
        self.hub.log_action("Health Check: power plan", "Switch to High performance", msg if ok else "Failed",
                            "" if ok else msg)
        if not ok:
            info(self.tab, "Health Check", msg, error=True)
        run_bg(self.hub, hc.run_one, self._show, cid)      # show the real new state
