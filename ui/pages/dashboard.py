# ui/pages/dashboard.py
"""Live overview: CPU, RAM, every GPU, disk and network, each with a 60-second graph."""

from PySide6.QtWidgets import QGridLayout

from ui.widgets.banners import DashboardBanner, normalize_style
from ui.widgets.charts import MetricCard
from ui.widgets.common import Card, Notice, Page, fmt, fmt_rate, join, label, temp_text, NA


def _ghz(mhz):
    return f"{mhz / 1000:.2f} GHz" if mhz else None


def _temp(c):
    return temp_text(c)


class DashboardPage(Page):
    title = "Dashboard"
    subtitle = "Live view of your PC. Updates every second."

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        style = normalize_style((getattr(ctx, "settings", None) or {}).get("banner_style", "cores"))
        self.banner = DashboardBanner(ctx, style)
        self.banner.setVisible(style != "off")
        self.content.addWidget(self.banner)

        self.summary = label("Scanning hardware…", "pageSubtitle", wrap=True)
        self.content.addWidget(self.summary)

        self.sensor_notice = Notice(
            "CPU temperature and fan speeds aren't available yet. Windows needs a hardware "
            "driver for those, so RETWEAKS reads them from <b>LibreHardwareMonitor</b> "
            "(free, open source) when it's running with its web server on. See <b>Settings → Temperatures &amp; fans</b>.")
        self.sensor_notice.hide()
        self.content.addWidget(self.sensor_notice)

        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        self.content.addLayout(self.grid)

        self.cpu = MetricCard("Processor")
        self.ram = MetricCard("Memory")
        self.disk = MetricCard("Disk activity", maximum=None, show_bar=False)
        self.net = MetricCard("Network", maximum=None, show_bar=False)
        self.gpu_cards = []
        self.fans = Card("Fans")
        self.fans_label = label("", "cardLine", wrap=True)
        self.fans.body.addWidget(self.fans_label)
        self.fans.hide()
        self._layout_cards()
        self.finish()

    def _all_cards(self):
        return [self.cpu, self.ram, *self.gpu_cards, self.disk, self.net]

    def _layout_cards(self):
        for card in self._all_cards() + [self.fans]:
            self.grid.removeWidget(card)
        for i, card in enumerate(self._all_cards()):
            self.grid.addWidget(card, i // 2, i % 2)
        rows = (len(self._all_cards()) + 1) // 2
        self.grid.addWidget(self.fans, rows, 0, 1, 2)

    def on_banner_changed(self, style):
        """Settings changed banner_style: 'off' hides it (no timers run)."""
        style = normalize_style(style)
        self.banner.set_style(style)
        self.banner.setVisible(style != "off")

    def on_theme(self, theme):
        self.banner.apply_theme(theme)
        for card in self._all_cards():
            card.set_theme(theme)

    def on_static(self, data):
        cpu = data.get("cpu", {})
        gpus = data.get("gpus", [])
        ram = data.get("ram", {})
        comp = data.get("computer", {})
        pc = join(comp.get("manufacturer"), comp.get("model"))
        parts = [cpu.get("name"), *(g["name"] for g in gpus),
                 join(fmt(ram.get("installed_gb") or ram.get("total_gb"), "GB"), ram.get("type"))]
        self.summary.setText((pc + " · " if pc else "") + " · ".join(p for p in parts if p))

    def on_telemetry(self, s):
        try:
            self.banner.feed_sample(s)
        except Exception:
            pass  # a decorative banner must never break the live cards
        cpu, ram, io, sensors = s["cpu"], s["ram"], s["io"], s.get("sensors")
        static = self.ctx.static or {}
        scpu = static.get("cpu", {})

        # CPU
        self.cpu.set_value(cpu["load"])
        self.cpu.side.setText(join(_ghz(cpu["mhz"]), _temp(cpu["temp_c"]), sep="  ·  "))
        self.cpu.set_lines([
            scpu.get("name") or "",
            f"Clock: {_ghz(cpu['mhz']) or NA}   Temperature: {_temp(cpu['temp_c']) or NA}",
            f"{fmt(scpu.get('cores'))} cores / {fmt(scpu.get('threads'))} threads",
        ])

        # RAM
        self.ram.set_value(ram["percent"])
        self.ram.side.setText(f"{ram['used_gb']:.1f} / {ram['total_gb']:.1f} GB")
        sram = static.get("ram", {})
        speed = f"{sram['running_mts']} MT/s" if sram.get("running_mts") else None
        self.ram.set_lines([join(sram.get("type"), speed, sep=" · ") or "Memory in use"])

        # GPUs: one card each (laptops often have two)
        gpus = s["gpus"]
        if len(gpus) != len(self.gpu_cards):
            for c in self.gpu_cards:
                c.setParent(None)
                c.deleteLater()
            self.gpu_cards = [MetricCard(f"GPU {i + 1}" if len(gpus) > 1 else "Graphics") for i in range(len(gpus))]
            for c in self.gpu_cards:
                c.set_theme(self.ctx.theme)
            self._layout_cards()
        for card, g in zip(self.gpu_cards, gpus):
            card.set_value(g["load"])
            vram = (f"{g['vram_used_gb']:.1f} / {g['vram_total_gb']:.1f} GB"
                    if g["vram_used_gb"] is not None and g["vram_total_gb"] else fmt(g["vram_total_gb"], "GB", 1))
            card.side.setText(join(_temp(g["temp_c"]), g["engine"], sep="  ·  "))
            extra = join(fmt(g["core_mhz"], "MHz", na=""), fmt(g["power_w"], "W", 0, na=""),
                         f"Fan {g['fan_pct']}%" if g["fan_pct"] is not None else "", sep="   ")
            lines = [g["name"], f"VRAM: {vram}   Temperature: {_temp(g['temp_c']) or NA}"]
            if extra:
                lines.append(extra)
            card.set_lines(lines)

        # Disk + network (auto-scaled graphs)
        r, w = io["disk_read_bps"], io["disk_write_bps"]
        total = (r or 0) + (w or 0) if r is not None else None
        self.disk.set_value(None, fmt_rate(total) if total is not None else "…", graph_value=total)
        self.disk.set_lines([f"Read {fmt_rate(r)}   Write {fmt_rate(w)}"])
        d, u = io["net_down_bps"], io["net_up_bps"]
        self.net.set_value(None, fmt_rate(d) if d is not None else "…", graph_value=d)
        self.net.side.setText(f"↑ {fmt_rate(u)}" if u is not None else "")
        self.net.set_lines([f"Download {fmt_rate(d)}   Upload {fmt_rate(u)}"])

        # Sensors from LibreHardwareMonitor
        self.sensor_notice.setVisible(sensors is None)
        if sensors and sensors.get("fans"):
            self.fans.show()
            self.fans_label.setText("    ".join(f"{f['name']}: {f['rpm']:.0f} RPM" for f in sensors["fans"]))
        else:
            self.fans.hide()
