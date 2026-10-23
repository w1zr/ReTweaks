"""Cleanup: the parts of RETWEAKS' Storage & cleanup page that the base app's Storage Explorer doesn't have.

The base app's Storage page (storage_explorer.py) already shows drives (size/used/free/file system) and
browses, filters, sorts and opens files. This page adds, from RETWEAKS (ui/pages/storage.py), using
core.storage_manager unchanged:
  - drive health as reported by Windows (Get-PhysicalDisk, via core.hardware's scan)
  - temp-file cleanup with a preview of what will be deleted (CLAUDE.md: never delete unseen)
  - disk usage breakdown (top-level shares, largest folders, largest files; cancellable)
  - file search in a folder and its subfolders (cancellable, results open/show/copy)."""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog

from core.storage_manager import (BackgroundJob, ScanState, cleanup_temp_files_safe, format_mtime,
                                  get_disk_drives, human_size, preview_temp_files, scan_tree, search_files)
from rt_pages.common import NA, confirm, info, run_bg
from rt_pages.startup import make_table


def drive_rows(drives, static):
    """Join psutil drives with the physical disk's name and health from the hardware scan."""
    by_letter = {}
    for d in (static or {}).get("disks", []) or []:
        for letter in d.get("letters", []) or []:
            by_letter[str(letter).upper().rstrip("\\").rstrip(":") + ":"] = d
    rows = []
    for d in drives:
        letter = d["device"].rstrip("\\").upper()
        disk = by_letter.get(letter, {})
        rows.append((f"{d['device']}  ({d['fstype']})", disk.get("name") or NA, disk.get("health") or NA,
                     d["total"], d["free"], f"{d['percent']:.0f}%"))
    return rows


def cleanup_question(items, size):
    if items == 0:
        return None
    return (f"Found {items} item(s), about {size / 1024 ** 2:.1f} MB, in your Temp folder and Windows\\Temp.\n\n"
            "Delete them? Files that are in use will be skipped.")


def _open(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
        return None
    except OSError as e:
        return str(e)


def _show_in_explorer(path):
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        return None
    except OSError as e:
        return str(e)


class CleanupPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        self._loaded = False
        self._scan_job = self._scan_state = None
        self._search_job = self._search_state = None
        self._paths = {}
        g["page_header"](tab, "RETWEAKS", "Cleanup",
                         "Drive health, safe temp-file cleanup, a disk usage breakdown and file search. "
                         "Nothing is deleted without a preview and your OK.")
        body = hub._scroll_area(tab)
        self._drives_card(body)
        self._temp_card(body)
        self._usage_card(body)
        self._search_card(body)

    # ------------------------------------------------------------ drives
    def _drives_card(self, body):
        g = self.g
        c = g["Card"](body)
        c.pack(fill="x", pady=6, padx=(0, 12))
        b = c.body
        self._title(b, "Drive health", "Health is what Windows reports for each physical disk (Healthy, Warning or "
                    "Unhealthy). Unavailable means Windows didn't report it.")
        self.drives = make_table(self.hub, g, b, ("drive", "disk", "health", "size", "free", "used"),
                                 ("Drive", "Disk", "Health", "Size", "Free", "Used"), 4,
                                 {"drive": 160, "disk": 260, "health": 120, "size": 110, "free": 110, "used": 80})
        self.drive_note = tk.Label(b, text="", bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9), anchor="w")
        self.drive_note.pack(fill="x", padx=16, pady=(0, 12))

    def load_drives(self):
        def fill(static):
            st = static if isinstance(static, dict) else None
            if st is not None:
                self.hub.rt_static = st
            drives = get_disk_drives()
            self.drives.delete(*self.drives.get_children())
            for row in drive_rows(drives, st):
                self.drives.insert("", "end", values=row,
                                   tags=("good",) if row[2] == "Healthy" else (("bad",) if row[2] in ("Warning", "Unhealthy") else ()))
            self.drive_note.config(text="" if st else "Disk names and health are Unavailable: the hardware scan failed."
                                   if isinstance(static, Exception) else "")
        static = getattr(self.hub, "rt_static", None)
        if static:
            fill(static)
        else:
            self.drive_note.config(text="Reading disk health from Windows…")
            from core.hardware import scan_static
            run_bg(self.hub, scan_static, fill)

    # ------------------------------------------------------------ temp files
    def _temp_card(self, body):
        g = self.g
        c = g["Card"](body)
        c.pack(fill="x", pady=6, padx=(0, 12))
        b = c.body
        self._title(b, "Temp files", "Deletes files in your Temp folder and Windows\\Temp. Files that are in use are "
                    "skipped. Your documents, downloads and Recycle Bin are never touched.")
        row = tk.Frame(b, bg=b.cget("bg"))
        row.pack(fill="x", padx=16, pady=(4, 14))
        self.btn_clean = g["RButton"](row, "Clean temp files", self.run_cleanup, kind="primary")
        self.btn_clean.pack(side="left")
        self.clean_result = tk.Label(row, text="", bg=b.cget("bg"), fg=g["FG"], font=(g["UI"], 10), anchor="w",
                                     justify="left", wraplength=700)
        self.clean_result.pack(side="left", padx=12, fill="x")

    def run_cleanup(self):
        if not self.btn_clean.enabled:
            return
        self.btn_clean.set_enabled(False)
        self.clean_result.config(text="Checking temp folders…")
        run_bg(self.hub, preview_temp_files, self._confirm_cleanup)

    def _confirm_cleanup(self, result, ask=None):
        self.btn_clean.set_enabled(True)
        if not isinstance(result, tuple) or len(result) != 2:
            self.clean_result.config(text=f"Could not check the temp folders: {result}")
            return
        items, size = result
        q = cleanup_question(items, size)
        if q is None:
            self.clean_result.config(text="Temp folders are already empty.")
            return
        self.clean_result.config(text="")
        if not (ask or confirm)(self.hub, "Clean temp files", q):
            return
        self.btn_clean.set_enabled(False)
        self.clean_result.config(text="Cleaning…")

        def done(res):
            self.btn_clean.set_enabled(True)
            ok = isinstance(res, str)
            text = res if ok else f"Failed: {res}"
            self.clean_result.config(text=text)
            self.hub.log_action("Temp cleanup", "Clean", "Success" if ok else "Failed", "" if ok else text)
            self.load_drives()
        run_bg(self.hub, cleanup_temp_files_safe, done)

    # ------------------------------------------------------------ disk usage analyzer
    def _usage_card(self, body):
        g = self.g
        c = g["Card"](body)
        c.pack(fill="x", pady=6, padx=(0, 12))
        b = c.body
        bg = b.cget("bg")
        self._title(b, "Disk usage breakdown", "Scans a drive or folder in the background and shows where the space "
                    "goes. Nothing is deleted here. Symlinks and junctions are not followed.")
        row = tk.Frame(b, bg=bg)
        row.pack(fill="x", padx=16, pady=4)
        self.scan_target = tk.StringVar()
        g["REntry"](row, self.scan_target, 360).pack(side="left")
        self.target_pick = g["RSelect"](row, ["Choose a drive"], width=150,
                                        command=lambda v: v != "Choose a drive" and self.scan_target.set(v))
        self.target_pick.pack(side="left", padx=6)
        g["RButton"](row, "Choose folder…", self.choose_scan_folder).pack(side="left", padx=6)
        self.btn_scan = g["RButton"](row, "Scan", self.start_scan, kind="primary")
        self.btn_scan.pack(side="left", padx=6)
        self.btn_scan_cancel = g["RButton"](row, "Cancel", self.cancel_scan)
        self.btn_scan_cancel.pack(side="left", padx=6)
        self.btn_scan_cancel.set_enabled(False)
        self.scan_status = tk.Label(b, text="", bg=bg, fg=g["FG"], font=(g["UI"], 10), anchor="w", justify="left",
                                    wraplength=860)
        self.scan_status.pack(fill="x", padx=16, pady=2)
        self.scan_notice = tk.Label(b, text="", bg=bg, fg="#ffb020", font=(g["UI"], 9), anchor="w", justify="left",
                                    wraplength=860)
        self.scan_notice.pack(fill="x", padx=16)
        for attr, title, cols, heads, h, w in (
                ("tbl_children", "TOP-LEVEL BREAKDOWN", ("name", "size", "share"), ("Name", "Size", "Share of scanned space"), 8,
                 {"name": 420, "size": 120, "share": 260}),
                ("tbl_folders", "LARGEST FOLDERS (2-3 levels down)", ("path", "size"), ("Folder", "Size"), 8,
                 {"path": 640, "size": 120}),
                ("tbl_files", "LARGEST FILES", ("path", "size"), ("File", "Size"), 10, {"path": 640, "size": 120})):
            tk.Label(b, text=title, bg=bg, fg=g["MUTED"], font=(g["UI"], 8, "bold"), anchor="w").pack(
                fill="x", padx=16, pady=(10, 0))
            t = make_table(self.hub, g, b, cols, heads, h, w)
            setattr(self, attr, t)
            self._file_actions(t)
        tk.Frame(b, bg=bg, height=8).pack()

    def _fill_scan_targets(self):
        mounts = [d["mountpoint"] for d in get_disk_drives()]
        self.target_pick.values = ["Choose a drive"] + mounts
        if mounts and not self.scan_target.get():
            self.scan_target.set(mounts[0])

    def choose_scan_folder(self):
        d = filedialog.askdirectory(parent=self.hub, title="Choose a folder to analyze")
        if d:
            self.scan_target.set(os.path.normpath(d))

    def start_scan(self):
        if self._scan_job and not self._scan_job.done:
            return
        root = self.scan_target.get().strip().strip('"')
        if not root or not os.path.isdir(root):
            self.scan_status.config(text=f"Can't scan: '{root}' was not found. If it is a drive, it may be disconnected.")
            return
        for t in (self.tbl_children, self.tbl_folders, self.tbl_files):
            t.delete(*t.get_children())
        self.scan_notice.config(text="")
        state = ScanState()
        self._scan_state = state

        def work(stop):
            try:
                state.result = scan_tree(root, stop, state)
            finally:
                state.done = True
        self._scan_job = BackgroundJob(work).start()
        self.btn_scan.set_enabled(False)
        self.btn_scan_cancel.set_enabled(True)
        self.scan_status.config(text="Starting…")
        self._poll()

    def cancel_scan(self):
        if self._scan_job:
            self._scan_job.cancel()
            self.scan_status.config(text="Cancelling…")

    def show_scan_result(self, r):
        self.btn_scan.set_enabled(True)
        self.btn_scan_cancel.set_enabled(False)
        if r is None:
            self.scan_status.config(text="Scan failed.")
            return
        if r["error"]:
            self.scan_status.config(text=f"Can't read {r['root']}: {r['error']}")
            return
        head = "Scan cancelled. Partial results" if r["cancelled"] else "Scan finished"
        self.scan_status.config(text=f"{head}: {human_size(r['total'])} in {r['files']:,} files and "
                                     f"{r['folders']:,} folders under {r['root']}.")
        notes = []
        if r["skipped"]:
            notes.append(f"{r['skipped']:,} folders couldn't be read (access denied or removed during the scan); "
                         "their size is not included.")
        if r["link_count"]:
            notes.append(f"{r['link_count']:,} symlinks/junctions were not followed and are counted as 0.")
        if r["cancelled"]:
            notes.append("The scan was cancelled, so totals are incomplete.")
        self.scan_notice.config(text="\n".join(notes))
        total = max(r["total"], 1)
        for c in r["children"]:
            pct = c["size"] * 100.0 / total
            bar = "█" * int(round(pct / 5)) + "░" * (20 - int(round(pct / 5)))
            iid = self.tbl_children.insert("", "end", values=(
                c["name"] + ("  (link, not followed)" if c["is_link"] else ""), human_size(c["size"]),
                f"{bar}  {pct:.1f}%"))
            self._paths[(self.tbl_children, iid)] = c["path"]
        for p, sz in r["top_folders"]:
            iid = self.tbl_folders.insert("", "end", values=(os.path.relpath(p, r["root"]), human_size(sz)))
            self._paths[(self.tbl_folders, iid)] = p
        for sz, p in r["top_files"]:
            iid = self.tbl_files.insert("", "end", values=(os.path.relpath(p, r["root"]), human_size(sz)))
            self._paths[(self.tbl_files, iid)] = p

    # ------------------------------------------------------------ search
    def _search_card(self, body):
        g = self.g
        c = g["Card"](body)
        c.pack(fill="x", pady=6, padx=(0, 12))
        b = c.body
        bg = b.cget("bg")
        self._title(b, "Find files", "Searches a folder by name, including its subfolders if you want (Storage only "
                    "filters the folder you're in). Links and junctions are listed but not entered. Up to 1,000 results.")
        row = tk.Frame(b, bg=bg)
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text="Name contains", bg=bg, fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left", padx=(0, 6))
        self.search_q = tk.StringVar()
        e = g["REntry"](row, self.search_q, 220)
        e.pack(side="left")
        e.entry.bind("<Return>", lambda _e: self.start_search())
        tk.Label(row, text="in", bg=bg, fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left", padx=6)
        self.search_root = tk.StringVar(value=os.path.expanduser("~"))
        g["REntry"](row, self.search_root, 300).pack(side="left")
        g["RButton"](row, "Choose…", self._choose_search_root, kind="ghost", height=30).pack(side="left", padx=6)
        row2 = tk.Frame(b, bg=bg)
        row2.pack(fill="x", padx=16, pady=4)
        self.search_sub = tk.BooleanVar(value=True)
        self.search_hidden = tk.BooleanVar(value=bool(self.hub.settings.get("storage_show_hidden", True)))
        g["RCheck"](row2, "Include subfolders", self.search_sub).pack(side="left")
        g["RCheck"](row2, "Show hidden items", self.search_hidden, command=self._hidden_toggled).pack(side="left", padx=10)
        self.btn_search = g["RButton"](row2, "Search", self.start_search, kind="primary")
        self.btn_search.pack(side="left", padx=6)
        self.btn_search_cancel = g["RButton"](row2, "Cancel search", self.cancel_search)
        self.btn_search_cancel.pack(side="left", padx=6)
        self.btn_search_cancel.set_enabled(False)
        self.search_status = tk.Label(b, text="", bg=bg, fg=g["MUTED"], font=(g["UI"], 9), anchor="w")
        self.search_status.pack(fill="x", padx=16)
        self.tbl_search = make_table(self.hub, g, b, ("path", "size", "modified", "type"),
                                     ("Name", "Size", "Date modified", "Type"), 10,
                                     {"path": 460, "size": 110, "modified": 150, "type": 120})
        self._file_actions(self.tbl_search)
        tk.Frame(b, bg=bg, height=8).pack()

    def _hidden_toggled(self):
        self.hub.settings["storage_show_hidden"] = bool(self.search_hidden.get())
        self.hub.save_settings()

    def _choose_search_root(self):
        d = filedialog.askdirectory(parent=self.hub, title="Search in")
        if d:
            self.search_root.set(os.path.normpath(d))

    def start_search(self):
        q = self.search_q.get().strip()
        root = self.search_root.get().strip().strip('"')
        if not q:
            self.search_status.config(text="Type part of a name to search for.")
            return
        if not os.path.isdir(root):
            self.search_status.config(text=f"Folder not found or drive not connected: {root}")
            return
        if self._search_job and not self._search_job.done:
            self._search_job.cancel()
        state = ScanState()
        state.results = []
        self._search_state = state
        self._search_root = root
        self._search_q = q
        self.tbl_search.delete(*self.tbl_search.get_children())
        rec, hidden = bool(self.search_sub.get()), bool(self.search_hidden.get())
        self._search_job = BackgroundJob(lambda stop: search_files(root, q, rec, stop, state, hidden)).start()
        self.btn_search_cancel.set_enabled(True)
        self._shown_results = 0
        self._poll()

    def cancel_search(self):
        if self._search_job:
            self._search_job.cancel()
            self.search_status.config(text="Search cancelled. Showing what was found so far.")
            self.btn_search_cancel.set_enabled(False)

    def _add_search_rows(self):
        res = self._search_state.results
        for it in res[self._shown_results:]:
            iid = self.tbl_search.insert("", "end", values=(
                os.path.relpath(it["path"], self._search_root), "-" if it["is_dir"] else human_size(it["size"]),
                format_mtime(it["mtime"]), it["type"]))
            self._paths[(self.tbl_search, iid)] = it["path"]
        self._shown_results = len(res)

    # ------------------------------------------------------------ polling (Tk thread)
    def _poll(self):
        active = False
        if self._scan_job:
            st = self._scan_state
            if self._scan_job.done:
                job, self._scan_job = self._scan_job, None
                if job.error:
                    self.btn_scan.set_enabled(True)
                    self.btn_scan_cancel.set_enabled(False)
                    self.scan_status.config(text=f"Scan failed: {job.error}")
                else:
                    self.show_scan_result(st.result)
            else:
                active = True
                cur = st.current if len(st.current) < 80 else "…" + st.current[-77:]
                self.scan_status.config(text=f"Scanning… {st.items:,} items, {human_size(st.bytes)} so far. Now in: {cur}")
        if self._search_job:
            st = self._search_state
            self._add_search_rows()
            if self._search_job.done:
                job, self._search_job = self._search_job, None
                self.btn_search_cancel.set_enabled(False)
                if job.error:
                    self.search_status.config(text=f"Search failed: {job.error}")
                elif not job.stop.is_set():
                    self.search_status.config(text=f"{len(st.results)} match(es) for '{self._search_q}'"
                                                   + (" (limit reached)" if len(st.results) >= 1000 else ""))
            else:
                active = True
                self.search_status.config(text=f"Searching… {st.items:,} items checked, {len(st.results)} found")
        if active:
            try:
                self.hub.after(200, self._poll)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ open / show / copy
    def _file_actions(self, tree):
        menu = tk.Menu(tree, tearoff=0, bg=self.g["PANEL"], fg=self.g["FG"], activebackground=self.g["ACC"],
                       bd=0, relief="flat", font=(self.g["UI"], 10))
        menu.add_command(label="Open", command=lambda: self._act(tree, "open"))
        menu.add_command(label="Show in Explorer", command=lambda: self._act(tree, "show"))
        menu.add_command(label="Copy path", command=lambda: self._act(tree, "copy"))

        def popup(e):
            row = tree.identify_row(e.y)
            if row:
                tree.selection_set(row)
                try:
                    menu.tk_popup(e.x_root, e.y_root)
                finally:
                    menu.grab_release()
        tree.bind("<Button-3>", popup)
        tree.bind("<Double-Button-1>", lambda e: self._act(tree, "open"))

    def _act(self, tree, what):
        sel = tree.selection()
        path = self._paths.get((tree, sel[0])) if sel else None
        if not path:
            return
        if what == "copy":
            self.hub.clipboard_clear()
            self.hub.clipboard_append(path)
            return
        err = _open(path) if what == "open" else _show_in_explorer(path)
        if err:
            info(self.hub, "Cleanup", f"Couldn't open {path}: {err}", error=True)

    # ------------------------------------------------------------ misc
    def _title(self, b, title, sub):
        g = self.g
        tk.Label(b, text=title, bg=b.cget("bg"), fg=g["FG"], font=(g["UI"], 13, "bold"), anchor="w").pack(
            fill="x", padx=16, pady=(12, 2))
        tk.Label(b, text=sub, bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9), anchor="w", justify="left",
                 wraplength=860).pack(fill="x", padx=16)

    def on_shown(self):
        if not self._loaded:
            self._loaded = True
            self.load_drives()
            self._fill_scan_targets()

    def close(self):
        for job in (self._scan_job, self._search_job):
            if job:
                job.cancel()
