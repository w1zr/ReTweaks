# core/overlay_fps.py
"""Live frame times for the in-game FPS overlay. Nothing is injected into the game.

PresentMon 2.x console (Intel) runs for one process and streams its CSV to stdout
(--output_stdout, documented in PresentMon's console README). A background thread reads the
lines, and RollingMetrics keeps the last ~10 s of frame times. Pure logic (line parsing,
metrics, text, corner placement) is testable on any OS; the Windows window lookup is guarded.
"""

import math
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque

from core import fps

SESSION_NAME = "RETWEAKS_overlay"   # the FPS test uses RETWEAKS_FPS
WINDOW_S = 10.0                     # default span for the 1% low (setting overlay_low_window_s)
FPS_SPAN_MS = 1000.0                # default "current FPS" span (setting overlay_fps_span_s)
LOW_WINDOWS_S = (5, 10, 30, 60)     # choices for the 1% low window (owner request 2026-10-22)
FPS_SPANS_S = (0.5, 1.0, 2.0)       # choices for the FPS averaging span
MIN_FRAMES_LOW = 100                # below this the 1% low is Unavailable
STALE_S = 2.0                       # no frames for this long -> values show "–"

CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
SIZES = ("small", "medium", "large")
SOURCES = ("builtin", "presentmon")     # v1.4.3: built-in Windows frame events (default) or PresentMon
DEFAULTS = {"overlay_position": "top-left", "overlay_size": "medium",
            "overlay_show_load": True, "overlay_opacity": 85, "overlay_source": "builtin",
            "overlay_low_window_s": 10, "overlay_fps_span_s": 1.0}

# Timings every RollingMetrics without explicit values follows, so a change applies to a running overlay at once.
_TIMINGS = {"low_window_s": WINDOW_S, "fps_span_s": FPS_SPAN_MS / 1000.0}


def _pick(value, choices, default):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if any(abs(v - c) < 1e-9 for c in choices) else default


def set_timings(low_window_s=None, fps_span_s=None):
    """Change the live overlay timings (validated; bad values keep the current ones). Returns the timings."""
    if low_window_s is not None:
        _TIMINGS["low_window_s"] = _pick(low_window_s, LOW_WINDOWS_S, _TIMINGS["low_window_s"])
    if fps_span_s is not None:
        _TIMINGS["fps_span_s"] = _pick(fps_span_s, FPS_SPANS_S, _TIMINGS["fps_span_s"])
    return dict(_TIMINGS)


def timings():
    return dict(_TIMINGS)
SETTING_NOTE = ("Works over games in windowed fullscreen or borderless mode. Games in exclusive "
                "fullscreen draw over it. Nothing is injected into the game; frame times come "
                "straight from Windows (built-in), or from PresentMon if you choose it.")


# ---------------------------------------------------------------- settings
def clean_settings(settings):
    """Overlay settings from the saved dict, with bad or missing values replaced by defaults."""
    s = settings or {}
    pos = s.get("overlay_position")
    size = s.get("overlay_size")
    try:
        op = int(s.get("overlay_opacity", DEFAULTS["overlay_opacity"]))
    except (TypeError, ValueError):
        op = DEFAULTS["overlay_opacity"]
    load = s.get("overlay_show_load", DEFAULTS["overlay_show_load"])
    src = s.get("overlay_source")
    low_w = _pick(s.get("overlay_low_window_s", DEFAULTS["overlay_low_window_s"]), LOW_WINDOWS_S,
                  float(DEFAULTS["overlay_low_window_s"]))
    span = _pick(s.get("overlay_fps_span_s", DEFAULTS["overlay_fps_span_s"]), FPS_SPANS_S,
                 DEFAULTS["overlay_fps_span_s"])
    return {"overlay_low_window_s": int(low_w), "overlay_fps_span_s": span,
            "overlay_position": pos if pos in CORNERS else DEFAULTS["overlay_position"],
            "overlay_size": size if size in SIZES else DEFAULTS["overlay_size"],
            "overlay_show_load": bool(load),
            "overlay_opacity": min(100, max(50, op)),
            "overlay_source": src if src in SOURCES else DEFAULTS["overlay_source"]}


# ---------------------------------------------------------------- command line
def build_command(exe, process_name):
    """PresentMon 2.x console command that streams CSV to stdout for one process."""
    if not process_name or not str(process_name).strip():
        raise ValueError("No process selected.")
    return [str(exe), "--process_name", str(process_name), "--output_stdout",
            "--no_console_stats", "--session_name", SESSION_NAME, "--stop_existing_session"]


# ---------------------------------------------------------------- line parsing
def parse_header(line):
    """Index of the frame time column if this line is a PresentMon header, else None."""
    cols = [c.strip().strip('"').lower() for c in (line or "").lstrip("﻿").split(",")]
    for name in fps.FRAME_TIME_COLUMNS:
        if name in cols:
            return cols.index(name)
    return None


def parse_frame_line(line, idx):
    """Frame time in ms from one CSV data line, or None when unusable."""
    if idx is None or not line or not line.strip():
        return None
    parts = line.rstrip("\r\n").split(",")
    try:
        v = float(parts[idx].strip().strip('"'))
    except (IndexError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


class LineParser:
    """Feeds lines in; the header is read once, then frame times come out."""

    def __init__(self):
        self.idx = None
        self.skipped = 0

    def feed(self, line):
        if self.idx is None:
            self.idx = parse_header(line)
            return None
        v = parse_frame_line(line, self.idx)
        if v is None and line.strip():
            self.skipped += 1
        return v


# ---------------------------------------------------------------- rolling metrics
class RollingMetrics:
    """Rolling frame-time window. Time is the running sum of frame times, so the numbers do not
    depend on how bursty the pipe delivery is.

    - FPS = frames that ended in the last `fps_span_s` seconds, divided by the time those frames took.
    - 1% low = average of the slowest 1% of frames in the last `window_s` seconds, shown as FPS; it
      needs at least MIN_FRAMES_LOW frames in that window, otherwise it is Unavailable.
    Without explicit values both spans follow set_timings() live (the user's overlay settings)."""

    def __init__(self, window_s=None, fps_span_s=None):
        self._window_s, self._span_s = window_s, fps_span_s
        self.frames = deque()       # (end_time_ms, frame_ms)
        self.clock = 0.0

    @property
    def window_ms(self):
        return (self._window_s if self._window_s is not None else _TIMINGS["low_window_s"]) * 1000.0

    @property
    def span_ms(self):
        return (self._span_s if self._span_s is not None else _TIMINGS["fps_span_s"]) * 1000.0

    def add(self, frame_ms):
        self.clock += frame_ms
        self.frames.append((self.clock, frame_ms))
        cutoff = self.clock - max(self.window_ms, self.span_ms)
        while self.frames and self.frames[0][0] <= cutoff:
            self.frames.popleft()

    def snapshot(self):
        """{'fps', 'low1', 'frame_ms'}; each is None (Unavailable) when it cannot be computed."""
        out = {"fps": None, "low1": None, "frame_ms": None}
        if not self.frames:
            return out
        span = self.span_ms
        recent = [ft for end, ft in self.frames if end > self.clock - span]
        if recent:
            covered = sum(recent)                  # the time those frames actually took
            out["fps"] = len(recent) * 1000.0 / covered
            out["frame_ms"] = covered / len(recent)
        window = [ft for end, ft in self.frames if end > self.clock - self.window_ms]
        if len(window) >= MIN_FRAMES_LOW:
            desc = sorted(window, reverse=True)
            n = max(1, math.ceil(len(desc) * 0.01))
            out["low1"] = 1000.0 / (sum(desc[:n]) / n)
        return out


# ---------------------------------------------------------------- display text
def _num(v, digits=0):
    return "–" if v is None else f"{v:.{digits}f}"


def format_lines(snap, cpu=None, gpu=None, show_load=True, state="running"):
    """Overlay text lines. Missing values are '–'; never an invented number."""
    if state == "closed":
        return ["Game closed"]
    if state == "error":
        return ["Overlay stopped"]
    snap = snap or {}
    lines = [f"FPS {_num(snap.get('fps'))}",
             f"1% low {_num(snap.get('low1'))}",
             f"Frame {_num(snap.get('frame_ms'), 1)} ms"]
    if show_load:
        c = "–" if cpu is None else f"{cpu:.0f}%"
        g = "–" if gpu is None else f"{gpu:.0f}%"
        lines.append(f"CPU {c} · GPU {g}")
    return lines


def loads_from_sample(sample):
    """(cpu_percent, gpu_percent) from a core.telemetry sample; None when missing."""
    try:
        cpu = sample["cpu"]["load"]
    except (KeyError, TypeError):
        cpu = None
    gpu = None
    try:
        for g in sample.get("gpus") or []:
            if g.get("load") is not None:
                gpu = g["load"]
                break
    except AttributeError:
        pass
    return cpu, gpu


# ---------------------------------------------------------------- placement
def corner_position(area, size, corner, margin=16):
    """Top-left (x, y) of a box of `size` (w, h) inside `area` (x, y, w, h) at a corner."""
    ax, ay, aw, ah = area
    w, h = size
    x = ax + margin if corner.endswith("left") else ax + aw - w - margin
    y = ay + margin if corner.startswith("top") else ay + ah - h - margin
    return int(x), int(y)


def find_game_window_rect(process_name):
    """(left, top, width, height) in pixels of the largest visible window of the process, or
    None. Windows only."""
    if sys.platform != "win32" or not process_name:
        return None
    try:
        import ctypes
        from ctypes import wintypes
        import psutil
        pids = {p.pid for p in psutil.process_iter(["name"])
                if (p.info.get("name") or "").lower() == process_name.lower()}
        if not pids:
            return None
        user32 = ctypes.windll.user32
        best = [None, 0]
        WNDENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in pids:
                    r = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(r))
                    w, h = r.right - r.left, r.bottom - r.top
                    if w * h > best[1]:
                        best[0], best[1] = (r.left, r.top, w, h), w * h
            return True
        user32.EnumWindows(WNDENUM(cb), 0)
        return best[0]
    except Exception:
        return None


def process_running(process_name):
    import psutil
    low = (process_name or "").lower()
    try:
        return any((p.info.get("name") or "").lower() == low for p in psutil.process_iter(["name"]))
    except Exception:
        return True   # cannot tell: do not claim the game closed


# ---------------------------------------------------------------- the stream
class OverlayStream:
    """PresentMon streaming for one process. start() / snapshot() / stop().

    state: 'idle', 'running', 'closed' (game exited), 'error' (see .error)."""

    def __init__(self, exe, process_name, alive_check=process_running):
        self.exe, self.process_name = exe, process_name
        self._alive_check = alive_check
        self.state = "idle"
        self.error = ""
        self._metrics = RollingMetrics()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._proc = None
        self._reader = None
        self._watcher = None
        self._err = None
        self._dir = None
        self._last_frame = None
        self._seen_frames = False

    def start(self):
        cmd = build_command(self.exe, self.process_name)
        self._dir = tempfile.mkdtemp(prefix="retweaks_overlay_")
        err_path = os.path.join(self._dir, "stderr.txt")
        self._err = open(err_path, "wb")
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=self._err,
                                          stdin=subprocess.DEVNULL, creationflags=fps.CREATE_NO_WINDOW)
        except Exception:
            self._cleanup_files()
            raise
        self.state = "running"
        self._reader = threading.Thread(target=self._read_loop, name="overlay-reader", daemon=True)
        self._watcher = threading.Thread(target=self._watch_loop, name="overlay-watch", daemon=True)
        self._reader.start()
        self._watcher.start()

    def _read_loop(self):
        parser = LineParser()
        try:
            for raw in iter(self._proc.stdout.readline, b""):
                if self._stop.is_set():
                    break
                v = parser.feed(raw.decode("utf-8", errors="replace"))
                if v is not None:
                    with self._lock:
                        self._metrics.add(v)
                        self._last_frame = time.monotonic()
                        self._seen_frames = True
        except Exception as e:   # pipe closed during stop is expected
            if not self._stop.is_set():
                self._fail(f"Reading PresentMon output failed: {e}")
            return
        if not self._stop.is_set() and self.state == "running":
            self._fail(self._exit_message())

    def _watch_loop(self):
        while not self._stop.wait(2.0):
            if self.state != "running":
                return
            if not self._alive_check(self.process_name):
                self.state = "closed"
                self._stop.set()
                self._kill()
                return

    def _exit_message(self):
        code = self._proc.poll() if self._proc else None
        text = ""
        try:
            self._err.flush()
            text = open(os.path.join(self._dir, "stderr.txt"), encoding="utf-8",
                        errors="replace").read().strip()
        except Exception:
            pass
        low = text.lower()
        if any(s in low for s in ("access is denied", "administrator", "performance log users", "elevat")):
            return fps.ADMIN_HINT
        msg = f"PresentMon stopped (exit code {code})."
        return msg + (f" It said: {text}" if text else "")

    def _fail(self, msg):
        if self.state == "running":
            self.error = msg
            self.state = "error"

    def snapshot(self):
        """(metrics dict, state). Values are None when no recent frames arrived."""
        with self._lock:
            snap = self._metrics.snapshot()
            stale = (self._last_frame is None or time.monotonic() - self._last_frame > STALE_S)
        if stale:
            snap = {"fps": None, "low1": None, "frame_ms": None}
        return snap, self.state

    def has_frames(self):
        return self._seen_frames

    def _kill(self):
        p = self._proc
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=5)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    def stop(self):
        """Terminate PresentMon and join both threads. Safe to call twice."""
        self._stop.set()
        self._kill()
        for t in (self._reader, self._watcher):
            if t and t.is_alive() and t is not threading.current_thread():
                t.join(timeout=5)
        if self._proc and self._proc.stdout:
            try:
                self._proc.stdout.close()
            except Exception:
                pass
        if self.state == "running":
            self.state = "idle"
        self._cleanup_files()

    def _cleanup_files(self):
        import shutil
        if self._err:
            try:
                self._err.close()
            except Exception:
                pass
            self._err = None
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None
