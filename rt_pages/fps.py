# rt_pages/fps.py
"""FPS overlay page (renamed from "FPS test", owner request 2026-10-22): the in-game FPS overlay first
(built-in Windows frame events or PresentMon, with changeable timings), then the timed FPS test: real
average FPS and 1% / 0.1% lows measured with Intel PresentMon, saved runs with notes and comparison. Nothing here is estimated, and no result is credited to a
tweak automatically. All logic lives in core.fps / core.overlay_fps / core.etw_frames."""

import os
import sys
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from core import fps
from core import overlay_fps as of
from rt_pages.common import NA, button_row, card, label, run_bg

SETTING_PATH = "fps_presentmon_path"
SOURCE_LABELS = {"builtin": "Built-in (no download needed)", "presentmon": "PresentMon (uses the path below)"}
CORNER_LABELS = {c: c.replace("-", " ").capitalize() for c in of.CORNERS}
SIZE_LABELS = {z: z.capitalize() for z in of.SIZES}


def _inv(d):
    return {v: k for k, v in d.items()}


TEST_SECONDS_SETTING = "fps_test_seconds"
CUSTOM_LABEL = "Custom…"
LOW_WINDOW_LABELS = {f"{w} s": w for w in of.LOW_WINDOWS_S}
FPS_SPAN_LABELS = {("0.5 s" if s == 0.5 else f"{int(s)} s"): s for s in of.FPS_SPANS_S}
LOW_WINDOW_HELP = ("1% low window: the overlay's 1% low is the average of the slowest 1% of frames from this many "
                   "seconds back, shown as FPS. Longer = steadier number that remembers stutters longer; shorter = "
                   "reacts faster. It needs at least 100 frames in the window, otherwise it shows –.")
FPS_SPAN_HELP = ("FPS averaging: the big FPS number counts the frames from this many seconds back and divides by "
                 "the time they took. Shorter = reacts faster but jumps around more; longer = smoother.")
STALE_HELP = "If no frames arrive for 2 seconds (game minimized or paused), the numbers show – until frames return."


class FpsPage:
    title = "FPS overlay"
    subtitle = ("Live FPS, 1% low and frame time over your game, and a timed FPS test with Intel PresentMon "
                "(average FPS, 1% and 0.1% lows). Nothing here is estimated, and no result is credited to a "
                "tweak automatically.")

    def __init__(self, hub, tab, g):
        self.hub, self.tab, self.g = hub, tab, g
        self.capture = None
        self.capture_game = None
        self.current_runs = []
        self.procs = []
        self._loaded = False
        self._closed = False
        self.overlay_stream = None
        self.overlay_win = None
        self.overlay_game = None
        self.overlay_telemetry = None
        self._tick_job = None
        self._overlay_job = None
        self._stop_later_job = None
        self._row_ids = {}
        g["page_header"](tab, "RETWEAKS", self.title, self.subtitle)
        body = hub._scroll_area(tab)
        self.body = body
        self._style()

        # ---- in-game overlay first (owner choice 2026-10-22), with the game picker it shares with the test
        self._build_overlay_card(body)

        # ---- timed FPS test
        # ---- PresentMon location
        b = card(body, g, "PresentMon", "Needed for the FPS test, and for the overlay when Frame data is set to PresentMon.")
        label(b, "Missing PresentMon installs automatically when this page opens. You can also download the console from the "
                 "official releases page and select PresentMon.exe below. It needs administrator rights.",
              g, 9, g["MUTED"])
        link = label(b, "Open the official PresentMon releases page", g, 9, g["ACC"])
        link.configure(cursor="hand2")
        link.bind("<Button-1>", lambda e: webbrowser.open(fps.RELEASES_URL))
        row = tk.Frame(b, bg=b.cget("bg"))
        row.pack(fill="x", padx=16, pady=4)
        self.path_var = tk.StringVar(value=hub.settings.get(SETTING_PATH, "") or "")
        self.path_edit = g["REntry"](row, self.path_var)
        self.path_edit.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.path_edit.entry.bind("<FocusOut>", lambda e: self._path_typed())
        self.path_edit.entry.bind("<Return>", lambda e: self._path_typed())
        g["RButton"](row, "Browse…", self.browse).pack(side="left")
        self.path_status = label(b, "", g, 9, g["MUTED"], pady=(2, 12))

        # ---- run a test
        r = card(body, g, "FPS test", "Records the game you picked above for a set time with Intel PresentMon, "
                 "then saves average FPS, 1% low and 0.1% low. Start the game first and get to the scene you want "
                 "to test. Use the same scene, settings and length every time you compare.")
        drow = tk.Frame(r, bg=r.cget("bg"))
        drow.pack(fill="x", padx=16, pady=(4, 2))
        tk.Label(drow, text="Test length", bg=drow.cget("bg"), fg=g["FG"], font=(g["UI"], 10)).pack(side="left", padx=(0, 8))
        self.dur_labels = {(f"{d // 60} minutes" if d >= 300 else f"{d} seconds"): d for d in fps.DURATIONS}
        self.duration = g["RSelect"](drow, list(self.dur_labels) + [CUSTOM_LABEL], width=150,
                                     command=self._duration_changed)
        self.duration.pack(side="left")
        self.custom_var = tk.StringVar()
        self.custom_box = g["REntry"](drow, self.custom_var, width_px=80)
        self.custom_box.entry.bind("<Return>", lambda e: self._custom_seconds_typed())
        self.custom_box.entry.bind("<FocusOut>", lambda e: self._custom_seconds_typed())
        self.custom_unit = tk.Label(drow, text=f"seconds ({fps.CUSTOM_MIN_S}–{fps.CUSTOM_MAX_S})", bg=drow.cget("bg"),
                                    fg=g["MUTED"], font=(g["UI"], 9))
        self.btn_cancel = g["RButton"](drow, "Cancel", self.cancel)
        self.btn_cancel.pack(side="right")
        self.btn_start = g["RButton"](drow, "Start test", self.start, kind="primary")
        self.btn_start.pack(side="right", padx=(0, 8))
        self.btn_cancel.set_enabled(False)
        self.duration_help = label(r, "", g, 9, g["MUTED"])
        self.status = label(r, "", g, 10, pady=(4, 12))
        self._load_duration()

        # ---- result
        self.result_holder = tk.Frame(body, bg=g["BG"])
        self.result_holder.pack(fill="x")
        self.result_body = None

        # ---- saved runs
        s = card(body, g, "Saved runs")
        tf = tk.Frame(s, bg=s.cget("bg"))
        tf.pack(fill="x", padx=16, pady=4)
        cols = ("program", "date", "length", "avg", "low1", "low01", "notes")
        heads = ("Program", "Date", "Length", "Avg FPS", "1% low", "0.1% low", "Notes")
        self.table = ttk.Treeview(tf, columns=cols, show="headings", height=7, selectmode="extended",
                                  style="RT.Treeview")
        for c, h, w in zip(cols, heads, (170, 130, 70, 90, 90, 95, 220)):
            self.table.heading(c, text=h)
            self.table.column(c, width=w, minwidth=60, stretch=(c == "notes"))
        tsb = ttk.Scrollbar(tf, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=tsb.set)
        self.table.pack(side="left", fill="x", expand=True)
        tsb.pack(side="left", fill="y")
        self.table.bind("<<TreeviewSelect>>", lambda e: self._selection_changed())
        nrow = tk.Frame(s, bg=s.cget("bg"))
        nrow.pack(fill="x", padx=16, pady=4)
        self.notes_var = tk.StringVar()
        self.notes = g["REntry"](nrow, self.notes_var)
        self.notes.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.notes.entry.configure(disabledbackground=g.get("PANEL2", g["PANEL"]), disabledforeground=g["MUTED"])
        self.btn_notes = g["RButton"](nrow, "Save notes", self.save_notes)
        self.btn_notes.pack(side="left")
        brow = button_row(s, g)
        self.btn_compare = g["RButton"](brow, "Compare selected two", self.compare, kind="primary")
        self.btn_compare.pack(side="left", padx=(0, 8))
        self.btn_delete = g["RButton"](brow, "Delete selected run", self.delete)
        self.btn_delete.pack(side="left")
        self.saved_hint = label(s, "Select one run to edit its notes (for example \"Game Mode off, 1080p low\"), "
                                   "or two runs to compare them.", g, 9, g["MUTED"], pady=(0, 12))

        # ---- comparison
        self.compare_holder = tk.Frame(body, bg=g["BG"])
        self.compare_holder.pack(fill="x")
        self.compare_body = None

        if not self.path_var.get():
            found = fps.find_presentmon_near_exe()
            if found:
                self.path_var.set(found)
                self._set_setting(SETTING_PATH, found)
        self._check_path()
        self._selection_changed()
        tab.bind("<Destroy>", lambda e: self.close() if e.widget is tab else None, add="+")

    # ---------------------------------------------------------------- helpers
    def _style(self):
        g = self.g
        st = ttk.Style(self.hub)
        panel2 = g.get("PANEL2", g["PANEL"])
        st.configure("RT.Treeview", background=g["PANEL"], fieldbackground=g["PANEL"], foreground=g["FG"],
                     rowheight=28, borderwidth=0, font=(g["UI"], 10))
        st.configure("RT.Treeview.Heading", background=panel2, foreground=g["FG"], font=(g["UI"], 10, "bold"),
                     relief="flat")
        st.map("RT.Treeview", background=[("selected", panel2)], foreground=[("selected", g["FG"])])

    def _set_setting(self, key, value):
        self.hub.settings[key] = value
        self.hub.save_settings()

    def _after(self, ms, fn):
        if self._closed:
            return None
        try:
            return self.hub.after(ms, fn)
        except tk.TclError:
            return None

    def _cancel(self, job):
        if job:
            try:
                self.hub.after_cancel(job)
            except tk.TclError:
                pass

    def _set_color(self, w, color):
        try:
            w.configure(fg=color)
        except tk.TclError:
            pass

    # ---------------------------------------------------------------- lifecycle
    def on_shown(self):
        if not self._loaded:
            self._loaded = True
            self.refresh_processes()
            self.reload_runs()

    def close(self):
        """App closing / tab destroyed: stop timers, the overlay and any capture."""
        self._cancel(self._tick_job)
        self._tick_job = None
        self.stop_overlay()
        if self.capture:
            try:
                self.capture.cancel()
                self.capture.cleanup()
            except Exception:
                pass
            self.capture = None
        self._closed = True

    # ---------------------------------------------------------------- PresentMon path
    def browse(self):
        start = self.path_var.get() or os.path.expanduser("~")
        path = filedialog.askopenfilename(parent=self.hub, title="Select PresentMon.exe",
                                          initialdir=os.path.dirname(start) if os.path.isfile(start) else start,
                                          filetypes=[("Programs", "*.exe"), ("All files", "*")])
        if path:
            self.path_var.set(path)
            self._path_typed()

    def _path_typed(self):
        self._set_setting(SETTING_PATH, self.path_var.get().strip())
        self._check_path()

    def _check_path(self):
        ok, msg = fps.validate_presentmon_path(self.path_var.get().strip())
        self.path_status.configure(text="PresentMon found." if ok else msg)
        self._set_color(self.path_status, self.g["GREEN"] if ok else self.g["MUTED"])
        return ok

    # ---------------------------------------------------------------- processes
    def refresh_processes(self):
        self.proc_hint.configure(text="Reading running programs…")
        run_bg(self.hub, fps.list_processes, self._procs_loaded)

    def _procs_loaded(self, result):
        self.procs = result if isinstance(result, list) else []
        if not self.procs:
            self.proc_hint.configure(text="Could not read the list of running programs.")
        else:
            self.proc_hint.configure(text="Programs with a visible window." if sys.platform == "win32"
                                     else "All running processes.")
        self._filter_procs()

    def _selected_proc(self):
        sel = self.proc_list.curselection()
        return self.proc_names[sel[0]] if sel else None

    def _filter_procs(self):
        text = self.search_var.get().lower().strip()
        keep = self._selected_proc()
        self.proc_list.delete(0, "end")
        self.proc_names = []
        for name, title in self.procs:
            if text and text not in name.lower() and text not in (title or "").lower():
                continue
            self.proc_list.insert("end", f"{name}   {title}" if title else name)
            self.proc_names.append(name)
            if name == keep:
                self.proc_list.selection_set("end")

    # ---------------------------------------------------------------- running a test
    def _set_busy(self, busy):
        self.btn_overlay_start.set_enabled(not busy and not self.overlay_stream)
        self.btn_start.set_enabled(not busy)
        self.btn_cancel.set_enabled(busy)
        self.proc_list.configure(state="disabled" if busy else "normal")

    def start(self):
        if self.capture:
            return
        if self.overlay_stream:
            self.status.configure(text="Stop the in-game overlay first: only one PresentMon capture runs at a time.")
            return
        if not self._check_path():
            self.status.configure(text="Select PresentMon.exe first.")
            return
        name = self._selected_proc()
        if not name:
            self.status.configure(text="Pick the running program to measure.")
            return
        seconds = self.test_seconds()
        if seconds is None:
            self.status.configure(text=f"Type a test length between {fps.CUSTOM_MIN_S} and {fps.CUSTOM_MAX_S} seconds.")
            return
        cap = fps.Capture(self.path_var.get().strip(), name, seconds)
        try:
            cap.start()
        except (OSError, ValueError) as e:
            cap.cleanup()
            msg = str(e)
            if getattr(e, "winerror", None) == 740:
                msg = "Windows needs administrator rights to start PresentMon. " + fps.ADMIN_HINT
            self.status.configure(text=f"Could not start PresentMon: {msg}")
            self.hub.log_action("FPS overlay", f"FPS test with PresentMon on {name}", "Failed", msg)
            return
        self.capture, self.capture_game = cap, name
        self._set_busy(True)
        self._clear_result()
        self.status.configure(text=f"Measuring {name}… 0 / {seconds} s")
        self._tick_job = self._after(250, self._tick)

    def cancel(self):
        if self.capture:
            self._cancel(self._tick_job)
            self._tick_job = None
            self.capture.cancel()
            self.capture.cleanup()
            self.capture = None
            self._set_busy(False)
            self.status.configure(text="Cancelled. Nothing was saved.")

    def _tick(self):
        self._tick_job = None
        cap = self.capture
        if not cap:
            return
        if cap.running():
            if cap.overdue():
                cap.terminate()      # finish() below handles whatever was written
            else:
                self.status.configure(text=f"Measuring {self.capture_game}… "
                                           f"{min(int(cap.elapsed()), cap.seconds)} / {cap.seconds} s")
                self._tick_job = self._after(250, self._tick)
                return
        self.status.configure(text="Reading the results…")
        self.btn_cancel.set_enabled(False)     # too late to cancel: the results are being read
        game, secs = self.capture_game, cap.seconds
        run_bg(self.hub, cap.finish, lambda res: self._finished(res, cap, game, secs))

    def _finished(self, result, cap, game, seconds):
        cap.cleanup()
        self.capture = None
        self._set_busy(False)
        if not (isinstance(result, tuple) and len(result) == 2):
            self.status.configure(text=f"Unexpected error: {result}")
            return
        frames, err = result
        if err:
            self.status.configure(text=err)
            self.hub.log_action("FPS overlay", f"FPS test with PresentMon on {game}", "Failed", err.splitlines()[0])
            return
        metrics = fps.compute_metrics(frames)
        run = fps.make_run(game, seconds, metrics)
        try:
            fps.add_run(run)
            saved = "Saved to your run list."
        except OSError as e:
            saved = f"The result could not be saved ({e})."
        avg = metrics.get("avg_fps")
        self.hub.log_action("FPS overlay", f"FPS test with PresentMon on {game}, {seconds} s",
                            (f"{avg:.1f} FPS average" if avg is not None else "No average") +
                            f", {metrics.get('frames', 0)} frames")
        self.status.configure(text=f"Done. {saved}")
        self._show_result(run)
        self.reload_runs()

    def _clear_result(self):
        for w in self.result_holder.winfo_children():
            w.destroy()
        self.result_body = None

    def _show_result(self, run):
        self._clear_result()
        g = self.g
        b = card(self.result_holder, g, "Result")
        from rt_pages.common import kv_rows
        kv_rows(b, g, [("Program", run.get("game") or NA)] +
                [(lbl, fps.format_metric(key, run.get(key))) for key, lbl, _u in fps.METRIC_ROWS])
        label(b, fps.METHOD_TEXT, g, 9, g["MUTED"], pady=(4, 12))
        self.result_body = b

    # ---------------------------------------------------------------- in-game overlay
    # ------------------------------------------------------------ test length (setting fps_test_seconds)
    def _load_duration(self):
        saved = fps.clean_seconds(self.hub.settings.get(TEST_SECONDS_SETTING), default=fps.DURATIONS[1])
        label = next((k for k, v in self.dur_labels.items() if v == saved), None)
        if label:
            self.duration.set(label)
        else:
            self.duration.set(CUSTOM_LABEL)
            self.custom_var.set(str(saved))
        self._duration_changed(self.duration.get(), save=False)

    def _duration_changed(self, text, save=True):
        custom = text == CUSTOM_LABEL
        if custom:
            self.custom_box.pack(side="left", padx=(8, 4))
            self.custom_unit.pack(side="left")
            if not self.custom_var.get():      # start from the length used last time
                self.custom_var.set(str(fps.clean_seconds(self.hub.settings.get(TEST_SECONDS_SETTING),
                                                          default=fps.DURATIONS[1])))
        else:
            self.custom_box.pack_forget()
            self.custom_unit.pack_forget()
        secs = self.test_seconds()
        self.duration_help.configure(text=(f"The test records {secs} seconds of frames, then shows the results."
                                           if secs else "Type a length, then press Enter."))
        if save and secs:
            self.hub.settings[TEST_SECONDS_SETTING] = secs
            self.hub.save_settings()

    def _custom_seconds_typed(self):
        secs = self.test_seconds()
        if secs is None:
            self.duration_help.configure(text=f"Type a whole number of seconds from {fps.CUSTOM_MIN_S} to "
                                              f"{fps.CUSTOM_MAX_S}.")
            return
        self._duration_changed(CUSTOM_LABEL)

    def test_seconds(self):
        """The chosen test length in seconds, or None when the custom box holds an invalid number."""
        text = self.duration.get()
        if text != CUSTOM_LABEL:
            return self.dur_labels.get(text, fps.DURATIONS[1])
        v = fps.clean_seconds(self.custom_var.get().strip(), default=None)
        return v

    def _build_overlay_card(self, body):
        g = self.g
        cfg = of.clean_settings(self.hub.settings)
        o = card(body, g, "In-game overlay", "Shows FPS, 1% low and frame time over the game while you play. "
                 "Pick the running game below, then press Start overlay. Needs administrator rights.")
        label(o, of.SETTING_NOTE, g, 9, g["MUTED"])
        r = o
        srow = tk.Frame(o, bg=o.cget("bg"))
        srow.pack(fill="x", padx=16, pady=4)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter_procs())
        g["REntry"](srow, self.search_var).pack(side="left", fill="x", expand=True, padx=(0, 8))
        g["RButton"](srow, "Refresh list", self.refresh_processes).pack(side="left")
        lf = tk.Frame(o, bg=o.cget("bg"))
        lf.pack(fill="x", padx=16, pady=4)
        self.proc_list = tk.Listbox(lf, height=8, bg=g["PANEL2"] if "PANEL2" in g else g["PANEL"], fg=g["FG"],
                                    selectbackground=g["ACC"], selectforeground=g.get("ACC_D", "#141416"),
                                    highlightthickness=1, highlightbackground=g["LINE"], highlightcolor=g["ACC"],
                                    relief="flat", bd=0, font=(g["UI"], 10), activestyle="none", exportselection=False)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.proc_list.yview)
        self.proc_list.configure(yscrollcommand=sb.set)
        self.proc_list.pack(side="left", fill="x", expand=True)
        sb.pack(side="left", fill="y")
        self.proc_names = []
        self.proc_hint = label(o, "", g, 9, g["MUTED"])

        row = tk.Frame(o, bg=o.cget("bg"))
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text="Position", bg=row.cget("bg"), fg=g["FG"], font=(g["UI"], 10)).pack(side="left", padx=(0, 6))
        self.ov_pos = g["RSelect"](row, list(CORNER_LABELS.values()), width=150, command=self._overlay_setting_changed)
        self.ov_pos.set(CORNER_LABELS[cfg["overlay_position"]])
        self.ov_pos.pack(side="left", padx=(0, 14))
        tk.Label(row, text="Size", bg=row.cget("bg"), fg=g["FG"], font=(g["UI"], 10)).pack(side="left", padx=(0, 6))
        self.ov_size = g["RSelect"](row, list(SIZE_LABELS.values()), width=120, command=self._overlay_setting_changed)
        self.ov_size.set(SIZE_LABELS[cfg["overlay_size"]])
        self.ov_size.pack(side="left", padx=(0, 14))
        self.ov_load_var = tk.BooleanVar(value=cfg["overlay_show_load"])
        g["RCheck"](row, "Show hardware metrics", self.ov_load_var, command=self._overlay_setting_changed).pack(side="left")
        srow = tk.Frame(o, bg=o.cget("bg"))
        srow.pack(fill="x", padx=16, pady=4)
        tk.Label(srow, text="Frame data", bg=srow.cget("bg"), fg=g["FG"], font=(g["UI"], 10)).pack(side="left", padx=(0, 6))
        self.ov_source = g["RSelect"](srow, list(SOURCE_LABELS.values()), width=290,
                                      command=self._overlay_setting_changed)
        self.ov_source.set(SOURCE_LABELS[cfg["overlay_source"]])
        self.ov_source.pack(side="left")
        label(o, "Built-in: RETWEAKS reads Windows' own frame events, the same data PresentMon uses. It measures "
                 "the time between frames the game sends to Windows.", g, 9, g["MUTED"])
        orow = tk.Frame(o, bg=o.cget("bg"))
        orow.pack(fill="x", padx=16, pady=4)
        tk.Label(orow, text="Opacity", bg=orow.cget("bg"), fg=g["FG"], font=(g["UI"], 10)).pack(side="left", padx=(0, 6))
        self.ov_opacity = tk.Scale(orow, from_=50, to=100, orient="horizontal", showvalue=False, length=260,
                                   bg=orow.cget("bg"), fg=g["FG"], troughcolor=g.get("PANEL2", g["PANEL"]),
                                   highlightthickness=0, bd=0, sliderrelief="flat", activebackground=g["ACC"],
                                   command=lambda v: self._overlay_setting_changed())
        self.ov_opacity.set(cfg["overlay_opacity"])
        self.ov_opacity.pack(side="left")
        self.ov_opacity_lbl = tk.Label(orow, text=f"{cfg['overlay_opacity']}%", bg=orow.cget("bg"), fg=g["FG"],
                                       font=(g["UI"], 10))
        self.ov_opacity_lbl.pack(side="left", padx=8)
        # timings (owner request 2026-10-22): changeable, saved, applied to a running overlay at once
        trow = tk.Frame(o, bg=o.cget("bg"))
        trow.pack(fill="x", padx=16, pady=(8, 2))
        tk.Label(trow, text="1% low window", bg=trow.cget("bg"), fg=g["FG"], font=(g["UI"], 10)).pack(side="left", padx=(0, 6))
        self.ov_low = g["RSelect"](trow, list(LOW_WINDOW_LABELS), width=110, command=self._overlay_setting_changed)
        self.ov_low.set(next(k for k, v in LOW_WINDOW_LABELS.items() if v == cfg["overlay_low_window_s"]))
        self.ov_low.pack(side="left", padx=(0, 14))
        tk.Label(trow, text="FPS averaging", bg=trow.cget("bg"), fg=g["FG"], font=(g["UI"], 10)).pack(side="left", padx=(0, 6))
        self.ov_span = g["RSelect"](trow, list(FPS_SPAN_LABELS), width=110, command=self._overlay_setting_changed)
        self.ov_span.set(next(k for k, v in FPS_SPAN_LABELS.items() if v == cfg["overlay_fps_span_s"]))
        self.ov_span.pack(side="left")
        self.timing_help = label(o, "\n".join((LOW_WINDOW_HELP, FPS_SPAN_HELP, STALE_HELP)), g, 9, g["MUTED"])
        of.set_timings(cfg["overlay_low_window_s"], cfg["overlay_fps_span_s"])
        label(o, 'Overlay metrics', g, 12, bold=True)
        label(o, 'Choose individual readings. Hardware metrics uses system-wide utilization; GPU readings follow '
              'the busiest adapter. Unsupported sensors show –. The hardware switch above hides hardware rows. '
              '0.1% lows need 1,000 frames in the rolling window. Min/max are individual-frame FPS equivalents.',
              g, 9, g['MUTED'])
        metrics = tk.Frame(o, bg=o.cget('bg'))
        metrics.pack(fill='x', padx=16, pady=6)
        self.ov_metric_vars = {}
        for index, (key, title, _) in enumerate(of.METRIC_OPTIONS):
            var = tk.BooleanVar(value=cfg['overlay_show_' + key])
            self.ov_metric_vars[key] = var
            g['RCheck'](metrics, title, var, command=self._overlay_setting_changed).grid(
                row=index // 3, column=index % 3, sticky='w', padx=(0, 18), pady=2)
        row = button_row(o, g)
        self.ov_layout = g['RSelect'](row, ['Stacked', 'Compact'], width=130, command=self._overlay_setting_changed)
        self.ov_layout.set(cfg['overlay_layout'].capitalize())
        self.ov_layout.pack(side='left', padx=(0, 8))
        self.ov_refresh = g['RSelect'](row, ['100 ms', '250 ms', '400 ms', '1000 ms'], width=120, command=self._overlay_setting_changed)
        self.ov_refresh.set(str(cfg['overlay_refresh_ms']) + ' ms')
        self.ov_refresh.pack(side='left', padx=(0, 8))
        self.ov_margin = g['RSelect'](row, ['8 px', '16 px', '24 px', '32 px', '48 px'], width=110, command=self._overlay_setting_changed)
        self.ov_margin.set(str(cfg['overlay_margin']) + ' px')
        self.ov_margin.pack(side='left', padx=(0, 8))
        self.ov_digits = g['RSelect'](row, ['Whole FPS', '1 decimal'], width=130, command=self._overlay_setting_changed)
        self.ov_digits.set('1 decimal' if cfg['overlay_decimals'] else 'Whole FPS')
        self.ov_digits.pack(side='left')
        label(o, 'Layout · text refresh · screen-edge spacing · FPS precision. Changes apply live and are saved.', g, 9, g['MUTED'])
        brow = button_row(o, g)
        self.btn_overlay_start = g["RButton"](brow, "Start overlay", self.start_overlay, kind="primary")
        self.btn_overlay_start.pack(side="left", padx=(0, 8))
        self.btn_overlay_stop = g["RButton"](brow, "Stop overlay", lambda: self.stop_overlay())
        self.btn_overlay_stop.pack(side="left")
        self.btn_overlay_stop.set_enabled(False)
        self.overlay_status = label(o, "", g, 10, pady=(0, 12))

    def _overlay_values(self):
        return {**{'overlay_show_' + key: var.get() for key, var in self.ov_metric_vars.items()},
                'overlay_layout': self.ov_layout.get().lower(),
                'overlay_refresh_ms': int(self.ov_refresh.get().split()[0]),
                'overlay_margin': int(self.ov_margin.get().split()[0]),
                'overlay_decimals': int(self.ov_digits.get() == '1 decimal'),
                "overlay_position": _inv(CORNER_LABELS).get(self.ov_pos.get(), of.DEFAULTS["overlay_position"]),
                "overlay_size": _inv(SIZE_LABELS).get(self.ov_size.get(), of.DEFAULTS["overlay_size"]),
                "overlay_show_load": bool(self.ov_load_var.get()),
                "overlay_opacity": int(self.ov_opacity.get()),
                "overlay_source": _inv(SOURCE_LABELS).get(self.ov_source.get(), of.DEFAULTS["overlay_source"]),
                "overlay_low_window_s": LOW_WINDOW_LABELS.get(self.ov_low.get(), of.DEFAULTS["overlay_low_window_s"]),
                "overlay_fps_span_s": FPS_SPAN_LABELS.get(self.ov_span.get(), of.DEFAULTS["overlay_fps_span_s"])}

    def _overlay_setting_changed(self, *_):
        vals = self._overlay_values()
        self.ov_opacity_lbl.configure(text=f"{vals['overlay_opacity']}%")
        changed = False
        for k, v in vals.items():
            if self.hub.settings.get(k) != v:
                self.hub.settings[k] = v
                changed = True
        if changed:
            self.hub.save_settings()
        of.set_timings(vals["overlay_low_window_s"], vals["overlay_fps_span_s"])   # live, also for a running overlay
        self._sync_overlay_telemetry(vals)
        if self.overlay_win:
            self.overlay_win.apply_settings(vals)
            self._update_overlay_text()

    def _overlay_colors(self):
        g = self.g
        return {"bg": g["BG"], "text": g["FG"], "subtext": g["MUTED"]}

    def _overlay_problem(self, msg, log=None):
        """Show why the overlay didn't start: in the card AND as a pop-up, so it can't go unnoticed."""
        self.overlay_status.configure(text=msg)
        if log:
            self.hub.log_action("FPS overlay", log, "Failed", msg)
        messagebox.showwarning("In-game overlay", msg, parent=self.hub)

    def start_overlay(self):
        if self.overlay_stream:
            return
        vals = self._overlay_values()
        builtin = vals["overlay_source"] == "builtin"
        if not builtin and self.capture:
            return self._overlay_problem("An FPS test is running: only one PresentMon capture runs at a time.")
        if not builtin and not self._check_path():
            return self._overlay_problem("Select PresentMon.exe first, or switch Frame data to Built-in.")
        name = self._selected_proc()
        if not name:
            return self._overlay_problem("First click the game in the list of running programs above "
                                         "(start the game, press Refresh list if it isn't listed), then press "
                                         "Start overlay.")
        what = "the built-in frame counter" if builtin else "PresentMon"
        stream = None
        try:
            if builtin:
                from core.etw_frames import BuiltinOverlayStream
                stream = BuiltinOverlayStream(name)
            else:
                stream = of.OverlayStream(self.path_var.get().strip(), name)
            stream.start()
        except (OSError, ValueError) as e:
            msg = str(e)
            if getattr(e, "winerror", None) == 740:
                msg = "Windows needs administrator rights to start PresentMon. " + fps.ADMIN_HINT
            return self._overlay_problem(f"Could not start {what}: {msg}", f"{what} on {name}")
        except Exception as e:       # never fail silently
            if stream:
                try:
                    stream.stop()
                except Exception:
                    pass
            return self._overlay_problem(f"Could not start {what}: {type(e).__name__}: {e}", f"{what} on {name}")
        try:
            from rt_pages.overlay_tk import OverlayWindow
            self.overlay_stream, self.overlay_game = stream, name
            self.overlay_win = OverlayWindow(self.hub, self._overlay_colors(), vals, name)
            self.overlay_win.set_lines(self._format_overlay(None, vals))
            self.overlay_win.show_overlay()
        except Exception as e:
            self.stop_overlay()
            return self._overlay_problem(f"Couldn't show the overlay window: {type(e).__name__}: {e}",
                                         f"Overlay window for {name}")
        self.btn_overlay_start.set_enabled(False)
        self.btn_overlay_stop.set_enabled(True)
        self.btn_start.set_enabled(False)
        self.overlay_status.configure(text=f"Overlay running for {name}. Waiting for frames…")
        self.hub.log_action("FPS overlay", f"Start overlay on {name}", "Started")
        self._sync_overlay_telemetry(vals)
        self._prime_cpu()
        self._overlay_job = self._after(vals["overlay_refresh_ms"], self._overlay_tick)

    def stop_overlay(self, message=None):
        self._cancel(self._overlay_job)
        self._cancel(self._stop_later_job)
        self._overlay_job = self._stop_later_job = None
        stream, win = self.overlay_stream, self.overlay_win
        if self.overlay_telemetry is not None:
            self.overlay_telemetry.release(self)
            self.overlay_telemetry = None
        self.overlay_stream = self.overlay_win = None
        if win:
            win.destroy()
        if stream:
            try:
                stream.stop()
            except Exception:
                pass
        if self._closed:
            return
        try:
            self.btn_overlay_stop.set_enabled(False)
            self.btn_overlay_start.set_enabled(not self.capture)
            self.btn_start.set_enabled(not self.capture)
            if stream:
                self.overlay_status.configure(text=message or "Overlay stopped.")
        except tk.TclError:
            pass

    def on_theme(self, *_):
        if self.overlay_win:
            self.overlay_win.set_theme(self._overlay_colors())

    def _prime_cpu(self):
        try:
            import psutil
            psutil.cpu_percent(None)
        except Exception:
            pass

    def _loads(self):
        """(cpu %, gpu %): from the dashboard's live sample when it has one; otherwise CPU from psutil
        and GPU Unavailable ('–' in the overlay). Never invented."""
        sample = getattr(self.hub, "rt_last_sample", None)
        if sample:
            return of.loads_from_sample(sample)
        try:
            import psutil
            return psutil.cpu_percent(None), None
        except Exception:
            return None, None

    def _format_overlay(self, snap, vals):
        sample = getattr(self.hub, 'rt_last_sample', None)
        interval = getattr(getattr(self, 'overlay_telemetry', None), 'interval', lambda: 1.0)()
        hardware = of.hardware_from_sample(sample, max_age=max(5, interval * 3))
        from rt_pages.settings_store import temp_unit
        hardware['temperature_unit'] = temp_unit(self.hub)
        return of.format_lines(snap, settings=vals, hardware=hardware, game_name=self.overlay_game)

    def _sync_overlay_telemetry(self, vals):
        hardware_keys = [key for key, _, _ in of.METRIC_OPTIONS][8:-1]
        needed = self.overlay_stream is not None and vals['overlay_show_load'] and any(
            vals['overlay_show_' + key] for key in hardware_keys)
        if needed and self.overlay_telemetry is None:
            from rt_pages.monitor import telemetry_service
            self.overlay_telemetry = telemetry_service(self.hub)
            self.overlay_telemetry.acquire(self)
        elif not needed and self.overlay_telemetry is not None:
            self.overlay_telemetry.release(self)
            self.overlay_telemetry = None

    def _update_overlay_text(self):
        if self.overlay_stream and self.overlay_win:
            snap, state = self.overlay_stream.snapshot()
            self.overlay_win.set_lines(of.format_lines(None, state=state) if state in ('closed', 'error')
                                      else self._format_overlay(snap, self._overlay_values()))

    def _overlay_tick(self):
        self._overlay_job = None
        stream, win = self.overlay_stream, self.overlay_win
        if not stream or not win:
            return
        snap, state = stream.snapshot()
        if state == "closed":
            win.set_lines(of.format_lines(None, state="closed"))
            name = self.overlay_game
            self.hub.log_action("FPS overlay", f"Overlay on {name}", "Stopped: game closed")
            self._stop_overlay_later(f"{name} closed. The overlay stopped.")
            return
        if state == "error":
            msg = stream.error or "The frame capture stopped."
            self.hub.log_action("FPS overlay", f"Overlay on {self.overlay_game}", "Failed", msg)
            self.stop_overlay(msg)
            return
        win.set_lines(self._format_overlay(snap, self._overlay_values()))
        if not stream.has_frames():
            self.overlay_status.configure(text=f"Overlay running for {self.overlay_game}. Waiting for frames: the "
                                               "program must be presenting (not minimized).")
        else:
            src = getattr(stream, "source", None)
            how = {"api": " Frame data: DirectX presents (built-in).",
                   "kernel": " Frame data: Windows graphics kernel presents (built-in; used for OpenGL "
                             "and some Vulkan games)."}.get(src, "")
            self.overlay_status.configure(text=f"Overlay running for {self.overlay_game}.{how}")
        self._overlay_job = self._after(self._overlay_values()["overlay_refresh_ms"], self._overlay_tick)

    def _stop_overlay_later(self, message):
        """Show 'Game closed' for 3 s, then stop and tidy up."""
        s = self.overlay_stream
        self._stop_later_job = self._after(3000, lambda: self.stop_overlay(message) if self.overlay_stream is s else None)
        self.overlay_status.configure(text=message)

    # ---------------------------------------------------------------- saved runs
    def reload_runs(self):
        self.current_runs = fps.load_runs()
        self.table.delete(*self.table.get_children())
        self._row_ids = {}
        for run in reversed(self.current_runs):
            try:
                date = datetime.fromisoformat(run.get("date", "")).strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                date = run.get("date", "") or NA
            vals = [run.get("game", ""), date, f"{run.get('seconds', '?')} s",
                    fps.format_metric("avg_fps", run.get("avg_fps")) if run.get("avg_fps") is not None else NA,
                    fps.format_metric("low1_fps", run.get("low1_fps")),
                    fps.format_metric("low01_fps", run.get("low01_fps")),
                    run.get("notes", "")]
            iid = self.table.insert("", "end", values=vals)
            self._row_ids[iid] = run.get("id")
        self._selection_changed()

    def _selected_ids(self):
        return [self._row_ids[i] for i in self.table.selection() if i in self._row_ids]

    def _run_by_id(self, rid):
        return next((r for r in self.current_runs if r.get("id") == rid), None)

    def _selection_changed(self):
        ids = self._selected_ids()
        self.btn_compare.set_enabled(len(ids) == 2)
        self.btn_delete.set_enabled(len(ids) == 1)
        self.btn_notes.set_enabled(len(ids) == 1)
        self.notes.entry.configure(state="normal" if len(ids) == 1 else "disabled")
        if len(ids) == 1:
            run = self._run_by_id(ids[0])
            self.notes_var.set(run.get("notes", "") if run else "")
            if run:
                self._show_result(run)
        else:
            self.notes_var.set("")

    def save_notes(self):
        ids = self._selected_ids()
        if len(ids) == 1:
            try:
                fps.update_notes(ids[0], self.notes_var.get().strip())
            except OSError as e:
                self.saved_hint.configure(text=f"Could not save notes: {e}")
                return
            self.reload_runs()
            self.saved_hint.configure(text="Notes saved.")

    def delete(self):
        ids = self._selected_ids()
        if len(ids) != 1:
            return
        run = self._run_by_id(ids[0]) or {}
        if not messagebox.askyesno("Delete run", f"Delete the saved run for {run.get('game', '')} "
                                                 f"({run.get('date', '')})? This cannot be undone.", parent=self.hub):
            return
        try:
            fps.delete_run(ids[0])
        except OSError as e:
            self.saved_hint.configure(text=f"Could not delete: {e}")
            return
        self._clear_compare()
        self.reload_runs()

    def _clear_compare(self):
        for w in self.compare_holder.winfo_children():
            w.destroy()
        self.compare_body = None

    def compare(self):
        ids = self._selected_ids()
        if len(ids) != 2:
            return
        a, b = (self._run_by_id(i) for i in ids)
        if not a or not b:
            return
        if a.get("date", "") > b.get("date", ""):
            a, b = b, a      # A = older run
        self._clear_compare()
        g = self.g
        title = (f"Comparison: A = {a.get('game')} {a.get('date', '')[:16]}   "
                 f"B = {b.get('game')} {b.get('date', '')[:16]}")
        body = card(self.compare_holder, g, title)
        warns = fps.comparison_warnings(a, b)
        if warns:
            label(body, "\n".join("• " + w for w in warns), g, 9, "#ffb020")
        tf = tk.Frame(body, bg=body.cget("bg"))
        tf.pack(fill="x", padx=16, pady=4)
        cols = ("metric", "a", "b", "diff", "pct")
        rows = fps.compare_runs(a, b)
        tree = ttk.Treeview(tf, columns=cols, show="headings", height=max(1, len(rows)), style="RT.Treeview")
        for c, h in zip(cols, ("Metric", "Run A", "Run B", "Difference (B − A)", "Change")):
            tree.heading(c, text=h)
            tree.column(c, width=150, stretch=True)
        tree.pack(fill="x")
        for key, lbl, va, vb, diff, pct in rows:
            unit = "ms" if key.endswith("_ms") else ("s" if key == "duration_s" else "")
            if diff is None:
                d, p = NA, NA
            else:
                digits = 0 if key == "frames" else (2 if unit == "ms" else 1)
                d = f"{diff:+.{digits}f} {unit or ('FPS' if key.endswith('_fps') else '')}".strip()
                p = f"{pct:+.1f}%" if pct is not None else NA
            tree.insert("", "end", values=(lbl, fps.format_metric(key, va), fps.format_metric(key, vb), d, p))
        label(body, "A difference is a measurement, not proof that a setting caused it. Run-to-run variation is "
                    "normal; repeat each test before drawing conclusions.", g, 9, g["MUTED"], pady=(4, 12))
        self.compare_body = body
        self.compare_tree = tree
