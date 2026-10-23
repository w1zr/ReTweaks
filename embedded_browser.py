"""RETWEAKS Browser process bridge (the base app's v1.5 EmbeddedBrowser, GPL-3.0, with RETWEAKS branding and data).

The browser runs as its own program, ai/EmbeddedBrowser.exe (Windows Forms + Microsoft Edge WebView2),
parented into the Browser page's frame. If that program fails, only the browser stops: RETWEAKS keeps
running and the page offers Restart. Nothing here touches Tk from another thread: the reader thread only
puts dicts on `events`, which the page drains on the Tk thread.

Protocol (one JSON object per line):
  to the browser:   first line {"op":"theme", BG, PANEL, FG, MUTED, LINE, ACC, "data":{...}}
                    then "visibility", "theme", "data", "navigate", "new-tab", "close", "inspect"
  from the browser: "ready", "loaded", "error", "stopped", "bookmarks", "visit", "title", "clear-history",
                    "setting", "state"
"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from embedded_ai import EmbeddedAI

EXE = "EmbeddedBrowser.exe"


def ai_folder():
    return Path(__file__).with_name("ai")


def command(parent_id):
    """How to start the browser. RETWEAKS_BROWSER_CMD (tests) is 'program|arg|...'; the window id is added."""
    override = os.environ.get("RETWEAKS_BROWSER_CMD")
    if override:
        return override.split("|") + [str(parent_id)]
    return [str(ai_folder() / EXE), str(parent_id)]


def available():
    return bool(os.environ.get("RETWEAKS_BROWSER_CMD")) or (ai_folder() / EXE).is_file()


class EmbeddedBrowser(EmbeddedAI):
    def __init__(self, parent, colors, events, data=None):
        super().__init__(parent, colors, events)
        self.data = data or (lambda: {})
        self.starting = False
        self.generation = 0

    def start(self):
        if self.closed or self.starting or (self.process is not None and self.process.poll() is None):
            return
        if not available():
            self.events.put({"type": "error", "message": "The browser files are missing from this build "
                             f"({EXE}). Rebuild RETWEAKS with build.py."})
            return
        args = command(self.parent.winfo_id())
        initial = {"op": "theme", **self.colors(), "data": self.data()}
        self.starting = True
        self.generation += 1
        gen = self.generation
        flags = 0x08000000 if sys.platform == "win32" else 0        # CREATE_NO_WINDOW

        def post(d):
            if not self.closed and gen == self.generation:
                self.events.put(d)

        def launch():
            try:
                process = subprocess.Popen(args, cwd=str(ai_folder()), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
                                           creationflags=flags)
                # Handshake first (off the Tk thread), then the process can take visibility/theme commands.
                process.stdin.write(json.dumps(initial, ensure_ascii=True) + "\n")
                process.stdin.flush()
                self.process = process
                if self.closed:
                    process.terminate()
                    return
            except (OSError, ValueError):
                post({"type": "error", "message": "The browser couldn't start. Check that Microsoft Edge WebView2 "
                      "Runtime is installed, then press Restart browser."})
                return
            finally:
                self.starting = False
            try:
                for raw in process.stdout:
                    try:
                        d = json.loads(raw)
                    except ValueError:
                        continue
                    if isinstance(d, dict) and self.process is process:
                        post(d)
            except (OSError, ValueError):
                pass
            finally:
                if not self.closed and self.process is process:
                    post({"type": "stopped", "message": "The browser stopped."})
        threading.Thread(target=launch, daemon=True, name="RetweaksBrowser").start()

    def running(self):
        return self.process is not None and self.process.poll() is None

    def restart(self):
        p = self.process
        self.process = None
        if p is not None and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
        self.start()
