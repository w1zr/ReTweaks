"""Performance snapshots (from RETWEAKS): record what the PC is doing for a set time (load, clocks, temps)
and keep the averages, to compare before and after a tweak. It measures; it doesn't score.
Also: sensor logging to CSV (core/sensorlog.py) and comparing two saved FPS runs (core/fps.py)."""
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk

from core import fps as fpsmod
from core.sensorlog import SensorLogger, default_log_path
from rt_pages.common import NA, card, label

COLUMNS = ["Name", "Time", "Length", "CPU load avg / max", "CPU clock avg", "CPU temp max",
           "GPU load avg / max", "GPU temp max", "RAM avg"]
LENGTHS = ["15 seconds", "30 seconds", "60 seconds", "120 seconds"]


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _max(xs):
    xs = [x for x in xs if x is not None]
    return max(xs) if xs else None


def _f(v, unit="", digits=0):
    return NA if v is None else f"{v:.{digits}f}{unit}"


def _get(d, *path):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _gpu0(sample, key):
    gpus = sample.get("gpus") or []
    return gpus[0].get(key) if gpus and isinstance(gpus[0], dict) else None


def summarize(name, start, samples, length_s, temp_text):
    """One table row from recorded telemetry samples (real values; Unavailable when missing)."""
    cpu_load = [_get(x, "cpu", "load") for x in samples]
    gpu_load = [_gpu0(x, "load") for x in samples]
    gpu_temp = [_gpu0(x, "temp_c") for x in samples]
    return [
        name, start.strftime("%H:%M:%S"), f"{length_s} s",
        f"{_f(_avg(cpu_load), '%')} / {_f(_max(cpu_load), '%')}",
        _f(_avg([_get(x, "cpu", "mhz") for x in samples]), " MHz"),
        temp_text(_max([_get(x, "cpu", "temp_c") for x in samples])) or NA,
        f"{_f(_avg(gpu_load), '%')} / {_f(_max(gpu_load), '%')}",
        temp_text(_max(gpu_temp)) or NA,
        _f(_avg([_get(x, "ram", "percent") for x in samples]), "%"),
    ]


class _Sampler:
    """Live telemetry (core/telemetry.py) about once a second on a worker thread, only while needed.
    Samples arrive on the Tk thread through poll()."""

    def __init__(self):
        self.q = queue.Queue()
        self.error = None
        self._stop = threading.Event()
        self._thread = None

    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if self.running():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        try:
            from core.telemetry import Telemetry
            t = Telemetry()      # created on this thread (COM/WMI objects live here)
        except Exception as e:
            self.error = f"Live readings unavailable: {e}"
            return
        if self._stop.wait(1.0):            # counters need two readings; the first would show 0%
            return
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.q.put(t.sample())
            except Exception as e:
                self.error = f"Reading failed: {e}"
            self._stop.wait(max(0.05, 1.0 - (time.monotonic() - started)))


class SnapshotsPage:
    TITLE = "Performance snapshots"
    SUB = ("Start your game or task, then record a snapshot. Change a tweak and record another to compare. "
           "Snapshots measure what your PC is doing; they don't measure FPS.")

    def __init__(self, hub, tab, g):
        self.hub, self.tab, self.g = hub, tab, g
        self.recording = None
        self.samples = []
        self.logger = None
        self._log_path = None
        self._sampler = _Sampler()
        self._feed = False          # True when the app's shared live feed is used instead of our sampler
        g["page_header"](tab, "RETWEAKS", self.TITLE, self.SUB)
        body = hub._scroll_area(tab)

        # ---- new snapshot
        c = card(body, g, "New snapshot")
        row = tk.Frame(c, bg=c.cget("bg"))
        row.pack(fill="x", padx=16, pady=(6, 4))
        self.name_var = tk.StringVar()
        e = g["REntry"](row, self.name_var, width_px=320)
        e.pack(side="left")
        self._placeholder(e.entry, "Name, e.g. “Before Game Mode”")
        self.length = g["RSelect"](row, LENGTHS, width=150)
        self.length.set(LENGTHS[1])
        self.length.pack(side="left", padx=8)
        self.btn = g["RButton"](row, "Record", self.toggle, kind="primary")
        self.btn.pack(side="left")
        self.progress = label(c, "", g, 9, g["MUTED"], pady=(2, 10))

        # ---- results table
        t = card(body, g, "Snapshots")
        style = ttk.Style(hub)
        style.configure("RtSnap.Treeview", background=g["PANEL"], fieldbackground=g["PANEL"], foreground=g["FG"],
                        rowheight=26, borderwidth=0, font=(g["UI"], 9))
        style.configure("RtSnap.Treeview.Heading", background=g["PANEL"], foreground=g["MUTED"],
                        font=(g["UI"], 9, "bold"), relief="flat")
        self.table = ttk.Treeview(t, columns=COLUMNS, show="headings", height=7, style="RtSnap.Treeview")
        for col in COLUMNS:
            self.table.heading(col, text=col)
            self.table.column(col, width=150 if col == "Name" else 120, anchor="w", stretch=True)
        self.table.pack(fill="x", padx=16, pady=(6, 4))
        brow = tk.Frame(t, bg=t.cget("bg"))
        brow.pack(fill="x", padx=16, pady=(4, 12))
        g["RButton"](brow, "Clear list", self.clear, kind="default").pack(side="left")

        # ---- sensor logging to CSV
        lc = card(body, g, "Log sensors to CSV",
                  "Writes one row per live sample (about once a second): CPU and GPU load, clocks, VRAM, RAM, disk "
                  "and network rates, and temperatures and fans when LibreHardwareMonitor is running. Missing "
                  "readings are left empty, never 0.")
        lrow = tk.Frame(lc, bg=lc.cget("bg"))
        lrow.pack(fill="x", padx=16, pady=6)
        self.log_btn = g["RButton"](lrow, "Start logging…", self.toggle_logging, kind="primary")
        self.log_btn.pack(side="left")
        self.log_open = g["RButton"](lrow, "Open folder", self.open_log_folder, kind="default")
        self.log_open.pack(side="left", padx=8)
        self.log_open.set_enabled(False)
        self.log_status = label(lc, "Not logging.", g, 9, pady=(2, 12))

        # ---- FPS run compare
        fc = card(body, g, "Compare FPS runs",
                  "Pick two runs saved by the FPS test (FPS overlay page). Results only compare fairly with the same scene, in-game "
                  "settings and duration; this doesn't say which tweak helped.")
        frow = tk.Frame(fc, bg=fc.cget("bg"))
        frow.pack(fill="x", padx=16, pady=6)
        self.run_a = g["RSelect"](frow, [NA], width=300)
        self.run_a.pack(side="left")
        tk.Label(frow, text="vs", bg=frow.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left", padx=8)
        self.run_b = g["RSelect"](frow, [NA], width=300)
        self.run_b.pack(side="left")
        g["RButton"](frow, "Compare", self.compare, kind="primary").pack(side="left", padx=8)
        g["RButton"](frow, "Reload runs", self.load_runs, kind="ghost").pack(side="left")
        self.cmp_box = tk.Frame(fc, bg=fc.cget("bg"))
        self.cmp_box.pack(fill="x", padx=16, pady=(4, 12))
        self.runs = []
        self.load_runs()

        self._poll_job = None

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _placeholder(entry, text):
        def show(_e=None):
            if not entry.get():
                entry.insert(0, text)
                entry._ph = True
        def hide(_e=None):
            if getattr(entry, "_ph", False):
                entry.delete(0, "end")
                entry._ph = False
        entry.bind("<FocusIn>", hide, add="+")
        entry.bind("<FocusOut>", show, add="+")
        show()

    def _name(self):
        v = self.name_var.get().strip()
        if v.startswith("Name, e.g."):
            v = ""
        return v

    def temp_text(self, c):
        if c is None:
            return None
        if self.hub.settings.get("temp_unit") == "F":
            return f"{c * 9 / 5 + 32:.0f} °F"
        return f"{c:.0f} °C"

    # ---------------------------------------------------------------- live samples
    def _need_samples(self):
        return bool(self.recording or self.logger)

    def _ensure_feed(self):
        """Use the app's shared live feed when the Dashboard provides one, else our own sampler."""
        add = getattr(self.hub, "add_telemetry_listener", None)
        if callable(add):
            if not self._feed:
                add(self.on_telemetry)
                self._feed = True
            return
        self._sampler.start()
        if self._poll_job is None:
            self._poll_job = self.hub.after(200, self._poll)

    def _release_feed(self):
        if self._need_samples():
            return
        if self._feed:
            rem = getattr(self.hub, "remove_telemetry_listener", None)
            if callable(rem):
                rem(self.on_telemetry)
            self._feed = False
        self._sampler.stop()

    def _poll(self):
        self._poll_job = None
        while True:
            try:
                s = self._sampler.q.get_nowait()
            except queue.Empty:
                break
            self.on_telemetry(s)
        if self._sampler.error and self.recording and not self.samples:
            self.progress.configure(text=self._sampler.error)
        if self._sampler.running() or self._need_samples():
            try:
                self._poll_job = self.hub.after(200, self._poll)
            except tk.TclError:
                pass

    def on_telemetry(self, s):
        if self.logger:
            try:
                self.logger.write(s)
                self._log_update()
            except OSError as e:
                self.stop_logging()
                self.log_status.configure(text=f"Logging stopped: could not write the file ({e})")
        if not self.recording:
            return
        self.samples.append(s)
        elapsed = int((datetime.now() - self.recording["start"]).total_seconds())
        total = self.recording["seconds"]
        self.progress.configure(text=f"Recording… {min(elapsed, total)} / {total} s")
        if elapsed >= total:
            self._finish()

    # ---------------------------------------------------------------- snapshots
    def toggle(self):
        if self.recording:
            self._finish()
            return
        seconds = int(self.length.get().split()[0])
        n = len(self.table.get_children()) + 1
        self.recording = {"seconds": seconds, "start": datetime.now(), "name": self._name() or f"Snapshot {n}"}
        self.samples = []
        self.btn.set_text("Stop")
        self.progress.configure(text=f"Recording… 0 / {seconds} s")
        self._ensure_feed()

    def _finish(self):
        rec, samples = self.recording, self.samples
        self.recording = None
        self.btn.set_text("Record")
        self._release_feed()
        if not rec:
            return
        if not samples:
            self.progress.configure(text="Stopped before any data was recorded.")
            return
        length = int((datetime.now() - rec["start"]).total_seconds())
        values = summarize(rec["name"], rec["start"], samples, length, self.temp_text)
        item = self.table.insert("", "end", values=values)
        if not hasattr(self, "_raw_rows"):
            self._raw_rows = {}
        self._raw_rows[item] = (rec, samples, length)     # kept so °C/°F can be switched afterwards
        self.progress.configure(text=f"Saved “{rec['name']}”. GPU columns use GPU 1.")
        self.name_var.set("")

    def clear(self):
        for item in self.table.get_children():
            self.table.delete(item)
        self._raw_rows = {}

    def on_temp_unit(self, unit):
        """settings_store.set_temp_unit: show the recorded temperatures in the new unit."""
        for item, (rec, samples, length) in list(getattr(self, "_raw_rows", {}).items()):
            try:
                self.table.item(item, values=summarize(rec["name"], rec["start"], samples, length, self.temp_text))
            except Exception:
                self._raw_rows.pop(item, None)

    # ---------------------------------------------------------------- CSV logging
    def toggle_logging(self):
        if self.logger:
            self.stop_logging()
            return
        start = default_log_path()
        path = filedialog.asksaveasfilename(parent=self.tab, title="Save sensor log", initialdir=str(start.parent),
                                            initialfile=start.name, defaultextension=".csv",
                                            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            lg = SensorLogger(path)
            lg.start()
        except OSError as e:
            self.log_status.configure(text=f"Could not create the file: {e}")
            return
        self.logger = lg
        self._log_path = Path(path)
        self.log_btn.set_text("Stop logging")
        self.log_open.set_enabled(True)
        self._log_update()
        self._ensure_feed()

    def stop_logging(self):
        lg, self.logger = self.logger, None
        if lg:
            lg.stop()
            self.log_status.configure(text=f"Stopped. {lg.rows} rows written to {lg.path}{self._dropped_note(lg)}")
        self.log_btn.set_text("Start logging…")
        self._release_feed()

    @staticmethod
    def _dropped_note(lg):
        if lg.dropped_keys:
            return (f" Note: {len(lg.dropped_keys)} reading(s) appeared after logging started and are not in the "
                    "file (the header stays fixed).")
        return ""

    def _log_update(self):
        lg = self.logger
        if lg:
            self.log_status.configure(text=f"Logging: {lg.rows} rows written to {lg.path}{self._dropped_note(lg)}")

    def open_log_folder(self):
        folder = self._log_path.parent if self._log_path else default_log_path().parent
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))  # noqa
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            self.log_status.configure(text=f"Could not open the folder: {e}")

    # ---------------------------------------------------------------- FPS run compare
    @staticmethod
    def _run_label(r):
        avg = r.get("avg_fps")
        avg_t = f"{avg:.1f} FPS" if isinstance(avg, (int, float)) else NA
        return f"{(r.get('date') or '')[:16].replace('T', ' ')} · {r.get('game') or '?'} · {avg_t} [{r.get('id')}]"

    def load_runs(self):
        self.runs = fpsmod.load_runs()
        labels = [self._run_label(r) for r in self.runs] or ["No saved FPS runs yet"]
        for sel in (self.run_a, self.run_b):
            sel.values = labels
        self.run_a.set(labels[-2] if len(labels) > 1 else labels[0])
        self.run_b.set(labels[-1])

    def _run_for(self, text):
        for r in self.runs:
            if self._run_label(r) == text:
                return r
        return None

    def compare(self):
        for w in self.cmp_box.winfo_children():
            w.destroy()
        g = self.g
        a, b = self._run_for(self.run_a.get()), self._run_for(self.run_b.get())
        bg = self.cmp_box.cget("bg")
        if not a or not b:
            tk.Label(self.cmp_box, text="Save at least two FPS runs with the FPS test on the FPS overlay page first.", bg=bg,
                     fg=g["MUTED"], font=(g["UI"], 9)).pack(anchor="w")
            return
        grid = tk.Frame(self.cmp_box, bg=bg)
        grid.pack(fill="x")
        heads = ["Metric", "Run A", "Run B", "Difference"]
        for c, h in enumerate(heads):
            tk.Label(grid, text=h, bg=bg, fg=g["MUTED"], font=(g["UI"], 9, "bold"), anchor="w").grid(
                row=0, column=c, sticky="w", padx=(0, 22), pady=2)
        for i, (key, lbl, va, vb, diff, pct) in enumerate(fpsmod.compare_runs(a, b), start=1):
            if diff is None:
                d = NA
            else:
                d = fpsmod.format_metric(key, diff)
                if diff > 0:
                    d = "+" + d
                if pct is not None:
                    d += f" ({pct:+.1f}%)"
            cells = [lbl, fpsmod.format_metric(key, va), fpsmod.format_metric(key, vb), d]
            for c, v in enumerate(cells):
                tk.Label(grid, text=v, bg=bg, fg=g["FG"], font=(g["UI"], 9), anchor="w").grid(
                    row=i, column=c, sticky="w", padx=(0, 22), pady=1)
        for w_text in fpsmod.comparison_warnings(a, b):
            tk.Label(self.cmp_box, text=w_text, bg=bg, fg=g["MUTED"], font=(g["UI"], 9), anchor="w",
                     justify="left", wraplength=760).pack(fill="x", pady=(4, 0))

    # ---------------------------------------------------------------- lifecycle
    def on_shown(self):
        self.load_runs()

    def close(self):
        self.stop_logging()
        self._sampler.stop()
