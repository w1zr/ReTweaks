# ui/workers.py
"""Background threads, so the window never freezes while Windows is being queried."""

import time
import traceback

from PySide6.QtCore import QThread, Signal

from core.hardware import scan_static


class StaticScanWorker(QThread):
    """One-time hardware inventory (1–5 seconds)."""
    done = Signal(dict)

    def run(self):
        try:
            self.done.emit(scan_static())
        except Exception:
            traceback.print_exc()
            self.done.emit({})


class TelemetryWorker(QThread):
    """Emits a live sample every `interval` seconds until stop() is called."""
    sample = Signal(dict)
    sources = Signal(dict)

    def __init__(self, interval=1.0, parent=None):
        super().__init__(parent)
        self.interval = interval
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        # Created here (not in __init__) so COM/WMI objects live on this thread
        from core.telemetry import Telemetry
        try:
            telemetry = Telemetry()
        except Exception:
            traceback.print_exc()
            return
        last_sources = None
        # Counters need time between two readings; the first one would show 0%
        waited = time.monotonic()
        while self._running and time.monotonic() - waited < 1.0:
            self.msleep(50)
        while self._running:
            started = time.monotonic()
            try:
                self.sample.emit(telemetry.sample())
                src = telemetry.sources()
                if src != last_sources:
                    last_sources = src
                    self.sources.emit(src)
            except Exception:
                traceback.print_exc()
            # sleep in small steps so closing the app is instant
            while self._running and time.monotonic() - started < self.interval:
                self.msleep(50)


class TaskWorker(QThread):
    """Runs one function in the background and emits its return value."""
    done = Signal(object)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.done.emit(self.fn(*self.args))
        except Exception as e:
            self.done.emit((False, str(e)))


class AutoGameWorker(QThread):
    """Auto game mode: checks every few seconds whether a watched program started or closed."""
    event = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        from core.app_rules import AutoGameMode, load_rules
        mode = AutoGameMode()
        while self._running:
            try:
                for e in mode.poll(load_rules()):
                    self.event.emit(e)
            except Exception:
                traceback.print_exc()
            for _ in range(60):          # 3 seconds, in small steps so closing is instant
                if not self._running:
                    break
                self.msleep(50)
        for e in mode.restore():         # RYTWEAKS is closing: put the power plan back
            self.event.emit(e)
