"""Small harness for rt_pages checks: a Tk root with the Hub methods pages use, and retweaks.py's
widget globals as g. Run checks through tools/linux_shim.py on Linux."""
import time
import tkinter as tk

import retweaks as app


class FakeHub(tk.Tk):
    def __init__(self):
        super().__init__()
        self.logs = []
        self.settings = {}

    def _scroll_area(self, parent):
        return app.Hub._scroll_area(self, parent)

    def log_action(self, component, requested, result, error=""):
        self.logs.append((component, requested, result, error))

    def save_settings(self):
        return True


def g():
    return vars(app)


def pump(hub, until=lambda: False, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        hub.update()
        if until():
            return True
        time.sleep(0.01)
    return until()
