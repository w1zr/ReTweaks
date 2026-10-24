"""'Download & install' section of the Drivers page (owner request 2026-10-22).

Per vendor (NVIDIA / AMD / Intel): Check latest -> shows name, version, size and the official address; Download
asks first, streams in the background with real progress and Cancel, then Windows checks the signature; Run
installer asks again and opens the vendor's own installer. Vendors that don't match this PC are hidden. Windows Update drivers: search, tick, Install selected, per-driver results and the restart flag.
All network / PowerShell work runs on worker threads; results come back through a queue polled with after().
"""
import os
import queue
import tkinter as tk

from core import driver_download as dd

VENDORS = ("NVIDIA", "AMD", "Intel")
WHAT = {"NVIDIA": "NVIDIA graphics driver", "AMD": "AMD graphics + chipset (auto-detect installer)",
        "Intel": "Intel graphics, chipset and Wi-Fi (Driver & Support Assistant)"}


def _ask(parent, title, text):
    from tkinter import messagebox
    return messagebox.askyesno(title, text, parent=parent)


def _mb(n):
    return f"{n / 1e6:,.1f} MB"


class DriverDownloads:
    def __init__(self, hub, parent, g, api=dd, ask=_ask, windows_build=None):
        self.hub, self.g, self.api, self.ask = hub, g, api, ask
        if windows_build is None:
            from retweaks_data import win_build
            windows_build = win_build()
        self.build = windows_build
        self.q = queue.Queue()
        self.jobs, self.offers, self.files, self.rows = {}, {}, {}, {}
        self.install_requests, self.run_after_download = set(), set()
        self.wu, self.wu_vars = [], {}
        self.polling = self.closed = self.detected = False
        self.matches = {}

        c = g["Card"](parent)
        c.pack(fill="x", pady=6, padx=(0, 12))
        body = self.body = c.body
        bg = body.cget("bg")
        tk.Label(body, text="Download & install", bg=bg, fg=g["FG"], font=(g["UI"], 15, "bold"), anchor="w").pack(
            fill="x", padx=16, pady=(12, 0))
        tk.Label(body, text="Install driver checks the official release, asks once, downloads it, verifies its "
                            "publisher signature, and opens the maker's setup. No website visit is needed for "
                            "the download. You can also download and run separately. Intel's assistant may "
                            "open a browser for its later driver scan.",
                 bg=bg, fg=g["MUTED"], font=(g["UI"], 9), anchor="w", justify="left", wraplength=740).pack(
            fill="x", padx=16, pady=(2, 6))
        self.vendor_body=tk.Frame(body,bg=bg)
        self.vendor_body.pack(fill='x')
        self.scan_status=tk.Label(self.vendor_body,text='Scanning installed hardware...',bg=bg,fg=g['MUTED'],font=(g['UI'],9),anchor='w')
        self.scan_status.pack(fill='x',padx=16,pady=6)
        for v in VENDORS:
            self.rows[v] = self._vendor_row(self.vendor_body, v)
            self.rows[v]['frame'].pack_forget()
        self._wu_section(body)
        tk.Label(body, text=f"Saved to {dd.downloads_dir()}", bg=bg, fg=g["MUTED"], font=(g["UI"], 8),
                 anchor="w").pack(fill="x", padx=16, pady=(4, 12))

    # ------------------------------------------------------------------ layout
    def _vendor_row(self, parent, v):
        g = self.g
        bg = parent.cget("bg")
        f = tk.Frame(parent, bg=bg)
        f.pack(fill="x", padx=16, pady=6)
        tk.Frame(f, bg=g["LINE"], height=1).pack(fill="x", pady=(0, 8))
        title = tk.Label(f, text=WHAT[v], bg=bg, fg=g["FG"], font=(g["UI"], 11, "bold"), anchor="w")
        title.pack(fill="x")
        status = tk.Label(f, text="Detecting your hardware…", bg=bg, fg=g["MUTED"], font=(g["UI"], 9), anchor="w",
                          justify="left", wraplength=720)
        status.pack(fill="x", pady=(2, 4))
        bar = tk.Canvas(f, height=6, bg=bg, highlightthickness=0, bd=0)
        btns = tk.Frame(f, bg=bg)
        btns.pack(fill="x")
        row = {"frame": f, "title": title, "status": status, "bar": bar, "btns": btns, "frac": None}
        row["install"] = g["RButton"](btns, "Install driver", lambda: self.install(v), kind="primary",
                                      height=32, radius=11)
        row["check"] = g["RButton"](btns, "Check latest", lambda: self.check(v), height=32, radius=11)
        row["download"] = g["RButton"](btns, "Download", lambda: self.download(v), kind="primary", height=32,
                                       radius=11)
        row["cancel"] = g["RButton"](btns, "Cancel", lambda: self.cancel(v), kind="ghost", height=32, radius=11)
        row["run"] = g["RButton"](btns, "Run installer", lambda: self.run(v), kind="primary", height=32, radius=11)
        for k in ("install", "check", "download", "cancel", "run"):
            row[k].pack(side="left", padx=(0, 6))
        bar.bind("<Configure>", lambda e: self._draw_bar(v))
        for k in ("install", "check", "download", "cancel", "run"):
            row[k].set_enabled(False)
        return row

    def _wu_section(self, parent):
        g = self.g
        bg = parent.cget("bg")
        f = tk.Frame(parent, bg=bg)
        f.pack(fill="x", padx=16, pady=6)
        tk.Frame(f, bg=g["LINE"], height=1).pack(fill="x", pady=(0, 8))
        tk.Label(f, text="Windows Update drivers", bg=bg, fg=g["FG"], font=(g["UI"], 11, "bold"), anchor="w").pack(
            fill="x")
        self.wu_status = tk.Label(f, text="Optional and pending drivers Microsoft offers for this PC.", bg=bg,
                                  fg=g["MUTED"], font=(g["UI"], 9), anchor="w", justify="left", wraplength=720)
        self.wu_status.pack(fill="x", pady=(2, 4))
        self.wu_list = tk.Frame(f, bg=bg)
        self.wu_list.pack(fill="x")
        b = tk.Frame(f, bg=bg)
        b.pack(fill="x", pady=(4, 0))
        self.wu_search_btn = g["RButton"](b, "Search Windows Update", self.wu_search, height=32, radius=11)
        self.wu_search_btn.pack(side="left", padx=(0, 6))
        self.wu_install_btn = g["RButton"](b, "Install selected", self.wu_install, kind="primary", height=32,
                                           radius=11)
        self.wu_install_btn.pack(side="left")
        self.wu_install_btn.set_enabled(False)

    def _set(self, v, **flags):
        for k, on in flags.items():
            self.rows[v][k].set_enabled(on)

    def _status(self, v, text, color=None):
        self.rows[v]["status"].configure(text=text, fg=color or self.g["MUTED"])

    def _draw_bar(self, v):
        row = self.rows.get(v)
        if not row:
            return
        cv, frac = row["bar"], row["frac"]
        cv.delete("all")
        w = max(40, cv.winfo_width())
        cv.create_rectangle(0, 1, w, 5, fill=self.g["LINE"], outline="")
        if frac is not None:
            cv.create_rectangle(0, 1, max(2, w * frac), 5, fill=self.g["ACC"], outline="")

    def _show_bar(self, v, on):
        row = self.rows[v]
        if on and not row["bar"].winfo_ismapped():
            row["bar"].pack(fill="x", pady=(0, 6), before=row["btns"])
        elif not on:
            row["bar"].pack_forget()
            row["frac"] = None

    # ------------------------------------------------------------------ hardware match
    def open(self):
        if self.detected or self.closed:
            return
        self.detected = True
        info = dict(getattr(self.hub, "info", None) or {})
        self._start("detect", lambda job: (self.api.detect_gpus(info_gpu=info.get("gpu", "")),
                                            str(info.get("cpu", ""))))

    def _detected(self, result):
        if getattr(self,'component_matches',False):return
        gpus, cpu = result
        names = {v: [x["name"] for x in gpus if x["vendor"] == v] for v in VENDORS}
        cpu_l = cpu.lower()
        for v in VENDORS:
            reason = ""
            if v == "NVIDIA":
                ok = bool(names[v])
                found = ", ".join(names[v])
                reason = "No NVIDIA GPU found on this PC."
            else:
                cpu_hit = ("intel" in cpu_l) if v == "Intel" else ("amd" in cpu_l or "ryzen" in cpu_l)
                ok = bool(names[v]) or cpu_hit
                found = ", ".join(names[v] + ([cpu] if cpu_hit else []))
                reason = f"No {v} GPU or CPU found on this PC."
            self.matches[v] = names[v][0] if names[v] else (cpu if ok else "")
            if ok:
                self.rows[v]['frame'].pack(fill='x',padx=16,pady=6)
                self._status(v, f"For: {found}. Click Check latest to look up the current release.")
                self._set(v, check=True, install=True)
            else:
                self.rows[v]['frame'].pack_forget()
                self._status(v, reason, self.g.get("DIM", self.g["MUTED"]))
                self.rows[v]["title"].configure(fg=self.g["MUTED"])
                self._set(v, check=False)

        self.scan_status.configure(text='Matching installers for detected hardware only.' if any(self.matches.values()) else
                                   'No matching vendor installer detected. Use Windows Update for this PC or the component support pages below.')

    def set_components(self, components):
        """Refine matching with the same present-device scan used by the component list."""
        self.component_matches=True
        matches={v:[] for v in VENDORS}
        for row in components:
            key=row.get('device_vendor') or row.get('vendor_key','')
            v={'nvidia':'NVIDIA','amd':'AMD','intel':'Intel'}.get(key)
            if v and (v!='NVIDIA' or row.get('kind')=='Graphics'):
                matches[v].append(row['name'])
        for v in VENDORS:
            self.matches[v]=next(iter(matches[v]),'')
            frame=self.rows[v]['frame']
            if matches[v]:
                frame.pack(fill='x',padx=16,pady=6)
                if not self._busy(v):
                    self._set(v,check=True,install=True)
                    self._status(v,'Detected: '+', '.join(dict.fromkeys(matches[v]))+'. Check for an official installer.')
            else:
                frame.pack_forget()
                self._set(v,check=False,install=False,download=False,run=False)
        self.scan_status.configure(text='Matching installers for detected hardware only.' if any(self.matches.values()) else
                                   'Use Windows Update or the detected component support pages below.')

    # ------------------------------------------------------------------ actions
    def _busy(self, v):
        return any(key.startswith(v + ':') for key in self.jobs)

    def install(self, v):
        if self.closed or self._busy(v) or not self.matches.get(v):
            return
        self.install_requests.add(v)
        # Always get a fresh offer before the combined download/setup action.
        self.check(v)

    def check(self, v):
        if self.closed or self._busy(v) or not self.matches.get(v):
            return
        self._set(v, check=False, download=False, run=False, install=False)
        self._status(v, f"Asking {v} for the latest release…")
        gpu = self.matches.get(v, "")
        api, build = self.api, self.build

        def lookup(job):
            if v == "NVIDIA":
                offer = api.nvidia_offer(gpu, build)
            elif v == "AMD":
                offer = api.amd_offer()
            else:
                offer = api.intel_offer()
            return api.probe(offer)
        self._start(f"{v}:check", lookup)

    def _offer_text(self, o):
        size = _mb(o["size_bytes"]) if o.get("size_bytes") else (o.get("size_text") or "size not reported")
        parts = [o["title"]]
        if o.get("date"):
            parts.append(o["date"])
        parts.append(size)
        return " · ".join(parts) + f"\n{o.get('note', '')}\nFrom: {o['url']}"

    def download(self, v, install=False):
        o = self.offers.get(v)
        if self.closed or not o or self._busy(v):
            return
        size = _mb(o["size_bytes"]) if o.get("size_bytes") else (o.get("size_text") or "not reported by the server")
        text = (f"{'Download and start setup' if install else 'Download this'} from {v}?\n\n{o['title']}\nVersion: {o.get('version') or 'not shown'}\n"
                f"Size: {size}\nFrom: {o['url']}\n\nSaved to: {dd.downloads_dir()}\n\nNothing is installed until "
                f"you click Run installer.")
        if install:
            text = text.replace("Nothing is installed until you click Run installer.",
                "After the publisher signature is verified, the vendor's setup opens automatically. "
                "Follow its installation steps. Your screen may flicker and a restart may be needed.")
        if not self.ask(self.body, "Install driver" if install else "Download driver", text):
            self.hub.log_action("Drivers", f"Download {o['title']}", "Not downloaded (you said no)")
            return
        if install:self.run_after_download.add(v)
        self._set(v, check=False, download=False, run=False, cancel=True, install=False)
        self._status(v, f"Downloading {o['title']}…")
        self.rows[v]["frac"] = 0.0
        self._show_bar(v, True)
        self._draw_bar(v)
        api, q = self.api, self.q

        def fetch(job):
            path = api.download(o, progress=lambda d, t: q.put((f"{v}:download", "progress", (d, t))),
                                cancel=job.cancel)
            ok, msg = api.verify_signature(path, v)
            return path, ok, msg
        self._start(f"{v}:download", fetch)

    def cancel(self, v):
        job = self.jobs.get(f"{v}:download")
        if job:
            self.run_after_download.discard(v)
            job.cancel.set()
            self._status(v, "Cancelling…")
            self._set(v, cancel=False)

    def run(self, v):
        item = self.files.get(v)
        if not item:
            return
        path, msg = item
        if not self.ask(self.body, "Run installer",
                        f"Run {v}'s installer now?\n\n{os.path.basename(str(path))}\n{msg}\n\n{v}'s own setup "
                        f"window opens and does the install. Your screen may flicker and a restart may be needed."):
            self.hub.log_action("Drivers", f"Run {os.path.basename(str(path))}", "Not run (you said no)")
            return
        self._launch(v, item)

    def _launch(self, v, item):
        path, msg = item
        ok, text = self.api.run_installer(path)
        self._status(v, text, None if ok else self.g.get("RED"))
        self.hub.log_action("Drivers", f"Run {os.path.basename(str(path))}", "Started" if ok else "Failed",
                            "" if ok else text)

    # ------------------------------------------------------------------ Windows Update
    def wu_search(self):
        if "wu:search" in self.jobs or "wu:install" in self.jobs:
            return
        self.wu_search_btn.set_enabled(False)
        self.wu_install_btn.set_enabled(False)
        self.wu_status.configure(text="Searching Windows Update for drivers… this can take a minute or two.",
                                 fg=self.g["MUTED"])
        self._start("wu:search", lambda job: self.api.wu_search())

    def _wu_render(self):
        for w in self.wu_list.winfo_children():
            w.destroy()
        self.wu_vars = {}
        RCheck = self.g.get("RCheck")
        for d in self.wu:
            var = tk.BooleanVar(value=False)
            self.wu_vars[d["id"]] = var
            bits = [x for x in (d["maker"], d["cls"], d["date"], _mb(d["size"]) if d["size"] else "") if x]
            text = d["title"] + (f"   ({' · '.join(bits)})" if bits else "")
            if RCheck:
                RCheck(self.wu_list, text, var, command=self._wu_sel).pack(anchor="w", pady=1)
            else:
                tk.Checkbutton(self.wu_list, text=text, variable=var, command=self._wu_sel).pack(anchor="w")

    def _wu_sel(self):
        self.wu_install_btn.set_enabled(any(v.get() for v in self.wu_vars.values()) and "wu:install" not in self.jobs)

    def wu_install(self):
        ids = [i for i, var in self.wu_vars.items() if var.get()]
        if not ids or "wu:install" in self.jobs:
            return
        titles = [d["title"] for d in self.wu if d["id"] in ids]
        if not self.ask(self.body, "Install Windows Update drivers",
                        f"Download and install {len(ids)} driver(s) from Windows Update?\n\n" + "\n".join(
                            "• " + t for t in titles) + "\n\nA restart may be needed afterwards."):
            return
        self.wu_search_btn.set_enabled(False)
        self.wu_install_btn.set_enabled(False)
        self.wu_status.configure(text=f"Installing {len(ids)} driver(s) through Windows Update…", fg=self.g["MUTED"])
        self._start("wu:install", lambda job: self.api.wu_install(ids))

    # ------------------------------------------------------------------ worker plumbing
    def _start(self, kind, target):
        self.jobs[kind] = self.api.Job(self.q.put, kind, target)
        if not self.polling:
            self.polling = True
            self.hub.after(100, self._poll)

    def _poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, what, data = self.q.get_nowait()
                if what != "progress":
                    self.jobs.pop(kind, None)
                try:
                    self._handle(kind, what, data)
                except tk.TclError:
                    return
        except queue.Empty:
            pass
        if self.jobs:
            self.hub.after(100, self._poll)
        else:
            self.polling = False

    def _handle(self, kind, what, data):
        g = self.g
        red = g.get("RED", g["FG"])
        if kind == "detect":
            self._detected(data if what == "done" else ([], ""))
            return
        if kind.startswith("wu:"):
            self.wu_search_btn.set_enabled(True)
            if what == "error":
                self.wu_status.configure(text=data, fg=red)
                self.hub.log_action("Drivers", "Windows Update drivers", "Failed", data)
            elif kind == "wu:search":
                self.wu = data
                self._wu_render()
                self.wu_status.configure(
                    text=(f"Windows Update offers {len(data)} driver(s) for this PC. Tick the ones you want."
                          if data else "Windows Update has no driver updates waiting for this PC right now."),
                    fg=g["MUTED"])
                self.hub.log_action("Drivers", "Search Windows Update drivers", f"{len(data)} found")
            else:
                reboot = any(r["reboot"] for r in data)
                lines = [f"{r['result']}: {r['title']}" for r in data] or ["Windows Update installed nothing."]
                if reboot:
                    lines.append("Restart Windows to finish installing.")
                self.wu_status.configure(text="\n".join(lines), fg=g["FG"])
                for r in data:
                    self.hub.log_action("Drivers", f"Windows Update: {r['title']}", r["result"],
                                        "" if r["result"].startswith("Installed") else r["result"])
                done = {r["id"] for r in data if r["result"].startswith("Installed")}
                self.wu = [d for d in self.wu if d["id"] not in done]
                self._wu_render()
            self._wu_sel()
            return
        v, step = kind.split(":", 1)
        if what == "progress":
            done, total = data
            row = self.rows[v]
            row["frac"] = (done / total) if total else None
            self._draw_bar(v)
            self._status(v, f"Downloading… {_mb(done)}" + (f" of {_mb(total)} ({done * 100 // total}%)" if total
                                                              else " (the server didn't say the total size)"))
            return
        if step == "check":
            self._set(v, check=True, install=True)
            if what == "error":
                self.install_requests.discard(v)
                self.offers.pop(v, None)
                self._status(v, data, red)
                self.hub.log_action("Drivers", f"Check {v} latest", "Failed", data)
            else:
                self.offers[v] = data
                self._status(v, self._offer_text(data), g["FG"])
                self._set(v, download=True, run=v in self.files)
                self.hub.log_action("Drivers", f"Check {v} latest", data["title"])
                if v in self.install_requests:
                    self.install_requests.discard(v)
                    self.download(v, install=True)
        elif step == "download":
            self._show_bar(v, False)
            self._set(v, check=True, download=v in self.offers, cancel=False, install=True)
            if what == "error":
                self.run_after_download.discard(v)
                self._status(v, data, red)
                self.hub.log_action("Drivers", f"Download {v} driver", "Stopped", data)
                return
            path, ok, msg = data
            if ok:
                self.files[v] = (path, msg)
                self._status(v, f"Downloaded: {path}\n{msg}. Click Run installer when you're ready.", g["FG"])
                self._set(v, run=True)
                self.hub.log_action("Drivers", f"Download {v} driver", f"Saved {path}; {msg}")
                if v in self.run_after_download:
                    self.run_after_download.discard(v)
                    self._launch(v, self.files[v])
            else:
                self.run_after_download.discard(v)
                self.files.pop(v, None)
                self._set(v, run=False)
                self._status(v, f"Downloaded, but blocked: {msg}\nFile: {path}", red)
                self.hub.log_action("Drivers", f"Download {v} driver", "Signature check failed", msg)

    def destroy(self):
        self.closed = True
        for job in list(self.jobs.values()):
            job.cancel.set()
