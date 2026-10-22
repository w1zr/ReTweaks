# core/autoclicker.py
"""Auto clicker: validated settings, a precise click loop and global hotkeys.

Clicks are sent with the Windows SendInput API at the current cursor position.
The pure logic (validation, intervals, stop conditions) has no Windows
dependency and the loop takes an injectable clock/clicker, so it is unit tested
on any OS. Only SendInput and GetAsyncKeyState need Windows.
"""

import ctypes
import random
import sys
import threading
import time
from dataclasses import dataclass, asdict

# ---------------------------------------------------------------- limits

CPS_MIN, CPS_MAX = 1.0, 100.0
INTERVAL_MIN_MS, INTERVAL_MAX_MS = 10, 60000
DELAY_MIN_S, DELAY_MAX_S = 0.0, 10.0
COUNT_MIN, COUNT_MAX = 1, 10_000_000
SECONDS_MIN, SECONDS_MAX = 1, 86_400

BUTTONS = ("left", "right", "middle")
CLICK_TYPES = ("single", "double")
SPEED_MODES = ("cps", "interval")

DEFAULT_START_KEY = "F6"
DEFAULT_STOP_KEY = "F8"

# Gap between the two clicks of a "double click" (seconds). Shorter than the
# Windows default double-click time (500 ms) so applications see a double click.
DOUBLE_CLICK_GAP = 0.02

# Keys offered for the hotkeys: name -> Windows virtual-key code
HOTKEY_VKS = {f"F{i}": 0x6F + i for i in range(1, 13)}
HOTKEY_VKS.update({"Pause": 0x13, "Scroll Lock": 0x91, "Insert": 0x2D, "Home": 0x24,
                   "End": 0x23, "Page Up": 0x21, "Page Down": 0x22})


@dataclass
class ClickerConfig:
    button: str = "left"
    click_type: str = "single"
    speed_mode: str = "cps"
    cps: float = 10.0
    interval_ms: float = 100.0
    random_enabled: bool = False
    random_min_ms: float = 80.0
    random_max_ms: float = 120.0
    stop_after_clicks: int = 0      # 0 = no limit
    stop_after_seconds: float = 0   # 0 = no limit
    start_delay_s: float = 0.0

    def as_dict(self):
        return asdict(self)


def _num(value, name, lo, hi, unit="", integer=False):
    """Convert to a number and check the range. Returns (value, error)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None, f"{name} must be a number."
    if v != v or v in (float("inf"), float("-inf")):
        return None, f"{name} must be a number."
    if integer:
        if v != int(v):
            return None, f"{name} must be a whole number."
        v = int(v)
    if v < lo or v > hi:
        u = f" {unit}" if unit else ""
        return None, f"{name} must be between {lo:g} and {hi:g}{u}."
    return v, None


def validate_config(cfg):
    """Check a ClickerConfig. Returns a list of plain-language error strings (empty = valid)."""
    errors = []
    if cfg.button not in BUTTONS:
        errors.append("Mouse button must be left, right or middle.")
    if cfg.click_type not in CLICK_TYPES:
        errors.append("Click type must be single or double.")
    if cfg.speed_mode not in SPEED_MODES:
        errors.append("Speed mode must be CPS or interval.")
    if cfg.speed_mode == "cps":
        _, e = _num(cfg.cps, "Speed", CPS_MIN, CPS_MAX, "CPS")
        if e:
            errors.append(e)
    else:
        _, e = _num(cfg.interval_ms, "Interval", INTERVAL_MIN_MS, INTERVAL_MAX_MS, "ms")
        if e:
            errors.append(e)
    if cfg.random_enabled:
        lo, e1 = _num(cfg.random_min_ms, "Random minimum", INTERVAL_MIN_MS, INTERVAL_MAX_MS, "ms")
        hi, e2 = _num(cfg.random_max_ms, "Random maximum", INTERVAL_MIN_MS, INTERVAL_MAX_MS, "ms")
        errors += [e for e in (e1, e2) if e]
        if lo is not None and hi is not None and lo > hi:
            errors.append("Random minimum must not be greater than the maximum.")
    if cfg.stop_after_clicks:
        _, e = _num(cfg.stop_after_clicks, "Click count", COUNT_MIN, COUNT_MAX, integer=True)
        if e:
            errors.append(e)
    if cfg.stop_after_seconds:
        _, e = _num(cfg.stop_after_seconds, "Run time", SECONDS_MIN, SECONDS_MAX, "s")
        if e:
            errors.append(e)
    _, e = _num(cfg.start_delay_s, "Start delay", DELAY_MIN_S, DELAY_MAX_S, "s")
    if e:
        errors.append(e)
    return errors


def config_from_dict(d):
    """Build a config from saved settings, replacing missing or bad values with defaults."""
    base = ClickerConfig()
    out = base.as_dict()
    for key, default in out.items():
        if key in d and d[key] is not None:
            try:
                out[key] = type(default)(d[key]) if not isinstance(default, bool) else bool(d[key])
            except (TypeError, ValueError):
                pass
    cfg = ClickerConfig(**out)
    # Anything still invalid goes back to the defaults for that field only
    for _ in range(3):
        if not validate_config(cfg):
            break
        for key in ("button", "click_type", "speed_mode"):
            if getattr(cfg, key) not in {"button": BUTTONS, "click_type": CLICK_TYPES,
                                         "speed_mode": SPEED_MODES}[key]:
                setattr(cfg, key, getattr(base, key))
        if not CPS_MIN <= cfg.cps <= CPS_MAX:
            cfg.cps = base.cps
        if not INTERVAL_MIN_MS <= cfg.interval_ms <= INTERVAL_MAX_MS:
            cfg.interval_ms = base.interval_ms
        if not (INTERVAL_MIN_MS <= cfg.random_min_ms <= INTERVAL_MAX_MS) or \
                not (INTERVAL_MIN_MS <= cfg.random_max_ms <= INTERVAL_MAX_MS) or \
                cfg.random_min_ms > cfg.random_max_ms:
            cfg.random_min_ms, cfg.random_max_ms = base.random_min_ms, base.random_max_ms
        if cfg.stop_after_clicks and not COUNT_MIN <= cfg.stop_after_clicks <= COUNT_MAX:
            cfg.stop_after_clicks = 0
        if cfg.stop_after_seconds and not SECONDS_MIN <= cfg.stop_after_seconds <= SECONDS_MAX:
            cfg.stop_after_seconds = 0
        if not DELAY_MIN_S <= cfg.start_delay_s <= DELAY_MAX_S:
            cfg.start_delay_s = 0.0
    return cfg


def validate_hotkeys(start_key, stop_key):
    """Returns a list of errors; the two hotkeys must exist and differ."""
    errors = []
    for name, key in (("Start/stop hotkey", start_key), ("Emergency stop hotkey", stop_key)):
        if key not in HOTKEY_VKS:
            errors.append(f"{name} is not a supported key.")
    if start_key == stop_key:
        errors.append("The start/stop hotkey and the emergency stop hotkey must be different keys.")
    return errors


# ---------------------------------------------------------------- pure logic

def base_interval_s(cfg):
    """Seconds between click actions for the fixed (non-random) setting."""
    if cfg.speed_mode == "cps":
        return 1.0 / float(cfg.cps)
    return float(cfg.interval_ms) / 1000.0


def next_interval_s(cfg, rng=random):
    """Seconds until the next click action. Uses the random range when enabled."""
    if cfg.random_enabled:
        return rng.uniform(float(cfg.random_min_ms), float(cfg.random_max_ms)) / 1000.0
    return base_interval_s(cfg)


def clicks_in_next_action(cfg, clicks_sent):
    """1 or 2 clicks, never going over the click limit."""
    n = 2 if cfg.click_type == "double" else 1
    if cfg.stop_after_clicks:
        n = min(n, max(0, int(cfg.stop_after_clicks) - clicks_sent))
    return n


def stop_reason(cfg, clicks_sent, elapsed_s):
    """Why the loop should stop now ('count' / 'time'), or None to carry on."""
    if cfg.stop_after_clicks and clicks_sent >= int(cfg.stop_after_clicks):
        return "count"
    if cfg.stop_after_seconds and elapsed_s >= float(cfg.stop_after_seconds):
        return "time"
    return None


# ---------------------------------------------------------------- SendInput

INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
BUTTON_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32),
                ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort)]


class _INPUTUNION(ctypes.Union):
    # All three members are needed: the union's size decides sizeof(INPUT),
    # which SendInput checks (40 bytes on 64-bit Windows, 28 on 32-bit).
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_uint32), ("u", _INPUTUNION)]


def _make_mouse_input(flags):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
    return inp


class SendInputClicker:
    """Sends real mouse clicks at the current cursor position. Windows only."""

    def __init__(self):
        if sys.platform != "win32":
            raise OSError("Auto clicking needs Windows.")
        self._send = ctypes.windll.user32.SendInput
        self._send.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
        self._send.restype = ctypes.c_uint

    def _event(self, flags):
        inp = _make_mouse_input(flags)
        if self._send(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
            raise OSError(f"Windows refused the click (SendInput error {ctypes.GetLastError()}). "
                          "It can be blocked by a window running as administrator "
                          "or by the secure desktop.")

    def click(self, button):
        """Press and release. If the press was sent, the release is always attempted."""
        down, up = BUTTON_FLAGS[button]
        self._event(down)
        # The button is now down: retry the release so it is never left stuck
        last = None
        for _ in range(3):
            try:
                self._event(up)
                return
            except OSError as exc:
                last = exc
        raise last


# ---------------------------------------------------------------- engine

class ClickEngine:
    """Runs the click loop on its own thread.

    clicker: object with click(button). clock: perf_counter-like function.
    wait(seconds): interruptible wait used for gaps; defaults to the stop
    event so Stop takes effect immediately. All three can be faked in tests.
    """

    def __init__(self, cfg, clicker, clock=time.perf_counter, rng=random,
                 sleep=None, on_finish=None):
        self.cfg = cfg
        self.clicker = clicker
        self.clock = clock
        self.rng = rng
        self._stop = threading.Event()
        self._sleep = sleep or self._default_sleep
        self.on_finish = on_finish
        self._lock = threading.Lock()
        self._thread = None
        self.state = "idle"        # idle | delay | running | stopped
        self.clicks = 0
        self.first_click_t = None
        self.last_click_t = None
        self.end_t = None
        self.reason = None         # 'user' | 'emergency' | 'count' | 'time' | 'error'
        self.error = ""

    # -- waiting: coarse sleep on the stop event, then a short spin for precision
    def _default_sleep(self, seconds):
        end = self.clock() + seconds
        while True:
            left = end - self.clock()
            if left <= 0 or self._stop.is_set():
                return
            if left > 0.003:
                self._stop.wait(left - 0.002)
            else:
                time.sleep(0)

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self._thread = threading.Thread(target=self.run, name="RetweaksClicker", daemon=True)
        self._thread.start()
        return True

    def stop(self, reason="user"):
        with self._lock:
            if self.reason is None:
                self.reason = reason
        self._stop.set()

    def join(self, timeout=2.0):
        if self._thread:
            self._thread.join(timeout)
        return not (self._thread and self._thread.is_alive())

    def is_active(self):
        return self.state in ("delay", "running")

    def _finish(self, reason):
        with self._lock:
            if self.reason is None:
                self.reason = reason
            self.state = "stopped"
            self.end_t = self.clock()
        if self.on_finish:
            try:
                self.on_finish(self)
            except Exception:
                pass

    def run(self):
        """The loop. Safe to call directly (blocking) in tests."""
        cfg = self.cfg
        try:
            if cfg.start_delay_s > 0:
                self.state = "delay"
                self._sleep(float(cfg.start_delay_s))
            if self._stop.is_set():
                return self._finish("user")
            self.state = "running"
            t0 = self.clock()
            next_t = t0
            while not self._stop.is_set():
                now = self.clock()
                why = stop_reason(cfg, self.clicks, now - t0)
                if why:
                    return self._finish(why)
                if now < next_t:
                    self._sleep(next_t - now)
                    continue
                n = clicks_in_next_action(cfg, self.clicks)
                if n == 0:
                    return self._finish("count")
                for i in range(n):
                    if i > 0 and self._stop.is_set():
                        break           # Stop during a double click: don't send the second click
                    self.clicker.click(cfg.button)
                    t = self.clock()
                    with self._lock:
                        self.clicks += 1
                        if self.first_click_t is None:
                            self.first_click_t = t
                        self.last_click_t = t
                    if i + 1 < n:
                        self._sleep(DOUBLE_CLICK_GAP)
                # Schedule from the planned time, so timing does not drift;
                # if we fell behind (slow system), resynchronise instead of bursting.
                next_t += next_interval_s(cfg, self.rng)
                now = self.clock()
                if next_t < now:
                    next_t = now
            self._finish("user")
        except Exception as exc:  # any error stops the loop; buttons are never left down
            self.error = str(exc) or exc.__class__.__name__
            self._finish("error")

    def snapshot(self):
        """Thread-safe view of the real state for the UI."""
        with self._lock:
            end = self.end_t if self.end_t is not None else self.clock()
            elapsed = (end - self.first_click_t) if self.first_click_t is not None else 0.0
            cps = None
            if self.first_click_t is not None and self.last_click_t is not None \
                    and self.clicks >= 2 and self.last_click_t > self.first_click_t:
                cps = (self.clicks - 1) / (self.last_click_t - self.first_click_t)
            return {"state": self.state, "clicks": self.clicks, "elapsed": elapsed,
                    "cps": cps, "reason": self.reason, "error": self.error}


# ---------------------------------------------------------------- hotkeys

class HotkeyWatcher:
    """Polls GetAsyncKeyState about every 15 ms, so hotkeys work in any window.

    A key press is reported once per physical press (edge detection).
    """

    def __init__(self, start_key, stop_key, on_toggle, on_emergency,
                 get_key_state=None, interval=0.015):
        self.set_keys(start_key, stop_key)
        self.on_toggle, self.on_emergency = on_toggle, on_emergency
        self.interval = interval
        self._get = get_key_state or self._win_state
        self._quit = threading.Event()
        self._thread = None

    def set_keys(self, start_key, stop_key):
        errs = validate_hotkeys(start_key, stop_key)
        if errs:
            raise ValueError(errs[0])
        self.start_vk, self.stop_vk = HOTKEY_VKS[start_key], HOTKEY_VKS[stop_key]

    @staticmethod
    def _win_state(vk):
        if sys.platform != "win32":
            return False
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

    def available(self):
        return sys.platform == "win32" or self._get != self._win_state

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._quit.clear()
        self._thread = threading.Thread(target=self._loop, name="RetweaksHotkeys", daemon=True)
        self._thread.start()

    def stop(self, timeout=1.0):
        self._quit.set()
        if self._thread:
            self._thread.join(timeout)

    def poll_once(self, prev):
        """One poll. prev = (start_down, stop_down). Returns the new pair, firing callbacks."""
        s, e = self._get(self.start_vk), self._get(self.stop_vk)
        # Emergency stop first, so it wins if both keys land in the same poll
        if e and not prev[1]:
            self.on_emergency()
        elif s and not prev[0]:
            self.on_toggle()
        return (s, e)

    def _loop(self):
        prev = (self._get(self.start_vk), self._get(self.stop_vk))  # ignore keys already held
        while not self._quit.wait(self.interval):
            try:
                prev = self.poll_once(prev)
            except Exception:
                pass
