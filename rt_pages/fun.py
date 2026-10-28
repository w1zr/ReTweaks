"""Fun tools (from RETWEAKS): mouse polling rate, clicks per second, reaction time. Real measurements
only; the maths lives in core/funtools.py, unchanged. Settings: fun_cps_best, fun_reaction_best_ms."""
import collections
import sys
import threading
import time
import tkinter as tk

from core import funtools as ft
from rt_pages.common import NA

now = time.perf_counter

TK_NOTE = "Measured through window mouse events; real polling rate may be higher."
RAW_NOTE = ("Measured from raw mouse input (WM_INPUT), counted when each message reaches this app. "
            "A busy PC can bunch messages, so treat it as an estimate.")


# ------------------------------------------------------------------ raw input (Windows)

class RawMouseListener:
    """Receives raw mouse input (WM_INPUT) on a hidden message-only window with its own thread, so Tk's
    own window procedure is never touched. Movement timestamps are queued while `inside` is True."""

    def __init__(self):
        self.times = collections.deque()
        self.inside = False
        self.ok = False
        self.error = None
        self._hwnd = None
        self._thread = None
        self._ready = threading.Event()
        self._procs = []        # every window procedure ever handed to Windows stays alive (see _run)

    def start(self, timeout=1.0):
        if sys.platform != "win32":
            self.error = "Raw input is only available on Windows."
            return False
        if self._thread and self._thread.is_alive():
            return self.ok
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self.ok

    def stop(self):
        hwnd, self._hwnd = self._hwnd, None
        if hwnd:
            try:
                import ctypes
                ctypes.windll.user32.PostMessageW(hwnd, 0x0012, 0, 0)     # WM_QUIT ends the loop
            except Exception:
                pass
        self.ok = False

    def _run(self):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            LRESULT = ctypes.c_ssize_t
            WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

            class WNDCLASSW(ctypes.Structure):
                _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                            ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                            ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                            ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

            class RAWINPUTDEVICE(ctypes.Structure):
                _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                            ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]

            class RAWINPUTHEADER(ctypes.Structure):
                _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                            ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]

            class RAWMOUSE(ctypes.Structure):
                _fields_ = [("usFlags", wintypes.USHORT), ("ulButtons", wintypes.ULONG),
                            ("ulRawButtons", wintypes.ULONG), ("lLastX", wintypes.LONG),
                            ("lLastY", wintypes.LONG), ("ulExtraInformation", wintypes.ULONG)]

            class RAWINPUT(ctypes.Structure):
                _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]

            user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.DefWindowProcW.restype = LRESULT
            user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                               ctypes.POINTER(wintypes.UINT), wintypes.UINT]
            user32.GetRawInputData.restype = wintypes.UINT
            user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
            user32.RegisterRawInputDevices.restype = wintypes.BOOL
            user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                               ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                               wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
            user32.CreateWindowExW.restype = wintypes.HWND
            user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
            user32.RegisterClassW.restype = wintypes.ATOM
            user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
            user32.GetMessageW.restype = wintypes.BOOL
            user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user32.DispatchMessageW.restype = LRESULT
            user32.DestroyWindow.argtypes = [wintypes.HWND]
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE
            WM_INPUT, RID_INPUT, RIDEV_INPUTSINK, RIM_TYPEMOUSE = 0x00FF, 0x10000003, 0x00000100, 0
            HWND_MESSAGE = wintypes.HWND(-3)

            def proc(hwnd, msg, wp, lp):
                if msg == WM_INPUT and self.inside:
                    try:
                        raw = RAWINPUT()
                        size = wintypes.UINT(ctypes.sizeof(raw))
                        got = user32.GetRawInputData(lp, RID_INPUT, ctypes.byref(raw), ctypes.byref(size),
                                                     ctypes.sizeof(RAWINPUTHEADER))
                        if got != 0xFFFFFFFF and raw.header.dwType == RIM_TYPEMOUSE and \
                                (raw.mouse.lLastX != 0 or raw.mouse.lLastY != 0):
                            self.times.append(now())
                    except Exception:
                        pass
                return user32.DefWindowProcW(hwnd, msg, wp, lp)

            # Opening the page again reruns this. Up to 2.0.9 the second RegisterClassW failed (same name)
            # and Windows kept the first run's procedure, which Python had freed: the app crashed on the next
            # message. Now the class is unregistered when the loop ends, and no procedure is ever freed.
            self._proc = WNDPROC(proc)
            self._procs.append(self._proc)
            hinst = kernel32.GetModuleHandleW(None)
            cls = WNDCLASSW()
            cls.lpfnWndProc = self._proc
            cls.hInstance = hinst
            cls.lpszClassName = f"RETWEAKS_RawMouse_{id(self)}"
            user32.RegisterClassW(ctypes.byref(cls))
            hwnd = user32.CreateWindowExW(0, cls.lpszClassName, "", 0, 0, 0, 0, 0, HWND_MESSAGE, None, hinst, None)
            if not hwnd:
                raise OSError(f"CreateWindowExW failed ({ctypes.get_last_error()})")
            dev = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, hwnd)
            if not user32.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(dev)):
                user32.DestroyWindow(hwnd)
                raise OSError(f"RegisterRawInputDevices failed ({ctypes.get_last_error()})")
            self._hwnd = hwnd
            self.ok = True
        except Exception as e:
            self.error = str(e)
            self.ok = False
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        try:
            user32.DestroyWindow(hwnd)
            user32.UnregisterClassW(cls.lpszClassName, hinst)
        except Exception:
            pass
        self.ok = False


# ------------------------------------------------------------------ widgets

class ClickArea(tk.Canvas):
    """Rounded coloured box with centred text that reports left-button presses."""

    def __init__(self, parent, g, text="", height=190):
        super().__init__(parent, height=height, bg=parent.cget("bg"), highlightthickness=0, bd=0, cursor="hand2")
        self.g, self.text, self.colors = g, text, (g["PANEL"], g["FG"], g["LINE"])
        self.on_press = None
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<ButtonPress-1>", lambda e: self.on_press and self.on_press())

    def paint(self, bg, fg, border):
        self.colors = (bg, fg, border)
        self.draw()

    def set_text(self, text):
        self.text = text
        self.draw()

    def draw(self):
        w, h = max(self.winfo_width(), 40), max(self.winfo_height(), 40)
        bg, fg, border = self.colors
        self.delete("all")
        self.create_polygon(self.g["rr"](1, 1, w - 1, h - 1, 14), smooth=True, fill=bg, outline=border)
        self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=(self.g["UI"], 15), justify="center",
                         width=max(80, w - 40))


class FunPage:
    TITLE = "Fun tools"
    SUB = "Three quick tests. Every number comes from a real measurement on this PC."
    MODES = ("Mouse polling rate", "Clicks per second", "Reaction time")

    def __init__(self, hub, tab, g):
        self.hub, self.tab, self.g = hub, tab, g
        self._job = None
        self._shown = False
        self.raw = RawMouseListener()
        g["page_header"](tab, "RETWEAKS", self.TITLE, self.SUB)
        body = hub._scroll_area(tab)
        self.mode = tk.StringVar(value=self.MODES[0])
        seg_row = tk.Frame(body, bg=g["BG"])
        seg_row.pack(fill="x", pady=(0, 6))
        seg = g["Segmented"](seg_row, self.MODES, self.mode, command=self._switch)
        for b in seg.btns.values():      # wider buttons for the long labels
            b.bw = g["text_w"]((g["UI"], 10, "bold"), b.label) + 36
            b.configure(width=b.bw)
            b._draw()
        seg.pack(anchor="w")
        self.frames = {}
        self.holder = tk.Frame(body, bg=g["BG"])
        self.holder.pack(fill="x")
        self.frames[self.MODES[0]] = self._build_polling(self.holder)
        self.frames[self.MODES[1]] = self._build_cps(self.holder)
        self.frames[self.MODES[2]] = self._build_reaction(self.holder)
        self._switch()
        self._paint_all()

    # ------------------------------------------------------------ helpers
    def _colors(self, kind):
        g = self.g
        risk = g.get("RISKCOL", {})
        bg = {"idle": g["PANEL"], "good": g["GREEN"], "bad": risk.get("Advanced", "#ff5c5c"),
              "warn": risk.get("Medium", "#ffb020")}[kind]
        fg = "#141416" if kind in ("good", "bad", "warn") else g["FG"]
        return bg, fg, g["LINE"]

    def _box(self, area, kind="idle"):
        area.paint(*self._colors(kind))

    def _paint_all(self):
        self._box(self.poll_box)
        self._box(self.cps_box)
        self._paint_reaction()

    def _card(self, parent, title):
        c = self.g["Card"](parent)
        c.pack(fill="x", pady=6, padx=(0, 12))
        tk.Label(c.body, text=title, bg=c.body.cget("bg"), fg=self.g["FG"], font=(self.g["UI"], 14, "bold"),
                 anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        return c.body

    def _text(self, parent, text, muted=False):
        lbl = tk.Label(parent, text=text, bg=parent.cget("bg"), fg=self.g["MUTED"] if muted else self.g["FG"],
                       font=(self.g["UI"], 9 if muted else 10), anchor="w", justify="left", wraplength=760)
        lbl.pack(fill="x", padx=16, pady=3)
        return lbl

    def _stats(self, parent, titles):
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", padx=16, pady=(8, 2))
        out = []
        for t in titles:
            col = tk.Frame(row, bg=row.cget("bg"))
            col.pack(side="left", padx=(0, 48))
            tk.Label(col, text=t, bg=col.cget("bg"), fg=self.g["MUTED"], font=(self.g["UI"], 9), anchor="w").pack(anchor="w")
            v = tk.Label(col, text=NA, bg=col.cget("bg"), fg=self.g["FG"], font=(self.g["UI"], 14, "bold"), anchor="w")
            v.pack(anchor="w")
            out.append(v)
        return out

    def _switch(self):
        for name, f in self.frames.items():
            f.pack_forget()
        self.frames[self.mode.get()].pack(fill="x")

    @staticmethod
    def _hz(v):
        return NA if v is None else f"{v:,.0f} Hz"

    # ------------------------------------------------------------ lifecycle
    def on_shown(self):
        self._shown = True
        self._paint_all()
        if sys.platform == "win32" and not self.raw.ok:
            self.raw.start()
        self._update_poll_note()
        if self._job is None:
            self._job = self.hub.after(15, self._tick)

    def on_hidden(self):
        self._shown = False
        self.raw.stop()
        if self._job is not None:
            try:
                self.hub.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def close(self):
        self.on_hidden()

    def _tick(self):
        self._job = None
        t = now()
        # raw-input samples gathered by the listener thread
        while self.raw.times:
            try:
                self.poll_meter.add(self.raw.times.popleft())
            except IndexError:
                break
        if self.poll_meter.total_events:
            cur = None if self.poll_meter.stale(t) else self.poll_meter.current()
            self.p_cur.configure(text=self._hz(cur))
            self.p_avg.configure(text=self._hz(self.poll_meter.average()))
            self.p_max.configure(text=self._hz(self.poll_meter.maximum()))
        if self.cps and self.cps.start is not None and not self._cps_done:
            self.cps_time.configure(text=f"{max(self.cps.duration - self.cps.elapsed(t), 0):.1f} s left")
            self.cps_now.configure(text=f"{self.cps.cps(t):.1f}")
            if self.cps.finished(t):
                self._cps_finish(t)
        if self.rx.tick(t):
            self._paint_reaction()
            self.rx_box.set_text("Click now")
        if self._shown:
            try:
                self._job = self.hub.after(15, self._tick)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ polling rate
    def _build_polling(self, parent):
        f = tk.Frame(parent, bg=self.g["BG"])
        c = self._card(f, "Mouse polling rate")
        self._text(c, "Move the mouse fast in circles")
        self.poll_meter = ft.PollingMeter()
        self.poll_box = ClickArea(c, self.g, "Move the mouse in here")
        self.poll_box.pack(fill="x", padx=16, pady=6)
        self.poll_box.bind("<Enter>", lambda e: setattr(self.raw, "inside", True), add="+")
        self.poll_box.bind("<Leave>", lambda e: setattr(self.raw, "inside", False), add="+")
        self.poll_box.bind("<Motion>", self._tk_motion, add="+")
        self.p_cur, self.p_avg, self.p_max = self._stats(c, ("Current", "Average (last 5 s)", "Max (last 5 s)"))
        self.poll_note = self._text(c, "", muted=True)
        row = tk.Frame(c, bg=c.cget("bg"))
        row.pack(fill="x", padx=16, pady=(4, 12))
        self.g["RButton"](row, "Reset", self._poll_reset, kind="default").pack(side="left")
        self._update_poll_note()
        return f

    def _tk_motion(self, _e):
        if not self.raw.ok:          # raw input not available: fall back to window mouse events
            self.poll_meter.add(now())

    def _update_poll_note(self):
        self.poll_note.configure(text=RAW_NOTE if self.raw.ok else TK_NOTE)

    def _poll_reset(self):
        self.poll_meter.reset()
        self.raw.times.clear()
        for lbl in (self.p_cur, self.p_avg, self.p_max):
            lbl.configure(text=NA)

    # ------------------------------------------------------------ clicks per second
    def _build_cps(self, parent):
        f = tk.Frame(parent, bg=self.g["BG"])
        c = self._card(f, "Clicks per second")
        self.cps_secs = tk.StringVar(value="5 s")
        mode = tk.Frame(c, bg=c.cget("bg"))
        mode.pack(fill="x", padx=16, pady=4)
        self.g["Segmented"](mode, ("5 s", "10 s"), self.cps_secs).pack(anchor="w")
        self.cps = None
        self._cps_done = False
        self.cps_box = ClickArea(c, self.g, "Click here as fast as you can.\nThe timer starts on your first click.")
        self.cps_box.on_press = self._cps_click
        self.cps_box.pack(fill="x", padx=16, pady=6)
        self.cps_now, self.cps_time, self.cps_best = self._stats(c, ("CPS", "Time", "Best"))
        best = self.hub.settings.get("fun_cps_best")
        self.cps_best.configure(text=f"{best:.1f}" if isinstance(best, (int, float)) else NA)
        self._text(c, "Best score is saved across both modes.", muted=True).pack_configure(pady=(3, 12))
        return f

    def _cps_click(self):
        t = now()
        if self.cps is None or self._cps_done:
            self._cps_done = False
            self.cps = ft.CpsTest(int(self.cps_secs.get().split()[0]))
            self._box(self.cps_box, "warn")
        if self.cps.click(t):
            self.cps_box.set_text(f"{self.cps.clicks} clicks")

    def _cps_finish(self, t):
        score = self.cps.cps()
        old = self.hub.settings.get("fun_cps_best")
        old = old if isinstance(old, (int, float)) else None
        msg = f"{score:.1f} CPS  ({self.cps.clicks} clicks in {self.cps.duration:.0f} s)"
        if ft.is_new_best(score, old):
            self.hub.settings["fun_cps_best"] = round(score, 2)
            self.hub.save_settings()
            self.cps_best.configure(text=f"{score:.1f}")
            msg += "\nNew best!"
        self.cps_now.configure(text=f"{score:.1f}")
        self.cps_time.configure(text="0.0 s left")
        self.cps_box.set_text(msg + "\nClick to try again.")
        self._box(self.cps_box)
        self._cps_done = True

    # ------------------------------------------------------------ reaction
    def _build_reaction(self, parent):
        f = tk.Frame(parent, bg=self.g["BG"])
        c = self._card(f, "Reaction time")
        self._text(c, "Click when the box turns green. Average of 5 tries.")
        self.rx = ft.ReactionTest(5)
        self.rx_box = ClickArea(c, self.g, "Click to start")
        self.rx_box.on_press = self._rx_click
        self.rx_box.pack(fill="x", padx=16, pady=6)
        self.rx_last, self.rx_avg, self.rx_best = self._stats(c, ("Last", "Average", "Best ever"))
        best = self.hub.settings.get("fun_reaction_best_ms")
        self.rx_best.configure(text=f"{best:.0f} ms" if isinstance(best, (int, float)) else NA)
        self._text(c, "Time is measured from when the box changes color to your click (the screen and mouse add "
                      "their own small delay).", muted=True).pack_configure(pady=(3, 12))
        return f

    def _paint_reaction(self):
        kind = {"waiting": "bad", "ready": "good", "too_soon": "warn"}.get(self.rx.state, "idle")
        self._box(self.rx_box, kind)

    def _rx_click(self):
        t = now()
        st = self.rx.state
        if st in ("idle", "shown", "too_soon", "done"):
            if st == "done":
                self.rx.reset()
                self.rx_avg.configure(text=NA)
                self.rx_last.configure(text=NA)
            self.rx.begin_try(t)
            self.rx_box.set_text("Wait for green...")
            self._paint_reaction()
            return
        outcome = self.rx.click(t)
        if outcome == "too_soon":
            self.rx_box.set_text("Too soon. Click to try again.")
        elif outcome in ("shown", "done"):
            self.rx_last.configure(text=f"{self.rx.last_ms:.0f} ms")
            self.rx_avg.configure(text=f"{self.rx.average_ms():.0f} ms ({len(self.rx.results_ms)}/5)")
            text = f"{self.rx.last_ms:.0f} ms"
            if outcome == "done":
                text += f"\nAverage of 5: {self.rx.average_ms():.0f} ms. Click to restart."
                best = self.rx.best_ms()
                old = self.hub.settings.get("fun_reaction_best_ms")
                old = old if isinstance(old, (int, float)) else None
                if ft.is_new_best(best, old, lower_is_better=True):
                    self.hub.settings["fun_reaction_best_ms"] = round(best, 1)
                    self.hub.save_settings()
                    self.rx_best.configure(text=f"{best:.0f} ms")
                    text += "\nNew best!"
            else:
                text += "\nClick for the next try."
            self.rx_box.set_text(text)
        self._paint_reaction()
