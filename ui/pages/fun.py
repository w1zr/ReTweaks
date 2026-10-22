# ui/pages/fun.py
"""Fun tools: mouse polling rate, clicks per second, reaction time. Real measurements only."""

import sys
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QPushButton, QRadioButton,
                               QTabWidget, QVBoxLayout, QWidget)

from core import funtools as ft
from ui.widgets.common import Card, NA, Page, label, set_role

now = time.perf_counter

QT_NOTE = "Measured through Qt mouse events; real polling rate may be higher."
RAW_NOTE = ("Measured from raw mouse input (WM_INPUT), counted when each message reaches "
            "this app. A busy PC can bunch messages, so treat it as an estimate.")


# ------------------------------------------------------------------ raw input (Windows)

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _WM_INPUT = 0x00FF
    _RID_INPUT = 0x10000003
    _RIDEV_INPUTSINK = 0x00000100
    _RIM_TYPEMOUSE = 0

    class _RAWINPUTDEVICE(ctypes.Structure):
        _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                    ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]

    class _RAWINPUTHEADER(ctypes.Structure):
        _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                    ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]

    class _RAWMOUSE(ctypes.Structure):
        _fields_ = [("usFlags", wintypes.USHORT), ("ulButtons", wintypes.ULONG),
                    ("ulRawButtons", wintypes.ULONG), ("lLastX", wintypes.LONG),
                    ("lLastY", wintypes.LONG), ("ulExtraInformation", wintypes.ULONG)]

    class _RAWINPUT(ctypes.Structure):
        _fields_ = [("header", _RAWINPUTHEADER), ("mouse", _RAWMOUSE)]

    def _register_raw_mouse(hwnd):
        try:
            dev = _RAWINPUTDEVICE(0x01, 0x02, _RIDEV_INPUTSINK, hwnd)
            u = ctypes.WinDLL("user32", use_last_error=True)
            u.RegisterRawInputDevices.argtypes = [ctypes.POINTER(_RAWINPUTDEVICE),
                                                  wintypes.UINT, wintypes.UINT]
            u.RegisterRawInputDevices.restype = wintypes.BOOL
            return bool(u.RegisterRawInputDevices(ctypes.byref(dev), 1, ctypes.sizeof(dev)))
        except Exception:
            return False

    def _raw_mouse_moved(lparam):
        """True if this WM_INPUT is a mouse movement."""
        try:
            u = ctypes.WinDLL("user32", use_last_error=True)
            u.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                          ctypes.POINTER(wintypes.UINT), wintypes.UINT]
            u.GetRawInputData.restype = wintypes.UINT
            raw = _RAWINPUT()
            size = wintypes.UINT(ctypes.sizeof(raw))
            got = u.GetRawInputData(lparam, _RID_INPUT, ctypes.byref(raw), ctypes.byref(size),
                                    ctypes.sizeof(_RAWINPUTHEADER))
            if got == 0xFFFFFFFF or raw.header.dwType != _RIM_TYPEMOUSE:
                return False
            return raw.mouse.lLastX != 0 or raw.mouse.lLastY != 0
        except Exception:
            return False


class ClickArea(QLabel):
    """Colored rounded box that reports presses."""
    pressed = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(190)
        self.setWordWrap(True)

    def paint(self, bg, fg, border):
        self.setStyleSheet(f"background:{bg}; color:{fg}; border:1px solid {border}; "
                           "border-radius:14px; padding:12px; font-size:18px;")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.pressed.emit()


class PollBox(ClickArea):
    """Receives mouse moves. Uses raw input on Windows, Qt events otherwise."""
    moved = Signal(float)

    def __init__(self, parent=None):
        super().__init__("Move the mouse in here", parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.inside = False
        self.raw_ok = False
        self._registered_hwnd = None

    def showEvent(self, e):
        super().showEvent(e)
        if sys.platform == "win32":
            hwnd = int(self.winId())
            if hwnd != self._registered_hwnd:
                self._registered_hwnd = hwnd
                self.raw_ok = _register_raw_mouse(hwnd)

    def enterEvent(self, e):
        self.inside = True

    def leaveEvent(self, e):
        self.inside = False

    def mouseMoveEvent(self, e):
        if not self.raw_ok:
            self.moved.emit(now())

    def nativeEvent(self, event_type, message):
        if self.raw_ok and sys.platform == "win32" and bytes(event_type) == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == _WM_INPUT and self.inside and _raw_mouse_moved(msg.lParam):
                    self.moved.emit(now())
            except Exception:
                pass
        return False, 0


class FunPage(Page):
    no_fade = True   # the raw-input box is a native window; Qt can't fade native widgets
    title = "Fun tools"
    subtitle = "Three quick tests. Every number comes from a real measurement on this PC."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_polling(), "Mouse polling rate")
        self.tabs.addTab(self._build_cps(), "Clicks per second")
        self.tabs.addTab(self._build_reaction(), "Reaction time")
        self.content.addWidget(self.tabs)
        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._paint_all()
        self.finish()

    # ------------------------------------------------------------ helpers

    def _t(self, key):
        return self.ctx.theme.get(key, self.ctx.theme.get("text", ""))

    def _box(self, area, kind="idle"):
        bg = {"idle": self._t("card"), "good": self._t("good"), "bad": self._t("bad"),
              "warn": self._t("warn")}[kind]
        fg = self._t("on_accent") if kind in ("good", "bad", "warn") else self._t("text")
        area.paint(bg, fg, self._t("border"))

    def on_theme(self, theme):
        self._paint_all()

    def _paint_all(self):
        self._box(self.poll_box)
        self._box(self.cps_box)
        self._paint_reaction()

    def wait_for_tasks(self):
        self._timer.stop()
        return super().wait_for_tasks()

    def on_shown(self):
        self._paint_all()

    def _tick(self):
        t = now()
        # polling readout refresh
        if self.poll_meter.total_events:
            stale = self.poll_meter.stale(t)
            cur = None if stale else self.poll_meter.current()
            self.p_cur.setText(self._hz(cur))
            self.p_avg.setText(self._hz(self.poll_meter.average()))
            self.p_max.setText(self._hz(self.poll_meter.maximum()))
        # cps
        if self.cps and self.cps.start is not None and not self._cps_done:
            self.cps_time.setText(f"{max(self.cps.duration - self.cps.elapsed(t), 0):.1f} s left")
            self.cps_now.setText(f"{self.cps.cps(t):.1f}")
            if self.cps.finished(t):
                self._cps_finish(t)
        # reaction
        if self.rx.tick(t):
            self._paint_reaction()
            self.rx_box.setText("Click now")

    @staticmethod
    def _hz(v):
        return NA if v is None else f"{v:,.0f} Hz"

    @staticmethod
    def _stat(card, title):
        v = label(NA, "sectionTitle")
        row = QVBoxLayout()
        row.addWidget(label(title, "muted"))
        row.addWidget(v)
        card.addLayout(row)
        return v

    # ------------------------------------------------------------ polling rate

    def _build_polling(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        card = Card("Mouse polling rate")
        card.body.addWidget(label("Move the mouse fast in circles", wrap=True))
        self.poll_meter = ft.PollingMeter()
        self.poll_box = PollBox()
        self.poll_box.moved.connect(self.poll_meter.add)
        card.body.addWidget(self.poll_box)
        row = QHBoxLayout()
        self.p_cur = self._stat(row, "Current")
        self.p_avg = self._stat(row, "Average (last 5 s)")
        self.p_max = self._stat(row, "Max (last 5 s)")
        card.body.addLayout(row)
        self.poll_note = label("", "muted", wrap=True)
        card.body.addWidget(self.poll_note)
        reset = QPushButton("Reset")
        reset.clicked.connect(self._poll_reset)
        card.body.addWidget(reset, 0, Qt.AlignLeft)
        lay.addWidget(card)
        lay.addStretch(1)
        self._update_poll_note()
        return w

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(300, self._update_poll_note)

    def _update_poll_note(self):
        self.poll_note.setText(RAW_NOTE if self.poll_box.raw_ok else QT_NOTE)

    def _poll_reset(self):
        self.poll_meter.reset()
        for lbl in (self.p_cur, self.p_avg, self.p_max):
            lbl.setText(NA)

    # ------------------------------------------------------------ clicks per second

    def _build_cps(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        card = Card("Clicks per second")
        mode_row = QHBoxLayout()
        self.cps_group = QButtonGroup(self)
        for secs in (5, 10):
            rb = QRadioButton(f"{secs} s")
            rb.setProperty("secs", secs)
            self.cps_group.addButton(rb)
            mode_row.addWidget(rb)
            if secs == 5:
                rb.setChecked(True)
        mode_row.addStretch(1)
        card.body.addLayout(mode_row)
        self.cps = None
        self._cps_done = False
        self.cps_box = ClickArea("Click here as fast as you can.\nThe timer starts on your first click.")
        self.cps_box.pressed.connect(self._cps_click)
        card.body.addWidget(self.cps_box)
        row = QHBoxLayout()
        self.cps_now = self._stat(row, "CPS")
        self.cps_time = self._stat(row, "Time")
        best = self.ctx.settings.get("fun_cps_best")
        self.cps_best = self._stat(row, "Best")
        self.cps_best.setText(f"{best:.1f}" if isinstance(best, (int, float)) else NA)
        card.body.addLayout(row)
        card.body.addWidget(label("Best score is saved across both modes.", "muted"))
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    def _cps_secs(self):
        b = self.cps_group.checkedButton()
        return int(b.property("secs")) if b else 5

    def _cps_click(self):
        t = now()
        if self.cps is None or self._cps_done:
            self._cps_done = False
            self.cps = ft.CpsTest(self._cps_secs())
            self._box(self.cps_box, "warn")
        if self.cps.click(t):
            self.cps_box.setText(f"{self.cps.clicks} clicks")

    def _cps_finish(self, t):
        score = self.cps.cps()
        old = self.ctx.settings.get("fun_cps_best")
        old = old if isinstance(old, (int, float)) else None
        msg = f"{score:.1f} CPS  ({self.cps.clicks} clicks in {self.cps.duration:.0f} s)"
        if ft.is_new_best(score, old):
            self.ctx.set_setting("fun_cps_best", round(score, 2))
            self.cps_best.setText(f"{score:.1f}")
            msg += "\nNew best!"
        self.cps_now.setText(f"{score:.1f}")
        self.cps_time.setText("0.0 s left")
        self.cps_box.setText(msg + "\nClick to try again.")
        self._box(self.cps_box)
        self._cps_done = True

    # ------------------------------------------------------------ reaction

    def _build_reaction(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        card = Card("Reaction time")
        card.body.addWidget(label("Click when the box turns green. Average of 5 tries.", wrap=True))
        self.rx = ft.ReactionTest(5)
        self.rx_box = ClickArea("Click to start")
        self.rx_box.pressed.connect(self._rx_click)
        card.body.addWidget(self.rx_box)
        row = QHBoxLayout()
        self.rx_last = self._stat(row, "Last")
        self.rx_avg = self._stat(row, "Average")
        best = self.ctx.settings.get("fun_reaction_best_ms")
        self.rx_best = self._stat(row, "Best ever")
        self.rx_best.setText(f"{best:.0f} ms" if isinstance(best, (int, float)) else NA)
        card.body.addLayout(row)
        card.body.addWidget(label("Time is measured from when the box changes color to your "
                                  "click (the screen and mouse add their own small delay).",
                                  "muted", wrap=True))
        lay.addWidget(card)
        lay.addStretch(1)
        return w

    def _paint_reaction(self):
        kind = {"waiting": "bad", "ready": "good", "too_soon": "warn"}.get(self.rx.state, "idle")
        self._box(self.rx_box, kind)

    def _rx_click(self):
        t = now()
        st = self.rx.state
        if st in ("idle", "shown", "too_soon", "done"):
            if st == "done":
                self.rx.reset()
                self.rx_avg.setText(NA)
                self.rx_last.setText(NA)
            self.rx.begin_try(t)
            self.rx_box.setText("Wait for green...")
            self._paint_reaction()
            return
        outcome = self.rx.click(t)
        if outcome == "too_soon":
            self.rx_box.setText("Too soon. Click to try again.")
        elif outcome in ("shown", "done"):
            self.rx_last.setText(f"{self.rx.last_ms:.0f} ms")
            self.rx_avg.setText(f"{self.rx.average_ms():.0f} ms ({len(self.rx.results_ms)}/5)")
            text = f"{self.rx.last_ms:.0f} ms"
            if outcome == "done":
                avg = self.rx.average_ms()
                text += f"\nAverage of 5: {avg:.0f} ms. Click to restart."
                best = self.rx.best_ms()
                old = self.ctx.settings.get("fun_reaction_best_ms")
                old = old if isinstance(old, (int, float)) else None
                if ft.is_new_best(best, old, lower_is_better=True):
                    self.ctx.set_setting("fun_reaction_best_ms", round(best, 1))
                    self.rx_best.setText(f"{best:.0f} ms")
                    text += "\nNew best!"
            else:
                text += "\nClick for the next try."
            self.rx_box.setText(text)
        self._paint_reaction()
