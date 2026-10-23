"""RETWEAKS theme maker on the Appearance page (Tk port of ui/widgets/theme_maker.py).

Users edit the same 10 colours as RETWEAKS v1.4.3+ and share themes as RET1- codes (old RYT1- codes still
import). Saved in settings 'custom_themes' {name: colours}; built-in names can't be reused. In this app's
palette model the background, sidebar, cards, borders and accent are applied (the raised-panel colour is
derived as before); text, secondary text and the status colours are kept in the theme and in share codes but
this app's text colours are fixed light tones, so they don't change on screen."""
import tkinter as tk
from tkinter import colorchooser

import appearance as ap
from core import themes as rt
from rt_pages.common import label, card, button_row

FIXED_TEXT = {"text": "#f5f5f6", "subtext": "#aaaab0", "good": "#69c59b", "warn": "#d29922", "bad": "#e07e81"}
APPLIED = {"bg", "sidebar", "card", "border", "accent"}


def editable_for(name):
    """The 10 editable colours for any theme in the combined app (a starting point for the maker)."""
    if name in ap.CUSTOM_COLORS:
        return dict(ap.CUSTOM_COLORS[name])
    if name in ap.RETWEAKS_FULL or name in ap.RETWEAKS_ACCENTS:
        return rt.editable_colors(name)
    bg, side, panel, _panel2, line, accent = ap.colors_of(name)
    return {"bg": bg, "sidebar": side, "card": panel, "border": line, "accent": accent, **FIXED_TEXT}


def palette_tuple(colors):
    t = rt.build_palette(colors)
    return (t["bg"], t["sidebar"], t["card"], t["card_hover"], t["border"], t["accent"])


class ThemeMaker:
    def __init__(self, hub, parent, g):
        self.hub, self.g = hub, g
        self.preview_of = None          # theme to go back to after a preview
        body = card(parent, g, "Theme maker",
                    "Pick your own colours, preview them, save the theme and share it as a code. Background, "
                    "sidebar, cards, borders and accent change this app; text and status colours are kept in the "
                    "theme and its share code.")
        self.body = body
        row = tk.Frame(body, bg=body.cget("bg"))
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text="Start from", bg=row.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left")
        self.base = g["RSelect"](row, ap.theme_names(), width=200, command=self.load_base)
        self.base.set(hub.theme_name)
        self.base.pack(side="left", padx=(8, 18))
        tk.Label(row, text="Name", bg=row.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left")
        self.name = tk.StringVar()
        g["REntry"](row, self.name, width_px=200).pack(side="left", padx=8)

        grid = tk.Frame(body, bg=body.cget("bg"))
        grid.pack(fill="x", padx=16, pady=6)
        self.vars, self.swatches = {}, {}
        for i, (key, title) in enumerate(rt.EDITABLE):
            r, c = divmod(i, 2)
            cell = tk.Frame(grid, bg=grid.cget("bg"))
            cell.grid(row=r, column=c, sticky="w", padx=(0, 30), pady=2)
            tk.Label(cell, text=title + ("" if key in APPLIED else " *"), width=16, anchor="w", bg=cell.cget("bg"),
                     fg=g["FG"], font=(g["UI"], 9)).pack(side="left")
            sw = tk.Canvas(cell, width=22, height=22, highlightthickness=1, highlightbackground=g["LINE"], bd=0,
                           cursor="hand2")
            sw.pack(side="left", padx=6)
            sw.bind("<Button-1>", lambda e, k=key: self.pick(k))
            v = tk.StringVar()
            v.trace_add("write", lambda *a, k=key: self._swatch(k))
            e = tk.Entry(cell, textvariable=v, width=9, bg=g["PANEL2"], fg=g["FG"], insertbackground=g["ACC"],
                         relief="flat", font=(g["UI"], 10))
            e.pack(side="left", ipady=3)
            self.vars[key], self.swatches[key] = v, sw
        label(body, "* kept in the theme and share code; this app's text colours stay the same.", g, 8, g["MUTED"])

        bar = button_row(body, g)
        g["RButton"](bar, "Preview", self.preview, kind="default").pack(side="left", padx=(0, 6))
        g["RButton"](bar, "Discard preview", self.discard, kind="ghost").pack(side="left", padx=(0, 6))
        g["RButton"](bar, "Save theme", self.save, kind="primary").pack(side="left", padx=(0, 6))
        g["RButton"](bar, "Delete theme", self.delete, kind="ghost").pack(side="left", padx=(0, 6))
        g["RButton"](bar, "Copy share code", self.copy_code, kind="default").pack(side="left", padx=(0, 6))
        imp = tk.Frame(body, bg=body.cget("bg"))
        imp.pack(fill="x", padx=16, pady=(0, 6))
        self.code = tk.StringVar()
        g["REntry"](imp, self.code, width_px=420).pack(side="left")
        g["RButton"](imp, "Import code", self.import_code, kind="default").pack(side="left", padx=8)
        self.msg = label(body, "", g, 9, g["MUTED"], pady=(0, 12))
        self.load_base(hub.theme_name)

    # ------------------------------------------------------------ helpers
    def colors(self):
        out = {}
        for k, v in self.vars.items():
            t = v.get().strip().lower()
            if t and not t.startswith("#"):
                t = "#" + t
            out[k] = t
        return out

    def _swatch(self, key):
        v = self.vars[key].get().strip()
        if not v.startswith("#"):
            v = "#" + v
        try:
            self.swatches[key].configure(bg=v if rt._HEX.match(v) else self.g["PANEL"])
        except tk.TclError:
            pass

    def say(self, text, error=False):
        self.msg.configure(text=text, fg="#e07e81" if error else self.g["MUTED"])

    def load_base(self, name):
        for k, v in editable_for(name).items():
            self.vars[k].set(v)
        if name in ap.CUSTOM:
            self.name.set(name)
        self.say(f"Started from {name}.")

    def pick(self, key):
        cur = self.colors()[key]
        res = colorchooser.askcolor(color=cur if rt._HEX.match(cur) else None, parent=self.hub,
                                    title=dict(rt.EDITABLE)[key])
        if res and res[1]:
            self.vars[key].set(res[1].lower())

    def _validated(self):
        colors = self.colors()
        ok, msg = rt.validate_colors(colors)
        if not ok:
            self.say(msg, error=True)
            return None
        return colors

    # ------------------------------------------------------------ actions
    def preview(self):
        colors = self._validated()
        if colors is None:
            return
        if self.preview_of is None:
            self.preview_of = self.hub.theme_name
        self.hub.apply_theme(self.preview_of, save=False, colors=palette_tuple(colors))
        self.say("Previewing. Save the theme to keep it, or Discard preview.")

    def discard(self):
        if self.preview_of is not None:
            back, self.preview_of = self.preview_of, None
            self.hub.apply_theme(back, save=False)
            self.say(f"Back to {back}.")

    def save(self):
        colors = self._validated()
        if colors is None:
            return
        name = rt.clean_theme_name(self.name.get())
        if not name:
            self.say("Give the theme a name first.", error=True)
            return
        if name in ap.builtin_names():
            self.say(f"'{name}' is a built-in theme name. Choose another name.", error=True)
            return
        saved = dict(self.hub.settings.get("custom_themes") or {})
        saved[name] = colors
        self.hub.settings["custom_themes"] = saved
        if not self.hub.save_settings():
            self.say("Couldn't save the theme to settings.", error=True)
            return
        ap.register_custom(saved)
        self.preview_of = None
        self.hub.apply_theme(name)
        self._refresh_lists(name)
        self.hub.log_action("Theme maker", f"Save theme {name}", "Saved")
        self.say(f"Saved and applied '{name}'.")

    def delete(self):
        name = rt.clean_theme_name(self.name.get())
        saved = dict(self.hub.settings.get("custom_themes") or {})
        if name not in saved:
            self.say("Only your own saved themes can be deleted. Type its name or start from it.", error=True)
            return
        from tkinter import messagebox
        if not messagebox.askyesno("Delete theme", f"Delete your theme '{name}'?", parent=self.hub):
            return
        del saved[name]
        self.hub.settings["custom_themes"] = saved
        self.hub.save_settings()
        ap.register_custom(saved)
        if self.hub.theme_name == name:
            self.hub.apply_theme("Graphite")
        self._refresh_lists(self.hub.theme_name)
        self.hub.log_action("Theme maker", f"Delete theme {name}", "Deleted")
        self.say(f"Deleted '{name}'.")

    def copy_code(self):
        colors = self._validated()
        if colors is None:
            return
        name = rt.clean_theme_name(self.name.get()) or "My theme"
        code = rt.export_code(name, colors)
        self.hub.clipboard_clear()
        self.hub.clipboard_append(code)
        self.code.set(code)
        self.say("Share code copied to the clipboard.")

    def import_code(self):
        ok, name, colors = rt.parse_code(self.code.get())
        if not ok:
            self.say(name, error=True)
            return
        for k, v in colors.items():
            self.vars[k].set(v)
        if name in ap.builtin_names():
            name = name + " (shared)"
        self.name.set(name)
        self.say(f"Loaded '{name}'. Preview it or Save theme to keep it.")

    def _refresh_lists(self, current):
        names = ap.theme_names()
        self.base.values = names
        self.base.set(current)
        for sel in getattr(self.hub, "_theme_selectors", []):
            sel.values = names
            sel.set(self.hub.theme_name)
