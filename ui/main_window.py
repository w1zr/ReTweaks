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

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QMainWindow,
                               QProgressBar, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from core.themes import get_stylesheet, get_theme
from core.version import APP_NAME, __version__
from core.winutil import is_admin
from ui.pages.about import AboutPage
from ui.pages.assistant import AssistantPage
from ui.pages.audio import AudioPage
from ui.pages.clicker import ClickerPage
from ui.pages.dashboard import DashboardPage
from ui.pages.display import DisplayPage
from ui.pages.fps import FpsPage
from ui.pages.fun import FunPage
from ui.pages.health import HealthPage
from ui.pages.games import GamesPage
from ui.pages.rules import RulesPage
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
from ui.workers import AutoGameWorker, StaticScanWorker, TelemetryWorker

# (section, [(button text, page class), ...])
NAV = [
    ("MONITOR", [("Dashboard", DashboardPage), ("Hardware", HardwarePage), ("Health Check", HealthPage),
                 ("FPS test", FpsPage), ("Display && drivers", DisplayPage)]),
    ("OPTIMIZE", [("Tweaks", TweaksPage), ("Profiles", ProfilesPage), ("Game presets", GamesPage),
                  ("Program rules", RulesPage),
                  ("Startup apps", StartupPage), ("Network", NetworkPage)]),
    ("TOOLS", [("Storage && cleanup", StoragePage), ("Audio mixer", AudioPage), ("Auto clicker", ClickerPage),
               ("AI Assistant", AssistantPage), ("Snapshots", SnapshotPage), ("Fun tools", FunPage),
               ("Logs", LogsPage)]),
]
BOTTOM_NAV = [("About", AboutPage), ("Settings", SettingsPage)]


def resource_path(relative_path):
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, relative_path)


def config_path():
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "RYTWEAKS" / "config.json"


class MainWindow(QMainWindow):
    def __init__(self, progress=None):
        super().__init__()
        # progress(status) keeps the splash animating while pages are built (see ui/splash.py)
        self._progress = progress or (lambda status=None: None)
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1320, 860)
        self.setMinimumSize(1000, 640)
        # Window + taskbar use the v1.4 drawing (owner preference); the .exe file keeps icon.ico
        icon = resource_path("assets/taskbar.ico")
        if not os.path.exists(icon):
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
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        rv.addWidget(self._build_update_bar())   # shown on every page when a new version exists
        rv.addWidget(self.stack, 1)
        lay.addWidget(right, 1)
        self.setCentralWidget(root)

        self.logs_page = next(p for p in self.pages if isinstance(p, LogsPage))
        self.settings_page = next(p for p in self.pages if isinstance(p, SettingsPage))
        self.apply_theme()
        names = self.page_names()
        start = self.settings.get("startup_page", "Dashboard")
        self._select(names.index(start) if start in names else 0)
        self._progress("Scanning hardware…")
        self.start_static_scan()
        self.start_telemetry()
        self.rules_page = next(p for p in self.pages if isinstance(p, RulesPage))
        self._auto = AutoGameWorker()
        self._auto.event.connect(self.rules_page.on_auto_event)
        self._auto.start()
        from core import updater
        result = updater.read_update_status()   # left behind by the in-app updater
        if result == "OK":
            self.log_action("Update", f"Installed v{__version__}", "Success")
            self.settings_page.upd_msg.setText(f"Updated to v{__version__}. The previous version is saved as "
                                               "RYTWEAKS.old.exe next to RYTWEAKS.exe.")
        elif result == "FAILED":
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Update", "The update couldn't be installed (Windows kept the file locked), "
                                f"so you're still on v{__version__}. Try again from Settings → Updates, or "
                                "download it from the release page.")
        if self.settings.get("check_updates", True):
            # quiet: only says something if an update exists
            self.settings_page.check_updates(quiet=True)

    # ------------------------------------------------------------ layout

    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        outer = QVBoxLayout(side)
        outer.setContentsMargins(0, 22, 0, 16)
        outer.setSpacing(2)
        # Header: small chip + wordmark by default; "Wordmark only" in Settings (owner choice 2026-10-21)
        from ui.widgets.brand import ChipLogo
        head = QHBoxLayout()
        head.setContentsMargins(12, 0, 12, 0)
        head.setSpacing(9)
        self.header_chip = ChipLogo(26)
        head.addWidget(self.header_chip, 0, Qt.AlignVCenter)
        brand = label(APP_NAME, "brand")
        head.addWidget(brand, 0, Qt.AlignVCenter)
        head.addStretch(1)
        outer.addLayout(head)
        ver = label(f"Version {__version__}", "brandVersion")
        self.header_version = ver
        outer.addWidget(ver)
        self.apply_header_style(self.settings.get("header_style", "chip"))

        # 20 pages don't fit short screens, so the page list scrolls
        scroll = QScrollArea()
        scroll.setObjectName("navScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        v = QVBoxLayout(holder)
        v.setContentsMargins(12, 0, 12, 0)
        v.setSpacing(2)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)
        self._nav_holder = holder

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        def add_button(text, page_cls, layout):
            self._progress(f"Loading {text.replace('&&', '&')}…")
            page = page_cls(self)
            index = self.stack.addWidget(page)
            self.pages.append(page)
            b = set_role(QPushButton(text), "nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=index: self._select(i))
            self.nav_group.addButton(b, index)
            layout.addWidget(b)

        for section, items in NAV:
            v.addWidget(label(section, "navSection"))
            for text, cls in items:
                add_button(text, cls, v)
        v.addStretch(1)
        bottom = QVBoxLayout()
        bottom.setContentsMargins(12, 6, 12, 0)
        bottom.setSpacing(2)
        for text, cls in BOTTOM_NAV:
            add_button(text, cls, bottom)
        outer.addLayout(bottom)
        self.update_label = set_role(QPushButton(""), "primary")
        self.update_label.hide()
        self.update_label.clicked.connect(lambda: self._select(self.stack.indexOf(self.settings_page)))
        wrap = QHBoxLayout()
        wrap.setContentsMargins(12, 0, 12, 0)
        wrap.addWidget(self.update_label)
        outer.addLayout(wrap)
        admin = "Running as administrator" if is_admin() else "Not running as administrator"
        footer = label(admin, "sidebarFooter", wrap=True)
        footer.setContentsMargins(22, 10, 12, 0)
        outer.addWidget(footer)

        # Accent bar that slides to the selected page (150 ms)
        self._indicator = QFrame(side)
        self._indicator.setObjectName("navIndicator")
        self._indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._indicator.hide()
        self._indicator_anim = QPropertyAnimation(self._indicator, b"geometry", self)
        self._indicator_anim.setDuration(150)
        self._indicator_anim.setEasingCurve(QEasingCurve.OutCubic)
        scroll.verticalScrollBar().valueChanged.connect(lambda _v: self._move_indicator(animate=False))
        self._side = side
        return side

    def _indicator_rect(self, button):
        top_left = button.mapTo(self._side, button.rect().topLeft())
        return QRect(top_left.x(), top_left.y() + 7, 3, button.height() - 14)

    def _move_indicator(self, animate=True):
        button = self.nav_group.checkedButton()
        if not button or not button.isVisible():
            self._indicator.hide()
            return
        # Hide it when the selected button is scrolled out of the visible list
        target = self._indicator_rect(button)
        holder_top = self._nav_holder.parentWidget().mapTo(self._side, self._nav_holder.parentWidget().rect().topLeft()).y()
        holder_bottom = holder_top + self._nav_holder.parentWidget().height()
        in_list = button.parentWidget() is self._nav_holder
        if in_list and (target.bottom() < holder_top or target.top() > holder_bottom):
            self._indicator.hide()
            return
        self._indicator.show()
        self._indicator.raise_()
        if animate and self._indicator.geometry().isValid() and self._indicator.width() > 0:
            self._indicator_anim.stop()
            self._indicator_anim.setStartValue(self._indicator.geometry())
            self._indicator_anim.setEndValue(target)
            self._indicator_anim.start()
        else:
            self._indicator.setGeometry(target)

    def _apply_nav_icons(self):
        from ui.widgets.brand import nav_icon
        for b in self.nav_group.buttons():
            name = b.text().replace("&&", "&")
            off = nav_icon(name, self.theme["subtext"])
            on = nav_icon(name, self.theme["text"])
            if off is None:
                continue
            icon = QIcon()
            icon.addPixmap(off.pixmap(18, 18), QIcon.Normal, QIcon.Off)
            icon.addPixmap(on.pixmap(18, 18), QIcon.Normal, QIcon.On)
            icon.addPixmap(on.pixmap(18, 18), QIcon.Active, QIcon.Off)
            b.setIcon(icon)
            b.setIconSize(QSize(18, 18))

    def go_to_page(self, name):
        """Open a page by its sidebar label (used by Health Check fixes and About)."""
        names = self.page_names()
        if name in names:
            self._select(names.index(name))
            return True
        return False

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self._move_indicator(animate=False))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_indicator"):
            self._move_indicator(animate=False)

    def page_names(self):
        return [self.nav_group.button(i).text().replace("&&", "&") for i in range(len(self.pages))]

    def _build_update_bar(self):
        bar = QFrame()
        bar.setObjectName("updateBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(20, 10, 20, 10)
        h.setSpacing(10)
        self.upd_bar_text = label("", "updateBarText", wrap=True)
        h.addWidget(self.upd_bar_text, 1)
        self.upd_bar_progress = QProgressBar()
        self.upd_bar_progress.setRange(0, 100)
        self.upd_bar_progress.setFixedSize(160, 6)
        self.upd_bar_progress.setTextVisible(False)
        self.upd_bar_progress.hide()
        h.addWidget(self.upd_bar_progress)
        self.upd_bar_now = set_role(QPushButton("Update now"), "primary")
        self.upd_bar_now.clicked.connect(lambda: self.settings_page.install_update())
        h.addWidget(self.upd_bar_now)
        self.upd_bar_notes = QPushButton("What's new")
        self.upd_bar_notes.clicked.connect(lambda: self.settings_page.open_release_page())
        h.addWidget(self.upd_bar_notes)
        self.upd_bar_later = QPushButton("Later")
        self.upd_bar_later.setToolTip("Hide this bar until RYTWEAKS restarts")
        self.upd_bar_later.clicked.connect(bar.hide)
        h.addWidget(self.upd_bar_later)
        bar.hide()
        self.update_bar = bar
        return bar

    def show_update_available(self, version):
        from core import updater
        self.update_label.setText(f"Update available: {version}")
        self.update_label.show()
        if updater.can_self_update():
            self.upd_bar_text.setText(f"RYTWEAKS {version} is available. You're on v{__version__}. "
                                      "Update now to install it here: your settings are kept.")
            self.upd_bar_now.show()
        else:
            self.upd_bar_text.setText(f"RYTWEAKS {version} is available. You're on v{__version__} "
                                      "(running from source: use git pull, or download the .exe).")
            self.upd_bar_now.hide()
        self.update_bar.show()

    def update_progress(self, text, percent=None, busy=False):
        """Called by the Settings page while an update downloads, so the top bar shows it too."""
        self.upd_bar_text.setText(text)
        self.upd_bar_progress.setVisible(percent is not None)
        if percent is not None:
            self.upd_bar_progress.setValue(int(percent))
        self.upd_bar_now.setEnabled(not busy)
        self.upd_bar_later.setEnabled(not busy)

    def quit_for_update(self):
        """The updater script is waiting for this process to exit."""
        QApplication.instance().quit()

    def _select(self, index):
        button = self.nav_group.button(index)
        button.setChecked(True)
        changed = self.stack.currentIndex() != index
        self.stack.setCurrentIndex(index)
        if changed and self.isVisible() and not getattr(self.pages[index], "no_fade", False):
            self._fade_in(self.pages[index])
        scroll = self._nav_holder.parentWidget().parentWidget() if hasattr(self, "_nav_holder") else None
        if isinstance(scroll, QScrollArea) and button.parentWidget() is self._nav_holder:
            scroll.ensureWidgetVisible(button, 0, 8)
        self._move_indicator(animate=self.isVisible())
        self.pages[index].on_shown()

    def _fade_in(self, page):
        """150 ms fade between pages. The effect is removed afterwards so scrolling stays fast."""
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", page)
        anim.setDuration(150)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: page.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeleteWhenStopped)

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

    def apply_header_style(self, style):
        chip = style != "wordmark"
        self.header_chip.setVisible(chip)
        # line the version up under the wordmark
        self.header_version.setContentsMargins(12 + (35 if chip else 0), 0, 12, 0)

    def apply_theme(self):
        from ui.widgets import brand
        brand.set_logo_color(self.theme.get("logo"))
        qss = get_stylesheet(self.settings.get("theme", "Midnight"), self.settings.get("custom_accent"))
        if self.theme.get("stars"):
            try:
                path = brand.galaxy_backdrop_path().replace("\\", "/")
                qss += (f"\nQScrollArea#pageScroll {{ background-color: {self.theme['bg']}; "
                        f"background-image: url('{path}'); background-position: top right; "
                        "background-attachment: fixed; }\n"
                        "QWidget#pageInner { background: transparent; }\n")
            except Exception:
                pass      # the starfield is decoration only; the plain Galaxy colors still apply
        self.setStyleSheet(qss)
        # Links in labels (Settings → LibreHardwareMonitor, GitHub) use the accent color
        pal = QApplication.palette()
        for role in (QPalette.Link, QPalette.LinkVisited):
            pal.setColor(role, QColor(self.theme["accent"]))
        QApplication.setPalette(pal)
        for p in self.pages:
            p.on_theme(self.theme)
        if hasattr(self, "nav_group"):
            self._apply_nav_icons()
        if hasattr(self, "header_chip"):
            self.header_chip.update()

    def set_setting(self, key, value):
        self.settings[key] = value
        if key == "temp_unit":
            common.TEMP_UNIT["unit"] = value
        elif key == "header_style":
            self.apply_header_style(value)
        elif key == "banner_style":
            for p in self.pages:
                if hasattr(p, "on_banner_changed"):
                    p.on_banner_changed(value)
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
        if getattr(self, "_auto", None):
            self._auto.stop()        # also switches the power plan back if a game was boosted
            self._auto.wait()
        if self._scan_worker:
            self._scan_worker.wait()
        stuck = False
        for p in self.pages:
            if p.wait_for_tasks() is False:
                stuck = True
        super().closeEvent(event)
        if stuck:
            # A background request (e.g. a slow AI or PowerShell call) didn't finish in time.
            # Settings are saved on every change and the workers above are already stopped and
            # restored, so exit now rather than leave a hidden process blocking the next launch.
            self._save_settings()
            os._exit(0)
