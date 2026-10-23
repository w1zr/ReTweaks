"""Hardware: everything RETWEAKS detected, one card per component, plus the hardware report export.
Ported from ui/pages/hardware.py (RETWEAKS v1.6) to Tk. Data: core.hardware.scan_static (one PowerShell
call + DXGI GPU list with exact names and 64-bit VRAM), core.display.list_displays (resolution and
refresh rate of each display), live data sources from core.telemetry. Export via core.report."""
import csv
import tkinter as tk
from tkinter import filedialog, messagebox

from rt_pages.common import NA
from rt_pages.monitor import fmt, join, on_static, request_static, telemetry_service

ORDER = [("system", "System"), ("cpu", "Processor"), ("board", "Motherboard & BIOS"),
         ("ram", "Memory"), ("gpu", "Graphics"), ("disks", "Storage"),
         ("displays", "Displays"), ("audio", "Audio"), ("net", "Network adapters"),
         ("sources", "Where live data comes from")]


def _yes(v):
    return "Yes" if v else "No"


def rows_from_static(d):
    """{card key: [(field, value)]} for a scan result (pure, tested). None/'' values become NA."""
    out = {}
    os_, comp = d.get("os", {}), d.get("computer", {})
    out["system"] = [
        ("Windows", os_.get("name")),
        ("Build", join(os_.get("build"), f"({os_.get('arch')})" if os_.get("arch") else None)),
        ("PC maker / model", join(comp.get("manufacturer"), comp.get("model")) or None),
        ("Running as admin", _yes(d.get("is_admin"))),
    ]
    cpu = d.get("cpu", {})
    out["cpu"] = [
        ("Model", cpu.get("name")),
        ("Cores / threads", f"{fmt(cpu.get('cores'))} / {fmt(cpu.get('threads'))}"),
        ("Base clock", fmt(cpu.get("base_mhz"), "MHz")),
        ("L2 / L3 cache", f"{fmt(cpu.get('l2_mb'), 'MB', 1)} / {fmt(cpu.get('l3_mb'), 'MB', 1)}"),
        ("Socket", cpu.get("socket")),
        ("Virtualization", cpu.get("virtualization")),
    ]
    mb = d.get("motherboard", {})
    out["board"] = [("Manufacturer", mb.get("manufacturer")), ("Model", mb.get("model")),
                    ("BIOS version", mb.get("bios_version")), ("BIOS date", mb.get("bios_date")),
                    ("BIOS vendor", mb.get("bios_vendor"))]
    ram = d.get("ram", {})
    rows = [("Installed", fmt(ram.get("installed_gb"), "GB", 0)),
            ("Usable by Windows", fmt(ram.get("total_gb"), "GB", 1)),
            ("Type", ram.get("type")),
            ("Running speed", fmt(ram.get("running_mts"), "MT/s")),
            ("Slots used", f"{fmt(ram.get('slots_used'))} of {fmt(ram.get('slots_total'))}"
             if ram.get("slots_used") else None)]
    for s in ram.get("sticks", []):
        rows.append((s.get("slot") or "Stick",
                     join(fmt(s.get("size_gb"), "GB"), s.get("type"), fmt(s.get("rated_mts"), "MT/s", na=""),
                          s.get("maker"), s.get("part"), sep=" · ")))
    out["ram"] = rows
    rows = []
    gpus = d.get("gpus", [])
    for i, gp in enumerate(gpus, 1):
        p = f"GPU {i} " if len(gpus) > 1 else ""
        rows += [(f"{p}Model", gp.get("name")),
                 (f"{p}Type", ("Integrated" if gp.get("integrated") else "Dedicated")
                  if gp.get("integrated") is not None else None),
                 (f"{p}VRAM", fmt(gp.get("vram_gb"), "GB", 1)),
                 (f"{p}Driver", join(gp.get("driver_version"),
                                     f"({gp['driver_date']})" if gp.get("driver_date") else None) or None)]
    out["gpu"] = rows or [("GPU", None)]
    rows = []
    for disk in d.get("disks", []):
        letters = " ".join(disk.get("letters") or [])
        rows.append((disk.get("name"), join(fmt(disk.get("size_gb"), "GB"), disk.get("media"), disk.get("bus"),
                                            f"drives {letters}" if letters else None, sep=" · ")))
        rows.append(("Health", disk.get("health")))
    out["disks"] = rows or [("Disks", None)]
    rows = []
    for m in d.get("display_modes", []) or []:
        res = f"{m.get('width')} × {m.get('height')}" if m.get("width") else None
        rows.append((m.get("name") or m.get("device") or "Display",
                     join(res, f"@ {m['hz']} Hz" if m.get("hz") else None,
                          "(primary)" if m.get("primary") else None) or None))
    for m in d.get("monitors", []):
        rows.append(("Monitor", join(m.get("name"), f"({m.get('maker')})" if m.get("maker") else None) or None))
    out["displays"] = rows or [("Displays", None)]
    out["audio"] = [(a.get("manufacturer") or "Device", a.get("name")) for a in d.get("audio", [])] or [("Audio", None)]
    out["net"] = [(n.get("name"), join(n.get("description"), n.get("status"), n.get("link_speed"), sep=" · "))
                  for n in d.get("network", [])] or [("Adapters", None)]
    return out


def rows_from_sources(src):
    lhm = src.get("lhm")
    return [
        ("GPU load, all brands", "Windows GPU counters (same as Task Manager)" if src.get("gpu_counters")
         else "Unavailable (needs Windows 10 version 1709 or newer)"),
        ("CPU clock", "Windows performance counters" if src.get("windows_counters") else NA),
        ("NVIDIA extras", f"NVIDIA driver ({src['nvml_gpus']} GPU)" if src.get("nvml_gpus")
         else "No NVIDIA GPU / driver"),
        ("Temperatures & fans", f"{lhm} (running)" if lhm else "No LibreHardwareMonitor readings yet"),
    ]


class KVCard:
    def __init__(self, parent, g, title):
        self.g, self.title_text = g, title
        self.card = g["Card"](parent)
        b = self.card.body
        tk.Label(b, text=title.upper(), bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9, "bold"),
                 anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        self.grid = tk.Frame(b, bg=b.cget("bg"))
        self.grid.pack(fill="x", padx=16, pady=(0, 12))
        self.grid.columnconfigure(1, weight=1)
        self.rows, self.widgets = [], []

    def set_rows(self, rows):
        for w in self.widgets:
            w.destroy()
        self.widgets, self.rows = [], []
        for i, (k, v) in enumerate(rows):
            value = v if v not in (None, "") else NA
            key = k if k not in (None, "") else NA
            self.rows.append((str(key), str(value)))
            kl = tk.Label(self.grid, text=key, bg=self.grid.cget("bg"), fg=self.g["MUTED"], font=(self.g["UI"], 9),
                          anchor="nw", justify="left", wraplength=170)
            vl = tk.Label(self.grid, text=value, bg=self.grid.cget("bg"), fg=self.g["FG"], font=(self.g["UI"], 10),
                          anchor="w", justify="left", wraplength=330)
            kl.grid(row=i, column=0, sticky="nw", padx=(0, 14), pady=1)
            vl.grid(row=i, column=1, sticky="w", pady=1)
            self.widgets += [kl, vl]

    def filter(self, text):
        """Shows only rows containing text (case-insensitive); returns how many match."""
        text = (text or "").strip().lower()
        n = 0
        for i, (k, v) in enumerate(self.rows):
            match = not text or text in k.lower() or text in v.lower() or text in self.title_text.lower()
            kl, vl = self.widgets[2 * i], self.widgets[2 * i + 1]
            if match:
                kl.grid()
                vl.grid()
                n += 1
            else:
                kl.grid_remove()
                vl.grid_remove()
        return n


class HardwarePage:
    title = "Hardware"
    subtitle = ("What Windows reports about this PC. If something looks wrong, use “Export hardware report” and "
                "attach it to an issue on GitHub so it can be fixed for everyone.")

    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        self.svc = telemetry_service(hub)
        g["page_header"](tab, "RETWEAKS", self.title, self.subtitle)
        bar = tk.Frame(tab, bg=g["BG"])
        bar.pack(fill="x", pady=(0, 8), padx=(0, 12))
        B = g["RButton"]
        self.btn_rescan = B(bar, "Rescan", self.rescan, kind="primary")
        self.btn_rescan.pack(side="left", padx=(0, 6))
        for text, cmd in (("Export hardware report (.json)", lambda: self.export("json")),
                          ("Export as text", lambda: self.export("txt")),
                          ("Export as CSV", lambda: self.export("csv")),
                          ("Copy to clipboard", self.copy_report)):
            B(bar, text, cmd).pack(side="left", padx=(0, 6))
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *a: self.apply_filter())
        tk.Label(bar, text="Search", bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 9)).pack(side="right", padx=(6, 0))
        self.search = g["REntry"](bar, self.query, width_px=220)
        self.search.pack(side="right")
        self.status = tk.Label(tab, text="Scanning hardware…", bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 9),
                               anchor="w")
        self.status.pack(fill="x", pady=(0, 4))
        body = hub._scroll_area(tab)
        self.grid = tk.Frame(body, bg=g["BG"])
        self.grid.pack(fill="x", padx=(0, 12))
        self.grid.columnconfigure(0, weight=1, uniform="c")
        self.grid.columnconfigure(1, weight=1, uniform="c")
        self.cards = {}
        for i, (key, title) in enumerate(ORDER):
            c = KVCard(self.grid, g, title)
            c.pos = (i // 2, i % 2)
            self.cards[key] = c
        self.cards["sources"].set_rows(rows_from_sources(getattr(hub, "rt_sources", None) or {}))
        self._layout()
        on_static(hub, self.on_static)
        self.svc.source_listeners.append(self.on_sources)
        request_static(hub)

    def _layout(self, visible=None):
        shown = [c for k, c in self.cards.items() if visible is None or k in visible]
        for c in self.cards.values():
            c.card.grid_forget()
        for i, c in enumerate(shown):
            c.card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, 8) if i % 2 == 0 else (8, 0), pady=6)

    def on_shown(self):
        self.svc.acquire(self)          # keeps "Where live data comes from" and the report's live data current

    def on_hidden(self):
        self.svc.release(self)

    def close(self):
        self.on_hidden()

    def rescan(self):
        self.status.config(text="Scanning hardware…")
        self.btn_rescan.set_enabled(False)
        request_static(self.hub, force=True)

    def on_static(self, d):
        self.btn_rescan.set_enabled(True)
        if not d:
            self.status.config(text="The hardware scan failed. Click Rescan to try again.")
            return
        self.status.config(text="Scan complete.")
        for key, rows in rows_from_static(d).items():
            self.cards[key].set_rows(rows)
        self.apply_filter()

    def on_sources(self, src):
        self.cards["sources"].set_rows(rows_from_sources(src))
        self.apply_filter()

    def apply_filter(self):
        text = self.query.get()
        if not text.strip():
            for c in self.cards.values():
                c.filter("")
            self._layout()
            return
        self._layout([k for k, c in self.cards.items() if c.filter(text) > 0])

    def _report(self):
        from core.report import build_report
        return build_report(getattr(self.hub, "rt_static", None) or {}, getattr(self.hub, "rt_last_sample", None),
                            getattr(self.hub, "rt_sources", None) or {})

    def export(self, ext):
        name = filedialog.asksaveasfilename(parent=self.hub, title="Export hardware report",
                                            initialfile=f"retweaks_hardware_report.{ext}",
                                            defaultextension=f".{ext}", filetypes=[(ext.upper(), f"*.{ext}")])
        if not name:
            return
        try:
            from core.report import report_to_json, report_to_text
            if ext == "csv":
                with open(name, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["Component", "Field", "Value"])
                    for c in self.cards.values():
                        for key, value in c.rows:
                            w.writerow([c.title_text, key, value])
            else:
                r = self._report()
                with open(name, "w", encoding="utf-8") as f:
                    f.write(report_to_json(r) if ext == "json" else report_to_text(r))
            self.status.config(text=f"Report saved to {name}")
            self.hub.log_action("Hardware", f"Export report ({ext})", f"Saved to {name}")
        except Exception as e:
            messagebox.showerror("Export failed", str(e), parent=self.hub)

    def copy_report(self):
        from core.report import report_to_text
        try:
            text = report_to_text(self._report())
            self.hub.clipboard_clear()
            self.hub.clipboard_append(text)
            self.status.config(text="Report copied. Paste it into a GitHub issue.")
        except Exception as e:
            messagebox.showerror("Copy failed", str(e), parent=self.hub)
