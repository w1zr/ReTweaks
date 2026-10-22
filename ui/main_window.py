# ui/main_window.py
"""App shell: sidebar + pages, background workers, settings and the change log.

Each page lives in its own file in ui/pages/. To add a page: create a Page subclass there
and add it to NAV below.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from core.themes import get_stylesheet, get_theme
from core.version import APP_NAME, __version__
from core.winutil import is_admin
from ui.pages.dashboard import DashboardPage
from ui.pages.games import GamesPage
from ui.pages.hardware import HardwarePage
from ui.pages.logs import LogsPage
from ui.pages.network import NetworkPage
from ui.pages.profiles import ProfilesPage
from ui.pages.settings import SettingsPage
from ui.pages.snapshot import SnapshotPage
from ui.pages.startup import StartupPage
from ui.pages.storage import StoragePage
from ui.pages.tweaks import TweaksPage
from ui.widgets import common
from ui.widgets.common import label, set_role
from ui.workers import StaticScanWorker, TelemetryWorker

# (section, [(button text, page class), ...])
NAV = [
    ("MONITOR", [("Dashboard", DashboardPage), ("Hardware", HardwarePage)]),
    ("OPTIMIZE", [("Tweaks", TweaksPage), ("Profiles", ProfilesPage), ("Game presets", GamesPage),
                  ("Startup apps", StartupPage), ("Network", NetworkPage)]),
    ("TOOLS", [("Storage && cleanup", StoragePage), ("Snapshots", SnapshotPage), ("Logs", LogsPage)]),
]
BOTTOM_NAV = [("Settings", SettingsPage)]


def resource_path(relative_path):
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, relative_path)


def config_path():
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "RYTWEAKS" / "config.json"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1320, 860)
        self.setMinimumSize(1000, 640)
        icon = resource_path("assets/icon.ico")
        if os.path.exists(icon):
            self.setWindowIcon(QIcon(icon))

        # Shared state that pages read through self.ctx
        self.settings = self._load_settings()
        common.TEMP_UNIT["unit"] = "F" if self.settings.get("temp_unit") == "F" else "C"
        self.update_label = None
        self.theme = get_theme(self.settings.get("theme", "Midnight"), self.settings.get("custom_accent"))
        self.static = {}
        self.last_sample = None
        self.sources = {}
        self.operation_logs = []
        self._scan_worker = None
        self._telemetry = None

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.stack = QStackedWidget()
        self.pages = []
        lay.addWidget(self._build_sidebar())
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.logs_page = next(p for p in self.pages if isinstance(p, LogsPage))
        self.settings_page = next(p for p in self.pages if isinstance(p, SettingsPage))
        self.apply_theme()
        names = self.page_names()
        start = self.settings.get("startup_page", "Dashboard")
        self._select(names.index(start) if start in names else 0)
        self.start_static_scan()
        self.start_telemetry()
        if self.settings.get("check_updates", True):
            # quiet: only says something if an update exists
            self.settings_page.check_updates(quiet=True)

    # ------------------------------------------------------------ layout

    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        v = QVBoxLayout(side)
        v.setContentsMargins(12, 22, 12, 16)
        v.setSpacing(2)
        v.addWidget(label(APP_NAME, "brand"))
        v.addWidget(label(f"Version {__version__}", "brandVersion"))

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        def add_button(text, page_cls):
            page = page_cls(self)
            index = self.stack.addWidget(page)
            self.pages.append(page)
            b = set_role(QPushButton(text), "nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=index: self._select(i))
            self.nav_group.addButton(b, index)
            v.addWidget(b)

        for section, items in NAV:
            v.addWidget(label(section, "navSection"))
            for text, cls in items:
                add_button(text, cls)
        v.addStretch(1)
        for text, cls in BOTTOM_NAV:
            add_button(text, cls)
        self.update_label = set_role(QPushButton(""), "primary")
        self.update_label.hide()
        self.update_label.clicked.connect(lambda: self._select(self.stack.indexOf(self.settings_page)))
        v.addWidget(self.update_label)
        admin = "Running as administrator" if is_admin() else "Not running as administrator"
        footer = label(admin, "sidebarFooter", wrap=True)
        footer.setContentsMargins(10, 10, 0, 0)
        v.addWidget(footer)
        return side

    def page_names(self):
        return [self.nav_group.button(i).text().replace("&&", "&") for i in range(len(self.pages))]

    def show_update_available(self, version):
        self.update_label.setText(f"Update available: {version}")
        self.update_label.show()

    def quit_for_update(self):
        """The updater script is waiting for this process to exit."""
        QApplication.instance().quit()

    def _select(self, index):
        self.nav_group.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)
        self.pages[index].on_shown()

    # ------------------------------------------------------------ workers

    def start_static_scan(self):
        if self._scan_worker and self._scan_worker.isRunning():
            return
        self._scan_worker = StaticScanWorker()
        self._scan_worker.done.connect(self._on_static)
        self._scan_worker.start()

    def _on_static(self, data):
        self.static = data
        for p in self.pages:
            p.on_static(data)

    def start_telemetry(self):
        self._telemetry = TelemetryWorker(self.settings.get("interval", 1.0))
        self._telemetry.sample.connect(self._on_sample)
        self._telemetry.sources.connect(self._on_sources)
        self._telemetry.start()

    def _on_sample(self, sample):
        self.last_sample = sample
        # Only the visible page (and the snapshot recorder) need every sample
        current = self.stack.currentWidget()
        for p in self.pages:
            if p is current or isinstance(p, SnapshotPage):
                p.on_telemetry(sample)

    def _on_sources(self, src):
        self.sources = src
        for p in self.pages:
            if hasattr(p, "on_sources"):
                p.on_sources(src)

    def set_interval(self, seconds):
        self.settings["interval"] = seconds
        if self._telemetry:
            self._telemetry.interval = seconds
        self._save_settings()

    # ------------------------------------------------------------ theme + settings

    def apply_theme(self):
        self.setStyleSheet(get_stylesheet(self.settings.get("theme", "Midnight"), self.settings.get("custom_accent")))
        # Links in labels (Settings → LibreHardwareMonitor, GitHub) use the accent color
        pal = QApplication.palette()
        for role in (QPalette.Link, QPalette.LinkVisited):
            pal.setColor(role, QColor(self.theme["accent"]))
        QApplication.setPalette(pal)
        for p in self.pages:
            p.on_theme(self.theme)

    def set_setting(self, key, value):
        self.settings[key] = value
        if key == "temp_unit":
            common.TEMP_UNIT["unit"] = value
        self._save_settings()

    def set_custom_accent(self, hex_color):
        self.settings["custom_accent"] = hex_color
        self.theme = get_theme(self.settings.get("theme", "Midnight"), hex_color)
        self.apply_theme()
        self._save_settings()

    def set_theme(self, name):
        self.settings["theme"] = name
        self.theme = get_theme(name, self.settings.get("custom_accent"))
        self.apply_theme()
        self._save_settings()

    def _load_settings(self):
        try:
            with open(config_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_settings(self):
        try:
            path = config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Could not save settings: {e}")

    # ------------------------------------------------------------ change log

    def log_action(self, component, requested, result, error=""):
        entry = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "component": component,
                 "requested": requested, "result": result, "error": error or ""}
        self.operation_logs.append(entry)
        self.logs_page.add(entry)

    # ------------------------------------------------------------ shutdown

    def closeEvent(self, event):
        # Hide right away so closing feels instant, then let background threads finish:
        # Qt crashes if a QThread is destroyed while it's still running.
        self.hide()
        if self._telemetry:
            self._telemetry.stop()
            self._telemetry.wait()
        if self._scan_worker:
            self._scan_worker.wait()
        for p in self.pages:
            p.wait_for_tasks()
        super().closeEvent(event)
