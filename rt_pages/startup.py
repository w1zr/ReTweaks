"""Startup apps manager (Tk port of RETWEAKS' ui/pages/startup.py; same behavior and setting keys).

Lists Run keys (current user / all users), Startup folders and Scheduled Tasks via core.startup_manager,
disables/enables them with a backup so they can be turned back on, and re-checks with Windows after
every change. RETWEAKS' own start-with-Windows task is shown but managed in Settings."""
import tkinter as tk
from tkinter import ttk

from core.startup_manager import (SCHED_SOURCE, TASK_ID_PREFIX, TASK_WARNING, disable_scheduled_tasks,
                                  disable_startup_entry, enable_scheduled_tasks, enable_startup_entry)
from rt_pages.common import NA, confirm, info, run_bg

FILTERS = ["All apps", "Enabled", "Disabled", "Current user", "All users", "Registry", "Startup folder",
           "Scheduled tasks"]
CHECK = "✔"


def list_startup_apps(include_windows_tasks=False):
    from core.startup_manager import list_startup_apps as _list
    return _list(include_windows_tasks)


def batch_disable(entries):
    """Registry and Startup-folder entries are instant; scheduled tasks go in one PowerShell run."""
    tasks = [e for e in entries if e.get("source") == SCHED_SOURCE]
    others = [(e, *disable_startup_entry(e)) for e in entries if e.get("source") != SCHED_SOURCE]
    return others + (disable_scheduled_tasks(tasks) if tasks else [])


def batch_enable(ids):
    tasks = [i for i in ids if str(i).startswith(TASK_ID_PREFIX)]
    others = [(i, *enable_startup_entry(i)) for i in ids if i not in tasks]
    return others + (enable_scheduled_tasks(tasks) if tasks else [])


def matches(entry, text, mode):
    """Search text (name, publisher, path) and the filter dropdown, exactly as the Qt page did."""
    status, scope, source = entry.get("status", "Enabled"), entry.get("scope", ""), entry.get("source", "")
    hay = " ".join((entry.get("name", ""), entry.get("publisher", ""), entry.get("path", ""))).lower()
    if text and text.lower() not in hay:
        return False
    return not ((mode == "Enabled" and status != "Enabled") or (mode == "Disabled" and status != "Disabled")
                or (mode == "Current user" and scope != "Current User")
                or (mode == "All users" and scope != "All Users")
                or (mode == "Registry" and "Registry" not in source)
                or (mode == "Startup folder" and "Startup Folder" not in source)
                or (mode == "Scheduled tasks" and source != SCHED_SOURCE))


def make_table(hub, g, parent, columns, headings, height, widths=None, expand=False):
    """A Treeview styled like the base app's Storage Explorer tables."""
    style = ttk.Style(hub)
    style.configure("RT.Treeview", background=g["PANEL"], fieldbackground=g["PANEL"], foreground=g["FG"],
                    rowheight=28, borderwidth=0, bordercolor=g["LINE"], lightcolor=g["PANEL"],
                    darkcolor=g["PANEL"], font=(g["UI"], 10))
    style.configure("RT.Treeview.Heading", background=g["PANEL2"], foreground=g["FG"],
                    font=(g["UI"], 10, "bold"), padding=(8, 8), relief="flat")
    style.map("RT.Treeview", background=[("selected", g["PANEL2"])], foreground=[("selected", g["FG"])])
    style.configure("RT.Vertical.TScrollbar", background=g["PANEL2"], troughcolor=g["PANEL"],
                    arrowcolor=g["MUTED"], bordercolor=g["PANEL"])
    frame = tk.Frame(parent, bg=parent.cget("bg"))
    frame.pack(fill="both" if expand else "x", expand=expand, padx=16, pady=6)
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse",
                        style="RT.Treeview")
    vs = ttk.Scrollbar(frame, orient="vertical", command=tree.yview, style="RT.Vertical.TScrollbar")
    tree.configure(yscrollcommand=vs.set)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    tree.grid(row=0, column=0, sticky="nsew")
    vs.grid(row=0, column=1, sticky="ns")
    for i, (col, title) in enumerate(zip(columns, headings)):
        tree.heading(col, text=title, anchor="w")
        w = (widths or {}).get(col, 140)
        tree.column(col, width=w, minwidth=min(w, 40), stretch=(i == 0 or col == "name" or col == "path"), anchor="w")
    tree.tag_configure("bad", foreground="#ff5c5c")
    tree.tag_configure("good", foreground=g["GREEN"])
    tree.tag_configure("managed", foreground=g["MUTED"])
    return tree


class StartupPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        self.entries, self.checked = [], set()
        self._loaded, self._busy, self._load_gen = False, False, 0
        g["page_header"](tab, "RETWEAKS", "Startup apps",
                         "Apps that start with Windows. Disabling them makes boot faster. RETWEAKS keeps a backup, "
                         "so you can turn them back on here.")
        body = hub._scroll_area(tab)
        c = g["Card"](body)
        c.pack(fill="x", pady=6, padx=(0, 12))
        b = c.body

        tools = tk.Frame(b, bg=b.cget("bg"))
        tools.pack(fill="x", padx=16, pady=(12, 4))
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.filter_table())
        tk.Label(tools, text="Search (name, publisher or path)", bg=b.cget("bg"), fg=g["MUTED"],
                 font=(g["UI"], 9)).pack(side="left", padx=(0, 8))
        g["REntry"](tools, self.search, 300).pack(side="left")
        self.filter = g["RSelect"](tools, FILTERS, width=180, command=lambda v: self.filter_table())
        self.filter.pack(side="left", padx=8)
        self.win_tasks = tk.BooleanVar(value=bool(hub.settings.get("startup_show_windows_tasks", False)))
        g["RCheck"](tools, "Show Windows tasks", self.win_tasks, command=self._win_tasks_toggled).pack(side="left", padx=8)
        tk.Label(b, text="Windows tasks are scheduled tasks under \\Microsoft\\ (Windows' own). Leave them alone "
                 "unless you know what they do.", bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9),
                 anchor="w").pack(fill="x", padx=16)

        sel = tk.Frame(b, bg=b.cget("bg"))
        sel.pack(fill="x", padx=16, pady=(8, 0))
        for text, fn in (("Select all", lambda: self.set_all(True)), ("Select none", lambda: self.set_all(False)),
                         ("Invert", self.invert)):
            g["RButton"](sel, text, fn, kind="ghost", height=30).pack(side="left", padx=(0, 6))
        self.count_lbl = tk.Label(sel, text="Selected: 0", bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9))
        self.count_lbl.pack(side="right")

        self.table = make_table(hub, g, b, ("sel", "name", "publisher", "source", "status", "scope"),
                                ("", "Application", "Publisher", "Source", "Status", "Scope"), 14,
                                {"sel": 34, "name": 300, "publisher": 170, "source": 190, "status": 150, "scope": 110})
        self.table.column("sel", stretch=False, anchor="center")
        self.table.bind("<ButtonRelease-1>", self._click)
        self.table.bind("<space>", lambda e: self._toggle(self.table.focus()))
        self.table.bind("<Motion>", self._hover)
        self.tip = tk.Label(b, text="", bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9), justify="left",
                            anchor="w", wraplength=900)
        self.tip.pack(fill="x", padx=16)

        btns = tk.Frame(b, bg=b.cget("bg"))
        btns.pack(fill="x", padx=16, pady=(6, 14))
        g["RButton"](btns, "Refresh", lambda: self.load(force=True)).pack(side="left", padx=(0, 6))
        g["RButton"](btns, "Disable selected", self.disable_selected, kind="primary").pack(side="left", padx=6)
        g["RButton"](btns, "Enable selected", self.enable_selected).pack(side="left", padx=6)

    # ------------------------------------------------------------ loading
    def on_shown(self):
        if not self._loaded:
            self.load()

    def load(self, force=False, quiet=False):
        """quiet=True re-checks in the background and keeps the current list on screen meanwhile."""
        if self._busy and not force:
            return
        self._loaded = True
        self._busy = True
        if not quiet:
            self.table.delete(*self.table.get_children())
            self.count_lbl.config(text="Loading…")
        self._load_gen += 1
        gen = self._load_gen
        run_bg(self.hub, list_startup_apps, lambda res, gen=gen: self._loaded_entries(res, gen),
               bool(self.win_tasks.get()))

    def _loaded_entries(self, res, gen):
        if gen != self._load_gen:
            return
        self._busy = False
        if isinstance(res, Exception):
            self.entries = []
            self.count_lbl.config(text=f"Couldn't read startup apps: {res}")
            return
        self.entries = res if isinstance(res, list) else []
        ids = {e.get("id") for e in self.entries}
        self.checked &= ids
        self.filter_table()

    def _win_tasks_toggled(self):
        self.hub.settings["startup_show_windows_tasks"] = bool(self.win_tasks.get())
        self.hub.save_settings()
        self.load(force=True)

    # ------------------------------------------------------------ table
    def filter_table(self):
        if not hasattr(self, "table"):
            return
        t = self.table
        t.delete(*t.get_children())
        text, mode = self.search.get().strip(), self.filter.get()
        self._row_entry = {}
        for i, e in enumerate(self.entries):
            if not matches(e, text, mode):
                continue
            managed = bool(e.get("managed"))
            status = e.get("status", "Enabled")
            iid = f"r{i}"
            self._row_entry[iid] = e
            t.insert("", "end", iid=iid, values=(
                "" if managed else (CHECK if e.get("id") in self.checked else ""),
                e.get("name", ""), e.get("publisher") or "Unknown", e.get("source", ""),
                "Managed in Settings" if managed else status, e.get("scope", "")),
                tags=("managed",) if managed else (("bad",) if status == "Disabled" else ("good",)))
        self.update_count()

    def _toggle(self, iid):
        e = getattr(self, "_row_entry", {}).get(iid)
        if not e or e.get("managed") or not e.get("id"):
            return
        if e["id"] in self.checked:
            self.checked.discard(e["id"])
        else:
            self.checked.add(e["id"])
        self.table.set(iid, "sel", CHECK if e["id"] in self.checked else "")
        self.update_count()

    def _click(self, event):
        if self.table.identify_region(event.x, event.y) != "cell":
            return
        self._toggle(self.table.identify_row(event.y))

    def _hover(self, event):
        e = getattr(self, "_row_entry", {}).get(self.table.identify_row(event.y))
        if not e:
            self.tip.config(text="")
        elif e.get("managed"):
            self.tip.config(text="RETWEAKS's own start-with-Windows task. Change it in Settings.")
        elif e.get("source") == SCHED_SOURCE:
            self.tip.config(text=f"Task: {e.get('task_path', '')}{e.get('task_name', '')}   Runs: {e.get('path', '')}   "
                                 f"Triggers: {', '.join(e.get('triggers', [])) or NA}   State: {e.get('task_state', '') or NA}")
        else:
            self.tip.config(text=e.get("path", "") or NA)

    def _visible(self):
        return [e for e in getattr(self, "_row_entry", {}).values() if not e.get("managed") and e.get("id")]

    def update_count(self):
        self.count_lbl.config(text=f"Selected: {len(self.checked)}")

    def set_all(self, checked):
        for e in self._visible():
            (self.checked.add if checked else self.checked.discard)(e["id"])
        self.filter_table()

    def invert(self):
        for e in self._visible():
            if e["id"] in self.checked:
                self.checked.discard(e["id"])
            else:
                self.checked.add(e["id"])
        self.filter_table()

    # ------------------------------------------------------------ actions
    def disable_selected(self):
        ids = list(self.checked)
        if not ids:
            info(self.hub, "Startup apps", "Tick at least one app first.")
            return
        chosen = [e for e in (next((x for x in self.entries if x.get("id") == i), None) for i in ids)
                  if e and e.get("status") == "Enabled" and not e.get("managed")]
        text = f"Disable {len(ids)} app(s) from starting with Windows?"
        if any(e.get("source") == SCHED_SOURCE for e in chosen):
            text += "\n\n" + TASK_WARNING
        if not confirm(self.hub, "Disable startup apps", text):
            return
        self.count_lbl.config(text="Working…")
        run_bg(self.hub, batch_disable, lambda res, n=len(ids): self._disabled(res, n), chosen)

    def _disabled(self, res, total):
        if not isinstance(res, list):
            info(self.hub, "Startup apps", f"Failed: {res}", error=True)
            self.load(force=True)
            return
        done = 0
        for e, ok, msg in res:
            done += bool(ok)
            self.hub.log_action("Startup apps", f"Disable {e['name']}", "Success" if ok else "Failed", "" if ok else msg)
        self._apply_status({e["id"] for e, ok, _ in res if ok}, "Disabled")
        info(self.hub, "Startup apps", f"Disabled {done} of {total} app(s)."
             + "".join(f"\n{e['name']}: {msg}" for e, ok, msg in res if not ok))
        self.load(force=True, quiet=True)   # re-check with Windows in the background

    def enable_selected(self):
        ids = list(self.checked)
        if not ids:
            info(self.hub, "Startup apps", "Tick at least one app first.")
            return
        self.count_lbl.config(text="Working…")
        run_bg(self.hub, batch_enable, lambda res, n=len(ids): self._enabled(res, n), ids)

    def _enabled(self, res, total):
        if not isinstance(res, list):
            info(self.hub, "Startup apps", f"Failed: {res}", error=True)
            self.load(force=True)
            return
        done = 0
        for entry_id, ok, msg in res:
            done += bool(ok)
            self.hub.log_action("Startup apps", f"Enable {entry_id}", "Success" if ok else "Failed", "" if ok else msg)
        self._apply_status({i for i, ok, _ in res if ok}, "Enabled")
        info(self.hub, "Startup apps", f"Enabled {done} of {total} app(s)."
             + "".join(f"\n{i}: {msg}" for i, ok, msg in res if not ok))
        self.load(force=True, quiet=True)

    def _apply_status(self, ids, status):
        """Show the verified result right away instead of waiting for a full re-scan."""
        for e in self.entries:
            if e.get("id") in ids:
                e["status"] = status
        self.checked -= set(ids)
        self.filter_table()
