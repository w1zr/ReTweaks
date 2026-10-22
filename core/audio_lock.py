# core/audio_lock.py
"""Volume lock (v1.5): keeps the default speaker and/or default microphone volume at a chosen
percent. When anything else changes it (Discord's or Zoom's automatic mic adjustment, a game, a
driver), RYTWEAKS puts it back within about half a second.

It follows the DEFAULT device: switch to another mic and the lock holds that one at the same %.
Mute is never touched (muting stays your choice). It only works while RYTWEAKS is running; with
"Keep running in the tray" on, that includes after the window is closed.

The decision logic here is pure and tested; the Qt timer that drives it lives in the main window.
"""

import time

KEYS = {"output": "audio_lock_output", "input": "audio_lock_input"}
NAMES = {"output": "Speaker volume", "input": "Microphone volume"}
INTERVAL_MS = 500
LOG_EVERY_S = 60          # at most one log line per minute per lock, so the Logs page isn't flooded


def clean_lock(value):
    """Saved lock value -> int 0..100, or None when the lock is off / the value is bad."""
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v < 0 or v > 100:
        return None
    return int(round(v))


def correction(current, locked):
    """The percent to set, or None when nothing needs doing."""
    if locked is None or current is None:
        return None
    return locked if int(current) != int(locked) else None


class VolumeLock:
    """Checks both locks once per tick(). Functions are injected so it runs anywhere:
    read(kind) -> (percent, muted) or None; write(kind, percent); get_lock(kind) -> value or None;
    log(component, requested, result, error)."""

    def __init__(self, read, write, get_lock, log=None, clock=time.monotonic):
        self.read, self.write, self.get_lock = read, write, get_lock
        self.log = log or (lambda *a: None)
        self.clock = clock
        self.corrections = {"output": 0, "input": 0}
        self.last_error = {"output": "", "input": ""}
        self._last_log = {"output": -1e9, "input": -1e9}

    def active(self):
        return any(clean_lock(self.get_lock(k)) is not None for k in KEYS)

    def tick(self):
        """Returns [(kind, from_percent, to_percent)] for every correction made."""
        done = []
        for kind in KEYS:
            locked = clean_lock(self.get_lock(kind))
            if locked is None:
                continue
            try:
                state = self.read(kind)
                if state is None:              # no default device right now
                    continue
                current = state[0]
                target = correction(current, locked)
                if target is None:
                    continue
                self.write(kind, target)
                self.corrections[kind] += 1
                self.last_error[kind] = ""
                done.append((kind, current, target))
                now = self.clock()
                if now - self._last_log[kind] >= LOG_EVERY_S:
                    self._last_log[kind] = now
                    self.log("Volume lock", f"{NAMES[kind]} changed to {current}%, put back to {target}%", "OK", "")
            except Exception as e:             # device unplugged mid-read, audio service restarting...
                self.last_error[kind] = str(e)
        return done
