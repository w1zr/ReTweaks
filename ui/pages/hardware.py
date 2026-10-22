# ui/pages/hardware.py
"""Everything RYTWEAKS detected, one card per component, plus the hardware report export."""

from PySide6.QtGui import QGuiApplication
import csv

from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox, QPushButton

from core.report import build_report, report_to_json, report_to_text
from ui.widgets.common import Card, KeyValueGrid, Page, fmt, join, label, set_role, NA


def _yes(v):
    return "Yes" if v else "No"


class HardwarePage(Page):
    title = "Hardware"
    subtitle = ("What Windows reports about this PC. If something looks wrong, use "
                "“Export hardware report” and attach it to an issue on GitHub so it can be fixed for everyone.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        bar = QHBoxLayout()
        self.btn_rescan = set_role(QPushButton("Rescan"), "primary")
        self.btn_rescan.clicked.connect(self.ctx.start_static_scan)
        self.btn_json = QPushButton("Export hardware report (.json)")
        self.btn_json.clicked.connect(lambda: self.export("json"))
        self.btn_txt = QPushButton("Export as text")
        self.btn_txt.clicked.connect(lambda: self.export("txt"))
        self.btn_csv = QPushButton("Export as CSV")
        self.btn_csv.clicked.connect(lambda: self.export("csv"))
        self.btn_copy = QPushButton("Copy to clipboard")
        self.btn_copy.clicked.connect(self.copy_report)
        for b in (self.btn_rescan, self.btn_json, self.btn_txt, self.btn_csv, self.btn_copy):
            bar.addWidget(b)
        bar.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search hardware…")
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(self.apply_filter)
        bar.addWidget(self.search)
        self.content.addLayout(bar)

        self.status = label("Scanning hardware…", "muted")
        self.content.addWidget(self.status)

        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.content.addLayout(self.grid)

        self.cards = {}
        order = [("system", "System"), ("cpu", "Processor"), ("board", "Motherboard & BIOS"),
                 ("ram", "Memory"), ("gpu", "Graphics"), ("disks", "Storage"),
                 ("displays", "Displays"), ("audio", "Audio"), ("net", "Network adapters"),
                 ("sources", "Where live data comes from")]
        for i, (key, title) in enumerate(order):
            card = Card(title)
            kv = KeyValueGrid()
            card.body.addWidget(kv)
            card.body.addStretch(1)
            card.kv = kv
            self.cards[key] = card
            self.grid.addWidget(card, i // 2, i % 2)
        self.finish()

    # ------------------------------------------------------------ filling the cards

    def on_static(self, d):
        if not d:
            self.status.setText("The hardware scan failed. Click Rescan to try again.")
            return
        self.status.setText("Scan complete.")
        os_, comp = d.get("os", {}), d.get("computer", {})
        self.cards["system"].kv.set_rows([
            ("Windows", os_.get("name")),
            ("Build", join(os_.get("build"), f"({os_.get('arch')})" if os_.get("arch") else None)),
            ("PC maker / model", join(comp.get("manufacturer"), comp.get("model")) or None),
            ("Running as admin", _yes(d.get("is_admin"))),
        ])

        cpu = d.get("cpu", {})
        self.cards["cpu"].kv.set_rows([
            ("Model", cpu.get("name")),
            ("Cores / threads", f"{fmt(cpu.get('cores'))} / {fmt(cpu.get('threads'))}"),
            ("Base clock", fmt(cpu.get("base_mhz"), "MHz")),
            ("L2 / L3 cache", f"{fmt(cpu.get('l2_mb'), 'MB', 1)} / {fmt(cpu.get('l3_mb'), 'MB', 1)}"),
            ("Socket", cpu.get("socket")),
            ("Virtualization", cpu.get("virtualization")),
        ])

        mb = d.get("motherboard", {})
        self.cards["board"].kv.set_rows([
            ("Manufacturer", mb.get("manufacturer")),
            ("Model", mb.get("model")),
            ("BIOS version", mb.get("bios_version")),
            ("BIOS date", mb.get("bios_date")),
            ("BIOS vendor", mb.get("bios_vendor")),
        ])

        ram = d.get("ram", {})
        rows = [
            ("Installed", fmt(ram.get("installed_gb"), "GB", 0)),
            ("Usable by Windows", fmt(ram.get("total_gb"), "GB", 1)),
            ("Type", ram.get("type")),
            ("Running speed", fmt(ram.get("running_mts"), "MT/s")),
            ("Slots used", f"{fmt(ram.get('slots_used'))} of {fmt(ram.get('slots_total'))}"
             if ram.get("slots_used") else None),
        ]
        for s in ram.get("sticks", []):
            rows.append((s.get("slot") or "Stick",
                         join(fmt(s.get("size_gb"), "GB"), s.get("type"),
                              fmt(s.get("rated_mts"), "MT/s", na=""), s.get("maker"), s.get("part"), sep=" · ")))
        self.cards["ram"].kv.set_rows(rows)

        rows = []
        for i, g in enumerate(d.get("gpus", []), 1):
            p = f"GPU {i} " if len(d.get("gpus", [])) > 1 else ""
            rows += [
                (f"{p}Model", g.get("name")),
                (f"{p}Type", ("Integrated" if g.get("integrated") else "Dedicated")
                 if g.get("integrated") is not None else None),
                (f"{p}VRAM", fmt(g.get("vram_gb"), "GB", 1)),
                (f"{p}Driver", join(g.get("driver_version"), f"({g['driver_date']})" if g.get("driver_date") else None)
                 or None),
            ]
        self.cards["gpu"].kv.set_rows(rows or [("GPU", None)])

        rows = []
        for disk in d.get("disks", []):
            letters = " ".join(disk.get("letters") or [])
            rows.append((disk.get("name"),
                         join(fmt(disk.get("size_gb"), "GB"), disk.get("media"), disk.get("bus"),
                              f"drives {letters}" if letters else None, sep=" · ")))
            rows.append(("Health", disk.get("health")))
        self.cards["disks"].kv.set_rows(rows or [("Disks", None)])

        rows = []
        for s in QGuiApplication.screens():
            ratio = s.devicePixelRatio()
            w, h = round(s.size().width() * ratio), round(s.size().height() * ratio)
            rows.append((s.name(), f"{w} × {h} @ {s.refreshRate():.0f} Hz"
                         + (f" · {ratio * 100:.0f}% scaling" if ratio != 1 else "")))
        for m in d.get("monitors", []):
            rows.append(("Monitor", join(m.get("name"), f"({m.get('maker')})" if m.get("maker") else None) or None))
        self.cards["displays"].kv.set_rows(rows or [("Displays", None)])

        self.cards["audio"].kv.set_rows(
            [(a.get("manufacturer") or "Device", a.get("name")) for a in d.get("audio", [])] or [("Audio", None)])
        self.cards["net"].kv.set_rows(
            [(n.get("name"), join(n.get("description"), n.get("status"), n.get("link_speed"), sep=" · "))
             for n in d.get("network", [])] or [("Adapters", None)])
        self.apply_filter()

    def apply_filter(self, text=None):
        text = self.search.text() if text is None else text
        for card in self.cards.values():
            card.setVisible(card.kv.filter(text) > 0 or not text)

    def on_sources(self, src):
        lhm = src.get("lhm")
        self.cards["sources"].kv.set_rows([
            ("GPU load, all brands", "Windows GPU counters (same as Task Manager)" if src.get("gpu_counters")
             else "Unavailable (needs Windows 10 version 1709 or newer)"),
            ("CPU clock", "Windows performance counters" if src.get("windows_counters") else NA),
            ("NVIDIA extras", f"NVIDIA driver ({src['nvml_gpus']} GPU)" if src.get("nvml_gpus")
             else "No NVIDIA GPU / driver"),
            ("Temperatures & fans", f"{lhm} (running)" if lhm else "LibreHardwareMonitor not running"),
        ])
        self.apply_filter()

    # ------------------------------------------------------------ export

    def _report(self):
        return build_report(self.ctx.static, self.ctx.last_sample, self.ctx.sources)

    def export(self, ext):
        name, _ = QFileDialog.getSaveFileName(self, "Export hardware report",
                                              f"rytweaks_hardware_report.{ext}", f"*.{ext}")
        if not name:
            return
        try:
            r = self._report()
            if ext == "csv":
                # One row per value shown on this page: Component, Field, Value
                with open(name, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f)
                    w.writerow(["Component", "Field", "Value"])
                    for card in self.cards.values():
                        title = card.title_label.text().title() if card.title_label else ""
                        for key, value in card.kv.rows:
                            w.writerow([title, key, value])
            else:
                with open(name, "w", encoding="utf-8") as f:
                    f.write(report_to_json(r) if ext == "json" else report_to_text(r))
            self.status.setText(f"Report saved to {name}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def copy_report(self):
        QGuiApplication.clipboard().setText(report_to_text(self._report()))
        self.status.setText("Report copied. Paste it into a GitHub issue.")
