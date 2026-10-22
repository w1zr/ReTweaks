# ui/splash.py
"""Startup splash: the chip-scan animation (owner choice 2026-10-21, design canvas "Splash C").

The chip outline draws, the pins light up in sequence, a scan line sweeps, the R traces in,
then the RYTWEAKS wordmark and an honest status line appear.

Timing rules (CLAUDE.md section 18a):
- If loading finishes in under ~1 s, the rest of the animation is sped up so the whole thing
  takes about 1 s and never looks cut off.
- If loading takes longer, the scan line keeps sweeping until loading really finishes.
- Nothing ever waits longer than that. No version number is shown.

The UI thread is busy while the main window is being built, so MainWindow calls pump()
between steps. Frames are drawn from real elapsed time, so the animation stays correct even
if a step takes a moment.
"""

from PySide6.QtCore import QElapsedTimer, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from ui.widgets.brand import LOGO_COLOR, paint_chip

WIDTH, HEIGHT = 600, 360
BG, BORDER, SUBTEXT = "#0b0d10", "#1f232a", "#9aa0a6"

# Timeline at normal speed, in seconds
CHIP = (0.00, 0.55)
PIN_START, PIN_STEP, PIN_FADE = 0.22, 0.05, 0.18
SCAN = (0.50, 1.00)
R_TRACE = (0.80, 1.22)
WORD = (1.10, 1.40)
REVEAL_END = 1.40
SCAN_LOOP = 0.9           # one sweep while waiting for loading to finish
QUICK_TOTAL = 1.0         # the "about 1 s" quick version
LATE_FINISH = 0.30        # if loading was slow, finish the reveal this fast
FADE = 0.18


def _phase(t, span):
    a, b = span
    if t <= a:
        return 0.0
    if t >= b:
        return 1.0
    x = (t - a) / (b - a)
    return x * x * (3 - 2 * x)   # smoothstep


class RytweaksSplash(QWidget):
    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)
        self.status = "Starting…"
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last_real = 0.0
        self._virtual = 0.0          # animation time
        self._speed = 1.0
        self._finishing = None       # window to show once the reveal completes
        self._fade_start = None
        self._done = False
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.center_on_screen()

    # ------------------------------------------------------------------ public

    def start(self):
        self.show()
        self._timer.start()
        self.pump()

    def pump(self, status=None):
        """Called from the UI thread during startup so the animation keeps moving."""
        if status:
            self.status = status
        QApplication.processEvents()

    def finish(self, window, show=None):
        """Loading is really done: complete the reveal quickly, then fade into `window`."""
        self._finishing = (window, show or window.show)
        self._advance()
        now = self._clock.elapsed() / 1000.0
        remaining = max(0.0, REVEAL_END - self._virtual)
        if remaining <= 0:
            self._speed = 1.0
        elif now < QUICK_TOTAL:
            self._speed = remaining / max(0.05, QUICK_TOTAL - now)
        else:
            self._speed = remaining / LATE_FINISH
        self._speed = max(1.0, self._speed)
        self.status = "Ready"

    def abort(self):
        """Startup failed: never leave the splash on screen."""
        self._timer.stop()
        self._done = True
        self.close()

    def center_on_screen(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        self.move(g.x() + (g.width() - WIDTH) // 2, g.y() + (g.height() - HEIGHT) // 2)

    # ------------------------------------------------------------------ animation

    def _advance(self):
        real = self._clock.elapsed() / 1000.0
        dt = max(0.0, real - self._last_real)
        self._last_real = real
        self._virtual += dt * self._speed
        return real

    def _tick(self):
        if self._done:
            return
        real = self._advance()
        if self._finishing and self._virtual >= REVEAL_END:
            if self._fade_start is None:
                self._fade_start = real
                window, show = self._finishing
                window.setWindowOpacity(0.0)
                show()
            f = min(1.0, (real - self._fade_start) / FADE)
            self.setWindowOpacity(1.0 - f)
            self._finishing[0].setWindowOpacity(f)
            if f >= 1.0:
                self._done = True
                self._timer.stop()
                self.close()
                return
        self.update()

    def paintEvent(self, _):
        t = self._virtual
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor(BG))
        p.drawRoundedRect(QRectF(0.5, 0.5, WIDTH - 1, HEIGHT - 1), 12, 12)

        pins = [_phase(t, (PIN_START + i * PIN_STEP, PIN_START + i * PIN_STEP + PIN_FADE)) for i in range(12)]
        pins = [0.12 + 0.88 * a for a in pins] if t > 0.05 else [0.0] * 12
        scan = None
        if SCAN[0] <= t <= SCAN[1]:
            scan = _phase(t, SCAN)
        elif t > REVEAL_END and not self._finishing:
            # still loading: keep the scan line sweeping (down, then up)
            k = ((t - REVEAL_END) % (2 * SCAN_LOOP)) / SCAN_LOOP
            scan = k if k <= 1 else 2 - k
        logo = QRectF((WIDTH - 120) / 2, 62, 120, 120)
        paint_chip(p, logo, LOGO_COLOR, chip=_phase(t, CHIP), pins=pins, r=_phase(t, R_TRACE), scan=scan)

        word = _phase(t, WORD)
        if word > 0:
            p.setOpacity(word)
            p.setPen(QColor(LOGO_COLOR))
            f = QFont("Segoe UI", 22, QFont.Bold)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 8)
            p.setFont(f)
            p.drawText(QRectF(0, 200, WIDTH, 44), Qt.AlignCenter, "RYTWEAKS")
            p.setPen(QColor(SUBTEXT))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(0, 250, WIDTH, 24), Qt.AlignCenter, self.status)
            p.setOpacity(1.0)
        p.end()
