# rt_pages/overlay_tk.py
"""The in-game FPS overlay window for the Tk app (replaces the Qt ui/overlay.py).

An ordinary top-level RETWEAKS window: borderless, always on top, never takes focus and lets
mouse clicks pass through to the game (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE |
WS_EX_TOOLWINDOW, set with SetWindowLongPtrW on the window's own HWND). Nothing is injected into
the game. Frame data comes from core.etw_frames / core.overlay_fps on their own threads; the
page pushes text lines here with set_lines() from the Tk thread.

Tk can't make only the background translucent, so the opacity setting (50-100 %) applies to the
whole box (Windows `-alpha`). The rounded corners use a transparent colour key (`-transparentcolor`).
"""

import sys
import tkinter as tk
import tkinter.font as tkfont

from core import overlay_fps as of

FONT_PT = {"small": 11, "medium": 14, "large": 18}
KEY = "#010203"              # colour made fully transparent (outside the rounded box)

# Win32 constants (used only on Windows)
GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x00080000, 0x00000020
WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = 0x08000000, 0x00000080
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
GA_ROOT = 2
MONITOR_DEFAULTTONEAREST = 2


def _round_rect(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
            x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def monitor_rect_at(x, y):
    """(x, y, w, h) of the monitor containing the point, or None. Windows only."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
        mon = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), MONITOR_DEFAULTTONEAREST)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not mon or not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        r = mi.rcMonitor
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        return None


class OverlayWindow:
    """Same interface as the Qt OverlayWindow: set_lines, apply_settings, set_theme,
    show_overlay, hide_overlay, destroy."""

    def __init__(self, master, colors, settings, game_name=""):
        self.master = master
        self.colors = dict(colors)          # {"bg", "text", "subtext"}
        self.cfg = of.clean_settings(settings)
        self.game_name = game_name
        self.lines = ["FPS –"]
        self._job = None
        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", KEY)     # Windows only
            self._keyed = True
        except tk.TclError:
            self._keyed = False
        self.win.configure(bg=KEY if self._keyed else self.colors["bg"])
        self.canvas = tk.Canvas(self.win, bg=KEY if self._keyed else self.colors["bg"],
                                highlightthickness=0, bd=0, takefocus=0)
        self.canvas.pack(fill="both", expand=True)
        self._native_done = False

    # ---------------------------------------------------------------- content
    def _font(self):
        families = set(tkfont.families(self.master))
        fam = "Consolas" if "Consolas" in families else "Courier"
        return (fam, FONT_PT[self.cfg["overlay_size"]], "bold")

    def set_lines(self, lines):
        if lines != self.lines:
            self.lines = list(lines)
            self._redraw()

    def apply_settings(self, settings):
        self.cfg = of.clean_settings(settings)
        self._apply_alpha()
        self._redraw()

    def set_theme(self, colors):
        self.colors = dict(colors)
        self._redraw()

    def _apply_alpha(self):
        try:
            self.win.attributes("-alpha", self.cfg["overlay_opacity"] / 100.0)
        except tk.TclError:
            pass

    def size(self):
        f = tkfont.Font(root=self.master, font=self._font())
        lh = f.metrics("linespace")
        pad = lh // 2
        w = max(f.measure(t) for t in self.lines) + pad * 2
        h = lh * len(self.lines) + pad * 2
        return w, h, lh, pad

    def _redraw(self):
        try:
            w, h, lh, pad = self.size()
            c = self.canvas
            c.delete("all")
            c.configure(width=w, height=h)
            c.create_polygon(_round_rect(0, 0, w - 1, h - 1, 10), smooth=True, fill=self.colors["bg"], outline="")
            y = pad
            font = self._font()
            for i, t in enumerate(self.lines):
                color = self.colors["text"] if i == 0 or len(self.lines) == 1 else self.colors["subtext"]
                c.create_text(pad, y, text=t, anchor="nw", fill=color, font=font)
                y += lh
            self.reposition(w, h)
        except tk.TclError:
            pass

    def _target_area(self):
        rect = of.find_game_window_rect(self.game_name)
        if rect:
            area = monitor_rect_at(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2)
            if area:
                return area
        area = monitor_rect_at(0, 0)
        if area:
            return area
        return (0, 0, self.master.winfo_screenwidth(), self.master.winfo_screenheight())

    def reposition(self, w=None, h=None):
        if w is None:
            w, h = self.size()[:2]
        x, y = of.corner_position(self._target_area(), (w, h), self.cfg["overlay_position"], self.cfg["overlay_margin"])
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    # ---------------------------------------------------------------- Windows behaviour
    def show_overlay(self):
        self._apply_alpha()
        self._redraw()
        self.win.deiconify()
        self.win.update_idletasks()
        self._apply_native_styles()
        self.assert_topmost()
        self._schedule_topmost()

    def hide_overlay(self):
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
        self.hide_overlay()
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _schedule_topmost(self):
        self._job = self.master.after(2000, self._topmost_tick)

    def _topmost_tick(self):
        self._job = None
        self.assert_topmost()
        self._schedule_topmost()

    def hwnd(self):
        """The real top-level HWND (Tk's winfo_id is a child of it)."""
        wid = self.win.winfo_id()
        if sys.platform != "win32":
            return wid
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.GetAncestor.restype = ctypes.c_void_p
            user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            return user32.GetAncestor(wid, GA_ROOT) or wid
        except Exception:
            return wid

    def _apply_native_styles(self):
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            hwnd = self.hwnd()
            ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
            self._native_done = True
            return True
        except Exception:
            return False

    def assert_topmost(self):
        if sys.platform != "win32":
            return
        try:
            if not self.win.winfo_viewable():
                return
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            user32.SetWindowPos(self.hwnd(), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception:
            pass
