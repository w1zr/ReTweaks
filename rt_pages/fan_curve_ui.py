"""Fan curve card on the Fan control page (RETWEAKS improvement on base app v1.5, owner request 2026-10-22).

Settings (config.json): fan_curves = {fan target name: {ids, source, preset, points, hysteresis, active}},
fan_curves_on_start = False. Nothing is sent to a fan until the user presses "Use this curve"; at launch the
saved active curves only start again when "Start my fan curves when RETWEAKS starts" is ticked.
The maths, hysteresis and failsafes live in fan_curves.py."""
import time
import tkinter as tk

from rt_pages.settings_store import format_temp, temp_unit

import fan_curves as fc

GRAPH_W, GRAPH_H = 560, 230
T_MIN, T_MAX = 20.0, 100.0
PAD_L, PAD_R, PAD_T, PAD_B = 46, 16, 14, 30
HYSTERESIS = {"2 °C": 2.0, "3 °C": 3.0, "5 °C": 5.0, "8 °C": 8.0}


class FanCurveCard:
    def __init__(self, page, hub, parent, g):
        self.page, self.hub, self.g = page, hub, g        # page = cooling_panel.FanPage
        self.engine = fc.CurveEngine(hub, hub.temperatures, on_status=self._engine_status)
        hub.fan_curves = self.engine
        self.points = list(fc.PRESETS["Balanced"])
        self.drag = None
        self.closed = False
        self.target = None
        card = g["Card"](parent)
        card.pack(fill="x", padx=8, pady=8)
        self.card = card
        b = card.body
        hub.label(b, "Fan curve", 17)
        self.state = hub.label(b, "Automatic (BIOS)", 13)
        self.readout = hub.label(b, "", 10, g["MUTED"])
        info = hub.label(b, "Speed follows a temperature. Drag the points, or start from a preset. The fans "
                            "stay at 30 % or more, pumps are never touched, and the hardware's own (BIOS) control "
                            "takes over again if the temperature can't be read, at 85 °C, or when RETWEAKS closes.",
                         10, g["MUTED"])
        card.wrap(info)
        row = tk.Frame(b, bg=b.cget("bg"))
        row.pack(fill="x", padx=16, pady=(4, 2))
        tk.Label(row, text="Temperature", bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left")
        self.source = g["RSelect"](row, fc.SOURCES, width=210, command=lambda v: self._draft())
        self.source.pack(side="left", padx=(8, 16))
        tk.Label(row, text="Preset", bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left")
        self.preset = g["RSelect"](row, fc.PRESET_ORDER, width=150, command=self._pick_preset)
        self.preset.set("Balanced")
        self.preset.pack(side="left", padx=(8, 16))
        tk.Label(row, text="Hysteresis", bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left")
        self.hyst = g["RSelect"](row, list(HYSTERESIS), width=90, command=lambda v: self._draft())
        self.hyst.set("3 °C")
        self.hyst.pack(side="left", padx=8)
        self.graph = tk.Canvas(b, width=GRAPH_W, height=GRAPH_H, bg=b.cget("bg"), highlightthickness=0,
                               cursor="hand2")
        self.graph.pack(anchor="w", padx=16, pady=8)
        self.graph.bind("<ButtonPress-1>", self._press)
        self.graph.bind("<B1-Motion>", self._move)
        self.graph.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))
        buttons = tk.Frame(b, bg=b.cget("bg"))
        buttons.pack(fill="x", padx=16, pady=(2, 6))
        self.use = g["RButton"](buttons, "Use this curve", self.use_curve, kind="primary", width=150, height=38)
        self.use.pack(side="left", padx=(0, 10))
        self.auto = g["RButton"](buttons, "Back to Automatic (BIOS)", self.back_to_auto, width=220, height=38)
        self.auto.pack(side="left")
        self.msg = hub.label(b, "", 10, g["MUTED"])
        self.on_start = tk.BooleanVar(value=bool(hub.settings.get("fan_curves_on_start", False)))
        g["RCheck"](b, "Start my fan curves when RETWEAKS starts", self.on_start, self._save_on_start).pack(
            anchor="w", padx=16, pady=(0, 14))
        self.redraw()
        self.page.select.command = self._wrap(self.page.select.command, self.select_target)
        # manual speed / Automatic on the speed card take over from a curve on the same fans
        self.page.apply.command = self._wrap_ids(self.page.apply.command)
        self.page.auto.command = self._wrap_ids(self.page.auto.command)
        self._resume_job = None
        if self.on_start.get():
            self._resume_job = hub.after(3000, self._resume_saved)
        hub.after(1000, self._tick_readout)

    # ------------------------------------------------------------ helpers
    def _wrap(self, original, extra):
        def run(*a):
            if original:
                original(*a)
            extra()
        return run

    def _wrap_ids(self, original):
        def run(*a):
            ids = [r["id"] for r in self.page.selected_controls()]
            self.engine.stop_for(ids)
            if original:
                original(*a)
            self.update_state()
        return run

    def saved(self):
        v = self.hub.settings.get("fan_curves")
        return v if isinstance(v, dict) else {}

    def _save(self, curves):
        self.hub.settings["fan_curves"] = curves
        try:
            self.hub.save_settings()
        except Exception:
            pass

    def _save_on_start(self):
        self.hub.settings["fan_curves_on_start"] = bool(self.on_start.get())
        try:
            self.hub.save_settings()
        except Exception:
            pass

    def target_name(self):
        return self.page.select.get()

    def target_ids(self):
        return [r["id"] for r in self.page.selected_controls()]

    # ------------------------------------------------------------ editing
    def _pick_preset(self, name):
        self.preset.set(name)
        if name in fc.PRESETS:
            self.points = list(fc.PRESETS[name])
            self.redraw()
        self._draft()

    def _draft(self):
        name = self.target_name()
        if self.engine.running(name):
            self.msg.config(text="Changed. Press Use this curve to update the running curve.")

    def select_target(self):
        name = self.target_name()
        c = self.saved().get(name)
        if isinstance(c, dict):
            try:
                self.points = fc.clean_points(c.get("points", []))
            except ValueError:
                self.points = list(fc.PRESETS["Balanced"])
            self.source.set(c.get("source") if c.get("source") in fc.SOURCES else fc.SOURCES[0])
            self.preset.set(c.get("preset") if c.get("preset") in fc.PRESET_ORDER else "Custom")
            h = next((k for k, v in HYSTERESIS.items() if v == c.get("hysteresis")), "3 °C")
            self.hyst.set(h)
        self.redraw()
        self.update_state()

    def _xy(self, t, d):
        w = GRAPH_W - PAD_L - PAD_R
        h = GRAPH_H - PAD_T - PAD_B
        return PAD_L + (t - T_MIN) / (T_MAX - T_MIN) * w, PAD_T + (100 - d) / 70 * h

    def _td(self, x, y):
        w = GRAPH_W - PAD_L - PAD_R
        h = GRAPH_H - PAD_T - PAD_B
        return T_MIN + (x - PAD_L) / w * (T_MAX - T_MIN), 100 - (y - PAD_T) / h * 70

    def _press(self, e):
        best = None
        for i, (t, d) in enumerate(self.points):
            x, y = self._xy(t, d)
            dist = (x - e.x) ** 2 + (y - e.y) ** 2
            if dist <= 14 ** 2 and (best is None or dist < best[1]):
                best = (i, dist)
        self.drag = best[0] if best else None

    def _move(self, e):
        i = self.drag
        if i is None:
            return
        t, d = self._td(e.x, e.y)
        lo = self.points[i - 1][0] + 1 if i > 0 else T_MIN
        hi = self.points[i + 1][0] - 1 if i < len(self.points) - 1 else T_MAX
        t = round(max(lo, min(hi, t)))
        d = round(max(fc.MIN_DUTY, min(100, d)))
        self.points[i] = (t, d)
        self.preset.set("Custom")
        self.redraw()
        self._draft()

    def redraw(self):
        cv, g = self.graph, self.g
        cv.delete("all")
        bg = self.card.body.cget("bg")
        cv.configure(bg=bg)
        for duty in (30, 50, 70, 100):
            x0, y = self._xy(T_MIN, duty)
            cv.create_line(x0, y, GRAPH_W - PAD_R, y, fill=g["LINE"], dash=(3, 5))
            cv.create_text(PAD_L - 8, y, text=f"{duty}%", anchor="e", fill=g["MUTED"], font=(g["UI"], 8))
        for t in (20, 40, 60, 80, 100):
            x, y0 = self._xy(t, 30)
            cv.create_text(x, y0 + 14, text=(f"{t * 9 / 5 + 32:.0f}°F" if temp_unit(self.hub) == "F" else f"{t}°"),
                           fill=g["MUTED"], font=(g["UI"], 8))
        x85, _ = self._xy(fc.SAFETY_TEMP, 100)
        cv.create_line(x85, PAD_T, x85, GRAPH_H - PAD_B, fill=g["LINE"])
        cv.create_text(x85 + 4, PAD_T + 6, text="BIOS takes over", anchor="w", fill=g["MUTED"], font=(g["UI"], 8))
        coords = []
        first = self._xy(T_MIN, self.points[0][1])
        coords.extend(first)
        for t, d in self.points:
            coords.extend(self._xy(t, d))
        coords.extend(self._xy(T_MAX, self.points[-1][1]))
        cv.create_line(*coords, fill=g["ACC"], width=2)
        for t, d in self.points:
            x, y = self._xy(t, d)
            cv.create_oval(x - 6, y - 6, x + 6, y + 6, fill=g["PANEL2"], outline=g["ACC"], width=2, tags="point")
        c = self.engine.curves.get(self.target_name())
        if c and c.get("temp") is not None and c["state"].duty is not None:
            x, y = self._xy(max(T_MIN, min(T_MAX, c["temp"])), c["state"].duty)
            cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=g["FG"], outline="")

    # ------------------------------------------------------------ actions
    def use_curve(self):
        name, ids = self.target_name(), self.target_ids()
        try:
            points = fc.clean_points(self.points)
            hyst = HYSTERESIS.get(self.hyst.get(), 3.0)
            self.engine.start(name, ids, self.source.get(), points, hysteresis=hyst)
        except ValueError as e:
            self.msg.config(text=str(e))
            return False
        curves = dict(self.saved())
        curves[name] = dict(ids=ids, source=self.source.get(), preset=self.preset.get(),
                            points=[list(p) for p in points], hysteresis=hyst, active=True)
        self._save(curves)
        self.msg.config(text="Curve running. It is saved; tick the box below to start it with RETWEAKS.")
        self.update_state()
        return True

    def back_to_auto(self):
        name = self.target_name()
        ids = self.target_ids()
        if self.engine.running(name):
            self.engine.stop(name)
        else:
            self.engine.stop_for(ids)
            self.engine._default(ids)
        curves = dict(self.saved())
        if name in curves and isinstance(curves[name], dict):
            curves[name] = dict(curves[name], active=False)
            self._save(curves)
        self.msg.config(text="Automatic (BIOS) control requested for these fans.")
        self.update_state()

    def _resume_saved(self):
        """Launch with "Start my fan curves" ticked: start saved active curves once their controllers exist."""
        self._resume_job = None
        if self.closed or not self.on_start.get():
            return
        controls = {r["id"] for r in (getattr(self.hub.temperatures, "fan_controls", None) or [])}
        waiting = False
        for name, c in self.saved().items():
            if not (isinstance(c, dict) and c.get("active")) or self.engine.running(name):
                continue
            ids = [i for i in c.get("ids", []) if isinstance(i, str)]
            if not ids or not set(ids) <= controls:
                waiting = True
                continue
            try:
                self.engine.start(name, ids, c.get("source"), c.get("points", []),
                                  hysteresis=c.get("hysteresis", 3.0))
            except ValueError:
                pass
        if waiting and time.monotonic() - getattr(self, "_resume_t0", time.monotonic()) < 120:
            self._resume_t0 = getattr(self, "_resume_t0", time.monotonic())
            self._resume_job = self.hub.after(3000, self._resume_saved)
        self.update_state()

    # ------------------------------------------------------------ status
    def _engine_status(self, name, text):
        if name == self.target_name():
            self.update_state()

    def update_state(self):
        if self.closed:
            return
        name = self.target_name()
        c = self.engine.curves.get(name)
        try:
            if c is not None:
                self.state.config(text=c.get("status") or "RETWEAKS curve")
            elif self.engine.owns(self.target_ids()):
                self.state.config(text="Part of a running RETWEAKS curve on another fan group")
            else:
                saved = self.saved().get(name)
                self.state.config(text="Automatic (BIOS)" + (" · saved curve not running" if saved else ""))
        except tk.TclError:
            pass

    def _tick_readout(self):
        if self.closed:
            return
        try:
            rows = self.page.selected_controls()
            duty = [r.get("value") for r in rows if r.get("value") is not None]
            temp = fc.source_temperature(self.hub.temperatures, self.source.get())
            rpm = getattr(self.page.visual, "rpm", None)
            parts = [f"Fan {rpm:,.0f} RPM" if rpm is not None else "Fan RPM unavailable",
                     (f"duty {min(duty):.0f}–{max(duty):.0f}%" if len(set(round(d) for d in duty)) > 1
                      else f"duty {duty[0]:.0f}%") if duty else "duty unavailable",
                     f"{self.source.get()} {format_temp(temp, self.hub)}" if temp is not None
                     else f"{self.source.get()} temperature unavailable"]
            self.readout.config(text="  ·  ".join(parts))
            self.update_state()
            if self.engine.running(self.target_name()):
                self.redraw()
        except tk.TclError:
            return
        self.hub.after(1000, self._tick_readout)

    def close(self):
        self.closed = True
        self.engine.close()          # every fan a curve touched goes back to automatic (BIOS)
