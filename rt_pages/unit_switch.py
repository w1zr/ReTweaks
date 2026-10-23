"""°C | °F switch used on the Temperatures page and in Settings (owner report 2026-10-22: the Settings dropdown
didn't change the unit on his PC while the Temperatures page switch did, so both places now use this one control).

Click a side, or use Left/Right/Space when focused. It calls rt_pages.settings_store.set_temp_unit, which saves
config.json and tells every page (on_temp_unit), so the whole app switches at once. get()/set() accept "°C"/"°F"
or "C"/"F" so older code that treated the Settings control like a dropdown keeps working.
"""
import tkinter as tk

W, H = 104, 32


class UnitSwitch(tk.Canvas):
    def __init__(self, parent, hub, g, on_change=None):
        bg = parent.cget("bg") if "bg" in parent.keys() else g["BG"]
        super().__init__(parent, width=W, height=H, bg=bg, highlightthickness=0, bd=0, cursor="hand2", takefocus=1)
        self.hub, self.g, self.on_change = hub, g, on_change
        self.bind("<ButtonRelease-1>", lambda e: self.choose("C" if e.x < W / 2 else "F"))
        self.bind("<Left>", lambda e: self.choose("C"))
        self.bind("<Right>", lambda e: self.choose("F"))
        self.bind("<space>", lambda e: self.choose("F" if self.unit() == "C" else "C"))
        self.bind("<FocusIn>", lambda e: self.draw())
        self.bind("<FocusOut>", lambda e: self.draw())
        self.draw()

    def unit(self):
        from rt_pages.settings_store import temp_unit
        return temp_unit(self.hub)

    def choose(self, unit):
        from rt_pages.settings_store import set_temp_unit
        unit = set_temp_unit(self.hub, unit)          # saves + notifies every page (which redraws this switch)
        self.draw()
        if self.on_change:
            try:
                self.on_change(unit)
            except Exception:
                pass

    # dropdown-compatible API
    def get(self):
        return "°F" if self.unit() == "F" else "°C"

    def set(self, value):
        self.draw()

    def draw(self):
        g = self.g
        self.delete("all")
        u = self.unit()
        rr = g.get("rr")

        def pill(x0, y0, x1, y1, r, **kw):
            if rr:
                self.create_polygon(rr(x0, y0, x1, y1, r), smooth=True, **kw)
            else:
                self.create_rectangle(x0, y0, x1, y1, **kw)
        focus = self.focus_get() is self if self.winfo_exists() else False
        pill(1, 1, W - 1, H - 1, 15, fill=g["PANEL"], outline=g["ACC"] if focus else g["LINE"])
        x0 = 4 if u == "C" else W / 2
        pill(x0, 4, x0 + W / 2 - 4, H - 4, 12, fill=g.get("PANEL2", g["PANEL"]), outline=g["LINE"])
        for label, cx, on in (("°C", W / 4 + 2, u == "C"), ("°F", 3 * W / 4 - 2, u == "F")):
            self.create_text(cx, H / 2, text=label, fill=g["FG"] if on else g["MUTED"],
                             font=(g["UI"], 10, "bold" if on else "normal"))
