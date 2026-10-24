"""Fan control, RGB lighting, Temperatures and Run pages (from base app v1.5, owner request 2026-10-22).

The page code itself is the base app's v1.5 (cooling_panel.py, thermal_dashboard.py, run_panel.py, GPL-3.0); these
wrappers plug it into the RETWEAKS page registry so the sidebar, search, on_shown/on_hidden and Quit cleanup
(rt_shell.quit_app calls close()) work like every other RETWEAKS page.

Sensors come from hub.temperatures (temperatures.Temperatures): nvidia-smi and Windows storage sensors, plus the
bundled LibreHardwareMonitor 0.9.6 (ai/sensors/SensorHost.exe) for CPU, motherboard and fans. CPU/motherboard
sensors and fan control need the PawnIO driver, which the user installs once from its official page; RETWEAKS
doesn't install drivers.
"""
import time
import tkinter as tk
import webbrowser

PAWNIO_URL = "https://github.com/namazso/PawnIO.Setup/releases"   # linked from LibreHardwareMonitor 0.9.6's notes
PAWNIO_NOTE = ("CPU and motherboard temperatures and most fan controllers need the free PawnIO driver. Windows "
               "doesn't let apps read those sensors without a driver. Missing PawnIO installs automatically on this page: "
               "if setup fails, install from the official page and press Retry sensor detection.")


def _pawnio_card(hub, parent, g):
    card = g["Card"](parent)
    card.pack(fill="x", padx=(0, 12), pady=(0, 8))
    lbl = hub.label(card.body, PAWNIO_NOTE, 10, g["MUTED"])
    card.wrap(lbl)
    row = tk.Frame(card.body, bg=card.body.cget("bg"))
    row.pack(fill="x", padx=16, pady=(0, 12))
    g["RButton"](row, "PawnIO download page ↗", lambda: webbrowser.open(PAWNIO_URL)).pack(side="left", padx=(0, 8))
    g["RButton"](row, "Retry sensor detection", lambda: _rescan(hub), kind="ghost").pack(side="left")
    return card


def _rescan(hub):
    t = getattr(hub, "temperatures", None)
    if t is not None:
        t.full_scan()


class FanControlPage:
    def __init__(self, hub, tab, g):
        from cooling_panel import FanPage
        self.hub = hub
        self.inner = FanPage(hub, tab, g)
        hub.fan_control = self.inner
        # RETWEAKS improvement (owner request 2026-10-22): temperature-based fan curves under the speed card
        from rt_pages.fan_curve_ui import FanCurveCard
        self.curves = FanCurveCard(self.inner, hub, self.inner.body, g)
        self.inner.fan_advanced.pack_forget()
        _pawnio_card(hub, self.inner.body, g)

    def on_temp_unit(self, unit):
        try:
            self.curves.redraw()
        except Exception:
            pass

    def on_shown(self):
        _rescan(self.hub)            # starts the sensor host if it isn't running (no hardware writes)
        self.curves.select_target()

    def close(self):
        self.curves.close()          # curves hand their fans back to automatic (BIOS) first
        self.inner.close()


class LightingPage:
    def __init__(self, hub, tab, g):
        from cooling_panel import RGBPage
        self.inner = RGBPage(hub, tab, g)
        hub.rgb_lighting = self.inner

    def close(self):
        self.inner.close()


class TemperaturesPage:
    """Live sensor tiles (the base app's v1.5 Temperatures page, simplified 2026-10-22) with a °C/°F switch that uses
    the one temp_unit setting (rt_pages.settings_store.set_temp_unit), so Settings and every page agree."""

    def __init__(self, hub, tab, g):
        from thermal_dashboard import ThermalDashboard
        self.hub, self.g = hub, g
        self.job = None
        self.closed = False
        g["page_header"](tab, "RETWEAKS", "Temperatures",
                         "Live readings from your hardware sensors. Sensors that report nothing are left out.")
        body = hub._scroll_area(tab)
        top = tk.Frame(body, bg=g["BG"])
        top.pack(fill="x", padx=(0, 12), pady=(0, 6))
        self.status = tk.Label(top, text="Detecting hardware sensors…", bg=g["BG"], fg=g["MUTED"],
                               font=(g["UI"], 10), anchor="w", justify="left")
        self.status.pack(side="left", fill="x", expand=True)
        from rt_pages.unit_switch import UnitSwitch
        self.switch = UnitSwitch(top, hub, g)
        self.switch.pack(side="right")
        self.pawnio = _pawnio_card(hub, body, g)
        self.pawnio.pack_forget()
        self._pawnio_shown = False
        self.dash_holder = tk.Frame(body, bg=g["BG"])
        self.dash_holder.pack(fill="x")
        self.dashboard = ThermalDashboard(hub, self.dash_holder, g)
        self.draw_switch()

    def unit(self):
        from rt_pages.settings_store import temp_unit
        return temp_unit(self.hub)

    def set_unit(self, unit):
        self.switch.choose(unit)

    def on_temp_unit(self, unit):
        self.switch.draw()
        if not self.closed:
            for tile in self.dashboard.tiles.values():
                tile["unit"] = unit
                self.dashboard.draw(tile)

    def draw_switch(self):
        self.switch.draw()

    def refresh(self):
        self.job = None
        if self.closed:
            return
        sampler = getattr(self.hub, "temperatures", None)
        fresh = sampler is not None and time.time() - getattr(sampler, "updated", 0) < 15
        rows = sampler.rows if fresh else []
        try:
            cpu = (getattr(self.hub, "info", None) or {}).get("cpu") or "CPU"
            self.dashboard.update(rows, self.unit(), cpu_name=cpu)
            count = sum(len(t["readings"]) for t in self.dashboard.tiles.values())
            self.status.config(text=(f"Live · {count} sensor reading{'s' if count != 1 else ''} · updates every 5 s"
                                     if count else "No temperature sensors are reporting yet."))
            # The PawnIO note only appears when CPU temperatures are actually missing.
            cpu_missing = not any(t["readings"] for (part, _), t in self.dashboard.tiles.items() if part == "CPU")
            if cpu_missing and not self._pawnio_shown:
                self.pawnio.pack(fill="x", padx=(0, 12), pady=(0, 8), before=self.dash_holder)
                self._pawnio_shown = True
            elif not cpu_missing and self._pawnio_shown:
                self.pawnio.pack_forget()
                self._pawnio_shown = False
        except tk.TclError:
            return
        self.job = self.hub.after(2000, self.refresh)

    def on_shown(self):
        _rescan(self.hub)
        if self.job is None:
            self.refresh()

    def on_hidden(self):
        if self.job is not None:
            try:
                self.hub.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None

    def close(self):
        self.closed = True
        self.on_hidden()
        # Quit: running fan curves hand back first, then the sensor host stops (it also restores any fan it was
        # controlling to automatic control when it exits).
        curves = getattr(self.hub, "fan_curves", None)
        if curves is not None:
            try:
                curves.release_all()
            except Exception:
                pass
        for name in ("temperatures", "gpu_sampler"):
            obj = getattr(self.hub, name, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass


class RunLauncherPage:
    def __init__(self, hub, tab, g):
        from run_panel import RunPage
        self.inner = RunPage(hub, tab, g)
