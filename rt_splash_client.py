"""App side of the v1.6 startup screen (rt_splash_qt runs it in its own process; see that file).

make_intro() returns an object with the same interface as appearance.Intro (pump, ready, finish, closed,
on_done), so hubplus doesn't care which one runs. Falls back to the Tk Intro when the Qt process can't be
started (not Windows, or PySide6 missing) so startup never breaks. Nothing here waits on purpose: the
window appears when the splash says so, and a safety timer shows it anyway if the splash process dies.
"""
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk

_early = None          # the splash process started by start_early()
SAFETY = 12.0          # seconds after "ready" before the window is shown no matter what


def _command():
    override = os.environ.get("RETWEAKS_SPLASH_CMD")          # tests: a fake splash process
    if override:
        return override.split("|")
    if getattr(sys, "frozen", False):
        return [sys.executable, "--rt-splash"]
    here = os.path.dirname(os.path.abspath(__file__))
    return [sys.executable, os.path.join(here, "rt_splash_qt.py")]


def wanted():
    if os.environ.get("RETWEAKS_SPLASH_CMD"):
        return True
    if os.environ.get("RETWEAKS_TK_SPLASH"):
        return False
    return sys.platform == "win32"


def _spawn():
    flags = 0x08000000 if sys.platform == "win32" else 0          # CREATE_NO_WINDOW
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    return subprocess.Popen(_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", bufsize=1, creationflags=flags, env=env,
                            cwd=os.path.dirname(os.path.abspath(__file__)))


def start_early():
    """Started right after the single-instance check, before the app builds anything, so the splash is up
    as soon as possible. Never raises."""
    global _early
    if _early is None and wanted():
        try:
            _early = _spawn()
        except Exception:
            _early = None
    return _early


class QtIntro:
    def __init__(self, root, proc, on_done=None, status=None):
        self.root, self.proc, self.on_done = root, proc, on_done
        self.closed = False
        self.ready_at = None
        self.t0 = time.monotonic()
        self._time = time.monotonic
        self.REVEAL, self.HOLD, self.FADE = 2.38, 0.3, 0.55
        self.shown = False
        self.lines = queue.Queue()
        self.job = None
        threading.Thread(target=self._read, daemon=True, name="splash-stdout").start()
        if status:
            self.pump(status)

    def _read(self):
        try:
            for raw in self.proc.stdout:
                self.lines.put(raw.strip())
        except Exception:
            pass
        self.lines.put("EOF")

    def _send(self, line):
        try:
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
            return True
        except Exception:
            return False

    # ---- same interface as appearance.Intro
    def pump(self, status=None):
        if status and not self.closed:
            self._send("status " + status)

    def ready(self):
        if self.ready_at is not None or self.closed:
            return
        self.ready_at = self._time()
        if self.proc.poll() is not None or not self._send("ready"):
            self.finish()                              # splash process is gone: just show the window
            return
        self._poll()

    def _poll(self):
        self.job = None
        if self.closed:
            return
        try:
            while True:
                line = self.lines.get_nowait()
                if line == "show":
                    self._show(0.0)
                elif line.startswith("alpha "):
                    try:
                        self._show(float(line[6:]))
                    except ValueError:
                        pass
                elif line in ("done", "EOF"):
                    self.finish()
                    return
        except queue.Empty:
            pass
        if self._time() - self.ready_at > SAFETY:
            self.finish()
            return
        self.job = self.root.after(8, self._poll)

    def _show(self, alpha):
        try:
            self.root.attributes("-alpha", max(0.0, min(1.0, alpha)))
            if not self.shown:
                self.shown = True
                self.root.deiconify()
        except tk.TclError:
            pass

    def finish(self):
        if self.closed:
            return
        self.closed = True
        if self.job:
            try:
                self.root.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.proc.poll() is None:
            self._send("quit")
            try:
                self.proc.stdin.close()
            except Exception:
                pass
        try:
            self.root.attributes("-alpha", 1.0)
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass
        if self.on_done:
            try:
                self.on_done()
            except Exception:
                pass


def make_intro(root, colors, status, on_done=None):
    """The v1.6 Qt splash when possible, otherwise the Tk Intro (appearance.Intro)."""
    global _early
    proc = _early
    _early = None
    if proc is None and wanted():
        try:
            proc = _spawn()
        except Exception:
            proc = None
    if proc is not None and proc.poll() is None:
        return QtIntro(root, proc, on_done=on_done, status=status)
    from appearance import Intro
    return Intro(root, colors, status=status, on_done=on_done)
