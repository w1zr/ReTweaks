"""Crosshair page (owner request 2026-10-22: "a custom crosshair feature that acts like Crosshair X").

Make your own crosshair, pick a built-in one, or get other people's through share codes, .rtxhair files
or the online gallery. The crosshair is drawn by an ordinary RETWEAKS window: borderless, always on top,
click-through and never focused (the same window flags as the FPS overlay). Nothing is injected into a
game. It shows over borderless / windowed games; exclusive fullscreen draws over every other window.

Settings (config.json): crosshair_enabled (show when RETWEAKS starts, default off), crosshair_active (the
design in use), crosshair_hotkey, crosshair_monitor, crosshair_offset [x, y]. Saved designs live in
%APPDATA%\\RETWEAKS\\crosshairs.json (core.crosshair.Store)."""
import queue
import sys
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox

from core import crosshair as xh
from rt_pages.common import card, label, run_bg
from rt_pages.overlay_tk import (GA_ROOT, GWL_EXSTYLE, HWND_TOPMOST, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE,
                                 WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT)

KEY_HEX = "#010203"
TABS = ("Editor", "Built-in", "My crosshairs", "Gallery", "Share")


def monitors(master):
    """[(label, (x, y, w, h))] for every monitor; primary first. Windows: EnumDisplayMonitors."""
    out = []
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
            user32 = ctypes.windll.user32
            found = []
            PROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.POINTER(wintypes.RECT), ctypes.c_void_p)

            def cb(hmon, hdc, rect, data):
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(mi)):
                    r = mi.rcMonitor
                    found.append(((r.left, r.top, r.right - r.left, r.bottom - r.top), bool(mi.dwFlags & 1)))
                return 1
            user32.EnumDisplayMonitors(None, None, PROC(cb), 0)
            found.sort(key=lambda m: (not m[1], m[0][0], m[0][1]))
            for i, (rect, primary) in enumerate(found):
                out.append((f"Screen {i + 1}: {rect[2]} x {rect[3]}" + (" (main)" if primary else ""), rect))
        except Exception:
            out = []
    if not out:
        w, h = master.winfo_screenwidth(), master.winfo_screenheight()
        out = [(f"Screen 1: {w} x {h}", (0, 0, w, h))]
    return out


class CrosshairOverlay:
    """The click-through, always-on-top window that draws the crosshair at the screen centre."""

    def __init__(self, master):
        self.master = master
        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", KEY_HEX)     # Windows only
            self.keyed = True
        except tk.TclError:
            self.keyed = False
        self.win.configure(bg=KEY_HEX)
        self.label = tk.Label(self.win, bd=0, bg=KEY_HEX, highlightthickness=0, takefocus=0)
        self.label.pack()
        self.photo = None
        self.visible = False
        self._job = None
        self.geometry = None

    def show(self, design, rect, offset):
        from PIL import ImageTk
        img = xh.render_keyed(design)
        self.photo = ImageTk.PhotoImage(img, master=self.win)
        self.label.configure(image=self.photo)
        x, y, w, h = rect
        cx, cy = x + w // 2 + int(offset[0]), y + h // 2 + int(offset[1])
        half = img.width // 2
        self.geometry = (img.width, img.height, cx - half, cy - half)
        self.win.geometry(f"{img.width}x{img.height}+{cx - half}+{cy - half}")
        try:
            self.win.attributes("-alpha", design["opacity"] / 100.0)
        except tk.TclError:
            pass
        if not self.visible:
            self.win.deiconify()
            self.win.update_idletasks()
            self._native()
            self.visible = True
            self._tick()
        self._topmost()

    def hide(self):
        self.visible = False
        if self._job:
            try:
                self.master.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        try:
            self.win.withdraw()
        except tk.TclError:
            pass

    def destroy(self):
        self.hide()
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _tick(self):
        self._job = None
        if not self.visible:
            return
        self._topmost()
        self._job = self.master.after(2000, self._tick)

    def _hwnd(self):
        wid = self.win.winfo_id()
        if sys.platform != "win32":
            return wid
        try:
            import ctypes
            u = ctypes.windll.user32
            u.GetAncestor.restype = ctypes.c_void_p
            u.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            return u.GetAncestor(wid, GA_ROOT) or wid
        except Exception:
            return wid

    def _native(self):
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            u = ctypes.windll.user32
            u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            h = self._hwnd()
            ex = u.GetWindowLongPtrW(h, GWL_EXSTYLE)
            u.SetWindowLongPtrW(h, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
                                | WS_EX_TOOLWINDOW)
            return True
        except Exception:
            return False

    def _topmost(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            u.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_uint]
            u.SetWindowPos(self._hwnd(), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception:
            pass


class Slider(tk.Canvas):
    """Rounded integer slider (drag, click, arrow keys) with its value shown on the right."""

    def __init__(self, parent, g, lo, hi, value, command, width=260):
        super().__init__(parent, width=width, height=28, bg=parent.cget("bg"), highlightthickness=0, bd=0,
                         takefocus=1, cursor="hand2")
        self.g, self.lo, self.hi, self.value, self.command, self.w = g, lo, hi, int(value), command, width
        for ev, fn in (("<ButtonPress-1>", self._mouse), ("<B1-Motion>", self._mouse),
                       ("<Left>", lambda e: self.set(self.value - 1, True)),
                       ("<Right>", lambda e: self.set(self.value + 1, True)),
                       ("<FocusIn>", lambda e: self.draw()), ("<FocusOut>", lambda e: self.draw())):
            self.bind(ev, fn)
        self.draw()

    def _mouse(self, e):
        self.focus_set()
        span = self.w - 70
        self.set(self.lo + round((e.x - 10) / max(1, span) * (self.hi - self.lo)), True)

    def set(self, v, user=False):
        v = max(self.lo, min(self.hi, int(v)))
        changed = v != self.value
        self.value = v
        self.draw()
        if user and changed and self.command:
            self.command(v)

    def draw(self):
        g = self.g
        self.delete("all")
        self.configure(bg=self.master.cget("bg"))
        span = self.w - 70
        x = 10 + span * (self.value - self.lo) / max(1, self.hi - self.lo)
        self.create_line(10, 14, 10 + span, 14, fill=g["LINE"], width=4, capstyle="round")
        self.create_line(10, 14, x, 14, fill=g["ACC"], width=4, capstyle="round")
        self.create_oval(x - 7, 7, x + 7, 21, fill=g["FG"], outline=self.master.cget("bg"), width=2)
        if self.focus_get() is self:
            self.create_oval(x - 10, 4, x + 10, 24, outline=g["ACC"])
        self.create_text(self.w - 4, 14, text=str(self.value), anchor="e", fill=g["FG"], font=(g["UI"], 10, "bold"))


class CrosshairPage:
    TITLE = "Crosshair"
    SUB = ("Your own crosshair on top of any game window. Make one, pick a built-in one, or use someone "
           "else's share code. Nothing is added to the game itself.")

    def __init__(self, hub, tab, g):
        self.hub, self.tab, self.g = hub, tab, g
        s = hub.settings
        self.store = xh.Store()
        try:
            self.design = xh.validate(s.get("crosshair_active") or xh.BUILTIN[0])
        except xh.CrosshairError:
            self.design = dict(xh.BUILTIN[0])
        self.hotkey = s.get("crosshair_hotkey") if s.get("crosshair_hotkey") in xh.hotkey_names() else xh.DEFAULT_HOTKEY
        off = s.get("crosshair_offset")
        self.offset = [int(max(-500, min(500, v))) for v in off] if (
            isinstance(off, list) and len(off) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                            for v in off)) else [0, 0]
        self.monitor_list = monitors(hub)
        mi = s.get("crosshair_monitor", 0)
        self.monitor = mi if isinstance(mi, int) and 0 <= mi < len(self.monitor_list) else 0
        self.overlay = None
        self.events = queue.Queue()
        self.poller = None
        self._job = None
        self._photos = []
        self.gallery = None
        self.closed = False

        g["page_header"](tab, "RETWEAKS", self.TITLE, self.SUB)
        body = hub._scroll_area(tab)
        self._build_top(body)
        self.tab_var = tk.StringVar(value=TABS[0])
        seg_row = tk.Frame(body, bg=g["BG"])
        seg_row.pack(fill="x", pady=(8, 4))
        seg = g["Segmented"](seg_row, TABS, self.tab_var, command=self._switch)
        for b in seg.btns.values():
            b.bw = g["text_w"]((g["UI"], 10, "bold"), b.label) + 36
            b.configure(width=b.bw)
            b._draw()
        seg.pack(anchor="w")
        self.holder = tk.Frame(body, bg=g["BG"])
        self.holder.pack(fill="x")
        self.frames = {
            "Editor": self._build_editor(self.holder),
            "Built-in": self._build_builtin(self.holder),
            "My crosshairs": self._build_mine(self.holder),
            "Gallery": self._build_gallery(self.holder),
            "Share": self._build_share(self.holder),
        }
        self._switch()
        self._load_into_editor()
        self._start_hotkey()
        self._job = hub.after(100, self._poll)
        if s.get("crosshair_enabled"):           # "Show when RETWEAKS starts" (off unless the user turned it on)
            hub.after(400, self.show)

    # ------------------------------------------------------------ layout
    def _row(self, parent):
        r = tk.Frame(parent, bg=parent.cget("bg"))
        r.pack(fill="x", padx=16, pady=4)
        return r

    def _lbl(self, parent, text, width=None):
        w = tk.Label(parent, text=text, bg=parent.cget("bg"), fg=self.g["MUTED"], font=(self.g["UI"], 9), anchor="w",
                     width=width)
        w.pack(side="left", padx=(0, 8))
        return w

    def _build_top(self, body):
        g = self.g
        b = card(body, g)
        top = tk.Frame(b, bg=b.cget("bg"))
        top.pack(fill="x", padx=16, pady=(14, 6))
        self.preview = tk.Canvas(top, width=220, height=160, bg=b.cget("bg"), highlightthickness=0, bd=0)
        self.preview.pack(side="left")
        right = tk.Frame(top, bg=b.cget("bg"))
        right.pack(side="left", fill="x", expand=True, padx=(18, 0))
        self.name_lbl = tk.Label(right, text="", bg=right.cget("bg"), fg=g["FG"], font=(g["UI"], 15, "bold"), anchor="w")
        self.name_lbl.pack(fill="x")
        self.state_lbl = tk.Label(right, text="Overlay: hidden", bg=right.cget("bg"), fg=g["MUTED"],
                                  font=(g["UI"], 10), anchor="w")
        self.state_lbl.pack(fill="x", pady=(2, 8))
        row = tk.Frame(right, bg=right.cget("bg"))
        row.pack(fill="x")
        self.show_btn = g["RButton"](row, "Show crosshair", self.toggle, kind="primary", width=150)
        self.show_btn.pack(side="left", padx=(0, 8))
        self._lbl(row, "Show / hide key")
        self.key_sel = g["RSelect"](row, xh.hotkey_names(), width=110, command=self.set_hotkey)
        self.key_sel.set(self.hotkey)
        self.key_sel.pack(side="left")
        row = tk.Frame(right, bg=right.cget("bg"))
        row.pack(fill="x", pady=(8, 0))
        self._lbl(row, "Screen")
        self.mon_sel = g["RSelect"](row, [m[0] for m in self.monitor_list], width=230, command=self.set_monitor)
        self.mon_sel.set(self.monitor_list[self.monitor][0])
        self.mon_sel.pack(side="left", padx=(0, 14))
        self._lbl(row, "Move")
        for text, dx, dy in (("←", -1, 0), ("→", 1, 0), ("↑", 0, -1), ("↓", 0, 1)):
            g["RButton"](row, text, lambda dx=dx, dy=dy: self.nudge(dx, dy), width=34, height=30).pack(side="left", padx=1)
        g["RButton"](row, "Centre", lambda: self.nudge(None, None), kind="ghost", width=70, height=30).pack(
            side="left", padx=(6, 0))
        self.off_lbl = tk.Label(row, text="", bg=row.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9))
        self.off_lbl.pack(side="left", padx=8)
        self.start_var = tk.BooleanVar(value=bool(self.hub.settings.get("crosshair_enabled", False)))
        g["RCheck"](right, "Show the crosshair when RETWEAKS starts", self.start_var, self.set_start).pack(
            anchor="w", pady=(10, 0))
        label(b, "Works over borderless and windowed games. Exclusive fullscreen draws over every other window, so "
                 "switch the game to borderless if the crosshair doesn't appear. RETWEAKS only draws a window on top; "
                 "it never changes the game. Some games or tournaments don't allow crosshair overlays — you're "
                 "responsible for following each game's rules.", g, 9, g["MUTED"], pady=(6, 14))
        self._update_offset()

    def _build_editor(self, parent):
        g = self.g
        f = tk.Frame(parent, bg=g["BG"])
        b = card(f, g, "Make your own", "Changes show in the preview right away, and on screen when the crosshair is showing.")
        row = self._row(b)
        self._lbl(row, "Style", 12)
        self.style_sel = g["RSelect"](row, list(xh.STYLES.values()), width=200, command=self._style_picked)
        self.style_sel.pack(side="left", padx=(0, 18))
        self.img_btn = g["RButton"](row, "Choose PNG…", self.pick_image, kind="default")
        self.img_btn.pack(side="left")
        row = self._row(b)
        self._lbl(row, "Colour", 12)
        self.color_sw = tk.Canvas(row, width=30, height=30, bg=row.cget("bg"), highlightthickness=0, cursor="hand2")
        self.color_sw.pack(side="left", padx=(0, 8))
        self.color_sw.bind("<ButtonRelease-1>", lambda e: self.pick_color("color"))
        self.hex_var = tk.StringVar()
        e = g["REntry"](row, self.hex_var, width_px=110)
        e.pack(side="left", padx=(0, 6))
        e.entry.bind("<Return>", lambda ev: self.apply_hex())
        e.entry.bind("<FocusOut>", lambda ev: self.apply_hex())
        g["RButton"](row, "Pick…", lambda: self.pick_color("color"), kind="ghost").pack(side="left")
        self.sliders = {}
        names = {"opacity": "Opacity %", "size": "Length", "thickness": "Thickness", "gap": "Gap",
                 "rotation": "Rotation °", "dot_size": "Dot size"}
        for key in ("opacity", "size", "thickness", "gap", "rotation"):
            row = self._row(b)
            self._lbl(row, names[key], 12)
            lo, hi, _ = xh.RANGES[key]
            s = Slider(row, g, lo, hi, self.design[key], lambda v, k=key: self.change(k, v))
            s.pack(side="left")
            self.sliders[key] = s
        row = self._row(b)
        self.dot_var = tk.BooleanVar()
        g["RCheck"](row, "Centre dot", self.dot_var, lambda: self.change("center_dot", self.dot_var.get())).pack(
            side="left", padx=(0, 18))
        self._lbl(row, "Dot size")
        lo, hi, _ = xh.RANGES["dot_size"]
        self.sliders["dot_size"] = Slider(row, g, lo, hi, self.design["dot_size"], lambda v: self.change("dot_size", v),
                                          width=200)
        self.sliders["dot_size"].pack(side="left")
        row = self._row(b)
        self.ol_var = tk.BooleanVar()
        g["RCheck"](row, "Outline", self.ol_var, lambda: self.change("outline", self.ol_var.get())).pack(
            side="left", padx=(0, 18))
        self.ol_sw = tk.Canvas(row, width=30, height=30, bg=row.cget("bg"), highlightthickness=0, cursor="hand2")
        self.ol_sw.pack(side="left", padx=(0, 8))
        self.ol_sw.bind("<ButtonRelease-1>", lambda e: self.pick_color("outline_color"))
        self._lbl(row, "Width")
        lo, hi, _ = xh.RANGES["outline_thickness"]
        self.sliders["outline_thickness"] = Slider(row, g, lo, hi, self.design["outline_thickness"],
                                                   lambda v: self.change("outline_thickness", v), width=160)
        self.sliders["outline_thickness"].pack(side="left")
        row = self._row(b)
        self._lbl(row, "Name", 12)
        self.name_var = tk.StringVar()
        ne = g["REntry"](row, self.name_var, width_px=240)
        ne.pack(side="left", padx=(0, 8))
        ne.entry.bind("<KeyRelease>", lambda e: self.change("name", self.name_var.get(), redraw=False))
        g["RButton"](row, "Save to My crosshairs", self.save_current, kind="primary").pack(side="left")
        self.edit_msg = label(b, "", g, 9, g["MUTED"], pady=(2, 12))
        return f

    def _tile_grid(self, parent, items, buttons):
        """Rows of tiles: preview + name + buttons. items: [(design, subtitle)]; buttons: [(text, fn(i))]."""
        g = self.g
        for w in parent.winfo_children():
            w.destroy()
        grid = tk.Frame(parent, bg=parent.cget("bg"))
        grid.pack(fill="x", padx=12, pady=(4, 12))
        cols = 4
        for i, (d, sub) in enumerate(items):
            t = tk.Frame(grid, bg=g["PANEL2"] if "PANEL2" in g else g["PANEL"], padx=10, pady=10)
            t.grid(row=i // cols, column=i % cols, padx=5, pady=5, sticky="nsew")
            cv = tk.Canvas(t, width=150, height=90, bg=t.cget("bg"), highlightthickness=0)
            cv.pack()
            self._draw_preview(cv, d, 150, 90, scale=3)
            tk.Label(t, text=d["name"], bg=t.cget("bg"), fg=g["FG"], font=(g["UI"], 10, "bold"), anchor="w").pack(fill="x")
            # always a subtitle line (blank if none), so tiles in a row line up
            tk.Label(t, text=sub or " ", bg=t.cget("bg"), fg=g["MUTED"], font=(g["UI"], 8), anchor="w").pack(fill="x")
            br = tk.Frame(t, bg=t.cget("bg"))
            br.pack(fill="x", pady=(6, 0))
            for text, fn in buttons:
                g["RButton"](br, text, lambda i=i, fn=fn: fn(i), kind="default", height=28,
                             font=(g["UI"], 9, "bold")).pack(side="left", padx=(0, 4))
        for c in range(cols):
            grid.grid_columnconfigure(c, weight=1)
        return grid

    def _build_builtin(self, parent):
        f = tk.Frame(parent, bg=self.g["BG"])
        sub = lambda d: xh.STYLES[d["style"]] if xh.STYLES[d["style"]] != d["name"] else ""
        b = card(f, self.g, "Built-in crosshairs", "Pick one to use it; you can then change it in the Editor.")
        self.builtin_box = tk.Frame(b, bg=b.cget("bg"))
        self.builtin_box.pack(fill="x")
        self._tile_grid(self.builtin_box, [(d, sub(d)) for d in xh.BUILTIN], [("Use", lambda i: self.use(xh.BUILTIN[i]))])
        b2 = card(f, self.g, "Pack 2", "21 more popular designs, recreated from small pictures, so they're close "
                                       "but may differ by a pixel or a shade.")
        self.pack2_box = tk.Frame(b2, bg=b2.cget("bg"))
        self.pack2_box.pack(fill="x")
        self._tile_grid(self.pack2_box, [(d, sub(d)) for d in xh.PACK2], [("Use", lambda i: self.use(xh.PACK2[i]))])
        return f

    def _build_mine(self, parent):
        g = self.g
        f = tk.Frame(parent, bg=g["BG"])
        b = card(f, g, "My crosshairs", "Saved on this PC in %APPDATA%\\RETWEAKS\\crosshairs.json.")
        self.mine_msg = label(b, self.store.note, g, 9, g["MUTED"])
        row = self._row(b)
        self._lbl(row, "New name for the selected one")
        self.rename_var = tk.StringVar()
        g["REntry"](row, self.rename_var, width_px=220).pack(side="left")
        self.mine_box = tk.Frame(b, bg=b.cget("bg"))
        self.mine_box.pack(fill="x")
        self._render_mine()
        return f

    def _render_mine(self):
        if not self.store.items:
            for w in self.mine_box.winfo_children():
                w.destroy()
            label(self.mine_box, "Nothing saved yet. Make a crosshair in the Editor and press Save to My crosshairs, "
                                 "or load a share code.", self.g, 10, self.g["MUTED"], pady=(6, 14))
            return
        self._tile_grid(self.mine_box, [(d, "") for d in self.store.items],
                        [("Use", lambda i: self.use(self.store.items[i])), ("Rename", self.rename),
                         ("Copy", self.duplicate), ("Delete", self.delete)])

    def _build_gallery(self, parent):
        g = self.g
        f = tk.Frame(parent, bg=g["BG"])
        b = card(f, g, "Online gallery", "Crosshairs other players shared on the RETWEAKS GitHub page. Each one is "
                                          "checked before it's shown. To share yours, see crosshairs/README.md in the repo.")
        row = self._row(b)
        self.gal_btn = g["RButton"](row, "Load gallery", self.load_gallery, kind="primary")
        self.gal_btn.pack(side="left")
        self.gal_msg = label(b, "Not loaded yet.", g, 10, g["MUTED"])
        self.gal_box = tk.Frame(b, bg=b.cget("bg"))
        self.gal_box.pack(fill="x")
        return f

    def _build_share(self, parent):
        g = self.g
        f = tk.Frame(parent, bg=g["BG"])
        b = card(f, g, "Share code", "Send this code to a friend. They paste it below to get the same crosshair.")
        row = self._row(b)
        self.code_var = tk.StringVar()
        ce = g["REntry"](row, self.code_var, width_px=520)
        ce.pack(side="left", padx=(0, 8))
        ce.entry.configure(state="readonly", readonlybackground=ce.entry.cget("bg"))
        g["RButton"](row, "Copy code", self.copy_code).pack(side="left")
        row = self._row(b)
        self.paste_var = tk.StringVar()
        pe = g["REntry"](row, self.paste_var, width_px=520)
        pe.pack(side="left", padx=(0, 8))
        pe.entry.bind("<Return>", lambda e: self.load_code())
        g["RButton"](row, "Use pasted code", self.load_code, kind="primary").pack(side="left")
        self.share_msg = label(b, "", g, 9, g["MUTED"])
        b2 = card(f, g, "Files", "Save the crosshair as a .rtxhair file, or open one someone sent you.")
        row = self._row(b2)
        g["RButton"](row, "Export file…", self.export_file).pack(side="left", padx=(0, 8))
        g["RButton"](row, "Import file…", self.import_file).pack(side="left")
        self.file_msg = label(b2, "", g, 9, g["MUTED"], pady=(2, 12))
        return f

    def _switch(self):
        for fr in self.frames.values():
            fr.pack_forget()
        self.frames[self.tab_var.get()].pack(fill="x")
        if self.tab_var.get() == "Gallery" and self.gallery is None:
            self.load_gallery()

    # ------------------------------------------------------------ drawing
    def _draw_preview(self, cv, d, w, h, scale=3):
        from PIL import Image, ImageTk
        g = self.g
        cv.delete("all")
        try:
            im = xh.render(d)
        except Exception as e:
            cv.create_text(w // 2, h // 2, text=f"Can't draw: {e}", fill=g["MUTED"], font=(g["UI"], 8), width=w - 10)
            return
        box = im.getchannel("A").getbbox()
        if box:                                   # crop to the drawn part (kept centred) so it can be enlarged
            m = im.width // 2
            r = max(m - box[0], box[2] - 1 - m, m - box[1], box[3] - 1 - m) + 3
            im = im.crop((m - r, m - r, m + r + 1, m + r + 1))
        side = max(im.width, im.height)
        k = max(1, min(scale, (min(w, h) - 12) // max(1, side)))
        bg = Image.new("RGBA", (w, h), (52, 60, 54, 255))           # a neutral "game scene" grey-green
        big = im.resize((im.width * k, im.height * k), Image.NEAREST)
        bg.alpha_composite(big, (w // 2 - big.width // 2, h // 2 - big.height // 2))
        mask = Image.new("L", (w, h), 0)
        from PIL import ImageDraw
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], 12, fill=255)
        out = Image.new("RGBA", (w, h), cv.cget("bg"))
        out.paste(bg, (0, 0), mask)
        ph = ImageTk.PhotoImage(out, master=cv)
        self._photos.append(ph)
        self._photos = self._photos[-200:]
        cv.create_image(0, 0, image=ph, anchor="nw")
        cv._photo = ph

    def _refresh(self):
        self._draw_preview(self.preview, self.design, 220, 160, scale=4)
        self.name_lbl.configure(text=self.design["name"])
        try:
            self.code_var.set(xh.to_code(self.design))
        except xh.CrosshairError as e:
            self.code_var.set("")
            self.share_msg.configure(text=str(e))
        if self.overlay is not None and self.overlay.visible:
            self._show_now()

    def _load_into_editor(self):
        d = self.design
        self.style_sel.set(xh.STYLES[d["style"]])
        self.hex_var.set(d["color"].upper())
        for k, s in self.sliders.items():
            s.set(d[k])
        self.dot_var.set(d["center_dot"])
        self.ol_var.set(d["outline"])
        self.name_var.set(d["name"])
        self._paint_swatches()
        self._refresh()

    def _paint_swatches(self):
        for cv, col in ((self.color_sw, self.design["color"]), (self.ol_sw, self.design["outline_color"])):
            cv.delete("all")
            cv.create_oval(3, 3, 27, 27, fill=col, outline=self.g["LINE"], width=2)

    # ------------------------------------------------------------ editing
    def change(self, key, value, redraw=True):
        d = dict(self.design)
        d[key] = value
        try:
            self.design = xh.validate(d)
        except xh.CrosshairError as e:
            self.edit_msg.configure(text=str(e))
            return False
        self.edit_msg.configure(text="")
        self._save_active()
        if redraw:
            self._refresh()
        else:
            self.name_lbl.configure(text=self.design["name"])
            try:
                self.code_var.set(xh.to_code(self.design))
            except xh.CrosshairError:
                pass
        return True

    def _style_picked(self, label_text):
        style = next(k for k, v in xh.STYLES.items() if v == label_text)
        if style == "image" and not self.design.get("image"):
            if not self.pick_image():
                self.style_sel.set(xh.STYLES[self.design["style"]])
            return
        self.change("style", style)

    def pick_image(self):
        path = filedialog.askopenfilename(parent=self.hub, title="Choose a crosshair image",
                                          filetypes=[("PNG images", "*.png"), ("All files", "*.*")])
        if not path:
            return False
        try:
            data = xh.image_from_png_file(path)
        except xh.CrosshairError as e:
            self.edit_msg.configure(text=str(e))
            return False
        d = dict(self.design, style="image", image=data)
        try:
            self.design = xh.validate(d)
        except xh.CrosshairError as e:
            self.edit_msg.configure(text=str(e))
            return False
        self.style_sel.set(xh.STYLES["image"])
        self._save_active()
        self._refresh()
        return True

    def apply_hex(self):
        v = self.hex_var.get().strip()
        if not v.startswith("#"):
            v = "#" + v
        if not xh.HEX_RE.match(v):
            self.edit_msg.configure(text="Type a colour like #00FF66.")
            return False
        ok = self.change("color", v)
        self._paint_swatches()
        return ok

    def pick_color(self, key):
        res = colorchooser.askcolor(color=self.design[key], parent=self.hub, title="Crosshair colour")
        if res and res[1]:
            self.change(key, res[1])
            if key == "color":
                self.hex_var.set(self.design["color"].upper())
            self._paint_swatches()

    def use(self, d):
        try:
            self.design = xh.validate(dict(d))
        except xh.CrosshairError as e:
            messagebox.showwarning("Crosshair", str(e), parent=self.hub)
            return
        self._save_active()
        self._load_into_editor()

    def save_current(self):
        d = dict(self.design, name=self.name_var.get() or self.design["name"])
        try:
            c = self.store.add(d)
        except xh.CrosshairError as e:
            self.edit_msg.configure(text=str(e))
            return
        self.edit_msg.configure(text=f"Saved as “{c['name']}”.")
        self._render_mine()
        self._log("Crosshair", f"saved {c['name']}", "Success")

    def rename(self, i):
        name = self.rename_var.get().strip()
        if not name:
            self.mine_msg.configure(text="Type the new name in the box above first, then press Rename.")
            return
        try:
            c = self.store.rename(i, name)
        except xh.CrosshairError as e:
            self.mine_msg.configure(text=str(e))
            return
        self.rename_var.set("")
        self.mine_msg.configure(text=f"Renamed to “{c['name']}”.")
        self._render_mine()

    def duplicate(self, i):
        c = self.store.duplicate(i)
        self.mine_msg.configure(text=f"Copied as “{c['name']}”.")
        self._render_mine()

    def delete(self, i):
        name = self.store.items[i]["name"]
        if not messagebox.askyesno("Delete crosshair", f"Delete “{name}” from My crosshairs?", parent=self.hub):
            return
        self.store.delete(i)
        self.mine_msg.configure(text=f"Deleted “{name}”.")
        self._render_mine()

    # ------------------------------------------------------------ sharing
    def copy_code(self):
        code = self.code_var.get()
        if not code:
            return
        self.hub.clipboard_clear()
        self.hub.clipboard_append(code)
        self.share_msg.configure(text="Code copied.")

    def load_code(self):
        try:
            d = xh.from_code(self.paste_var.get())
        except xh.CrosshairError as e:
            self.share_msg.configure(text=str(e))
            return False
        self.use(d)
        self.paste_var.set("")
        self.share_msg.configure(text=f"Loaded “{d['name']}”. Press Save to My crosshairs in the Editor to keep it.")
        return True

    def export_file(self):
        safe = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in self.design["name"]).strip() or "crosshair"
        path = filedialog.asksaveasfilename(parent=self.hub, title="Export crosshair", defaultextension=".rtxhair",
                                            initialfile=safe + ".rtxhair",
                                            filetypes=[("RETWEAKS crosshair", "*.rtxhair")])
        if not path:
            return
        try:
            xh.export_file(self.design, path)
            self.file_msg.configure(text=f"Saved {path}")
        except (OSError, xh.CrosshairError) as e:
            self.file_msg.configure(text=f"Couldn't save the file: {e}")

    def import_file(self):
        path = filedialog.askopenfilename(parent=self.hub, title="Import crosshair",
                                          filetypes=[("RETWEAKS crosshair", "*.rtxhair"), ("All files", "*.*")])
        if not path:
            return
        try:
            d = xh.import_file(path)
        except xh.CrosshairError as e:
            self.file_msg.configure(text=str(e))
            return
        self.use(d)
        self.file_msg.configure(text=f"Loaded “{d['name']}”. Press Save to My crosshairs in the Editor to keep it.")

    def load_gallery(self):
        self.gal_btn.enabled = False
        self.gal_msg.configure(text="Loading the gallery…")
        run_bg(self.hub, xh.fetch_gallery, self._gallery_done)

    def _gallery_done(self, res):
        self.gal_btn.enabled = True
        if self.closed:
            return
        if isinstance(res, Exception):
            res = {"status": "offline", "entries": [], "message": f"The gallery couldn't be loaded: {res}"}
        self.gallery = res
        self.gal_msg.configure(text=res["message"])
        for w in self.gal_box.winfo_children():
            w.destroy()
        entries = res["entries"]
        if entries:
            self._tile_grid(self.gal_box, [(e["crosshair"], f"by {e['author']}" if e["author"] else "") for e in entries],
                            [("Use", lambda i: self.use(entries[i]["crosshair"])),
                             ("Save", lambda i: (self.store.add(entries[i]["crosshair"]), self._render_mine(),
                                                 self.gal_msg.configure(text=f"Saved “{entries[i]['name']}” to My crosshairs.")))])

    # ------------------------------------------------------------ overlay
    def _show_now(self):
        if self.overlay is None:
            self.overlay = CrosshairOverlay(self.hub)
        rect = self.monitor_list[self.monitor][1]
        self.overlay.show(self.design, rect, self.offset)
        self.state_lbl.configure(text=f"Overlay: showing on {self.monitor_list[self.monitor][0]}  ·  {self.hotkey} hides it")
        self.show_btn.label = "Hide crosshair"
        self.show_btn._draw()

    def show(self):
        if self.closed:
            return
        try:
            self._show_now()
            self._log("Crosshair", "show overlay", "Success")
        except Exception as e:
            self.state_lbl.configure(text=f"Overlay couldn't be shown: {e}")

    def hide(self):
        if self.overlay is not None:
            self.overlay.hide()
        self.state_lbl.configure(text=f"Overlay: hidden  ·  {self.hotkey} shows it")
        self.show_btn.label = "Show crosshair"
        self.show_btn._draw()

    def visible(self):
        return self.overlay is not None and self.overlay.visible

    def toggle(self):
        self.hide() if self.visible() else self.show()

    def nudge(self, dx, dy):
        if dx is None:
            self.offset = [0, 0]
        else:
            self.offset = [max(-500, min(500, self.offset[0] + dx)), max(-500, min(500, self.offset[1] + dy))]
        self.hub.settings["crosshair_offset"] = list(self.offset)
        self.hub.save_settings()
        self._update_offset()
        if self.visible():
            self._show_now()

    def _update_offset(self):
        x, y = self.offset
        self.off_lbl.configure(text="centred" if not (x or y) else f"{x:+d} px, {y:+d} px")

    def set_monitor(self, text):
        self.monitor = next((i for i, m in enumerate(self.monitor_list) if m[0] == text), 0)
        self.hub.settings["crosshair_monitor"] = self.monitor
        self.hub.save_settings()
        if self.visible():
            self._show_now()

    def set_start(self):
        self.hub.settings["crosshair_enabled"] = bool(self.start_var.get())
        self.hub.save_settings()

    def set_hotkey(self, key):
        if key not in xh.hotkey_names():
            return
        self.hotkey = key
        self.hub.settings["crosshair_hotkey"] = key
        self.hub.save_settings()
        self._start_hotkey()
        self.state_lbl.configure(text=("Overlay: showing" if self.visible() else "Overlay: hidden")
                                      + f"  ·  {key} {'hides' if self.visible() else 'shows'} it")

    def _start_hotkey(self):
        if self.poller is not None:
            self.poller.stop()
        self.poller = xh.HotkeyPoller(self.hotkey, lambda: self.events.put("toggle"))
        if sys.platform == "win32":
            self.poller.start()

    def _poll(self):
        self._job = None
        if self.closed:
            return
        try:
            while True:
                if self.events.get_nowait() == "toggle":
                    self.toggle()
        except queue.Empty:
            pass
        self._job = self.hub.after(100, self._poll)

    def _save_active(self):
        self.hub.settings["crosshair_active"] = self.design
        self.hub.save_settings()

    def _log(self, comp, what, result):
        try:
            self.hub.log_action(comp, what, result)
        except Exception:
            pass

    def close(self):
        self.closed = True
        if self.poller is not None:
            self.poller.stop()
        if self._job is not None:
            try:
                self.hub.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None
