# ui/overlay.py
"""The in-game FPS overlay window: click-through, never takes focus, always on top.
Nothing is injected into the game; this is an ordinary top-level window of RETWEAKS."""

import sys

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from core import overlay_fps as of

FONT_PT = {"small": 11, "medium": 14, "large": 18}

# Win32 constants (used only on Windows)
GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x00080000, 0x00000020
WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = 0x08000000, 0x00000080
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010


class OverlayWindow(QWidget):
    def __init__(self, theme, settings, game_name=""):
        super().__init__(None)
        self.theme = theme
        self.cfg = of.clean_settings(settings)
        self.game_name = game_name
        self.lines = ["FPS –"]
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setFocusPolicy(Qt.NoFocus)
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(2000)
        self._topmost_timer.timeout.connect(self.assert_topmost)

    # ---------------------------------------------------------------- content
    def _font(self):
        f = QFont("Consolas")
        f.setStyleHint(QFont.Monospace)
        f.setFixedPitch(True)
        f.setPointSize(FONT_PT[self.cfg["overlay_size"]])
        f.setBold(True)
        return f

    def set_lines(self, lines):
        if lines != self.lines:
            self.lines = lines
            self._resize_and_place()
            self.update()

    def apply_settings(self, settings):
        self.cfg = of.clean_settings(settings)
        self._resize_and_place()
        self.update()

    def set_theme(self, theme):
        self.theme = theme
        self.update()

    def _resize_and_place(self):
        fm = QFontMetrics(self._font())
        pad = fm.height() // 2
        w = max(fm.horizontalAdvance(t) for t in self.lines) + pad * 2
        h = fm.height() * len(self.lines) + pad * 2
        self.resize(w, h)
        self.reposition()

    def _target_screen(self):
        screens = QGuiApplication.screens()
        rect = of.find_game_window_rect(self.game_name)
        if rect:
            cx, cy = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
            for s in screens:
                g, r = s.geometry(), s.devicePixelRatio()
                if g.x() * r <= cx < (g.x() + g.width()) * r and g.y() * r <= cy < (g.y() + g.height()) * r:
                    return s
        return QGuiApplication.primaryScreen()

    def reposition(self):
        screen = self._target_screen()
        if not screen:
            return
        g = screen.geometry()
        x, y = of.corner_position((g.x(), g.y(), g.width(), g.height()),
                                  (self.width(), self.height()), self.cfg["overlay_position"])
        self.move(QPoint(x, y))

    # ---------------------------------------------------------------- painting
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(self.theme["bg"])
        bg.setAlphaF(self.cfg["overlay_opacity"] / 100.0)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        p.setFont(self._font())
        fm = p.fontMetrics()
        pad = fm.height() // 2
        y = pad + fm.ascent()
        for i, t in enumerate(self.lines):
            color = self.theme["text"] if i == 0 or len(self.lines) == 1 else self.theme["subtext"]
            p.setPen(QColor(color))
            p.drawText(pad, y, t)
            y += fm.height()
        p.end()

    # ---------------------------------------------------------------- Windows behavior
    def show_overlay(self):
        self._resize_and_place()
        self.show()
        self._apply_native_styles()
        self.assert_topmost()
        self._topmost_timer.start()

    def hide_overlay(self):
        self._topmost_timer.stop()
        self.hide()

    def _hwnd(self):
        return int(self.winId())

    def _apply_native_styles(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            hwnd = self._hwnd()
            ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            ex |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
        except Exception:
            pass

    def assert_topmost(self):
        if sys.platform != "win32" or not self.isVisible():
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            user32.SetWindowPos(self._hwnd(), HWND_TOPMOST, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception:
            pass
