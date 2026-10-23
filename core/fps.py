# core/fps.py
"""Real FPS measurement using Intel PresentMon (not bundled; the user picks PresentMon.exe).

Pure logic (command line, CSV parsing, metric math, comparison, saved runs) lives here so it
can be tested on any OS. PresentMon console 2.x flags: --process_name, --timed,
--output_file, --terminate_after_timed, --no_console_stats, --session_name,
--stop_existing_session. The CSV column MsBetweenPresents exists in 1.x, in 2.x default
and in 2.x --v1_metrics output; "FrameTime" is accepted as a fallback for other tools/versions.
"""

import csv
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

RELEASES_URL = "https://github.com/GameTechDev/PresentMon/releases"
DURATIONS = (10, 30, 60, 120, 300)
CUSTOM_MIN_S, CUSTOM_MAX_S = 5, 1800     # custom test length limits (owner request 2026-10-22)


def clean_seconds(value, default=30):
    """A test length in whole seconds between CUSTOM_MIN_S and CUSTOM_MAX_S, else `default`."""
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return default
    return v if CUSTOM_MIN_S <= v <= CUSTOM_MAX_S else default
METHOD_TEXT = ("1% low = average of the slowest 1% of frames (by frame time), shown as FPS. "
               "0.1% low = same for the slowest 0.1%. Percentile values use the 99th / 99.9th "
               "percentile frame time instead.")
METHOD_ID = "avg-of-slowest-frames; nearest-rank-percentile; frame time = MsBetweenPresents"

# Column names in order of preference (compared lowercase)
FRAME_TIME_COLUMNS = ("msbetweenpresents", "frametime")

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ---------------------------------------------------------------- finding PresentMon

def find_presentmon_near_exe():
    """A PresentMon*.exe in the folder of RETWEAKS.exe (or this project), if any."""
    folders = []
    if getattr(sys, "frozen", False):
        folders.append(Path(sys.executable).parent)
    folders.append(Path(__file__).resolve().parent.parent)
    for folder in folders:
        try:
            for p in sorted(folder.glob("PresentMon*.exe")):
                if p.is_file():
                    return str(p)
        except OSError:
            pass
    return None


def validate_presentmon_path(path):
    """Returns (ok, message)."""
    if not path:
        return False, "No PresentMon.exe selected."
    p = Path(path)
    if not p.is_file():
        return False, f"File not found: {path}"
    if p.suffix.lower() != ".exe":
        return False, "That is not an .exe file."
    return True, "OK"


# ---------------------------------------------------------------- command line

def build_command(exe, process_name, seconds, output_file, session_name="RETWEAKS_FPS"):
    """PresentMon 2.x console command line (list for subprocess, no shell)."""
    seconds = int(seconds)
    if seconds <= 0:
        raise ValueError("Duration must be positive.")
    if not process_name or not str(process_name).strip():
        raise ValueError("No process selected.")
    return [str(exe),
            "--process_name", str(process_name),
            "--timed", str(seconds),
            "--terminate_after_timed",
            "--output_file", str(output_file),
            "--no_console_stats",
            "--session_name", session_name,
            "--stop_existing_session"]


# ---------------------------------------------------------------- CSV parsing

def parse_frame_times(csv_text):
    """Parse a PresentMon CSV (1.x or 2.x). Returns (frame_times_ms, info).

    info = {"column": name used, "rows": data rows seen, "skipped": rows ignored}
    Raises ValueError when no usable frame time column exists.
    Rows with a missing, non-numeric or non-positive frame time are skipped and counted.
    """
    text = (csv_text or "").lstrip("﻿")
    reader = csv.reader(io.StringIO(text))
    header = None
    for row in reader:
        if row and any(c.strip() for c in row):
            header = [c.strip() for c in row]
            break
    if header is None:
        raise ValueError("The PresentMon file is empty.")
    lower = [h.lower() for h in header]
    idx = None
    for name in FRAME_TIME_COLUMNS:
        if name in lower:
            idx = lower.index(name)
            break
    if idx is None:
        raise ValueError("No frame time column (MsBetweenPresents or FrameTime) in the CSV. "
                         "Columns found: " + ", ".join(header[:12]))
    frames, rows, skipped = [], 0, 0
    for row in reader:
        if not row or not any(c.strip() for c in row):
            continue
        rows += 1
        try:
            v = float(row[idx])
        except (IndexError, ValueError):
            skipped += 1
            continue
        if not math.isfinite(v) or v <= 0:
            skipped += 1
            continue
        frames.append(v)
    return frames, {"column": header[idx], "rows": rows, "skipped": skipped}


# ---------------------------------------------------------------- metrics

def _slowest_avg_fps(sorted_desc, fraction):
    n = max(1, math.ceil(len(sorted_desc) * fraction))
    worst = sorted_desc[:n]
    return 1000.0 / (sum(worst) / len(worst))


def _percentile_fps(sorted_asc, p):
    """Nearest-rank percentile of frame time, returned as FPS."""
    rank = max(1, math.ceil(p * len(sorted_asc)))
    return 1000.0 / sorted_asc[rank - 1]


MIN_FRAMES_1 = 100
MIN_FRAMES_01 = 1000


def compute_metrics(frames_ms):
    """Metrics from frame times in ms. Values that need more frames are None (Unavailable)."""
    n = len(frames_ms)
    if n == 0:
        raise ValueError("No frames were captured.")
    asc = sorted(frames_ms)
    desc = asc[::-1]
    total_ms = sum(frames_ms)
    m = {
        "frames": n,
        "duration_s": total_ms / 1000.0,
        "avg_fps": 1000.0 / (total_ms / n),
        "min_frame_ms": asc[0],
        "max_frame_ms": asc[-1],
        "low1_fps": None, "low01_fps": None, "p99_fps": None, "p999_fps": None,
    }
    if n >= MIN_FRAMES_1:
        m["low1_fps"] = _slowest_avg_fps(desc, 0.01)
        m["p99_fps"] = _percentile_fps(asc, 0.99)
    if n >= MIN_FRAMES_01:
        m["low01_fps"] = _slowest_avg_fps(desc, 0.001)
        m["p999_fps"] = _percentile_fps(asc, 0.999)
    return m


METRIC_ROWS = [
    ("avg_fps", "Average FPS", "fps"),
    ("low1_fps", "1% low (avg of slowest 1%)", "fps"),
    ("low01_fps", "0.1% low (avg of slowest 0.1%)", "fps"),
    ("p99_fps", "1% low (99th percentile)", "fps"),
    ("p999_fps", "0.1% low (99.9th percentile)", "fps"),
    ("min_frame_ms", "Fastest frame", "ms"),
    ("max_frame_ms", "Slowest frame", "ms"),
    ("frames", "Frames", ""),
    ("duration_s", "Captured time", "s"),
]


def unavailable_reason(key):
    if key in ("low01_fps", "p999_fps"):
        return f"Unavailable (needs {MIN_FRAMES_01}+ frames)"
    if key in ("low1_fps", "p99_fps"):
        return f"Unavailable (needs {MIN_FRAMES_01 // 10}+ frames)"
    return "Unavailable"


def format_metric(key, value):
    if value is None:
        return unavailable_reason(key)
    if key == "frames":
        return f"{int(value)}"
    if key == "duration_s":
        return f"{value:.1f} s"
    if key == "min_frame_ms" or key == "max_frame_ms":
        return f"{value:.2f} ms"
    return f"{value:.1f} FPS"


def compare_runs(a, b):
    """Differences b - a for each metric. Each item: (key, label, a, b, diff, percent).
    diff/percent are None when either side is unavailable. Never says which tweak helped."""
    out = []
    for key, lbl, _unit in METRIC_ROWS:
        va, vb = a.get(key), b.get(key)
        if va is None or vb is None:
            out.append((key, lbl, va, vb, None, None))
        else:
            diff = vb - va
            pct = (diff / va * 100.0) if va else None
            out.append((key, lbl, va, vb, diff, pct))
    return out


def comparison_warnings(a, b):
    """Honest caveats for comparing two saved runs."""
    w = ["Results only compare fairly with the same scene, in-game settings and duration."]
    if a.get("game") != b.get("game"):
        w.append("These runs are from different programs.")
    if a.get("seconds") != b.get("seconds"):
        w.append(f"The runs have different lengths ({a.get('seconds')} s and {b.get('seconds')} s).")
    return w


# ---------------------------------------------------------------- saved runs

def runs_path():
    return Path(os.getenv("APPDATA") or Path.home()) / "RETWEAKS" / "fps_runs.json"


def load_runs(path=None):
    path = Path(path) if path else runs_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [r for r in data if isinstance(r, dict) and "id" in r] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_runs(runs, path=None):
    path = Path(path) if path else runs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(runs, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def make_run(game, seconds, metrics, notes="", when=None):
    return {"id": uuid.uuid4().hex[:12], "game": game, "seconds": int(seconds),
            "date": (when or datetime.now()).isoformat(timespec="seconds"),
            "notes": notes, "method": METHOD_ID, **metrics}


def add_run(run, path=None):
    runs = load_runs(path)
    runs.append(run)
    save_runs(runs, path)
    return runs


def delete_run(run_id, path=None):
    runs = [r for r in load_runs(path) if r.get("id") != run_id]
    save_runs(runs, path)
    return runs


def update_notes(run_id, notes, path=None):
    runs = load_runs(path)
    for r in runs:
        if r.get("id") == run_id:
            r["notes"] = notes
    save_runs(runs, path)
    return runs


# ---------------------------------------------------------------- processes

def list_processes():
    """Running programs as sorted [(exe_name, window_title_or_'')]. On Windows only programs
    with a visible window are listed; elsewhere every process name."""
    import psutil
    names = {}
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            pids = {}
            WNDENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def cb(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    n = user32.GetWindowTextLengthW(hwnd)
                    if n > 0:
                        buf = ctypes.create_unicode_buffer(n + 1)
                        user32.GetWindowTextW(hwnd, buf, n + 1)
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        pids.setdefault(pid.value, buf.value)
                return True
            user32.EnumWindows(WNDENUM(cb), 0)
            for pid, title in pids.items():
                try:
                    names.setdefault(psutil.Process(pid).name(), title)
                except (psutil.Error, OSError):
                    pass
        except Exception:
            names = {}
    if not names:
        for p in psutil.process_iter(["name"]):
            if p.info.get("name"):
                names.setdefault(p.info["name"], "")
    return sorted(names.items(), key=lambda kv: kv[0].lower())


# ---------------------------------------------------------------- running PresentMon

ADMIN_HINT = ("PresentMon needs administrator rights or membership in the \"Performance Log "
              "Users\" group. RETWEAKS normally runs as administrator; check that it did.")


class Capture:
    """One PresentMon run. start(), then poll() until it returns a result tuple."""

    def __init__(self, exe, process_name, seconds):
        self.exe, self.process_name, self.seconds = exe, process_name, int(seconds)
        self.dir = tempfile.mkdtemp(prefix="retweaks_fps_")
        self.csv_path = os.path.join(self.dir, "capture.csv")
        self.err_path = os.path.join(self.dir, "stderr.txt")
        self.proc = None
        self.t0 = None
        self.cancelled = False
        self._err = None

    def start(self):
        cmd = build_command(self.exe, self.process_name, self.seconds, self.csv_path)
        self._err = open(self.err_path, "wb")
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=self._err,
                                     stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        self.t0 = time.monotonic()

    def elapsed(self):
        return 0.0 if self.t0 is None else time.monotonic() - self.t0

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def overdue(self):
        """True if PresentMon has not exited well after the requested duration."""
        return self.running() and self.elapsed() > self.seconds + 20

    def cancel(self):
        self.cancelled = True
        self.terminate()
        if self._err:
            try:
                self._err.close()    # otherwise Windows can't delete the temp folder
            except Exception:
                pass

    def terminate(self):
        if self.running():
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

    def finish(self):
        """After the process ended: returns (frames_ms or None, error_text or None)."""
        if self._err:
            self._err.close()
        stderr = ""
        try:
            stderr = Path(self.err_path).read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            pass
        code = self.proc.returncode if self.proc else None
        try:
            text = Path(self.csv_path).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            text = ""
        return interpret_result(text, stderr, code)

    def cleanup(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)


def interpret_result(csv_text, stderr, exit_code):
    """Turn PresentMon's output into (frames_ms, error). Pure, so it can be tested."""
    low = (stderr or "").lower()
    if any(s in low for s in ("access is denied", "administrator", "performance log users",
                              "access denied", "elevat")):
        return None, ADMIN_HINT + (f"\nPresentMon said: {stderr}" if stderr else "")
    if not (csv_text or "").strip():
        msg = ("No frames were captured. The program may not be presenting frames (not in the "
               "foreground or minimized), the process name may be wrong, or anti-cheat may block "
               "capture.")
        if stderr:
            msg += f"\nPresentMon said: {stderr}"
        elif exit_code not in (0, None):
            msg += f"\nPresentMon exited with code {exit_code}."
        return None, msg
    try:
        frames, info = parse_frame_times(csv_text)
    except ValueError as e:
        return None, f"Could not read the PresentMon file: {e}"
    if not frames:
        return None, ("PresentMon wrote a file but it holds no usable frames "
                      f"({info['rows']} rows, {info['skipped']} unreadable). The program may not "
                      "have been presenting frames.")
    return frames, None
