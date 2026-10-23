"""Temperature-based fan curves for the Fan control page (RETWEAKS addition on top of base app v1.5, owner
request 2026-10-22: "feel free to improve the fan rgb settings").

How a curve runs:
- Every tick (2 s) it reads one source temperature (CPU, GPU, or the hotter of the two) from the bundled
  LibreHardwareMonitor sensor host, works out a duty from 4-6 editable (temperature, duty) points, and sends it
  through temperatures.Temperatures -> SensorHost.exe, the same path as the manual "Apply speed" button.
- Hysteresis: speed goes up as soon as the curve asks for more, but only comes down once the temperature has
  dropped `hysteresis` degrees below the point that asked for the current speed, and then by at most
  `ramp_down` % per tick. Small changes (< 2 %) aren't sent. So the fans don't flap.
- Limits: never below 30 % or the controller's own minimum, never above its maximum; pumps are never listed
  (the sensor host leaves them out).
- Failsafes (all hand control back to the hardware / BIOS with SetDefault):
  * no valid source temperature for FAILSAFE_SECONDS -> automatic until readings come back;
  * source temperature >= 85 C -> automatic (the sensor host also enforces this and restores on its own);
  * stopping the curve, Quit (page close()), normal interpreter exit (atexit);
  * if RETWEAKS is killed or crashes, the sensor host's stdin closes and it restores every fan it touched
    (SensorHost.cs: reader thread ends -> stop -> finally Restore()); it also restores after 45 s without
    a heartbeat.
Curves never start on their own at launch unless the user ticked "Start my fan curves with RETWEAKS".
"""
import atexit
import math
import time

MIN_DUTY = 30.0
SAFETY_TEMP = 85.0          # same limit as SensorHost.cs: at or above this the hardware's own control takes over
FAILSAFE_SECONDS = 8.0
TICK_MS = 2000
SEND_DELTA = 2.0

PRESETS = {   # (temperature C, duty %), sorted; every preset ends at 100 % well before the 85 C hand-back
    "Silent": [(30, 30), (50, 35), (65, 50), (75, 75), (82, 100)],
    "Balanced": [(30, 30), (45, 40), (60, 60), (72, 85), (80, 100)],
    "Performance": [(30, 40), (45, 55), (60, 75), (70, 90), (78, 100)],
    "Full speed": [(20, 100), (40, 100), (60, 100), (80, 100)],
}
PRESET_ORDER = ["Silent", "Balanced", "Performance", "Full speed", "Custom"]
SOURCES = ["CPU", "GPU", "Hottest of CPU and GPU"]


def clean_points(points):
    """Validate user/config points: 4-6 pairs, finite numbers, temps 0-100 C rising, duty 30-100 %.
    Returns a new sorted list or raises ValueError."""
    try:
        pts = [(float(t), float(d)) for t, d in points]
    except (TypeError, ValueError):
        raise ValueError("Each curve point needs a temperature and a speed.")
    if not 4 <= len(pts) <= 6:
        raise ValueError("A fan curve needs 4 to 6 points.")
    for t, d in pts:
        if not (math.isfinite(t) and math.isfinite(d)):
            raise ValueError("Curve points must be numbers.")
        if not 0 <= t <= 100:
            raise ValueError("Curve temperatures must be between 0 and 100 °C.")
        if not MIN_DUTY <= d <= 100:
            raise ValueError("Curve speeds must be between 30 and 100 %.")
    pts.sort()
    if any(b[0] - a[0] < 1 for a, b in zip(pts, pts[1:])):
        raise ValueError("Curve temperatures must be at least 1 °C apart.")
    return pts


def interpolate(points, temp):
    """Duty for a temperature: flat before the first point and after the last, straight lines between."""
    if temp <= points[0][0]:
        return points[0][1]
    if temp >= points[-1][0]:
        return points[-1][1]
    for (t0, d0), (t1, d1) in zip(points, points[1:]):
        if t0 <= temp <= t1:
            return d0 + (d1 - d0) * (temp - t0) / (t1 - t0)
    return points[-1][1]


def clamp(duty, low, high):
    return max(max(MIN_DUTY, low), min(min(100.0, high), duty))


class CurveState:
    """Hysteresis + ramp for one curve. Pure (no hardware), so it can be unit tested."""

    def __init__(self, points, hysteresis=3.0, ramp_down=5.0):
        self.points = clean_points(points)
        self.hysteresis = max(0.0, min(10.0, float(hysteresis)))
        self.ramp_down = max(1.0, min(50.0, float(ramp_down)))
        self.duty = None          # last duty decided

    def next_duty(self, temp, low=MIN_DUTY, high=100.0):
        up = clamp(interpolate(self.points, temp), low, high)
        if self.duty is None:
            self.duty = up
            return self.duty
        if up >= self.duty:
            self.duty = up                                   # heating up: follow the curve at once
            return self.duty
        down = clamp(interpolate(self.points, temp + self.hysteresis), low, high)
        if down < self.duty:                                 # cooled past the hysteresis band: ease down
            self.duty = max(down, self.duty - self.ramp_down)
        return self.duty


def source_temperature(temperatures, source, now=None, max_age=FAILSAFE_SECONDS):
    """Freshest reading for CPU / GPU / hottest; None when nothing valid and recent is available."""
    from temperatures import primary_reading
    now = time.monotonic() if now is None else now
    rows = []
    if temperatures is not None:
        if now - (getattr(temperatures, "extended_time", 0) or 0) <= max_age:
            rows = list(getattr(temperatures, "extended", None) or [])
        if not rows and time.time() - (getattr(temperatures, "updated", 0) or 0) <= max_age:
            rows = list(getattr(temperatures, "rows", None) or [])
    parts = ["CPU", "GPU"] if source == SOURCES[2] else [source]
    values = [r["c"] for r in (primary_reading(rows, p) for p in parts) if r]
    return max(values) if values else None


class CurveEngine:
    """Runs saved curves on the Tk thread (hub.after). One curve per fan target (a list of controller ids)."""

    def __init__(self, hub, temperatures, on_status=None):
        self.hub, self.t = hub, temperatures
        self.on_status = on_status
        self.curves = {}          # name -> dict(ids, source, state, last_sent, missing_since, auto, status)
        self.job = None
        self.closed = False
        atexit.register(self.release_all)

    # ------------------------------------------------------------ control
    def start(self, name, ids, source, points, hysteresis=3.0, ramp_down=5.0):
        if not ids:
            raise ValueError("Pick fans that report a speed controller first.")
        if source not in SOURCES:
            raise ValueError("Unknown temperature source.")
        state = CurveState(points, hysteresis, ramp_down)
        for other, c in list(self.curves.items()):           # a controller follows one curve at a time
            if other != name and set(c["ids"]) & set(ids):
                self.stop(other)
        self.curves[name] = dict(ids=list(dict.fromkeys(ids)), source=source, state=state, last_sent=None,
                                 missing_since=None, auto=False, status="Starting…", temp=None)
        self.tick()

    def stop(self, name, reason="Automatic (BIOS)"):
        c = self.curves.pop(name, None)
        if c is not None:
            self._default(c["ids"])
            self._status(name, reason)
        if not self.curves and self.job is not None:
            try:
                self.hub.after_cancel(self.job)
            except Exception:
                pass
            self.job = None

    def running(self, name):
        return name in self.curves

    def owns(self, ids):
        return any(set(c["ids"]) & set(ids) for c in self.curves.values())

    def stop_for(self, ids):
        for name, c in list(self.curves.items()):
            if set(c["ids"]) & set(ids):
                self.stop(name, "Stopped: you set a manual speed")

    def release_all(self):
        """Quit / exit: every fan a curve touched goes back to the hardware's automatic control."""
        for name in list(self.curves):
            self.stop(name)

    def close(self):
        self.closed = True
        self.release_all()
        try:
            atexit.unregister(self.release_all)
        except Exception:
            pass

    # ------------------------------------------------------------ loop
    def _controls(self, ids):
        rows = {r["id"]: r for r in (getattr(self.t, "fan_controls", None) or [])}
        return [rows[i] for i in ids if i in rows]

    def _default(self, ids):
        try:
            if len(ids) > 1:
                self.t.fan_batch("default_many", ids)
            elif ids:
                self.t.fan_command("default", ids[0])
        except Exception:
            pass

    def _fmt(self, celsius):
        try:
            from rt_pages.settings_store import format_temp
            return format_temp(celsius, self.hub)
        except Exception:
            return f"{celsius:.0f} °C"

    def _status(self, name, text):
        c = self.curves.get(name)
        if c is not None:
            c["status"] = text
        if self.on_status:
            try:
                self.on_status(name, text)
            except Exception:
                pass

    def evaluate(self, name, now=None):
        """One decision for one curve. Returns the duty sent, or None (automatic / nothing sent)."""
        c = self.curves[name]
        now = time.monotonic() if now is None else now
        controls = self._controls(c["ids"])
        temp = source_temperature(self.t, c["source"], now=now)
        c["temp"] = temp
        if temp is None or len(controls) != len(c["ids"]):
            if c["missing_since"] is None:
                c["missing_since"] = now
            if now - c["missing_since"] >= FAILSAFE_SECONDS and not c["auto"]:
                self._default(c["ids"])
                c["auto"], c["last_sent"], c["state"].duty = True, None, None
                self._status(name, "Failsafe: no " + ("temperature reading" if temp is None else "fan controller")
                             + " for a few seconds, so the fans are back on automatic (BIOS). The curve resumes "
                               "when readings return.")
            return None
        c["missing_since"] = None
        if temp >= SAFETY_TEMP:
            if not c["auto"]:
                self._default(c["ids"])
                c["auto"], c["last_sent"], c["state"].duty = True, None, None
            self._status(name, f"{temp:.0f} °C is at or above {SAFETY_TEMP:.0f} °C: hardware automatic control "
                               "(safety). The curve resumes below that.")
            return None
        low = max(r.get("min", MIN_DUTY) or MIN_DUTY for r in controls)
        high = min(r.get("max", 100) or 100 for r in controls)
        if low > high:
            self._status(name, "These fans don't share a speed range; pick them one at a time.")
            return None
        duty = round(c["state"].next_duty(temp, low, high))
        c["auto"] = False
        if c["last_sent"] is None or abs(duty - c["last_sent"]) >= SEND_DELTA:
            try:
                ok = (self.t.fan_batch("manual_many", c["ids"], duty) if len(c["ids"]) > 1
                      else self.t.fan_command("manual", c["ids"][0], duty))
            except ValueError as e:
                self._status(name, str(e))
                return None
            if ok:
                c["last_sent"] = duty
        self._status(name, f"RETWEAKS curve · {c['source']} {self._fmt(temp)} → {duty}%")
        return duty

    def tick(self):
        self.job = None
        if self.closed:
            return
        for name in list(self.curves):
            try:
                self.evaluate(name)
            except Exception as e:                  # never leave a fan on a fixed duty because of a bug here
                c = self.curves.get(name)
                if c is not None:
                    self.stop(name, f"Stopped after an error ({type(e).__name__}); fans back on automatic (BIOS).")
        if self.curves:
            try:
                self.job = self.hub.after(TICK_MS, self.tick)
            except Exception:
                self.release_all()
