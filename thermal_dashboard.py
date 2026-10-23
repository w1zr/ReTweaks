"""Temperature tiles for the Temperatures page (the base app's v1.5 sensor cards, simplified for RETWEAKS).

Owner feedback 2026-10-22: the page had "too much going on" (a big 175 px gauge per device). Each device is now a
compact tile: part (CPU / GPU / STORAGE...), device name, the main reading large with a slim bar, and the other
readings (hot spot, cores, drive sensors) in small text. Core, hot-spot and drive sensors stay separately
labelled; sensors that report nothing are left out, never shown as 0. The unit follows the one temp_unit setting.
"""
import tkinter as tk

from temperatures import format_temperature, hardware_name, live_sensor, primary_reading

BAR_MAX_C = 100.0          # bar scale; the number itself is the real reading


def _fmt(value, unit):
    if value is None:
        return "—"
    return f"{value * 9 / 5 + 32:.0f}°F" if unit == "F" else f"{value:.0f}°C"


class ThermalDashboard:
    def __init__(self, hub, parent, g):
        self.hub, self.g = hub, g
        self.frame = tk.Frame(parent, bg=g["BG"])
        self.frame.pack(fill="x", padx=(0, 12))
        self.tiles = {}
        self.columns = 0
        self.frame.bind("<Configure>", self.layout)

    def layout(self, event=None):
        w = self.frame.winfo_width()
        columns = 3 if w > 900 else 2 if w > 600 else 1
        for index in range(3):
            self.frame.columnconfigure(index, weight=1 if index < columns else 0, uniform="thermal")
        for index, tile in enumerate(self.tiles.values()):
            tile["card"].grid(row=index // columns, column=index % columns, sticky="nsew", padx=6, pady=6)
        self.columns = columns

    def update(self, rows, unit, cpu_name=None):
        groups = {}
        for row in rows:
            if live_sensor(row):
                groups.setdefault((row["part"], hardware_name(row)), []).append(row)
        if cpu_name and not any(part == "CPU" for part, name in groups):
            groups[("CPU", cpu_name)] = []
        for key in list(self.tiles):
            if key not in groups:
                self.tiles.pop(key)["card"].destroy()
        for key, readings in groups.items():
            if key not in self.tiles:
                self.tiles[key] = self._make_tile(key)
            tile = self.tiles[key]
            tile["readings"] = readings
            tile["unit"] = unit
            self.draw(tile)
        self.layout()

    def _make_tile(self, key):
        g = self.g
        part, hardware = key
        card = g["Card"](self.frame, radius=14)
        body = card.body
        bg = body.cget("bg")
        tk.Label(body, text=part.upper(), bg=bg, fg=g["MUTED"], font=(g["UI"], 8, "bold"), anchor="w").pack(
            fill="x", padx=14, pady=(12, 0))
        title = tk.Label(body, text=hardware, bg=bg, fg=g["FG"], font=(g["UI"], 11, "bold"), anchor="w",
                         justify="left")
        title.pack(fill="x", padx=14)
        value = tk.Label(body, text="—", bg=bg, fg=g["FG"], font=(g["UI"], 24, "bold"), anchor="w")
        value.pack(fill="x", padx=14, pady=(6, 0))
        bar = tk.Canvas(body, height=6, bg=bg, highlightthickness=0, bd=0)
        bar.pack(fill="x", padx=14, pady=(2, 6))
        details = tk.Label(body, text="", bg=bg, fg=g["MUTED"], font=(g["UI"], 9), anchor="w", justify="left")
        details.pack(fill="x", padx=14, pady=(0, 12))
        tile = {"card": card, "title": title, "value": value, "bar": bar, "details": details,
                "gauge": bar, "readings": [], "unit": "C"}
        bar.bind("<Configure>", lambda e, t=tile: self._draw_bar(t))
        card.bind("<Configure>", lambda e, t=tile: t["title"].configure(wraplength=max(120, e.width - 40)), add="+")
        return tile

    def _primary(self, tile):
        p = primary_reading(tile["readings"])
        return p["c"] if p else None

    def _draw_bar(self, tile):
        cv = tile["bar"]
        g = self.g
        cv.delete("all")
        w = max(40, cv.winfo_width())
        cv.create_rectangle(0, 1, w, 5, fill=g["LINE"], outline="")
        v = self._primary(tile)
        if v is not None:
            frac = max(0.0, min(1.0, v / BAR_MAX_C))
            cv.create_rectangle(0, 1, max(2, w * frac), 5, fill=g["ACC"], outline="")

    def draw(self, tile):
        unit = tile["unit"]
        rows = tile["readings"]
        primary = primary_reading(rows)
        tile["value"].configure(text=_fmt(primary["c"] if primary else None, unit))
        lines = []
        for row in rows:
            if row is primary:
                continue                     # already shown large
            name = row["name"].split(" / ", 1)[-1]
            if name == hardware_name(row):
                name = "Core" if row["part"] == "GPU" else "Temperature"
            lines.append(f"{name}  {format_temperature(row['c'], unit)}")
        if not rows:
            lines = ["Not available from this sensor yet (see PawnIO above)."]
        elif primary is not None and not lines:
            name = primary["name"].split(" / ", 1)[-1]
            lines = [name if name != hardware_name(primary) else "Temperature"]
        tile["details"].configure(text="\n".join(lines[:6]) + (f"\n+{len(lines) - 6} more" if len(lines) > 6 else ""))
        self._draw_bar(tile)
