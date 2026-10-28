"""UI responsiveness: smooth, flicker-free scrolling and a slowness log (owner report 2026-10-22: scrolling is
"laggy and black occurs" on every page, and some buttons get no reaction).

1. smooth_scroll(canvas): wheel ticks are added up and applied once per screen refresh (~16 ms) instead of one
   scroll per event, so fast wheel turns don't queue dozens of full repaints. On Windows the canvas is told not to
   paint while it moves (WM_SETREDRAW) and is then repainted once with all its child windows (RedrawWindow), which
   removes the black gaps Windows shows while hundreds of child widgets catch up.
2. install(): every Python callback Tk runs on the UI thread (button commands, key/mouse bindings, timers) is timed;
   anything taking 100 ms or more is appended to %APPDATA%\\RETWEAKS\\perf.log with its name and duration. While a
   callback runs, the window can't react to clicks or scrolling, so this log shows exactly what makes buttons feel
   dead or scrolling lag. Small, capped (256 KB), never raises.
3. Tall frames (2.1, owner report 2026-10-27: App Starter and other long pages lag when scrolled). Tk repaints a
   frame's whole background whenever it moves, so every scroll step painted the full ~12,000 px content frame of
   App Starter (61 ms per step; 30 of 60 steps over 33 ms). Before each scroll step, frames more than twice the
   visible height switch to `_FastFrame`: Tk stops painting their background (-background {}) and Windows fills
   only the strip it's about to show, with the same colour (WM_ERASEBKGND). They still report and accept their real
   colour (cget/configure/["bg"]), so themes and children created inside them are unchanged. 61 -> 9 ms per step.
"""
import os
import contextlib
import sys
import time
import tkinter as tk
from pathlib import Path

SLOW_MS = 100
MAX_LOG = 256 * 1024
_installed = False


# ------------------------------------------------------------------ slowness log
def log_path():
    return Path(os.getenv("APPDATA") or Path.home()) / "RETWEAKS" / "perf.log"


def _unwrap(func):
    """tkinter's after() hands Tk a small 'callit' wrapper; report the function it calls instead."""
    for _ in range(3):
        qn = getattr(func, "__qualname__", "") or ""
        if not qn.endswith("callit") or not getattr(func, "__closure__", None):
            break
        inner = [c.cell_contents for c in func.__closure__
                 if callable(getattr(c, "cell_contents", None)) and c.cell_contents is not func]
        if not inner:
            break
        func = inner[0]
    return func


def _name(func):
    f = getattr(_unwrap(func), "__func__", _unwrap(func))
    mod = getattr(f, "__module__", "") or ""
    qn = getattr(f, "__qualname__", None) or getattr(f, "__name__", None) or type(f).__name__
    code = getattr(f, "__code__", None)
    where = f" ({os.path.basename(code.co_filename)}:{code.co_firstlineno})" if code else ""
    return f"{mod}.{qn}{where}"


def _write(line):
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > MAX_LOG:
            keep = p.read_bytes()[-MAX_LOG // 2:]
            p.write_bytes(keep)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def install(version=""):
    """Time every Tk callback (wraps tkinter's callback registration). Safe to call once at startup."""
    global _installed
    if _installed:
        return
    _installed = True
    _write(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')}  START  RETWEAKS {version}  (callbacks >= {SLOW_MS} ms)")
    original = tk.Misc._register

    def _register(self, func, subst=None, needcleanup=1):
        def timed(*args):
            t = time.perf_counter()
            try:
                return func(*args)
            finally:
                ms = (time.perf_counter() - t) * 1000
                if ms >= SLOW_MS:
                    _write(f"{time.strftime('%H:%M:%S')}  {ms:7.0f} ms  {_name(func)}")
        try:
            timed.__name__ = getattr(func, "__name__", "callback")
        except Exception:
            pass
        return original(self, timed, subst, needcleanup)

    tk.Misc._register = _register


# ------------------------------------------------------------------ scrolling
def _win32():
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        return ctypes.windll.user32
    except Exception:
        return None


@contextlib.contextmanager
def paint_once(widget):
    """Windows paints `widget` and its children once, after the block, instead of piece by piece while the
    block packs and lays out hundreds of widgets (owner report 2026-10-27: page switches showed black boxes).
    Same WM_SETREDRAW / RedrawWindow pair as smooth_scroll. Nested blocks only act at the outermost one; a
    hidden widget or a non-Windows system just runs the block."""
    user32 = _win32()
    hwnd = None
    if user32 is not None and widget is not None and not getattr(widget, "_rt_paint_once", False):
        try:
            if widget.winfo_viewable():
                hwnd = widget.winfo_id()
                user32.SendMessageW(hwnd, 0x000B, 0, 0)                 # WM_SETREDRAW off
                widget._rt_paint_once = True
        except Exception:
            hwnd = None
    try:
        yield
    finally:
        if hwnd is not None:
            try:
                widget.update_idletasks()                               # finish layout while nothing paints
            except tk.TclError:
                pass
            try:
                widget._rt_paint_once = False
                user32.SendMessageW(hwnd, 0x000B, 1, 0)                 # WM_SETREDRAW on
                # RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW | RDW_FRAME
                user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100 | 0x0400)
            except Exception:
                pass


_BG_KEYS = ("bg", "background")
_procs = []            # every window procedure handed to Windows stays alive for the whole run (see fun.py)
_win_api = None


def _api():
    """user32/gdi32 with 64-bit-safe signatures, or None."""
    global _win_api
    if _win_api is None:
        if sys.platform != "win32":
            _win_api = False
        else:
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                gdi32 = ctypes.WinDLL("gdi32")
                proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                          wintypes.LPARAM)
                user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                                   wintypes.LPARAM]
                user32.CallWindowProcW.restype = ctypes.c_ssize_t
                user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
                user32.SetWindowLongPtrW.restype = ctypes.c_void_p
                user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
                gdi32.GetClipBox.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT)]
                gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
                gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
                gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
                _win_api = (ctypes, wintypes, user32, gdi32, proc)
            except Exception:
                _win_api = False
    return _win_api or None


class _FastFrame(tk.Frame):
    """A tall frame whose background Windows paints, only where needed. Assigned with __class__ (see _make_fast);
    reports and accepts its real colour, so the rest of the app sees an ordinary frame."""

    def _rt_set_color(self, color):
        api = _api()
        ctypes, _w, _u, gdi32, _p = api
        r, g, b = (v // 257 for v in self.winfo_rgb(color))
        brush = gdi32.CreateSolidBrush(r | (g << 8) | (b << 16))
        old, self._rt_brush, self._rt_bg = getattr(self, "_rt_brush", None), brush, color
        if old:
            gdi32.DeleteObject(old)
        try:
            _u.InvalidateRect(self.winfo_id(), None, True)   # repaint the visible part in the new colour
        except Exception:
            pass

    def configure(self, cnf=None, **kw):
        if cnf is None and not kw:
            return tk.Frame.configure(self)
        if isinstance(cnf, str):                     # configure("bg") -> option description
            return tk.Frame.configure(self, cnf)
        kw = dict(cnf or {}, **kw)
        color = None
        for k in _BG_KEYS:
            if k in kw:
                color = kw.pop(k)
        if color:
            self._rt_set_color(color)
        if kw:
            return tk.Frame.configure(self, **kw)

    config = configure

    def cget(self, key):
        if key in _BG_KEYS:
            return self._rt_bg
        return tk.Frame.cget(self, key)

    __getitem__ = cget

    def __setitem__(self, key, value):
        self.configure({key: value})


def _make_fast(frame):
    api = _api()
    if api is None or type(frame) is not tk.Frame:
        return False
    ctypes, wintypes, user32, gdi32, WNDPROC = api
    color = frame.cget("bg")
    if not color:
        return False
    hwnd = frame.winfo_id()
    state = {"old": None}

    def proc(h, msg, wp, lp):
        if msg == 0x0014:                                # WM_ERASEBKGND: fill only what Windows asks for
            brush = getattr(frame, "_rt_brush", None)
            if brush:
                rc = wintypes.RECT()
                gdi32.GetClipBox(wp, ctypes.byref(rc))
                user32.FillRect(wp, ctypes.byref(rc), brush)
                return 1
        return user32.CallWindowProcW(state["old"], h, msg, wp, lp)

    p = WNDPROC(proc)
    _procs.append(p)
    frame.__class__ = _FastFrame
    frame._rt_set_color(color)
    state["old"] = user32.SetWindowLongPtrW(hwnd, -4, ctypes.cast(p, ctypes.c_void_p))   # GWLP_WNDPROC
    tk.Frame.configure(frame, bg="")                     # Tk stops painting the whole frame on every move
    return True


def speed_up_tall_frames(cv):
    """Switches frames inside scroll canvas `cv` that are over twice its visible height to _FastFrame."""
    if _api() is None:
        return 0
    try:
        items = cv.find_withtag("all")
        inner = next((cv.nametowidget(cv.itemcget(i, "window")) for i in items if cv.type(i) == "window"), None)
        if inner is None:
            return 0
        limit = 2 * max(1, cv.winfo_height())
    except (tk.TclError, KeyError):
        return 0
    done = 0

    def visit(w):
        nonlocal done
        try:
            if w.winfo_height() <= limit:
                return
            if type(w) is tk.Frame and _make_fast(w):
                done += 1
            for c in w.winfo_children():
                if isinstance(c, tk.Frame):
                    visit(c)
        except tk.TclError:
            pass
    visit(inner)
    return done


def smooth_scroll(cv, units_per_tick=3):
    """Replace direct yview_scroll for wheel input on canvas `cv` with a coalescing, flicker-free version.
    Sets cv.wheel_scroll(delta_units) which the app's global wheel handler calls."""
    state = {"pending": 0, "job": None}
    user32 = _win32()

    def apply():
        state["job"] = None
        n, state["pending"] = state["pending"], 0
        if not n:
            return
        try:
            speed_up_tall_frames(cv)                               # see 3. in the module notes
        except Exception:
            pass
        hwnd = None
        if user32 is not None:
            try:
                hwnd = cv.winfo_id()
                user32.SendMessageW(hwnd, 0x000B, 0, 0)            # WM_SETREDRAW off
            except Exception:
                hwnd = None
        try:
            cv.yview_scroll(n, "units")
            cv.update_idletasks()
        except tk.TclError:
            return
        finally:
            if hwnd is not None:
                try:
                    user32.SendMessageW(hwnd, 0x000B, 1, 0)         # WM_SETREDRAW on
                    # RDW_INVALIDATE | RDW_ERASE | RDW_ALLCHILDREN | RDW_UPDATENOW | RDW_FRAME
                    user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100 | 0x0400)
                except Exception:
                    pass

    def wheel_scroll(units):
        state["pending"] += units
        if state["job"] is None:
            try:
                state["job"] = cv.after(16, apply)
            except tk.TclError:
                pass

    cv.wheel_scroll = wheel_scroll
    return cv
