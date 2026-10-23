"""The real RETWEAKS v1.6 startup screen (ui/splash.py, Qt), run in its own small process.

Owner request 2026-10-22: the startup must look exactly like v1.6, be smooth, and last longer so the app
has time to load. The Tk app builds its pages on its only UI thread, so an animation drawn by Tk can only
move between pages (choppy). This process draws the original Qt splash on its own thread of control, so it
stays smooth however busy the app is.

Started by the app as `RETWEAKS.exe --rt-splash` (rt_splash_client). Talks over stdin/stdout, one line each:
  in:  "status <text>"   update the status line
       "ready"           the app finished loading: finish the reveal, hold, then cross-fade
       "quit"            close now (startup failed)
       (end of input)    the app went away: close now
  out: "show"            show the main window now, fully transparent (the cross-fade starts)
       "alpha <0..1>"    main window opacity during the cross-fade
       "done"            the splash is gone; the main window should be fully visible
Same timing rules as v1.6 (no version number, no fake waiting), only slower: SLOWER stretches the reveal
and the scan loop; the hold and the cross-fade stay as in v1.6.
"""
import os
import sys
import threading

SLOWER = 1.7          # 1.4 s reveal -> about 2.4 s (owner: "make it longer so everything has more time to load")


def _std_streams():
    """In a windowed .exe Python may leave sys.stdin/stdout as None; the parent's pipes are still the
    process's standard handles, so open them directly."""
    import io
    if sys.stdout is None or sys.stdin is None:
        try:
            import msvcrt
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.GetStdHandle.restype = ctypes.c_void_p
            for name, num, mode in (("stdin", -10, "r"), ("stdout", -11, "w")):
                if getattr(sys, name) is None:
                    h = k32.GetStdHandle(num)
                    if h and h != ctypes.c_void_p(-1).value:
                        fd = msvcrt.open_osfhandle(h, os.O_RDONLY if mode == "r" else os.O_WRONLY)
                        setattr(sys, name, io.open(fd, mode, encoding="utf-8", buffering=1 if mode == "w" else -1))
        except Exception:
            pass
    # The app always sends UTF-8. Streams Python opened by itself use the Windows code page (cp1252), which turned
    # "Loading Settings…" into "Loading Settingsâ€¦" (owner report 2026-10-23), so force UTF-8 on both.
    for stream in (sys.stdin, sys.stdout):
        try:
            if stream is not None and (getattr(stream, "encoding", "") or "").lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _send(line):
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def main():
    _std_streams()
    if sys.stdout is None or sys.stdin is None:
        return 2                                   # no way to talk to the app: let it use its own startup
    from PySide6.QtCore import QObject, QRect, QSize, Qt, Signal
    from PySide6.QtWidgets import QApplication

    from ui.splash import RetweaksSplash

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)

    class Bridge(QObject):
        line = Signal(str)

    class RemoteWindow:
        """Stands in for the main window: RetweaksSplash fades `window` in; here that means telling the app."""
        def __init__(self):
            self.shown = False
            self.last = -1.0

        def frameGeometry(self):
            return QRect()                       # invalid -> the splash uses size(); the app places itself

        def size(self):
            return QSize(0, 0)

        def move(self, *a):
            pass

        def show(self):
            self.shown = True
            _send("show")

        def setWindowOpacity(self, f):
            f = round(float(f), 3)
            if self.shown and abs(f - self.last) >= 0.01 or (f in (0.0, 1.0) and f != self.last):
                self.last = f
                _send(f"alpha {f}")

        def raise_(self):
            pass

        def activateWindow(self):
            pass

    splash = RetweaksSplash()
    splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)   # stays above the app window while it fades in
    splash._speed = 1.0 / SLOWER
    remote = RemoteWindow()
    state = {"ended": False}

    def finished():
        if not state["ended"]:
            state["ended"] = True
            _send("done")
            app.quit()

    splash.done.connect(finished)

    bridge = Bridge()

    def handle(line):
        if line.startswith("status "):
            splash.status = line[7:]
        elif line == "ready":
            splash.finish(remote, show=remote.show)
        elif line in ("quit", "EOF"):
            splash.abort()

    bridge.line.connect(handle)

    def reader():
        try:
            for raw in sys.stdin:
                bridge.line.emit(raw.rstrip("\r\n"))
        except Exception:
            pass
        bridge.line.emit("EOF")

    threading.Thread(target=reader, daemon=True, name="splash-stdin").start()
    splash.start()
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
