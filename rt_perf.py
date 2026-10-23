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
"""
import os
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
