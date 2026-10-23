# ui/splash.py
"""Startup splash: the chip-scan animation (owner choice 2026-10-21, design canvas "Splash C").

The chip outline draws, the pins light up in sequence, a scan line sweeps, the R traces in,
then the RETWEAKS wordmark and an honest status line appear.

Timing rules (CLAUDE.md section 18a, owner update 2026-10-21):
- The reveal always plays at normal speed (about 1.4 s), so it never looks rushed or cut off.
- If loading takes longer, the scan line keeps sweeping until loading really finishes.
- Then a short pause on the finished logo and a slow cross-fade: the main window opens centered
  behind the splash and fades in while the splash fades out. No version number is shown.

The UI thread is busy while the main window is being built, so MainWindow calls pump()
between steps. Frames are drawn from real elapsed time, so the animation stays correct even
if a step takes a moment.
"""

from PySide6.QtCore import QElapsedTimer, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from core.version import BRAND
from ui.widgets.brand import LOGO_COLOR, paint_chip

WIDTH, HEIGHT = 600, 360
BG, BORDER, SUBTEXT = "#000000", "#141518", "#9aa0a6"   # pure black (owner request 2026-10-22)

# Timeline at normal speed, in seconds
CHIP = (0.00, 0.55)
PIN_START, PIN_STEP, PIN_FADE = 0.22, 0.05, 0.18
SCAN = (0.50, 1.00)
R_TRACE = (0.80, 1.22)
WORD = (1.10, 1.40)
REVEAL_END = 1.40
SCAN_LOOP = 0.9           # one sweep while waiting for loading to finish
HOLD = 0.30               # pause on the finished logo before fading
FADE = 0.55               # cross-fade into the main window


def _phase(t, span):
    a, b = span
    if t <= a:
        return 0.0
    if t >= b:
        return 1.0
    x = (t - a) / (b - a)
    return x * x * (3 - 2 * x)   # smoothstep


class RetweaksSplash(QWidget):
    done = Signal()      # the fade into the window finished (or the splash was aborted)

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
        self._ready_at = None
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
        """Loading is really done: let the reveal finish at normal speed, then fade into `window`."""
        self._finishing = (window, show or window.show)
        self._ready_at = None
        self.status = "Ready"

    def abort(self):
        """Startup failed: never leave the splash on screen."""
        self._timer.stop()
        self._done = True
        self.close()
        self.done.emit()

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

    def _center_window(self, window):
        """Open the main window centered on the same screen as the splash, so it fades in behind it."""
        screen = self.screen() or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        size = window.frameGeometry().size() if window.frameGeometry().isValid() else window.size()
        window.move(g.x() + max(0, (g.width() - size.width()) // 2), g.y() + max(0, (g.height() - size.height()) // 2))

    def _tick(self):
        if self._done:
            return
        real = self._advance()
        if self._finishing and self._virtual >= REVEAL_END:
            window, show = self._finishing
            if self._ready_at is None:
                self._ready_at = real
            elif self._fade_start is None and real - self._ready_at >= HOLD:
                # Show the window invisibly first, so its first (slow) paint happens before the fade
                self._center_window(window)
                window.setWindowOpacity(0.0)
                show()
                self.raise_()
                self._fade_start = real + 0.05
            if self._fade_start is not None and real >= self._fade_start:
                x = min(1.0, (real - self._fade_start) / FADE)
                f = x * x * (3 - 2 * x)          # ease in and out
                self.setWindowOpacity(1.0 - f)
                window.setWindowOpacity(f)
                if x >= 1.0:
                    self._done = True
                    self._timer.stop()
                    window.setWindowOpacity(1.0)
                    window.raise_()
                    window.activateWindow()
                    self.close()
                    self.done.emit()
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
            f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
            p.setFont(f)
            p.drawText(QRectF(0, 200, WIDTH, 44), Qt.AlignCenter, BRAND)
            p.setPen(QColor(SUBTEXT))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(0, 250, WIDTH, 24), Qt.AlignCenter, self.status)
            p.setOpacity(1.0)
        p.end()
