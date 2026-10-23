"""Crash log for RETWEAKS: %APPDATA%\\RETWEAKS\\crash.log (owner report 2026-10-22: the app closed after a
while with no message). Records Python errors on any thread, errors inside Tk callbacks, native crashes
(faulthandler: access violations from ctypes/.NET/Tcl, with every thread's stack) and how the app ended,
so the next close can be explained. The file is kept small (last ~512 KB). No personal data is written
beyond file paths that appear in Python tracebacks."""
import datetime
import faulthandler
import os
import sys
import threading
import traceback
from pathlib import Path

MAX = 512 * 1024
_fault_file = None


def log_path():
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "RETWEAKS" / "crash.log"


def write(title, text=""):
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > MAX:
            data = p.read_bytes()[-MAX // 2:]
            p.write_bytes(data)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {title}\n{text}")
    except Exception:
        pass


def install(version=""):
    global _fault_file
    write("START", f"RETWEAKS {version}  pid {os.getpid()}  Python {sys.version.split()[0]}\n")
    try:
        _fault_file = open(log_path(), "a", encoding="utf-8")
        faulthandler.enable(_fault_file, all_threads=True)       # native crashes (no Python exception)
    except Exception:
        pass

    def hook(t, v, tb):
        write("UNCAUGHT ERROR", "".join(traceback.format_exception(t, v, tb)))
        sys.__excepthook__(t, v, tb)
    sys.excepthook = hook

    def thread_hook(args):
        write(f"THREAD ERROR in {getattr(args.thread, 'name', '?')}",
              "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = thread_hook


def watch_tk(root):
    """Tk callback errors don't close the app, but they're logged so broken buttons can be found."""
    def report(exc, val, tb):
        write("TK CALLBACK ERROR", "".join(traceback.format_exception(exc, val, tb)))
    root.report_callback_exception = report


def ended(reason):
    write("END", reason + "\n")
