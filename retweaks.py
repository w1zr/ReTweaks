"""
RETWEAKS - Windows 10/11 Performance Tweaker + Game Presets
GUI version. Needs retweaks_data.py next to it. Build to .exe with build_exe.bat

Run-and-done from a shortcut / command line:
    RETWEAKS.exe --preset maxfps            (apply a preset silently)
    RETWEAKS.exe --preset maxfps --undo     (undo it)
    RETWEAKS.exe --list                     (show preset names)
"""
import os, sys, threading, queue, datetime, re, math
if '--verify-startup' in sys.argv:
    def _verify_error(kind, value, tb):
        import traceback
        with open(os.path.join(os.path.dirname(sys.executable), 'startup-check-error.txt'), 'w', encoding='utf-8') as report:
            traceback.print_exception(kind, value, tb, file=report)
    sys.excepthook = _verify_error
import tkinter as tk
from tkinter import messagebox, filedialog
import tkinter.font as tkfont
from retweaks_data import *
from branding import feather
from core.version import BRAND, __version__ as VERSION

# ------------------------------------------------------------------ theme
BG, SIDE, PANEL, PANEL2, LINE = "#09090b", "#101012", "#151518", "#222226", "#303035"
FG, MUTED, DIM = "#f5f5f6", "#aaaab0", "#77777f"
ACC, ACC_D, ACC2, GREEN, RED = "#eeeef0", "#141416", "#b8b8c0", "#69c59b", "#e07e81"
HERO, HERO2, HERO_EDGE = "#1c1c20", "#18181c", "#37373e"
NAV_ACTIVE, NAV_HOVER, EDGE_HOVER = "#26262c", "#1c1c21", "#55555e"
RISKCOL = {"Safe": "#3ddc84", "Medium": "#ffb020", "Advanced": "#ff5c5c"}
UI = "Segoe UI"


# ------------------------------------------------------------------ drawing helpers
def _rgb(c):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(c1, c2, t):
    """Blend two #rrggbb colours (t=0 -> c1, t=1 -> c2)."""
    t = max(0.0, min(1.0, t))
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def rr(x1, y1, x2, y2, r):
    """Sample circular corners so pills stay round at every widget size."""
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    points = []
    for cx, cy, start in ((x2-r, y1+r, -90), (x2-r, y2-r, 0),
                          (x1+r, y2-r, 90), (x1+r, y1+r, 180)):
        for step in range(9):
            angle = math.radians(start + step * 90 / 8)
            points.extend((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


_fonts = {}


def text_w(spec, text):
    f = _fonts.get(spec)
    if f is None:
        f = _fonts[spec] = tkfont.Font(font=spec)
    return f.measure(text)


def _bg_of(w):
    try:
        return w.cget("bg")
    except Exception:
        return BG


def _descendants(w):
    out = []
    for c in w.winfo_children():
        out.append(c)
        out.extend(_descendants(c))
    return out


# ------------------------------------------------------------------ rounded widgets
class Card(tk.Canvas):
    """Rounded container. Put children in .body. Grows with its content unless elastic=True (then it fills its parent)."""

    def __init__(self, parent, fill=PANEL, edge=LINE, radius=14, margin_right=0, elastic=False, outer=None):
        inset = max(3, int(radius * 0.34))
        # Start tall enough that the body is inside the canvas: with a big radius (inset >= 10) a 10 px canvas
        # left the body window fully outside, Tk never mapped it, and the card never grew (empty cards).
        start = max(10, 2 * inset + 4)
        super().__init__(parent, bg=outer or _bg_of(parent), highlightthickness=0, bd=0, width=start, height=start)
        self.fill, self.edge, self.radius = fill, edge, radius
        self.margin_right, self.elastic = margin_right, elastic
        self.inset = inset
        self.deco = None  # optional callable(canvas, w, h) that draws decoration on the card
        self._wraps = []
        self.body = tk.Frame(self, bg=fill)
        self._win = self.create_window(self.inset, self.inset, window=self.body, anchor="nw")
        self.bind("<Configure>", self._on_size)
        self.body.bind("<Configure>", self._on_body)

    def _on_size(self, e):
        kw = dict(width=max(1, e.width - 2 * self.inset - self.margin_right))
        if self.elastic:
            kw["height"] = max(1, e.height - 2 * self.inset)
        self.itemconfigure(self._win, **kw)
        self.delete("bg")
        self.create_polygon(rr(1, 1, e.width - 1, e.height - 1, self.radius), smooth=True, fill=self.fill,
                            outline=self.edge, tags="bg")
        if self.deco:
            self.delete("deco")
            self.deco(self, e.width, e.height)
        self.tag_lower("bg")
        for lbl, margin in self._wraps:
            wl = max(100, e.width - 2 * self.inset - self.margin_right - margin)
            try:
                if int(str(lbl.cget("wraplength"))) != wl:
                    lbl.configure(wraplength=wl)
            except tk.TclError:
                pass

    def _on_body(self, e):
        if self.elastic:
            return
        h = e.height + 2 * self.inset
        if int(self.cget("height")) != h:
            self.configure(height=h)

    def wrap(self, label, margin=30):
        """Keep a label's wraplength matched to this card's width."""
        self._wraps.append((label, margin))

    def set_edge(self, color):
        self.edge = color
        self.itemconfigure("bg", outline=color)

    def hoverable(self, color=None):
        """Highlight the outline while the pointer is anywhere over the card."""
        self._hov_color = color or mix(LINE, ACC, 0.55)
        self._hov_base = self.edge

        def enter(_e=None):
            self.set_edge(self._hov_color)

        def leave(_e=None):
            self.after(40, self._hov_check)

        for w in [self, self.body] + _descendants(self.body):
            w.bind("<Enter>", enter, add="+")
            w.bind("<Leave>", leave, add="+")

    def _hov_check(self):
        try:
            x, y = self.winfo_pointerxy()
            rx, ry = self.winfo_rootx(), self.winfo_rooty()
            inside = rx <= x < rx + self.winfo_width() and ry <= y < ry + self.winfo_height()
            self.set_edge(self._hov_color if inside else self._hov_base)
        except tk.TclError:
            pass


class RButton(tk.Canvas):
    """Rounded button with a smooth hover fade."""
    KINDS = {
        "primary": dict(fill=ACC, hfill="#ffffff", edge=ACC, hedge="#ffffff", fg=ACC_D, hfg=ACC_D),
        "default": dict(fill=PANEL2, hfill="#303035", edge=LINE, hedge=ACC, fg=FG, hfg="#ffffff"),
        "ghost": dict(fill=None, hfill="#242428", edge=LINE, hedge=EDGE_HOVER, fg=MUTED, hfg=FG),
        "hero": dict(fill="#202024", hfill="#303035", edge=ACC, hedge="#ffffff", fg=FG, hfg="#ffffff"),
    }

    def __init__(self, parent, text, command=None, kind="default", width=None, height=34, radius=17,
                 font=(UI, 10, "bold"), outer=None):
        outer = outer or _bg_of(parent)
        w = width or (text_w(font, text) + 36)
        super().__init__(parent, width=w, height=height, bg=outer, highlightthickness=0, bd=0, cursor="hand2")
        self.outer, self.label, self.command, self.kind = outer, text, command, kind
        self.bw, self.bh, self.radius, self.font = w, height, radius, font
        self.p, self.target, self.job = 0.0, 0.0, None
        self.pressed, self.enabled = False, True
        self.bind("<Enter>", lambda e: self._go(1.0))
        self.bind("<Leave>", lambda e: self._go(0.0))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self._draw()

    def _go(self, target):
        if not self.enabled:
            target = 0.0
        self.target = target
        if self.job is None:
            self.job = self.after(15, self._step)

    def _step(self):
        self.job = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        d = self.target - self.p
        self.p = self.target if abs(d) < 0.04 else self.p + d * 0.4
        self._draw()
        if self.p != self.target:
            self.job = self.after(15, self._step)

    def _press(self, _e):
        if self.enabled:
            self.pressed = True
            self._draw()

    def _release(self, e):
        was = self.pressed
        self.pressed = False
        self._draw()
        # the button's real on-screen size counts (a stretched/scaled button used to ignore clicks past bw)
        w, h = max(self.bw, self.winfo_width()), max(self.bh, self.winfo_height())
        if was and self.enabled and 0 <= e.x <= w and 0 <= e.y <= h and self.command:
            self.command()

    def _draw(self):
        k = self.KINDS[self.kind]
        t = self.p
        fill = mix(k["fill"] or self.outer, k["hfill"], t)
        edge = mix(k["edge"], k["hedge"], t)
        fg = mix(k["fg"], k["hfg"], t)
        if not self.enabled:
            fill, edge, fg = mix(PANEL2, self.outer, 0.35), LINE, DIM
        self.delete("all")
        self.create_polygon(rr(1, 1, self.bw - 1, self.bh - 1, self.radius), smooth=True, fill=fill, outline=edge)
        self.create_text(self.bw / 2, self.bh / 2 + (1 if self.pressed else 0), text=self.label, fill=fg, font=self.font)

    def set_text(self, text):
        self.label = text
        self.bw = text_w(self.font, text) + 36
        self.configure(width=self.bw)
        self._draw()

    def set_kind(self, kind):
        self.kind = kind
        self._draw()

    def set_enabled(self, flag):
        self.enabled = bool(flag)
        self.configure(cursor="hand2" if flag else "arrow")
        if not flag:
            self.p = self.target = 0.0
        self._draw()


class NavItem(tk.Canvas):
    """Sidebar button. Each one has its own hover animation style: slide, bounce, pulse or glow."""

    def __init__(self, parent, icon, text, command, style="slide", height=44, badge=None):
        super().__init__(parent, width=200, height=height, bg=SIDE, highlightthickness=0, bd=0, cursor="hand2")
        self.icon, self.text_, self.command, self.style = icon, text, command, style
        self.badge = badge
        self.nw, self.nh = 200, height
        self.hv, self.t_hv, self.ac, self.t_ac, self.job = 0.0, 0.0, 0.0, 0.0, None
        self.bind("<Configure>", self._resize)
        self.bind("<Enter>", lambda e: self._go(hv=1.0))
        self.bind("<Leave>", lambda e: self._go(hv=0.0))
        self.bind("<ButtonRelease-1>", lambda e: self.command())
        self._draw()

    def _resize(self, e):
        self.nw = e.width
        self._draw()

    def set_active(self, flag):
        self._go(ac=1.0 if flag else 0.0)

    def _go(self, hv=None, ac=None):
        if hv is not None:
            self.t_hv = hv
        if ac is not None:
            self.t_ac = ac
        if self.job is None:
            self.job = self.after(15, self._step)

    def _step(self):
        self.job = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        for name, tgt in (("hv", self.t_hv), ("ac", self.t_ac)):
            cur = getattr(self, name)
            d = tgt - cur
            setattr(self, name, tgt if abs(d) < 0.04 else cur + d * 0.34)
        self._draw()
        if self.hv != self.t_hv or self.ac != self.t_ac:
            self.job = self.after(15, self._step)

    def _draw(self):
        h, a, w, ht = self.hv, self.ac, self.nw, self.nh
        bg = mix(mix(SIDE, NAV_HOVER, h), NAV_ACTIVE, a)
        edge = mix(mix(SIDE, EDGE_HOVER, h), ACC, a)
        self.delete("all")
        self.create_polygon(rr(1, 1, w - 1, ht - 1, (ht-2)/2), smooth=True, fill=bg, outline=edge)
        m = max(h, a)
        if m > 0.03:
            bh = 8 + 16 * m
            self.create_rectangle(9, ht / 2 - bh / 2, 12, ht / 2 + bh / 2, fill=ACC, outline="")
        ix, iy, isz, tx = 32, ht / 2, 12, 54
        icol = mix(ACC2, ACC, max(h,a))
        if self.style == "slide":
            tx += 7 * h
            ix += 3 * h
        elif self.style == "bounce":
            iy -= 5 * math.sin(math.pi * h)
            tx += 3 * h
        elif self.style == "pulse":
            isz = 12 + int(round(4 * h))
            tx += 3 * h
        else:  # glow
            icol = mix(icol, "#ffffff", 0.65 * h)
            tx += 4 * h
        self.create_text(ix, iy, text=self.icon, fill=icol, font=("Segoe UI Symbol", isz))
        self.create_text(tx, ht / 2, text=self.text_, anchor="w", fill=mix(mix(MUTED, FG, h), FG, a),
                         font=(UI, 9 if self.badge else 10, "bold"))
        if self.badge:
            left = w - 39
            self.create_polygon(rr(left, ht / 2 - 8, w - 5, ht / 2 + 8, 6), smooth=True,
                                fill=mix(bg, ACC, .17), outline=mix(bg, ACC, .42))
            self.create_text((left + w - 5) / 2, ht / 2, text=self.badge, fill=ACC, font=(UI, 7, 'bold'), tags='nav-badge')


def pill(parent, text, color, outer=None, font=(UI, 8, "bold"), h=20):
    """Small rounded tag."""
    outer = outer or _bg_of(parent)
    w = text_w(font, text) + 18
    c = tk.Canvas(parent, width=w, height=h, bg=outer, highlightthickness=0, bd=0)
    c.create_polygon(rr(1, 1, w - 1, h - 1, h / 2), smooth=True, fill=mix(outer, color, 0.16),
                     outline=mix(outer, color, 0.38))
    c.create_text(w / 2, h / 2, text=text, fill=color, font=font)
    return c


class RCheck(tk.Canvas):
    """Rounded checkbox bound to a tk.BooleanVar."""

    def __init__(self, parent, text, variable, command=None, disabled=False, font=(UI, 10, "bold"), outer=None):
        outer = outer or _bg_of(parent)
        self.cb_font = font
        super().__init__(parent, width=text_w(font, text) + 34, height=26, bg=outer, highlightthickness=0, bd=0,
                         cursor="arrow" if disabled else "hand2")
        self.cb_text, self.var, self.cmd, self.disabled, self.hov = text, variable, command, disabled, False
        self._tid = variable.trace_add("write", lambda *a: self._draw())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Destroy>", self._gone)
        self._draw()

    def _gone(self, e):
        if e.widget is self:
            try:
                self.var.trace_remove("write", self._tid)
            except Exception:
                pass

    def _hover(self, flag):
        self.hov = flag
        self._draw()

    def _click(self, _e):
        if self.disabled:
            return
        self.var.set(not self.var.get())
        if self.cmd:
            self.cmd()

    def _draw(self):
        on = bool(self.var.get())
        self.delete("all")
        y0 = 4
        if self.disabled:
            fill, edge, fg = PANEL2, LINE, DIM
        else:
            fill = ACC if on else PANEL2
            edge = ACC if (on or self.hov) else EDGE_HOVER
            fg = FG
        self.create_polygon(rr(2, y0, 20, y0 + 18, 6), smooth=True, fill=fill, outline=edge)
        if on:
            self.create_line(6.5, y0 + 9.5, 10, y0 + 13, 16, y0 + 5.5, fill=ACC_D if not self.disabled else DIM,
                             width=2.2, capstyle="round", joinstyle="round")
        self.create_text(29, 13, text=self.cb_text, anchor="w", fill=fg, font=self.cb_font)


def _unbind_one(widget, seq, funcid):
    """Remove only the binding `funcid` from `seq` (tkinter's unbind(seq, id) on Python < 3.13 removes every
    handler on that event, which would also drop other parts of the app listening to the same click)."""
    try:
        script = widget.tk.call("bind", widget._w, seq)
        keep = "\n".join(line for line in str(script).split("\n") if funcid not in line)
        widget.tk.call("bind", widget._w, seq, keep)
        widget.deletecommand(funcid)
    except (tk.TclError, ValueError):
        pass


class RSelect(tk.Canvas):
    """Rounded dropdown (opens a themed menu)."""

    def __init__(self, parent, values, width=240, height=34, command=None, outer=None):
        super().__init__(parent, width=width, height=height, bg=outer or _bg_of(parent), highlightthickness=0, bd=0,
                         cursor="hand2")
        self.values, self.value, self.command = list(values), (list(values)[0] if values else ""), command
        self.sw, self.sh, self.hov = width, height, False
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonRelease-1>", lambda e: self._open())
        self.bind("<Return>", lambda e: self._open())
        self.bind("<space>", lambda e: self._open())
        self.bind("<Destroy>", lambda e: e.widget is self and self._close_popup(), add="+")
        self.bind("<Unmap>", lambda e: e.widget is self and self._close_popup(), add="+")
        self._draw()

    def _hover(self, flag):
        self.hov = flag
        self._draw()

    def _draw(self):
        self.delete("all")
        self.create_polygon(rr(1, 1, self.sw - 1, self.sh - 1, 11), smooth=True, fill=PANEL2,
                            outline=ACC if self.hov else LINE)
        self.create_text(14, self.sh / 2, text=self.value, anchor="w", fill=FG, font=(UI, 10))
        self.create_text(self.sw - 18, self.sh / 2 + 1, text="▾", fill=ACC, font=(UI, 11))

    def get(self):
        return self.value

    def set(self, v):
        self.value = v
        self._draw()

    def current(self, i):
        self.set(self.values[i])

    def current(self, i):
        self.set(self.values[i])

    # Owner report 2026-10-22: dropdowns (Theme, Dashboard banner, Sidebar header, Refresh, Open on, °C/°F) did
    # nothing when clicked on Windows. The list used to be a separate borderless window with a mouse grab and a
    # "close when focus leaves" rule; on Windows that window often lost focus the moment it opened and closed
    # itself before the click landed (the base app's own notes mention dropdown failures). The list is now a
    # panel drawn INSIDE the main window (no extra window, no grab, no focus race): it opens on click, an
    # item is chosen on click, and it closes on Esc, a click anywhere else, scrolling the page, or
    # switching pages.
    def _close_popup(self):
        popup = getattr(self, "popup", None)
        self.popup = None
        if RSelect._open_one is self:
            RSelect._open_one = None
        root = self.winfo_toplevel()
        for seq, fid in getattr(self, "_global_binds", []):
            _unbind_one(root, seq, fid)
        self._global_binds = []
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass

    _open_one = None

    def _open(self):
        if getattr(self, "popup", None) is not None:
            self._close_popup()
            return
        if not self.values:
            return
        if RSelect._open_one is not None and RSelect._open_one is not self:
            try:
                RSelect._open_one._close_popup()
            except tk.TclError:
                pass
        root = self.winfo_toplevel()
        root.update_idletasks()
        row_h = 34
        width = min(max(self.sw, 220, max(text_w((UI, 10), str(v)) for v in self.values) + 58),
                    max(160, root.winfo_width() - 20))
        rx, ry = self.winfo_rootx() - root.winfo_rootx(), self.winfo_rooty() - root.winfo_rooty()
        space_below = root.winfo_height() - (ry + self.sh + 6) - 8
        space_above = ry - 6 - 8
        full = len(self.values) * row_h + 12
        below = space_below >= min(full, 160) or space_below >= space_above
        height = max(row_h + 12, min(full, space_below if below else space_above))
        x = max(8, min(rx, root.winfo_width() - width - 8))
        y = ry + self.sh + 6 if below else ry - 6 - height
        popup = tk.Canvas(root, width=width, height=height, bg=_bg_of(self), highlightthickness=0, bd=0,
                          yscrollincrement=row_h, cursor="hand2", takefocus=1)
        self.popup = popup
        RSelect._open_one = self
        selected = [self.values.index(self.value) if self.value in self.values else 0]
        top_pad = 6

        def draw(event=None):
            if not popup.winfo_exists():
                return
            popup.delete("all")
            w = width
            y0 = popup.canvasy(0)
            popup.create_polygon(rr(1, y0 + 1, w - 1, y0 + height - 1, 16), smooth=True, fill=PANEL, outline=LINE)
            popup.configure(scrollregion=(0, 0, w, max(height, len(self.values) * row_h + 2 * top_pad)))
            for i, value in enumerate(self.values):
                t = top_pad + i * row_h
                if i == selected[0]:
                    popup.create_polygon(rr(6, t + 1, w - 6, t + row_h - 1, 12), smooth=True, fill=PANEL2,
                                         outline="")
                popup.create_text(18, t + row_h / 2, text=str(value), anchor="w", fill=FG, font=(UI, 10))
                if value == self.value:
                    popup.create_text(w - 20, t + row_h / 2, text="✓", fill=ACC, font=(UI, 10))
            if full > height:      # thin scroll hint on the right
                frac0, frac1 = popup.yview()
                popup.create_line(w - 5, y0 + 8 + frac0 * (height - 16), w - 5, y0 + 8 + frac1 * (height - 16),
                                  fill=LINE, width=3, capstyle="round")

        def index_at(event):
            return max(0, min(len(self.values) - 1, int((popup.canvasy(event.y) - top_pad) // row_h)))

        def hover(event):
            i = index_at(event)
            if i != selected[0]:
                selected[0] = i
                draw()

        def choose(index):
            value = self.values[index]
            self._close_popup()
            self._pick(value)

        def move(delta):
            selected[0] = (selected[0] + delta) % len(self.values)
            t = top_pad + selected[0] * row_h
            v0 = popup.canvasy(0)
            if t < v0 or t + row_h > v0 + height:
                popup.yview_moveto(max(0.0, (t - height / 2) / max(1, full)))
            draw()
            return "break"

        def wheel(units):
            popup.yview_scroll(units, "units")
            draw()

        popup.bind("<Motion>", hover)
        popup.bind("<ButtonRelease-1>", lambda e: choose(index_at(e)))
        popup.bind("<Escape>", lambda e: self._close_popup())
        popup.bind("<Down>", lambda e: move(1))
        popup.bind("<Up>", lambda e: move(-1))
        popup.bind("<Return>", lambda e: choose(selected[0]))
        popup.wheel_target = popup
        popup.wheel_scroll = wheel

        def outside(event):
            w = event.widget
            if w is popup or w is self:
                return
            try:
                if str(w).startswith(str(popup)):
                    return
            except Exception:
                pass
            self._close_popup()
        self._global_binds = []
        for seq, fn in (("<ButtonPress-1>", outside), ("<ButtonPress-3>", outside),
                        ("<Escape>", lambda e: self._close_popup())):
            try:
                self._global_binds.append((seq, root.bind(seq, fn, add="+")))
            except tk.TclError:
                pass
        popup.place(x=x, y=y)
        tk.Misc.tkraise(popup)      # Canvas.lift() raises a drawn item, not the widget
        draw()
        if selected[0] * row_h + top_pad + row_h > height:
            move(0)
        try:
            popup.focus_set()
        except tk.TclError:
            pass

    def _pick(self, v):
        self.set(v)
        if self.command:
            self.command(v)


class Segmented(tk.Frame):
    """Row of rounded toggle buttons bound to a StringVar."""

    def __init__(self, parent, values, variable, command=None, outer=None):
        super().__init__(parent, bg=outer or _bg_of(parent))
        self.variable, self.command, self.btns = variable, command, {}
        for v in values:
            b = RButton(self, v, command=lambda v=v: self._pick(v), width=86, height=32,
                        kind="primary" if variable.get() == v else "default")
            b.pack(side="left", padx=(0, 6))
            self.btns[v] = b

    def _pick(self, v):
        self.variable.set(v)
        for k, b in self.btns.items():
            b.set_kind("primary" if k == v else "default")
        if self.command:
            self.command()


class REntry(Card):
    """Rounded text box. .entry is the real tk.Entry."""

    def __init__(self, parent, textvariable, width_px=None):
        super().__init__(parent, fill=PANEL2, edge=LINE, radius=11)
        self.entry = tk.Entry(self.body, textvariable=textvariable, bg=PANEL2, fg=FG, insertbackground=ACC,
                              relief="flat", bd=0, highlightthickness=0, font=(UI, 10), selectbackground=ACC2,
                              selectforeground="#fff")
        self.entry.pack(fill="x", padx=11, pady=8)
        self.entry.bind("<FocusIn>", lambda e: self.set_edge(ACC))
        self.entry.bind("<FocusOut>", lambda e: self.set_edge(LINE))
        if width_px:
            self.configure(width=width_px)


class RScrollbar(tk.Canvas):
    """Slim rounded scrollbar (same set()/command contract as ttk.Scrollbar)."""

    def __init__(self, parent, command, bg=BG, width=12):
        super().__init__(parent, width=width, bg=bg, highlightthickness=0, bd=0)
        self.command, self.lo, self.hi, self.drag, self.hot = command, 0.0, 1.0, None, False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._hot(True))
        self.bind("<Leave>", lambda e: self._hot(False))
        self.bind("<ButtonPress-1>", self._down)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))

    def _hot(self, flag):
        self.hot = flag
        self._draw()

    def set(self, lo, hi):
        self.lo, self.hi = float(lo), float(hi)
        self._draw()

    def _thumb(self):
        h = max(1, self.winfo_height())
        y1, y2 = self.lo * h, self.hi * h
        if y2 - y1 < 32:
            y2 = y1 + 32
        return y1, min(y2, h), h

    def _draw(self):
        self.delete("all")
        if self.hi - self.lo >= 0.999:
            return
        y1, y2, _h = self._thumb()
        w = self.winfo_width()
        self.create_polygon(rr(3, y1 + 1, w - 3, y2 - 1, (w - 6) / 2), smooth=True,
                            fill=ACC if (self.hot or self.drag) else EDGE_HOVER, outline="")

    def _down(self, e):
        y1, y2, h = self._thumb()
        if y1 <= e.y <= y2:
            self.drag = (e.y, self.lo)
        else:
            self.command("moveto", max(0.0, e.y / h - (self.hi - self.lo) / 2))
        self._draw()

    def _move(self, e):
        if self.drag:
            h = max(1, self.winfo_height())
            self.command("moveto", max(0.0, self.drag[1] + (e.y - self.drag[0]) / h))


class Bar(tk.Canvas):
    """Thin rounded progress bar."""

    def __init__(self, parent, frac, outer=None, height=8):
        super().__init__(parent, width=10, height=height, bg=outer or _bg_of(parent), highlightthickness=0, bd=0)
        self.frac, self.bar_h = max(0.0, min(1.0, frac)), height
        self.color = RED if frac > 0.9 else ("#ffb020" if frac > 0.75 else ACC)
        self.bind("<Configure>", lambda e: self._draw(e.width))

    def _draw(self, w):
        self.delete("all")
        h = self.bar_h
        self.create_polygon(rr(0, 0, w - 1, h - 1, h / 2), smooth=True, fill=PANEL2, outline="")
        if self.frac > 0:
            self.create_polygon(rr(0, 0, max(h, (w - 1) * self.frac), h - 1, h / 2), smooth=True, fill=self.color,
                                outline="")


def page_header(parent, kicker, title, sub=None):
    f = tk.Frame(parent, bg=BG)
    f.pack(fill="x", pady=(0, 12))
    left = tk.Frame(f, bg=BG)
    left.pack(side="left", fill="x", expand=True)
    tk.Label(left, text="●  " + kicker, bg=BG, fg=ACC, font=(UI, 8, "bold")).pack(anchor="w")
    tk.Label(left, text=title, bg=BG, fg=FG, font=(UI, 21, "bold")).pack(anchor="w")
    if sub:
        tk.Label(left, text=sub, bg=BG, fg=MUTED, font=(UI, 10), justify="left", wraplength=720).pack(anchor="w",
                                                                                                    pady=(2, 0))
    return f


# ------------------------------------------------------------------ help text
NAV = [("TUNE", [("Quick Presets", "✦", "slide"), ("Custom Tweaks", "⚙", "pulse"),
                 ("CTT Library", "▤", "bounce"), ("Game Presets", "◈", "glow")]),
       ("YOUR PC", [("System Info", "ⓘ", "slide")]),
       ("HELP", [("Tips", "✎", "bounce"), ("How It Works", "❖", "pulse"), ("Log", "≡", "glow")])]

HOW_STEPS = [
    ("Driver links & fullscreen",
     "Open Drivers to detect your components and find official download links automatically. Installed versions appear beside current "
     "vendor releases or AI-matched links. A release that cannot be confirmed is labeled; the vendor support page remains available. "
     "Click a driver-page or download button to open it in your browser. Refresh driver links repeats the check; results are cached for 24 hours. "
     "The top bar follows your Appearance theme. Drag it to move the window, double-click it to maximize or restore, "
     "or use the minimize, maximize and close buttons. The F11 shortcut enters or leaves fullscreen; Esc leaves fullscreen."),
    ("Auto clicker",
     "Open Auto clicker in the sidebar or Tools. Set the interval, mouse button, click cycles (0 repeats until stopped), "
     "single or double click, and optional fixed coordinates. Start / stop clicker toggles repeated clicks. "
     "F6 starts or stops clicking by default. Change the key and press Apply hotkey. Esc always stops. "
     "Save configuration stores only clicker settings in a local JSON file; Load restores them."),
    ("Start with a preset",
     "Quick Presets are ready-made bundles of tweaks for a goal: max FPS, esports, balanced, streaming, low-end PCs, "
     "laptops, privacy and cleanup, plus the Chris Titus (CTT) bundles. When RETWEAKS finishes scanning your PC it "
     "highlights the one it recommends for your hardware."),
    ("See exactly what is inside",
     "Click any preset card (or its Details button) to open the list of every tweak in the bundle. Each one has a "
     "plain-English description, a risk level, and tags that tell you if it needs a restart or cannot be undone."),
    ("Remove what you don't want",
     "Untick any tweak to leave it out. 'Run ticked' applies only the ticked ones. 'Save as my version' remembers "
     "your choices for that preset, so its RUN / Undo buttons and the command line use your edited bundle. "
     "'Reset to original' brings the default bundle back. Tick 'Also show tweaks not in this bundle' to add extras."),
    ("Run it safely",
     "Before anything changes RETWEAKS asks Windows for a System Restore point (Windows normally allows one per 24 "
     "hours, so it may skip if you already have a fresh one). Tweaks then run one at a time and every command's "
     "result is written to the Log page. If a restart is needed, RETWEAKS offers it at the end."),
    ("Undo",
     "Most tweaks have an Undo that puts Windows' defaults back. Tweaks tagged 'one-shot' (like removing apps or "
     "cleaning disks) do something that cannot be reversed by RETWEAKS - use your restore point or reinstall the app."),
    ("Custom Tweaks",
     "Every tweak RETWEAKS knows, grouped by category. Load a preset as a starting point or press 'Select Safe only', "
     "tick what you want, then Apply or Undo the selection."),
    ("CTT Library",
     "Only the Chris Titus Tech WinUtil-style tweaks (Essential, Advanced, Customize, Features, Fixes, Updates), with "
     "a search box and one-click CTT Standard / CTT Minimal loaders. Nothing else is mixed in."),
    ("Game Presets",
     "Pick a game and Low / Medium / High to see recommended in-game settings and tips, and copy them. The per-game "
     "optimizer sets Windows' graphics preference for that game's .exe to High performance, turns off fullscreen "
     "optimizations for it, and can raise its CPU priority. Undo removes those settings."),
    ("System Info",
     "A full scan of your PC: model, motherboard and BIOS, CPU, graphics and display, RAM modules, disks, network "
     "and battery. RETWEAKS uses it to recommend a preset, and 'Copy specs' puts it all on your clipboard."),
]

RISK_HELP = [("Safe", "Reversible, low impact, fine for almost every PC."),
             ("Medium", "Changes services or behaviour. Read the description first."),
             ("Advanced", "Can remove features or affect stability/security. Only if you know what it does.")]
TAG_HELP = [("reboot", "Needs a restart to fully apply."),
            ("one-shot", "Runs once and cannot be undone by RETWEAKS."),
            ("Windows 11 only", "Greyed out on Windows 10.")]

LOG_HELP = [("=====  time  APPLY  n tweaks  =====", ACC, "A run started: when, whether it is Apply or Undo, and how many tweaks."),
            ("[3/15]  APPLY: name", FG, "Progress: which tweak is running now, and its name."),
            ("[ok]", GREEN, "That command finished successfully."),
            ("[!!]", RED, "That command reported an error. Often harmless - the setting or service may not exist on "
                          "your Windows version, or was already off. The message after it says why."),
            ("== Done ==", ACC, "The run finished. Restart if RETWEAKS asks you to.")]


# ------------------------------------------------------------------ app
class Hub(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP} - Windows {'11' if IS_WIN11 else '10'} Tweaker & Game Presets")
        self.geometry("1260x820")
        self.minsize(1060, 680)
        self.configure(bg=BG)
        self.q = queue.Queue()
        self.vars = {}
        self.busy = False
        self.info = None
        self.rec_key = None
        self.bind_all("<MouseWheel>", self._wheel)
        self._build()
        self.after(100, self._poll)
        threading.Thread(target=self._load_info, daemon=True).start()

    # ------------------------------------------------------------ shared pieces
    def _wheel(self, e):
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except (KeyError, tk.TclError):
            return
        while w is not None:
            if isinstance(w, tk.Text):
                return
            target = getattr(w, "wheel_target", None)
            if target is not None:
                units = -3 if e.delta > 0 else 3
                opened = RSelect._open_one
                if opened is not None and target is not getattr(opened, "popup", None):
                    opened._close_popup()             # scrolling the page closes an open dropdown list
                if callable(getattr(target, "wheel_scroll", None)):
                    target.wheel_scroll(units)        # rt_perf: coalesced + flicker-free (owner report 2026-10-22)
                else:
                    target.yview_scroll(units, "units")
                return
            w = getattr(w, "master", None)

    def _scroll_area(self, parent):
        cv = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0, yscrollincrement=20)
        sb = RScrollbar(parent, command=cv.yview, bg=BG)
        inner = tk.Frame(cv, bg=BG)
        win = cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=(0, 0, e.width, e.height)))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(4, 0))
        cv.pack(side="left", fill="both", expand=True)
        cv.wheel_target = cv
        import rt_perf
        rt_perf.smooth_scroll(cv)
        return inner

    def set_status(self, text, color):
        self.status.config(text="●  " + text, fg=color)

    def tweak_row(self, parent, t, var, command=None, show_cat=False):
        """One tweak as a rounded card: checkbox + tags, then the description."""
        card = Card(parent, fill=PANEL, edge=LINE, radius=13)
        card.pack(fill="x", padx=(0, 12), pady=3)
        b = card.body
        top = tk.Frame(b, bg=PANEL)
        top.pack(fill="x", padx=(10, 12), pady=(9, 0))
        dis = bool(t["win11"] and not IS_WIN11)
        RCheck(top, t["name"] + ("   (Windows 11 only)" if dis else ""), var, command=command, disabled=dis,
               outer=PANEL).pack(side="left")
        pill(top, t["risk"], RISKCOL[t["risk"]], outer=PANEL).pack(side="right", padx=(6, 0))
        if t["reboot"]:
            pill(top, "reboot", ACC2, outer=PANEL).pack(side="right", padx=(6, 0))
        if not t["undo"]:
            pill(top, "one-shot", "#ffb020", outer=PANEL).pack(side="right", padx=(6, 0))
        if show_cat:
            pill(top, t["cat"], MUTED, outer=PANEL).pack(side="right", padx=(6, 0))
        d = tk.Label(b, text=t["desc"], bg=PANEL, fg=MUTED, font=(UI, 9), justify="left", anchor="w", wraplength=640)
        d.pack(fill="x", padx=(41, 14), pady=(1, 10))
        card.wrap(d, margin=58)
        return card

    # ------------------------------------------------------------ layout
    def _build(self):
        self.sidebar_slot = tk.Frame(self, bg=BG, width=244)
        self.sidebar_slot.pack(side="left", fill="y")
        self.sidebar_slot.pack_propagate(False)
        side = tk.Frame(self.sidebar_slot, bg=SIDE, width=244)
        self.sidebar = side
        side.place(x=0, y=0, width=244, relheight=1)
        side.pack_propagate(False)
        self.sidebar_divider = tk.Frame(self, bg=LINE, width=1)
        self.sidebar_divider.pack(side="left", fill="y")
        self.content = tk.Frame(self, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)

        brand = tk.Frame(side, bg=SIDE)
        brand.pack(fill="x", padx=18, pady=(22, 2))
        logo = tk.Canvas(brand, width=42, height=42, bg=SIDE, highlightthickness=0, bd=0)
        logo.pack(side="left")
        logo._feather=feather(logo,40)
        logo.create_image(21,21,image=logo._feather)
        names = tk.Frame(brand, bg=SIDE)
        names.pack(side="left", padx=12)
        tk.Label(names, text=BRAND, bg=SIDE, fg=FG, font=(UI, 16, "bold")).pack(anchor="w")
        tk.Label(names, text=f"Windows {'11' if IS_WIN11 else '10'}  |  build {win_build()}", bg=SIDE, fg=MUTED,
                 font=(UI, 8)).pack(anchor="w")

        sc = Card(side, fill=PANEL, edge=LINE, radius=13, outer=SIDE)
        sc.pack(side="bottom", fill="x", padx=14, pady=16)
        self.status = tk.Label(sc.body, text="", bg=PANEL, fg=GREEN, font=(UI, 9, "bold"), anchor="w")
        self.status.pack(fill="x", padx=12, pady=9)
        self.set_status("Ready", GREEN)

        self.nav, idx = [], 0
        for group, items in NAV:
            tk.Label(side, text=group, bg=SIDE, fg=DIM, font=(UI, 8, "bold")).pack(anchor="w", padx=22, pady=(18, 6))
            for name, icon, style in items:
                n = NavItem(side, icon, name, lambda i=idx: self.show_tab(i), style)
                n.pack(fill="x", padx=14, pady=2)
                self.nav.append(n)
                idx += 1

        self.tabs = [tk.Frame(self.content, bg=BG) for _ in self.nav]
        builders = (self._home_tab, self._tweaks_tab, self._ctt_tab, self._games_tab, self._info_tab,
                    self._tips_tab, self._how_tab, self._log_tab)
        for build, tab in zip(builders, self.tabs):
            build(tab)
        self.cur_tab = -1
        self.show_tab(0)

    def show_tab(self, i):
        if i == self.cur_tab:return
        previous = self.cur_tab
        if 0 <= self.cur_tab < len(self.tabs):
            self.tabs[self.cur_tab].pack_forget()
        self.cur_tab = i
        self.tabs[i].pack(fill="both", expand=True, padx=(26, 12), pady=(20, 12))
        if 0 <= previous < len(self.nav):self.nav[previous].set_active(False)
        self.nav[i].set_active(True)

    # ------------------------------------------------------------ quick presets (home)
    def _hero_deco(self, c, w, h):
        if w < 820:
            return
        cx, cy = w - 175, h / 2
        rmax = int(min(150, h / 2 - 8, 165))
        rings = 26
        for i in range(rings, 0, -1):
            r = rmax * i / rings
            col = mix(HERO, "#1c5b9a", ((1 - i / rings) ** 1.7) * 0.82)
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline="", tags="deco")
        px1, py1, px2, py2 = cx - 120, cy - 78, cx + 120, cy + 78
        c.create_polygon(rr(px1, py1, px2, py2, 18), smooth=True, fill="#0a1128", outline="#263372", tags="deco")
        for i, col in enumerate(("#3b4676", "#3b4676", "#3b4676")):
            c.create_oval(px1 + 16 + i * 13, py1 + 14, px1 + 24 + i * 13, py1 + 22, fill=col, outline="", tags="deco")
        c.create_text(px2 - 16, py1 + 18, text="PERF", anchor="e", fill=ACC, font=(UI, 8, "bold"), tags="deco")
        c.create_polygon(rr(px1 + 16, py1 + 38, px1 + 170, py1 + 46, 4), smooth=True, fill=ACC, outline="", tags="deco")
        c.create_polygon(rr(px1 + 16, py1 + 52, px1 + 120, py1 + 59, 3), smooth=True, fill=ACC2, outline="", tags="deco")
        for i, (txt, col) in enumerate((("FPS", GREEN), ("PING", ACC), ("CLEAN", ACC2))):
            x = px1 + 16 + i * 70
            c.create_polygon(rr(x, py1 + 78, x + 62, py1 + 102, 9), smooth=True, fill=mix("#0a1128", col, 0.14),
                             outline=mix("#0a1128", col, 0.5), tags="deco")
            c.create_text(x + 31, py1 + 90, text=txt, fill=col, font=(UI, 8, "bold"), tags="deco")
        for i, col in enumerate((GREEN, ACC, ACC2, "#3b4676")):
            c.create_oval(px2 - 80 + i * 16, py2 - 24, px2 - 70 + i * 16, py2 - 14, fill=col, outline="", tags="deco")

    def _home_tab(self, tab):
        inner = self._scroll_area(tab)
        hero = Card(inner, fill=HERO, edge=HERO_EDGE, radius=26, margin_right=340)
        hero.deco = self._hero_deco
        hero.pack(fill="x", padx=(0, 12), pady=(0, 14))
        hb = hero.body
        tk.Label(hb, text="●  RETWEAKS TUNER", bg=HERO, fg=ACC, font=(UI, 8, "bold")).pack(anchor="w", padx=22, pady=(24, 4))
        tk.Label(hb, text="Faster Windows.", bg=HERO, fg=FG, font=(UI, 34, "bold")).pack(anchor="w", padx=20)
        tk.Label(hb, text="One click away.", bg=HERO, fg=ACC, font=(UI, 34, "bold")).pack(anchor="w", padx=20)
        sub = tk.Label(hb, text="Pick a bundle, see exactly what's inside, drop what you don't want, and run it. "
                                "A restore point is made first and every preset can be undone.",
                       bg=HERO, fg=MUTED, font=(UI, 10), justify="left", wraplength=470)
        sub.pack(anchor="w", padx=22, pady=(8, 0))
        hero.wrap(sub, margin=44)
        btns = tk.Frame(hb, bg=HERO)
        btns.pack(anchor="w", padx=22, pady=(20, 26))
        RButton(btns, "Open CTT Library", lambda: self.show_tab(2), kind="hero", height=38, radius=13,
                outer=HERO).pack(side="left")
        RButton(btns, "How it works  →", lambda: self.show_tab(6), kind="ghost", height=38, radius=13,
                outer=HERO).pack(side="left", padx=10)

        rec = Card(inner, fill=HERO2, edge="#27388a", radius=18)
        rec.pack(fill="x", padx=(0, 12), pady=(0, 6))
        self.rec_btn = RButton(rec.body, "Run recommended", lambda: self.run_preset(self.rec_key, "apply"),
                               kind="primary", height=38, radius=13)
        self.rec_btn.pack(side="right", padx=16, pady=14)
        self.rec_btn.set_enabled(False)
        self.rec_lbl = tk.Label(rec.body, text="Scanning your PC for a recommendation...", bg=HERO2, fg=FG,
                                font=(UI, 10, "bold"), anchor="w", justify="left", wraplength=560)
        self.rec_lbl.pack(side="left", padx=18, pady=14, fill="x", expand=True)
        rec.wrap(self.rec_lbl, margin=230)

        tk.Label(inner, text="●  PRESETS", bg=BG, fg=ACC, font=(UI, 8, "bold")).pack(anchor="w", pady=(18, 0))
        tk.Label(inner, text="Pick your bundle", bg=BG, fg=FG, font=(UI, 18, "bold")).pack(anchor="w")
        tk.Label(inner, text="Click a preset (or Details) to see every tweak inside it and untick any you don't want.",
                 bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 8))
        self.card_titles = {}
        for key in PRESET_ORDER:
            p = PRESETS[key]
            card = Card(inner, fill=PANEL, edge=LINE, radius=16)
            card.pack(fill="x", padx=(0, 12), pady=5)
            b = card.body
            right = tk.Frame(b, bg=PANEL)
            right.pack(side="right", padx=(8, 14), pady=14)
            RButton(right, "Details", lambda k=key: self.open_preset(k), height=32, radius=10).pack(side="left", padx=3)
            RButton(right, "RUN", lambda k=key: self.run_preset(k, "apply"), kind="primary", height=32,
                    radius=10).pack(side="left", padx=3)
            if key != "clean":
                RButton(right, "Undo", lambda k=key: self.run_preset(k, "undo"), height=32, radius=10).pack(
                    side="left", padx=3)
            left = tk.Frame(b, bg=PANEL, cursor="hand2")
            left.pack(side="left", fill="x", expand=True, padx=(18, 4), pady=12)
            title = tk.Label(left, text=self._card_title(key), bg=PANEL, fg=FG, font=(UI, 11, "bold"), anchor="w",
                             cursor="hand2")
            title.pack(anchor="w")
            self.card_titles[key] = title
            desc = tk.Label(left, text=p["desc"], bg=PANEL, fg=MUTED, font=(UI, 9), justify="left", anchor="w",
                            wraplength=520, cursor="hand2")
            desc.pack(anchor="w", pady=(2, 0))
            card.wrap(desc, margin=360)
            for w in (left, title, desc):
                w.bind("<Button-1>", lambda e, k=key: self.open_preset(k))
            card.hoverable()

    def _card_title(self, key):
        mark = "   -  your edited version" if is_customized(key) else ""
        return f"{PRESETS[key]['name']}   ({len(preset_ids(key))} tweaks){mark}"

    def refresh_card(self, key):
        if key in getattr(self, "card_titles", {}):
            self.card_titles[key].config(text=self._card_title(key))

    def open_preset(self, key):
        PresetDialog(self, key)

    def run_preset(self, key, mode):
        if not key or self.busy:
            return
        ids = preset_ids(key)
        if mode == "undo":
            ids = [i for i in ids if BYID[i]["undo"]]
        name = PRESETS[key]["name"]
        verb = "Apply" if mode == "apply" else "Undo"
        extra = "\nA restore point will be created first." if mode == "apply" else ""
        if not messagebox.askyesno(APP, f"{verb} preset '{name}' ({len(ids)} tweaks)?{extra}"):
            return
        self.begin(ids, mode, True)

    # ------------------------------------------------------------ custom tweaks tab
    def _tweaks_tab(self, tab):
        # Owner request 2026-10-22: the exact-undo tweaks live on this page as a second tab. Two frames, each with
        # its own scroll area, swapped by the switch at the top; the "Exact undo" frame is filled by
        # rt_pages.tweaks_exact (built later, see rt_pages.build_pages). The last tab shown is remembered.
        switch = tk.Frame(tab, bg=BG)
        switch.pack(fill="x", pady=(0, 10))
        self.tweaks_tab_buttons = {}
        for key, label in (("all", "All tweaks"), ("exact", "Exact undo")):
            b = RButton(switch, label, command=lambda k=key: self.show_tweaks_tab(k), width=128, height=34,
                        kind="default")
            b.pack(side="left", padx=(0, 6))
            self.tweaks_tab_buttons[key] = b
        self.tweaks_all = tk.Frame(tab, bg=BG)
        self.tweaks_exact_holder = tk.Frame(tab, bg=BG)
        self.tweaks_tab_current = None
        tab = self.tweaks_all
        page_header(tab, "CUSTOM", "Build your own list",
                    "Every tweak RETWEAKS knows. Load a preset as a starting point, tick what you want, then apply or undo.")
        top = tk.Frame(tab, bg=BG)
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="Load preset", bg=BG, fg=MUTED, font=(UI, 9, "bold")).pack(side="left", padx=(0, 10))
        self.profile = RSelect(top, list(PROFILES), width=300, command=lambda v: self.load_profile())
        self.profile.pack(side="left")
        RButton(top, "Select Safe only", self.select_safe).pack(side="left", padx=(12, 4))
        RButton(top, "Clear", self.clear_sel, kind="ghost").pack(side="left", padx=4)

        bot = tk.Frame(tab, bg=BG)
        bot.pack(side="bottom", fill="x", pady=(10, 0))
        self.restore_var = tk.BooleanVar(value=True)
        RCheck(bot, "Create restore point first", self.restore_var).pack(side="left")
        RButton(bot, "Apply selected", lambda: self.start_custom("apply"), kind="primary", height=38, radius=13).pack(
            side="right", padx=(8, 12))
        RButton(bot, "Undo selected", lambda: self.start_custom("undo"), height=38, radius=13).pack(side="right")

        search_row = tk.Frame(tab, bg=BG)
        search_row.pack(fill="x", pady=(0, 8))
        self.tweak_search = tk.StringVar()
        self.tweak_search_entry = REntry(search_row, self.tweak_search)
        self.tweak_search_entry.pack(side="left", fill="x", expand=True)
        RButton(search_row, "Clear search", lambda:self.tweak_search.set(""), kind="ghost").pack(side="left", padx=8)
        self.tweak_search_count = tk.Label(search_row, bg=BG, fg=MUTED, font=(UI, 9))
        self.tweak_search_count.pack(side="right")
        inner = self._scroll_area(tab)
        self.tweak_scroll = inner.master
        def fit_filtered_region(event=None):
            cv=self.tweak_scroll
            cv.configure(scrollregion=(0,0,max(inner.winfo_width(),cv.winfo_width()),
                                       max(inner.winfo_reqheight(),cv.winfo_height())))
        inner.bind('<Configure>',fit_filtered_region,add='+')
        self.tweak_scroll.bind('<Configure>',fit_filtered_region,add='+')
        self.tweak_groups = []
        for cat in CATS:
            rows = [x for x in TWEAKS if x["cat"] == cat]
            heading = tk.Label(inner, text=f"{cat.upper()}   ({len(rows)})", bg=BG, fg=ACC, font=(UI, 9, "bold"))
            heading.pack(anchor="w", pady=(14, 4))
            group = []
            for t in rows:
                v = tk.BooleanVar(value=False)
                self.vars[t["id"]] = v
                widget = self.tweak_row(inner, t, v)
                group.append((t, widget))
            self.tweak_groups.append((heading, group))
        self.tweak_search.trace_add("write", self.filter_individual_tweaks)
        self.filter_individual_tweaks()

    def filter_individual_tweaks(self, *_):
        """Filter existing widgets; selected tweaks keep their values while hidden."""
        words = self.tweak_search.get().strip().lower().split()
        visible = []
        for heading, group in self.tweak_groups:
            heading.pack_forget()
            for _, widget in group:widget.pack_forget()
        for heading, group in self.tweak_groups:
            matches = [(t,w) for t,w in group if all(word in (t['name']+' '+t['desc']+' '+t['cat']).lower() for word in words)]
            if matches:heading.pack(anchor="w", pady=(14,4))
            for t,widget in matches:
                widget.pack(fill="x",padx=(0,12),pady=3)
                visible.append(t['id'])
        self.tweak_visible_ids = visible
        self.tweak_search_count.config(text=f"{len(visible)} / {len(TWEAKS)} tweaks")
        self.tweak_scroll.yview_moveto(0)

    def show_tweaks_tab(self, key, save=True):
        """'all' (every tweak) or 'exact' (exact-undo tweaks) on the Individual tweaks page."""
        key = "exact" if key == "exact" else "all"
        frames = {"all": self.tweaks_all, "exact": self.tweaks_exact_holder}
        if self.tweaks_tab_current != key:
            for k, f in frames.items():
                if k != key:
                    f.pack_forget()
            frames[key].pack(fill="both", expand=True)
            self.tweaks_tab_current = key
            page = (getattr(self, "rt_pages", None) or {}).get("Exact-undo tweaks")
            if key == "exact" and getattr(self, "cur_tab", None) == 1 and page is not None and hasattr(page, "on_shown"):
                try:
                    page.on_shown()
                except Exception:
                    pass
        for k, b in self.tweaks_tab_buttons.items():
            b.set_kind("primary" if k == key else "default")
        settings = getattr(self, "settings", None)
        if save and isinstance(settings, dict) and settings.get("tweaks_tab") != key:
            settings["tweaks_tab"] = key
            try:
                self.save_settings()
            except Exception:
                pass

    def load_profile(self):
        ids = PROFILES.get(self.profile.get(), [])
        for tid, v in self.vars.items():
            t = BYID[tid]
            v.set(tid in ids and not (t["win11"] and not IS_WIN11))

    def select_safe(self):
        for tid, v in self.vars.items():
            t = BYID[tid]
            v.set(t["risk"] == "Safe" and t["undo"] is not None and not (t["win11"] and not IS_WIN11))

    def clear_sel(self):
        for v in self.vars.values():
            v.set(False)

    def start_custom(self, mode):
        if self.busy:
            return
        ids = [i for i, v in self.vars.items() if v.get()]
        if mode == "undo":
            ids = [i for i in ids if BYID[i]["undo"]]
        if not ids:
            messagebox.showinfo(APP, "Select at least one tweak.")
            return
        if not messagebox.askyesno(APP, f"{'Apply' if mode == 'apply' else 'Undo'} {len(ids)} tweak(s)?"):
            return
        self.begin(ids, mode, self.restore_var.get())

    # ------------------------------------------------------------ CTT library tab
    def _ctt_tab(self, tab):
        page_header(tab, "CTT LIBRARY", "Chris Titus WinUtil tweaks",
                    "Only CTT-style tweaks, nothing else mixed in. Search, load a CTT bundle, or tick your own.")
        row = tk.Frame(tab, bg=BG)
        row.pack(fill="x", pady=(0, 8))
        self.ctt_search = tk.StringVar()
        se = REntry(row, self.ctt_search, width_px=250)
        se.pack(side="left")
        RButton(row, "CTT Standard", lambda: self.ctt_load("ctt_standard")).pack(side="left", padx=(12, 4))
        RButton(row, "CTT Minimal", lambda: self.ctt_load("ctt_minimal")).pack(side="left", padx=4)
        RButton(row, "Safe only", self.ctt_safe).pack(side="left", padx=4)
        RButton(row, "Clear", self.ctt_clear, kind="ghost").pack(side="left", padx=4)

        bot = tk.Frame(tab, bg=BG)
        bot.pack(side="bottom", fill="x", pady=(10, 0))
        self.ctt_restore = tk.BooleanVar(value=True)
        RCheck(bot, "Create restore point first", self.ctt_restore).pack(side="left")
        RButton(bot, "Apply selected", lambda: self.start_ctt("apply"), kind="primary", height=38, radius=13).pack(
            side="right", padx=(8, 12))
        RButton(bot, "Undo selected", lambda: self.start_ctt("undo"), height=38, radius=13).pack(side="right")

        inner = self._scroll_area(tab)
        self.ctt_vars, self.ctt_items, self.ctt_heads = {}, [], {}
        for cat in CTT_CATS:
            rows = [x for x in TWEAKS if ctt_cat(x) == cat]
            self.ctt_heads[cat] = tk.Label(inner, text=f"{cat.upper()}   ({len(rows)})", bg=BG, fg=ACC,
                                           font=(UI, 9, "bold"))
            for t in rows:
                v = tk.BooleanVar(value=False)
                self.ctt_vars[t["id"]] = v
                card = self.tweak_row(inner, t, v)
                card.pack_forget()
                self.ctt_items.append(dict(cat=cat, id=t["id"], row=card,
                                           text=(t["name"] + " " + t["desc"] + " " + t["id"]).lower()))
        self.ctt_search.trace_add("write", lambda *a: self._ctt_filter())
        self._ctt_filter()

    def _ctt_filter(self):
        q = self.ctt_search.get().lower().strip()
        for h in self.ctt_heads.values():
            h.pack_forget()
        for i in self.ctt_items:
            i["row"].pack_forget()
        for cat in CTT_CATS:
            shown = [i for i in self.ctt_items if i["cat"] == cat and q in i["text"]]
            if not shown:
                continue
            self.ctt_heads[cat].pack(anchor="w", pady=(14, 4))
            for i in shown:
                i["row"].pack(fill="x", padx=(0, 12), pady=3)

    def ctt_load(self, key):
        ids = preset_ids(key)
        for tid, v in self.ctt_vars.items():
            v.set(tid in ids)

    def ctt_safe(self):
        for tid, v in self.ctt_vars.items():
            t = BYID[tid]
            v.set(t["risk"] == "Safe" and t["undo"] is not None and not (t["win11"] and not IS_WIN11))

    def ctt_clear(self):
        for v in self.ctt_vars.values():
            v.set(False)

    def start_ctt(self, mode):
        if self.busy:
            return
        ids = [i for i, v in self.ctt_vars.items() if v.get()]
        if mode == "undo":
            ids = [i for i in ids if BYID[i]["undo"]]
        if not ids:
            messagebox.showinfo(APP, "Select at least one tweak.")
            return
        if not messagebox.askyesno(APP, f"{'Apply' if mode == 'apply' else 'Undo'} {len(ids)} CTT tweak(s)?"):
            return
        self.begin(ids, mode, self.ctt_restore.get())

    # ------------------------------------------------------------ running
    def begin(self, ids, mode, restore):
        if os.name != "nt":
            messagebox.showerror(APP, "This tool only runs on Windows.")
            return
        self.busy = True
        self.set_status("Working...", ACC)
        threading.Thread(target=self._worker, args=(ids, mode, restore), daemon=True).start()

    def _worker(self, ids, mode, restore):
        log = lambda m: self.q.put(("log", m))
        log(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {mode.upper()} {len(ids)} tweaks =====")
        reboot = apply_ids(ids, mode, log, restore)
        self.q.put(("done", reboot))

    def _load_info(self):
        info = sysinfo()
        key, why, tips = recommend(info)
        self.q.put(("info", (info, key, why, tips)))

    def _poll(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "log":
                    self.log_write(data)
                elif kind == "done":
                    self.busy = False
                    self.set_status("Finished - see Log", GREEN)
                    if data and messagebox.askyesno(APP, "Done! A restart is needed to finish applying.\nRestart now?"):
                        os.system("shutdown /r /t 10")
                    elif not data:
                        messagebox.showinfo(APP, "Done! Sign out/in if something doesn't apply right away.")
                elif kind == "info":
                    self._show_info(*data)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _show_info(self, info, key, why, tips):
        self.info, self.rec_key = info, key
        self.rec_lbl.config(text=f"Recommended for your PC:  {PRESETS[key]['name']}\n{why}")
        self.rec_btn.set_enabled(True)
        self._render_info(info)
        self.for_you.config(state="normal")
        self.for_you.delete("1.0", "end")
        self.for_you.insert("end", "FOR YOUR PC\n", "h")
        for t in tips or ["No special issues detected - the general tips below still apply."]:
            self.for_you.insert("end", "  -  " + t + "\n")
        self.for_you.config(state="disabled")

    # ------------------------------------------------------------ games
    def _games_tab(self, tab):
        page_header(tab, "GAME PRESETS", "Settings that fit your game",
                    "Pick a game and a quality level for recommended in-game settings, then optionally tune Windows for it.")
        inner = self._scroll_area(tab)
        top = tk.Frame(inner, bg=BG)
        top.pack(fill="x", padx=(0, 12), pady=(0, 10))
        tk.Label(top, text="Game", bg=BG, fg=MUTED, font=(UI, 9, "bold")).pack(side="left", padx=(0, 10))
        self.game = RSelect(top, list(GAMES), width=270, command=lambda v: self.show_game())
        self.game.pack(side="left")
        self.preset = tk.StringVar(value="Medium")
        seg = Segmented(top, ("Low", "Medium", "High"), self.preset, command=self.show_game)
        seg.pack(side="left", padx=18)
        RButton(top, "Copy settings", self.copy_game).pack(side="right")
        self.preset_lbl = tk.Label(inner, text="", bg=BG, fg=MUTED, anchor="w", justify="left", wraplength=800)
        self.preset_lbl.pack(fill="x", pady=(0, 8))

        tcard = Card(inner, fill=PANEL, edge=LINE, radius=16)
        tcard.pack(fill="x", padx=(0, 12), pady=4)
        from tkinter import ttk
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=30, borderwidth=0,
                    font=(UI, 10))
        s.configure("Treeview.Heading", background=PANEL2, foreground=ACC, relief="flat", font=(UI, 10, "bold"),
                    borderwidth=0)
        s.map("Treeview", background=[("selected", ACC2)], foreground=[("selected", "#ffffff")])
        s.map("Treeview.Heading", background=[("active", PANEL2)])
        self.tree = ttk.Treeview(tcard.body, columns=("s", "v"), show="headings", height=11)
        self.tree.heading("s", text="Setting")
        self.tree.heading("v", text="Recommended value")
        self.tree.column("s", width=300)
        self.tree.column("v", width=520)
        self.tree.pack(fill="x", padx=14, pady=14)

        tipc = Card(inner, fill=PANEL, edge=LINE, radius=16)
        tipc.pack(fill="x", padx=(0, 12), pady=8)
        self.tips_lbl = tk.Label(tipc.body, text="", bg=PANEL, fg=FG, font=(UI, 10), anchor="w", justify="left",
                                 wraplength=780)
        self.tips_lbl.pack(fill="x", padx=18, pady=14)
        tipc.wrap(self.tips_lbl, margin=40)

        opt = Card(inner, fill=PANEL, edge=LINE, radius=16)
        opt.pack(fill="x", padx=(0, 12), pady=(4, 10))
        tk.Label(opt.body, text="PER-GAME WINDOWS OPTIMIZER", bg=PANEL, fg=ACC, font=(UI, 9, "bold")).pack(
            anchor="w", padx=18, pady=(14, 2))
        tk.Label(opt.body, text="Sets this game's graphics preference to High performance and turns off fullscreen "
                                "optimizations for it. Optional: raise its CPU priority.",
                 bg=PANEL, fg=MUTED, font=(UI, 9), justify="left", wraplength=760).pack(anchor="w", padx=18)
        orow = tk.Frame(opt.body, bg=PANEL)
        orow.pack(fill="x", padx=18, pady=(10, 16))
        self.exe_path = tk.StringVar()
        ee = REntry(orow, self.exe_path)
        ee.pack(side="left", fill="x", expand=True)
        RButton(orow, "Browse .exe", self.browse_exe).pack(side="left", padx=(10, 6))
        self.cpu_high = tk.BooleanVar(value=False)
        RCheck(orow, "High CPU priority", self.cpu_high, outer=PANEL).pack(side="left", padx=6)
        RButton(orow, "Optimize", lambda: self.opt_game(True), kind="primary").pack(side="left", padx=(6, 4))
        RButton(orow, "Undo", lambda: self.opt_game(False)).pack(side="left")
        self.show_game()

    def show_game(self):
        g = GAMES[self.game.get()]
        idx = {"Low": 1, "Medium": 2, "High": 3}[self.preset.get()]
        self.tree.delete(*self.tree.get_children())
        for row in g["settings"]:
            self.tree.insert("", "end", values=(row[0], row[idx]))
        self.preset_lbl.config(text=PRESET_INFO[self.preset.get()])
        extra = "\n".join("-  " + t for t in g["tips"])
        if g.get("launch"):
            extra += f"\n-  Suggested launch options: {g['launch']}"
        self.tips_lbl.config(text=extra + "\n\n" + GENERIC_GPU_TIPS)
        self.current_text = f"{self.game.get()} - {self.preset.get()} preset\n" + "\n".join(
            f"{r[0]}: {r[idx]}" for r in g["settings"])

    def copy_game(self):
        self.clipboard_clear()
        self.clipboard_append(self.current_text)
        messagebox.showinfo(APP, "Settings copied to clipboard.")

    def browse_exe(self):
        p = filedialog.askopenfilename(title="Select the game's .exe", filetypes=[("Executable", "*.exe")])
        if p:
            self.exe_path.set(os.path.normpath(p))

    def opt_game(self, apply):
        path = self.exe_path.get().strip().strip('"')
        if not path or not path.lower().endswith(".exe"):
            messagebox.showinfo(APP, "Browse to the game's .exe first.")
            return
        exe = os.path.basename(path)
        gpu = r"HKCU\Software\Microsoft\DirectX\UserGpuPreferences"
        fso = r"HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
        ifeo = rf"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{exe}\PerfOptions"
        if apply:
            cmds = [reg(gpu, path, "GpuPreference=2;", "REG_SZ"),
                    reg(fso, path, "~ DISABLEDXMAXIMIZEDWINDOWEDMODE", "REG_SZ")]
            if self.cpu_high.get():
                cmds.append(reg(ifeo, "CpuPriorityClass", 3))
        else:
            cmds = [regdel(gpu, path), regdel(fso, path), ("cmd", f'reg delete "{ifeo}" /f')]
        self.log_write(f"\n>> Game optimizer ({'apply' if apply else 'undo'}): {exe}")
        for kind, c in cmds:
            rc, out = run(kind, c)
            self.log_write(("   [ok] " if rc == 0 else "   [!!] ") + (out[:160] or c[:80]))
        messagebox.showinfo(APP, "Done. Restart the game for it to take effect.")

    # ------------------------------------------------------------ system info
    def _info_tab(self, tab):
        hdr = page_header(tab, "YOUR PC", "Device specifications",
                          "Everything RETWEAKS found about this computer. It also drives the recommended preset.")
        br = tk.Frame(hdr, bg=BG)
        br.pack(side="right", anchor="n")
        RButton(br, "Copy specs", self.copy_info).pack(side="left", padx=4)
        RButton(br, "Rescan", self.rescan, kind="primary").pack(side="left", padx=(4, 12))
        inner = self._scroll_area(tab)
        self.info_host = tk.Frame(inner, bg=BG)
        self.info_host.pack(fill="x")
        self._info_placeholder("Scanning your PC...")

    def _info_placeholder(self, text):
        for w in self.info_host.winfo_children():
            w.destroy()
        c = Card(self.info_host, fill=PANEL, edge=LINE, radius=16)
        c.pack(fill="x", padx=(0, 12), pady=4)
        tk.Label(c.body, text=text, bg=PANEL, fg=MUTED, font=(UI, 11)).pack(anchor="w", padx=20, pady=20)

    def rescan(self):
        self._info_placeholder("Scanning your PC...")
        threading.Thread(target=self._load_info, daemon=True).start()

    def _render_info(self, info):
        host = self.info_host
        for w in host.winfo_children():
            w.destroy()
        title, subtitle = info_headline(info)
        head = Card(host, fill=HERO, edge=HERO_EDGE, radius=22)
        head.pack(fill="x", padx=(0, 12), pady=(0, 10))
        tk.Label(head.body, text="●  THIS PC", bg=HERO, fg=ACC, font=(UI, 8, "bold")).pack(anchor="w", padx=22,
                                                                                               pady=(18, 2))
        tk.Label(head.body, text=title, bg=HERO, fg=FG, font=(UI, 20, "bold"), anchor="w", justify="left").pack(
            anchor="w", padx=22)
        sl = tk.Label(head.body, text=subtitle or "-", bg=HERO, fg=MUTED, font=(UI, 10), justify="left",
                      anchor="w", wraplength=700)
        sl.pack(anchor="w", padx=22, pady=(2, 18))
        head.wrap(sl, margin=44)

        cols = tk.Frame(host, bg=BG)
        cols.pack(fill="x", padx=(0, 12))
        cols.grid_columnconfigure(0, weight=1, uniform="c")
        cols.grid_columnconfigure(1, weight=1, uniform="c")
        left, right = tk.Frame(cols, bg=BG), tk.Frame(cols, bg=BG)
        left.grid(row=0, column=0, sticky="new", padx=(0, 6))
        right.grid(row=0, column=1, sticky="new", padx=(6, 0))
        load = [0, 0]
        for sec_title, rows in info_sections(info):
            i = 0 if load[0] <= load[1] else 1
            load[i] += len(rows) + 3
            self._info_card((left, right)[i], sec_title, rows)

    def _info_card(self, parent, title, rows):
        card = Card(parent, fill=PANEL, edge=LINE, radius=18)
        card.pack(fill="x", pady=6)
        b = card.body
        tk.Label(b, text=title.upper(), bg=PANEL, fg=ACC, font=(UI, 9, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        tk.Frame(b, bg=LINE, height=1).pack(fill="x", padx=18)
        grid = tk.Frame(b, bg=PANEL)
        grid.pack(fill="x", padx=18, pady=(8, 16))
        grid.grid_columnconfigure(1, weight=1)
        r = 0
        for row in rows:
            label, value = row[0], row[1]
            tk.Label(grid, text=label, bg=PANEL, fg=MUTED, font=(UI, 9), anchor="nw", justify="left", width=13).grid(
                row=r, column=0, sticky="nw", pady=3, padx=(0, 10))
            v = tk.Label(grid, text=value or "-", bg=PANEL, fg=FG, font=(UI, 10), anchor="w", justify="left",
                         wraplength=230)
            v.grid(row=r, column=1, sticky="nw", pady=3)
            card.wrap(v, margin=160)
            r += 1
            if len(row) > 2 and row[2] is not None:
                Bar(grid, row[2]).grid(row=r, column=1, sticky="ew", pady=(0, 6))
                r += 1

    def copy_info(self):
        if not self.info:
            # the hardware scan hasn't finished (or failed): say so instead of silently doing nothing
            messagebox.showinfo(APP, "Your PC specs are still being read. Try again in a few seconds, or click "
                                     "Rescan if this keeps happening.")
            return
        t, s = info_headline(self.info)
        lines = [t, s, ""]
        for title, rows in info_sections(self.info):
            lines.append(f"[{title}]")
            for r in rows:
                lines.append(f"  {r[0].strip()}: {r[1]}")
            lines.append("")
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        messagebox.showinfo(APP, "System specs copied to the clipboard.")

    # ------------------------------------------------------------ tips
    def _tips_tab(self, tab):
        page_header(tab, "TIPS", "Get more out of your PC",
                    "Personalised notes for your hardware first, then general advice.")
        top = Card(tab, fill=HERO, edge=HERO_EDGE, radius=18)
        top.pack(fill="x", pady=(0, 10))
        self.for_you = tk.Text(top.body, bg=HERO, fg=FG, relief="flat", bd=0, highlightthickness=0, font=(UI, 10),
                               height=7, wrap="word", padx=8, pady=4, spacing1=2, cursor="arrow")
        self.for_you.tag_configure("h", foreground=ACC, font=(UI, 9, "bold"), spacing3=4)
        self.for_you.pack(fill="x", padx=14, pady=12)
        self.for_you.insert("end", "FOR YOUR PC\n", "h")
        self.for_you.insert("end", "  Scanning...\n")
        self.for_you.config(state="disabled")

        card = Card(tab, fill=PANEL, edge=LINE, radius=18, elastic=True)
        card.pack(fill="both", expand=True)
        wrapf = tk.Frame(card.body, bg=PANEL)
        wrapf.pack(fill="both", expand=True, padx=12, pady=12)
        box = tk.Text(wrapf, bg=PANEL, fg=FG, relief="flat", bd=0, highlightthickness=0, font=(UI, 10), wrap="word",
                      padx=10, pady=4, spacing1=2, cursor="arrow", selectbackground=ACC2)
        sb = RScrollbar(wrapf, command=box.yview, bg=PANEL)
        box.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(6, 0))
        box.pack(side="left", fill="both", expand=True)
        box.tag_configure("h", foreground=ACC, font=(UI, 11, "bold"), spacing1=14, spacing3=4)
        for cat, items in TIPS.items():
            box.insert("end", cat.upper() + "\n", "h")
            for t in items:
                box.insert("end", "  -  " + t + "\n")
        box.config(state="disabled")

    # ------------------------------------------------------------ how it works
    def _how_tab(self, tab):
        page_header(tab, "GUIDE", "How everything works",
                    "A quick tour of every page, what the tags mean, and how RETWEAKS keeps your PC safe.")
        inner = self._scroll_area(tab)
        self.help_ai_buttons = []
        for n, (title, body) in enumerate(HOW_STEPS, 1):
            card = Card(inner, fill=PANEL, edge=LINE, radius=18)
            card.pack(fill="x", padx=(0, 12), pady=5)
            row = tk.Frame(card.body, bg=PANEL)
            row.pack(fill="x", padx=18, pady=16)
            badge = tk.Canvas(row, width=40, height=40, bg=PANEL, highlightthickness=0, bd=0)
            badge.pack(side="left", anchor="n")
            badge.create_polygon(rr(1, 1, 39, 39, 13), smooth=True, fill=mix(PANEL, ACC, 0.14), outline=mix(PANEL, ACC, 0.5))
            badge.create_text(20, 20, text=str(n), fill=ACC, font=(UI, 13, "bold"))
            txt = tk.Frame(row, bg=PANEL)
            txt.pack(side="left", fill="x", expand=True, padx=(16, 0))
            heading = tk.Frame(txt, bg=PANEL)
            heading.pack(fill="x")
            ask = RButton(heading, "Ask AI for more help",
                          lambda t=title, b=body: self.ask_guide_ai(t, b), height=32)
            ask.pack(side="right", padx=(12, 0))
            self.help_ai_buttons.append(ask)
            title_label = tk.Label(heading, text=title, bg=PANEL, fg=FG, font=(UI, 12, "bold"),
                                   anchor="w", justify="left", wraplength=350)
            title_label.pack(side="left", fill="x", expand=True)
            card.wrap(title_label, margin=350)
            bl = tk.Label(txt, text=body, bg=PANEL, fg=MUTED, font=(UI, 10), justify="left", anchor="w", wraplength=700)
            bl.pack(anchor="w", pady=(4, 0))
            card.wrap(bl, margin=110)

        tags = Card(inner, fill=PANEL, edge=LINE, radius=18)
        tags.pack(fill="x", padx=(0, 12), pady=5)
        tb = tags.body
        tk.Label(tb, text="READING THE TAGS", bg=PANEL, fg=ACC, font=(UI, 9, "bold")).pack(anchor="w", padx=18, pady=(16, 6))
        for name, desc in RISK_HELP:
            r = tk.Frame(tb, bg=PANEL)
            r.pack(fill="x", padx=18, pady=4)
            pill(r, name, RISKCOL[name], outer=PANEL).pack(side="left")
            l = tk.Label(r, text=desc, bg=PANEL, fg=MUTED, font=(UI, 10), anchor="w", justify="left", wraplength=620)
            l.pack(side="left", padx=12)
            tags.wrap(l, margin=140)
        for name, desc in TAG_HELP:
            r = tk.Frame(tb, bg=PANEL)
            r.pack(fill="x", padx=18, pady=4)
            pill(r, name, ACC2 if name == "reboot" else ("#ffb020" if name == "one-shot" else MUTED), outer=PANEL).pack(
                side="left")
            tk.Label(r, text=desc, bg=PANEL, fg=MUTED, font=(UI, 10), anchor="w").pack(side="left", padx=12)
        tk.Frame(tb, bg=PANEL, height=12).pack()

        cli = Card(inner, fill=PANEL, edge=LINE, radius=18)
        cli.pack(fill="x", padx=(0, 12), pady=5)
        cb = cli.body
        tk.Label(cb, text="COMMAND LINE & SAVED FILES", bg=PANEL, fg=ACC, font=(UI, 9, "bold")).pack(anchor="w", padx=18,
                                                                                                    pady=(16, 6))
        code = Card(cb, fill="#080b17", edge=LINE, radius=12)
        code.pack(fill="x", padx=18, pady=(0, 8))
        tk.Label(code.body, text="RETWEAKS.exe --list                  show every preset name\n"
                                 "RETWEAKS.exe --preset maxfps         apply a preset with no window\n"
                                 "RETWEAKS.exe --preset maxfps --undo  undo it",
                 bg="#080b17", fg=GREEN, font=("Consolas", 10), justify="left", anchor="w").pack(anchor="w", padx=14,
                                                                                               pady=12)
        nl = tk.Label(cb, text="Your edited presets are saved to %APPDATA%\\RETWEAKS\\custom_presets.json. Silent "
                               "command-line runs write RETWEAKS_log.txt to your Desktop. RETWEAKS asks for administrator "
                               "rights on start because most tweaks change system settings.",
                      bg=PANEL, fg=MUTED, font=(UI, 10), justify="left", anchor="w", wraplength=700)
        nl.pack(anchor="w", padx=18, pady=(0, 16))
        cli.wrap(nl, margin=50)

        safe = Card(inner, fill=HERO2, edge="#27388a", radius=18)
        safe.pack(fill="x", padx=(0, 12), pady=(5, 10))
        sl = tk.Label(safe.body, text="Stay safe: a restore point is not a backup. Back up anything important before "
                                      "big changes, start with Safe-tagged tweaks, and read a tweak's description if "
                                      "you are unsure. Settings can behave differently between Windows versions.",
                      bg=HERO2, fg=FG, font=(UI, 10), justify="left", anchor="w", wraplength=700)
        sl.pack(anchor="w", padx=18, pady=16)
        safe.wrap(sl, margin=50)

    # ------------------------------------------------------------ log
    def _log_tab(self, tab):
        page_header(tab, "ACTIVITY", "Log", "Everything RETWEAKS runs is written here, so you can see exactly what changed.")
        guide = Card(tab, fill=PANEL, edge=LINE, radius=18)
        guide.pack(fill="x", pady=(0, 10))
        gb = guide.body
        tk.Label(gb, text="HOW TO READ THIS LOG", bg=PANEL, fg=ACC, font=(UI, 9, "bold")).pack(anchor="w", padx=18,
                                                                                                pady=(14, 4))
        for sample, col, meaning in LOG_HELP:
            r = tk.Frame(gb, bg=PANEL)
            r.pack(fill="x", padx=18, pady=3)
            tk.Label(r, text=sample, bg=PANEL, fg=col, font=("Consolas", 9, "bold"), width=34, anchor="w").pack(
                side="left")
            l = tk.Label(r, text=meaning, bg=PANEL, fg=MUTED, font=(UI, 9), anchor="w", justify="left", wraplength=480)
            l.pack(side="left", fill="x", expand=True)
            guide.wrap(l, margin=300)
        tk.Frame(gb, bg=PANEL, height=10).pack()

        bar = tk.Frame(tab, bg=BG)
        bar.pack(fill="x", pady=(0, 8))
        RButton(bar, "Copy log", self.copy_log).pack(side="left", padx=(0, 6))
        RButton(bar, "Save log...", self.save_log).pack(side="left", padx=6)
        RButton(bar, "Clear", self.clear_log, kind="ghost").pack(side="left", padx=6)
        tk.Label(bar, text="The log is cleared when you close RETWEAKS - save it if you want to keep it.", bg=BG,
                 fg=DIM, font=(UI, 9)).pack(side="right")

        card = Card(tab, fill="#080b17", edge=LINE, radius=18, elastic=True)
        card.pack(fill="both", expand=True)
        wrapf = tk.Frame(card.body, bg="#080b17")
        wrapf.pack(fill="both", expand=True, padx=12, pady=12)
        self.logbox = tk.Text(wrapf, bg="#080b17", fg=FG, relief="flat", bd=0, highlightthickness=0,
                              font=("Consolas", 10), wrap="word", padx=8, pady=4, insertbackground=ACC,
                              selectbackground=ACC2, spacing1=1)
        sb = RScrollbar(wrapf, command=self.logbox.yview, bg="#080b17")
        self.logbox.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(6, 0))
        self.logbox.pack(side="left", fill="both", expand=True)
        self.logbox.tag_configure("head", foreground=ACC, font=("Consolas", 10, "bold"), spacing1=6)
        self.logbox.tag_configure("step", foreground=FG, font=("Consolas", 10, "bold"))
        self.logbox.tag_configure("ok", foreground=GREEN)
        self.logbox.tag_configure("bad", foreground=RED)
        self.logbox.tag_configure("plain", foreground=MUTED)
        self.logbox.config(state="disabled")
        self.log_write("Log ready. Everything RETWEAKS runs shows up here.")

    def log_write(self, text):
        box = self.logbox
        box.config(state="normal")
        for line in str(text).split("\n"):
            s = line.strip()
            if s.startswith("=====") or s.startswith("== "):
                tag = "head"
            elif re.match(r"^\[\d+/\d+\]", s) or s.startswith(">>"):
                tag = "step"
            elif s.startswith("[ok]"):
                tag = "ok"
            elif s.startswith("[!!]"):
                tag = "bad"
            else:
                tag = "plain"
            box.insert("end", line + "\n", tag)
        box.see("end")
        box.config(state="disabled")

    def copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.logbox.get("1.0", "end"))
        messagebox.showinfo(APP, "Log copied to the clipboard.")

    def save_log(self):
        p = filedialog.asksaveasfilename(title="Save log", defaultextension=".txt", initialfile="RETWEAKS_log.txt",
                                         filetypes=[("Text file", "*.txt")])
        if p:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(self.logbox.get("1.0", "end"))
            except OSError as e:
                messagebox.showerror(APP, f"Could not save the log:\n{e}")

    def clear_log(self):
        self.logbox.config(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.config(state="disabled")
        self.log_write("Log cleared.")


class PresetDialog(tk.Toplevel):
    """Shows what's inside a preset. Untick tweaks to drop them from the bundle, then run or save your version."""

    def __init__(self, hub, key):
        super().__init__(hub)
        self.hub, self.key = hub, key
        self.title(f"{PRESETS[key]['name']} - what's inside")
        self.geometry(f"920x740+{hub.winfo_rootx() + 70}+{hub.winfo_rooty() + 30}")
        self.minsize(720, 520)
        self.configure(bg=BG)
        self.transient(hub)
        self.bind("<Escape>", lambda e: self.destroy())
        self.show_all = tk.BooleanVar(value=False)
        self._load_state()

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=22, pady=(18, 14))
        tk.Label(wrap, text="●  PRESET", bg=BG, fg=ACC, font=(UI, 8, "bold")).pack(anchor="w")
        tk.Label(wrap, text=PRESETS[key]["name"], bg=BG, fg=FG, font=(UI, 21, "bold")).pack(anchor="w")
        tk.Label(wrap, text=PRESETS[key]["desc"], bg=BG, fg=MUTED, wraplength=820, justify="left").pack(anchor="w",
                                                                                                    pady=(2, 10))
        bar = tk.Frame(wrap, bg=BG)
        bar.pack(fill="x", pady=(0, 8))
        RButton(bar, "Tick all", lambda: self._set_shown(lambda t: True), height=32, radius=10).pack(side="left", padx=(0, 6))
        RButton(bar, "Untick all", lambda: self._set_shown(lambda t: False), height=32, radius=10).pack(side="left", padx=6)
        RButton(bar, "Safe only", lambda: self._set_shown(lambda t: t["risk"] == "Safe"), height=32, radius=10).pack(
            side="left", padx=6)
        RCheck(bar, "Also show tweaks not in this bundle", self.show_all, command=self._render).pack(side="left", padx=14)
        self.count = tk.Label(bar, text="", bg=BG, fg=ACC, font=(UI, 10, "bold"))
        self.count.pack(side="right", padx=6)

        bot = tk.Frame(wrap, bg=BG)
        bot.pack(side="bottom", fill="x", pady=(12, 0))
        RButton(bot, "Save as my version", self._save, height=36, radius=12).pack(side="left", padx=(0, 6))
        RButton(bot, "Reset to original", self._reset, kind="ghost", height=36, radius=12).pack(side="left", padx=6)
        RButton(bot, "Close", self.destroy, kind="ghost", height=36, radius=12).pack(side="right", padx=(6, 0))
        RButton(bot, "Undo ticked", lambda: self._run("undo"), height=36, radius=12).pack(side="right", padx=6)
        RButton(bot, "Run ticked", lambda: self._run("apply"), kind="primary", height=36, radius=12).pack(side="right",
                                                                                                         padx=6)
        mid = tk.Frame(wrap, bg=BG)
        mid.pack(fill="both", expand=True)
        self.inner = hub._scroll_area(mid)
        self._render()

    def _ok(self, tid):
        t = BYID[tid]
        return not (t["win11"] and not IS_WIN11)

    def _load_state(self):
        self.orig = list(CUSTOM.get(self.key, PRESETS[self.key]["ids"]))
        self.vars = {t["id"]: tk.BooleanVar(value=(t["id"] in self.orig and self._ok(t["id"]))) for t in TWEAKS}

    def _order(self):
        return [i for i in self.orig if self._ok(i)] + [t["id"] for t in TWEAKS if t["id"] not in self.orig]

    def _shown(self):
        base = [i for i in self.orig if self._ok(i)]
        return base + ([t["id"] for t in TWEAKS if t["id"] not in self.orig] if self.show_all.get() else [])

    def _ticked(self):
        return [i for i in self._order() if self.vars[i].get()]

    def _update_count(self):
        self.count.config(text=f"{len(self._ticked())} tweaks ticked")

    def _set_shown(self, pred):
        for tid in self._shown():
            if self._ok(tid):
                self.vars[tid].set(bool(pred(BYID[tid])))
        self._update_count()

    def _render(self):
        for w in self.inner.winfo_children():
            w.destroy()
        for tid in [i for i in self.orig if self._ok(i)]:
            self.hub.tweak_row(self.inner, BYID[tid], self.vars[tid], command=self._update_count, show_cat=True)
        if self.show_all.get():
            tk.Label(self.inner, text="NOT IN THIS BUNDLE  (tick to add)", bg=BG, fg=ACC, font=(UI, 9, "bold")).pack(
                anchor="w", pady=(16, 4))
            for t in TWEAKS:
                if t["id"] not in self.orig:
                    self.hub.tweak_row(self.inner, t, self.vars[t["id"]], command=self._update_count, show_cat=True)
        self._update_count()

    def _run(self, mode):
        if self.hub.busy:
            messagebox.showinfo(APP, "RETWEAKS is already working. Wait for it to finish.", parent=self)
            return
        ids = self._ticked()
        if mode == "undo":
            ids = [i for i in ids if BYID[i]["undo"]]
        if not ids:
            messagebox.showinfo(APP, "Tick at least one tweak.", parent=self)
            return
        extra = "\nA restore point will be created first." if mode == "apply" else ""
        if not messagebox.askyesno(APP, f"{'Apply' if mode == 'apply' else 'Undo'} {len(ids)} tweak(s) from "
                                        f"'{PRESETS[self.key]['name']}'?{extra}", parent=self):
            return
        self.destroy()
        self.hub.begin(ids, mode, True)

    def _save(self):
        ticked = set(self._ticked())
        hidden = {i for i in self.orig if not self._ok(i)}  # Win-11-only items stay in the bundle on Win 10
        final = [i for i in self.orig if i in ticked or i in hidden]
        final += [i for i in self._order() if i in ticked and i not in self.orig]
        ok = set_custom(self.key, final)
        self.hub.refresh_card(self.key)
        if ok:
            messagebox.showinfo(APP, "Saved. This preset's RUN / Undo buttons and the --preset command line now use "
                                     "your version.", parent=self)
        else:
            messagebox.showwarning(APP, "Could not write the settings file, so the change only lasts until you close "
                                        "RETWEAKS.", parent=self)
        self._load_state()
        self._render()

    def _reset(self):
        reset_custom(self.key)
        self.hub.refresh_card(self.key)
        self._load_state()
        self._render()


def headless(argv):
    """Silent run-and-done mode for shortcuts / scripts."""
    if "--list" in argv:
        for k in PRESET_ORDER:
            print(f"{k:10} {PRESETS[k]['name']}")
        return
    key = argv[argv.index("--preset") + 1] if argv.index("--preset") + 1 < len(argv) else ""
    if key not in PRESETS:
        print("Unknown preset. Use --list")
        return
    mode = "undo" if "--undo" in argv else "apply"
    ids = preset_ids(key)
    logfile = os.path.join(os.path.expanduser("~"), "Desktop", "RETWEAKS_log.txt")

    def log(m):
        print(m)
        try:
            with open(logfile, "a", encoding="utf-8") as f:
                f.write(m + "\n")
        except Exception:
            pass

    apply_ids(ids, mode, log, restore=True)
    log("Restart your PC to finish applying.")


if __name__ == "__main__":
    if "--rt-splash" in sys.argv:                 # the v1.6 startup screen's own process (rt_splash_qt)
        import rt_splash_qt
        sys.exit(rt_splash_qt.main())
    from hubplus import install
    install(globals())
    if '--verify-browser' in sys.argv:
        from browser_check import main as verify_browser
        sys.exit(verify_browser())
    if '--verify-startup' in sys.argv:
        from PySide6.QtWidgets import QApplication
        qt_probe = QApplication.instance() or QApplication([])
        from ui.splash import RetweaksSplash
        splash_probe = RetweaksSplash()
        splash_probe.show()
        qt_probe.processEvents()
        splash_probe.close()
        # Exercise the packaged native image modules without tuning or elevation.
        from PIL import Image, ImageTk
        from audio_panel import WindowsAudio
        WindowsAudio()
        import io
        probe = tk.Tk()
        probe.withdraw()
        try:
            data = io.BytesIO()
            Image.new('RGBA', (4, 4), 'white').save(data, format='PNG')
            data.seek(0)
            loaded = Image.open(data)
            loaded.load()
            photo = ImageTk.PhotoImage(loaded, master=probe)
            assert photo.width() == 4
            assert feather(probe, 48).width() == 48
        finally:
            probe.destroy()
        sys.exit(0)
    ensure_admin()
    if "--preset" in sys.argv or "--list" in sys.argv:
        headless(sys.argv)
    else:
        import rt_crashlog
        rt_crashlog.install(VERSION)
        import rt_perf
        rt_perf.install(VERSION)                              # %APPDATA%\RETWEAKS\perf.log: slow UI callbacks                          # %APPDATA%\RETWEAKS\crash.log
        import rt_shell
        _instance_lock = rt_shell.acquire_single_instance()   # one RETWEAKS at a time (kept for the process)

        def _optional(step, fn, *args):
            """v2.0.8: a failing optional startup step is logged and skipped instead of stopping the app."""
            try:
                return fn(*args)
            except SystemExit:
                raise
            except Exception:
                import traceback
                rt_crashlog.write(f"STARTUP STEP FAILED: {step}", traceback.format_exc())
                return None
        try:
            _optional("close older version", rt_shell.close_legacy_copy)   # older version (previous name) running?
            _migration = _optional("carry over old data", rt_shell.migrate) or []   # before settings load
            import rt_i18n
            _optional("translations", rt_i18n.install, globals())   # setting `language`; hooks Tk text
            if "--minimized" not in sys.argv:
                import rt_splash_client
                rt_splash_client.start_early()                # v1.6 startup screen, up while the app loads
            import rt_welcome
            _optional("welcome tour", rt_welcome.prepare)     # the welcome tour asks the desktop-shortcut question
            hub = Hub(show_intro="--minimized" not in sys.argv)
            rt_crashlog.watch_tk(hub)
            rt_shell.Shell(hub, globals(), _migration)
        except SystemExit:
            raise
        except BaseException:
            # v2.0.8 (owner report: an error on the first launch, reopening worked): log it, then start again by
            # itself once, so the user doesn't have to reopen. A second failure shows where the log is.
            import traceback
            rt_crashlog.write("STARTUP FAILED", traceback.format_exc())
            if "--restarted" not in sys.argv and rt_shell.restart_after_exit():
                os._exit(1)
            try:
                messagebox.showerror(BRAND, f"{BRAND} couldn't start. Details were saved to "
                                     f"{rt_crashlog.log_path()}. Please send that file with your report.")
            except Exception:
                pass
            os._exit(1)
        _optional("welcome tour", rt_welcome.maybe_show, hub)   # first run of v2.0+: the welcome tour, once
        import rt_autoupdate
        _optional("automatic updates", rt_autoupdate.start, hub)   # setting auto_update: download + verify + ask
        if "--minimized" in sys.argv:                         # started with Windows + "Start minimized"
            if rt_shell.tray_active(hub):
                hub.withdraw()
            else:
                hub.iconify()
        try:
            hub.mainloop()
        finally:
            rt_crashlog.ended("window loop ended" + (" (Quit)" if getattr(hub, "_quitting", False)
                                                     else " (NOT through Quit)"))
        # Settings and logs are written as they change, so nothing is left to save here. End the process now
        # instead of letting Python wait for background threads (tray, .NET browser engine, sensors), which
        # made Quit take several seconds (owner report 2026-10-22). The watchdog stays as a last resort.
        rt_shell.exit_watchdog(0)
        try:
            sys.stdout and sys.stdout.flush()
            sys.stderr and sys.stderr.flush()
        except Exception:
            pass
        os._exit(0)
