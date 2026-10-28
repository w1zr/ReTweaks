"""Page fade-in (owner request 2026-10-27: "make cool animations for everything").

When a page is switched, a borderless, click-through window in the page background colour covers the page
area and fades out over ~160 ms, so the new page fades in. Only the overlay's opacity changes (Windows
composites it), so the page itself is laid out and painted once, exactly as without the animation; the speed
from rt_perf.paint_once stays.

The overlay never takes focus or clicks (WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW), is owned
by the main window (so it stays above it only, and hides with it), and sits off screen at opacity 0 when idle.
Skipped when Windows' "Animation effects" is off, when the window isn't on screen, and on other systems.
"""
import sys
import time
import tkinter as tk

DURATION = 0.16
FRAME_MS = 16


def windows_animations_on():
    """Settings → Accessibility → Visual effects → Animation effects (SPI_GETCLIENTAREAANIMATION)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        on = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0):
            return bool(on.value)
    except Exception:
        pass
    return True


class PageFade:
    def __init__(self, hub, area, color):
        self.hub, self.area, self.color = hub, area, color
        self.win = None
        self.job = None
        self.began = 0.0
        self.enabled = windows_animations_on()

    def _make(self):
        win = tk.Toplevel(self.hub)
        win.withdraw()
        win.overrideredirect(True)
        win.configure(bg=self.color)
        win.transient(self.hub)
        win.attributes("-alpha", 0.0)
        win.geometry("1x1+-32000+-32000")
        win.deiconify()
        win.update_idletasks()
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
            GWL_EXSTYLE = -20
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            # WS_EX_NOACTIVATE | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW (no focus, no clicks, no taskbar button)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | 0x08000000 | 0x00000020 | 0x00000080)
        except Exception:
            pass
        try:
            self.hub.focus_force()
        except tk.TclError:
            pass
        self.win = win

    def set_color(self, color):
        self.color = color
        if self.win is not None:
            try:
                self.win.configure(bg=color)
            except tk.TclError:
                pass

    def play(self):
        if not self.enabled:
            return
        try:
            if not self.area.winfo_viewable() or self.hub.state() in ("withdrawn", "iconic"):
                return
            if self.win is None or not self.win.winfo_exists():
                self._make()
            x, y = self.area.winfo_rootx(), self.area.winfo_rooty()
            w, h = self.area.winfo_width(), self.area.winfo_height()
            if w < 2 or h < 2:
                return
            self.win.geometry(f"{w}x{h}+{x}+{y}")
            self.win.attributes("-alpha", 1.0)
            self.win.lift(self.hub)
        except tk.TclError:
            return
        self.began = time.monotonic()
        if self.job is None:
            self.job = self.hub.after(FRAME_MS, self._step)

    def _step(self):
        self.job = None
        try:
            k = min(1.0, (time.monotonic() - self.began) / DURATION)
            eased = 1 - (1 - k) ** 3                  # ease-out: quick start, soft landing
            if k >= 1.0:
                self._park()
                return
            self.win.attributes("-alpha", 1.0 - eased)
            self.job = self.hub.after(FRAME_MS, self._step)
        except tk.TclError:
            pass

    def _park(self):
        try:
            self.win.attributes("-alpha", 0.0)
            self.win.geometry("1x1+-32000+-32000")
        except tk.TclError:
            pass

    def close(self):
        if self.job is not None:
            try:
                self.hub.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
            self.win = None
