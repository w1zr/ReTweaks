# ui/pages/settings.py
"""Theme, refresh speed, sensor setup help, and about."""

from PySide6.QtWidgets import QComboBox, QHBoxLayout

from core.themes import THEMES
from core.version import APP_NAME, __version__
from ui.widgets.common import Card, Page, label

LHM_URL = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases"
REPO_URL = "https://github.com/w1zr/rytweaks"
INTERVALS = {"Every second": 1.0, "Every 2 seconds": 2.0, "Every 5 seconds": 5.0}


class SettingsPage(Page):
    title = "Settings"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)

        look = Card("Appearance")
        row = QHBoxLayout()
        row.addWidget(label("Accent color", "cardLine"))
        self.theme = QComboBox()
        self.theme.addItems(list(THEMES.keys()))
        self.theme.setCurrentText(ctx.settings.get("theme", "Midnight"))
        self.theme.currentTextChanged.connect(ctx.set_theme)
        row.addWidget(self.theme)
        row.addStretch()
        look.body.addLayout(row)
        self.content.addWidget(look)

        live = Card("Live data")
        row = QHBoxLayout()
        row.addWidget(label("Refresh", "cardLine"))
        self.interval = QComboBox()
        self.interval.addItems(list(INTERVALS))
        current = ctx.settings.get("interval", 1.0)
        self.interval.setCurrentText(next((k for k, v in INTERVALS.items() if v == current), "Every second"))
        self.interval.currentTextChanged.connect(lambda t: ctx.set_interval(INTERVALS[t]))
        row.addWidget(self.interval)
        row.addStretch()
        live.body.addLayout(row)
        live.body.addWidget(label("Slower refresh uses a little less CPU.", "muted"))
        self.content.addWidget(live)

        sensors = Card("Temperatures & fans")
        self.lhm_status = label("LibreHardwareMonitor: checking…", "cardLine")
        sensors.body.addWidget(self.lhm_status)
        help_ = label(
            "Windows has no built-in way for apps to read CPU temperature, fan speeds or motherboard "
            "sensors. That needs a hardware driver, which RyTweaks does not install. Instead:<br><br>"
            f"1. Download <a href='{LHM_URL}'>LibreHardwareMonitor</a> (free, open source).<br>"
            "2. Run it as administrator and leave it open (it can start minimized).<br>"
            "3. RyTweaks finds it within about 15 seconds and shows temperatures and fans.<br><br>"
            "NVIDIA GPU temperature works without it, through the NVIDIA driver.", "cardLine", wrap=True)
        help_.setOpenExternalLinks(True)
        sensors.body.addWidget(help_)
        self.content.addWidget(sensors)

        about = Card("About")
        a = label(f"{APP_NAME} v{__version__}<br>Open source: <a href='{REPO_URL}'>{REPO_URL}</a><br>"
                  "Found something wrong? Open an issue on GitHub and attach a hardware report "
                  "(Hardware → Export hardware report).", "cardLine", wrap=True)
        a.setOpenExternalLinks(True)
        about.body.addWidget(a)
        self.content.addWidget(about)
        self.finish()

    def on_sources(self, src):
        lhm = src.get("lhm")
        self.lhm_status.setText(f"{lhm}: connected ✔" if lhm else "LibreHardwareMonitor: not running")
