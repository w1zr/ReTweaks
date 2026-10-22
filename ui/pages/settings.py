# ui/pages/settings.py
"""Appearance, behavior, updates, sensor setup help, and about."""

import re
from urllib.parse import quote

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QMessageBox,
                               QProgressBar, QPushButton)

from core import autostart, updater
from core.report import build_report, report_to_text
from core.themes import THEMES

HEADER_STYLES = [("Small chip + wordmark", "chip"), ("Wordmark only", "wordmark")]
BANNER_STYLES = [("CPU cores (live)", "cores"), ("Load wave (live)", "wave"), ("Circuit traces", "circuit"),
                 ("Galaxy", "galaxy"), ("Off", "off")]
from core.version import APP_NAME, __version__
from ui.widgets.common import Card, Page, label, set_role

LHM_URL = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases"
REPO_URL = "https://github.com/w1zr/rytweaks"
INTERVALS = {"Every second": 1.0, "Every 2 seconds": 2.0, "Every 5 seconds": 5.0}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def open_report_issue(ctx):
    """Copy the hardware report and open a new GitHub issue. Nothing is sent automatically."""
    text = report_to_text(build_report(ctx.static, ctx.last_sample, ctx.sources))
    QGuiApplication.clipboard().setText(text)
    body = ("**What happened?**\n\n\n**What did you expect?**\n\n\n"
            "**Hardware report:** RYTWEAKS copied it to your clipboard. Paste it below (Ctrl+V).\n\n")
    url = f"{REPO_URL}/issues/new?title={quote(f'[v{__version__}] ')}&body={quote(body)}"
    QDesktopServices.openUrl(QUrl(url))


class SettingsPage(Page):
    title = "Settings"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        s = ctx.settings
        self.update_info = None
        self._progress = 0
        self._downloading = False

        # ---------------- Appearance
        look = Card("Appearance")
        row = QHBoxLayout()
        row.addWidget(label("Theme", "cardLine"))
        self.theme = QComboBox()
        self.theme.addItems(list(THEMES.keys()))
        self.theme.setCurrentText(s.get("theme", "Midnight"))
        self.theme.currentTextChanged.connect(ctx.set_theme)
        row.addWidget(self.theme)
        row.addSpacing(20)
        row.addWidget(label("Custom accent (HEX)", "cardLine"))
        self.hex = QLineEdit(s.get("custom_accent") or "")
        self.hex.setPlaceholderText("#3b82f6")
        self.hex.setMaximumWidth(110)
        self.hex.returnPressed.connect(self.apply_hex)
        b_hex = QPushButton("Apply")
        b_hex.clicked.connect(self.apply_hex)
        b_hex_clear = QPushButton("Use theme color")
        b_hex_clear.clicked.connect(self.clear_hex)
        for w in (self.hex, b_hex, b_hex_clear):
            row.addWidget(w)
        row.addStretch()
        look.body.addLayout(row)
        self.hex_msg = label("", "muted")
        look.body.addWidget(self.hex_msg)

        row = QHBoxLayout()
        row.addWidget(label("Sidebar header", "cardLine"))
        self.header_style = QComboBox()
        for text, key in HEADER_STYLES:
            self.header_style.addItem(text, key)
        self.header_style.setCurrentIndex(1 if s.get("header_style") == "wordmark" else 0)
        self.header_style.currentIndexChanged.connect(
            lambda _i: ctx.set_setting("header_style", self.header_style.currentData()))
        row.addWidget(self.header_style)
        row.addSpacing(20)
        row.addWidget(label("Dashboard banner", "cardLine"))
        self.banner_style = QComboBox()
        for text, key in BANNER_STYLES:
            self.banner_style.addItem(text, key)
        keys = [k for _, k in BANNER_STYLES]
        cur = s.get("banner_style", "cores")
        self.banner_style.setCurrentIndex(keys.index(cur) if cur in keys else 0)
        self.banner_style.currentIndexChanged.connect(
            lambda _i: ctx.set_setting("banner_style", self.banner_style.currentData()))
        row.addWidget(self.banner_style)
        row.addStretch()
        look.body.addLayout(row)
        look.body.addWidget(label("Banners only animate while the Dashboard is open and RYTWEAKS isn't minimized. "
                                  "CPU cores and Load wave show real live readings; Circuit and Galaxy are "
                                  "decoration.", "muted", wrap=True))
        self.content.addWidget(look)

        # ---------------- Behavior
        beh = Card("Behavior")
        row = QHBoxLayout()
        row.addWidget(label("Refresh", "cardLine"))
        self.interval = QComboBox()
        self.interval.addItems(list(INTERVALS))
        current = s.get("interval", 1.0)
        self.interval.setCurrentText(next((k for k, v in INTERVALS.items() if v == current), "Every second"))
        self.interval.currentTextChanged.connect(lambda t: ctx.set_interval(INTERVALS[t]))
        row.addWidget(self.interval)
        row.addSpacing(20)
        row.addWidget(label("Temperature", "cardLine"))
        self.unit = QComboBox()
        self.unit.addItems(["°C", "°F"])
        self.unit.setCurrentText("°F" if s.get("temp_unit") == "F" else "°C")
        self.unit.currentTextChanged.connect(lambda t: ctx.set_setting("temp_unit", "F" if t == "°F" else "C"))
        row.addWidget(self.unit)
        row.addSpacing(20)
        row.addWidget(label("Open on", "cardLine"))
        self.start_page = QComboBox()
        self.start_page.addItem(s.get("startup_page", "Dashboard"))  # full list is filled in on_shown
        self.start_page.currentTextChanged.connect(self._start_page_changed)
        row.addWidget(self.start_page)
        row.addStretch()
        beh.body.addLayout(row)

        self.autostart = QCheckBox("Start RYTWEAKS when I sign in to Windows")
        self.autostart.setEnabled(autostart.available())
        if not autostart.available():
            self.autostart.setToolTip("Only available in RYTWEAKS.exe.")
        self.autostart.toggled.connect(self.toggle_autostart)
        beh.body.addWidget(self.autostart)
        self.minimized = QCheckBox("Start minimized when started with Windows")
        self.minimized.setChecked(bool(s.get("start_minimized", True)))
        self.minimized.toggled.connect(self.toggle_minimized)
        beh.body.addWidget(self.minimized)
        self.beh_msg = label("", "muted")
        beh.body.addWidget(self.beh_msg)
        self.content.addWidget(beh)

        # ---------------- Updates
        upd = Card("Updates")
        upd.body.addWidget(label(f"You have {APP_NAME} v{__version__}.", "cardLine"))
        self.auto_check = QCheckBox("Check for updates when RYTWEAKS starts (asks before downloading anything)")
        self.auto_check.setChecked(bool(s.get("check_updates", True)))
        self.auto_check.toggled.connect(lambda v: ctx.set_setting("check_updates", v))
        upd.body.addWidget(self.auto_check)
        row = QHBoxLayout()
        self.b_check = QPushButton("Check now")
        self.b_check.clicked.connect(lambda: self.check_updates(False))
        self.b_install = set_role(QPushButton("Download and install"), "primary")
        self.b_install.clicked.connect(self.install_update)
        self.b_install.hide()
        self.b_page = QPushButton("Open release page")
        self.b_page.clicked.connect(self.open_release_page)
        self.b_page.hide()
        for b in (self.b_check, self.b_install, self.b_page):
            row.addWidget(b)
        row.addStretch()
        upd.body.addLayout(row)
        self.upd_bar = QProgressBar()
        self.upd_bar.setRange(0, 100)
        self.upd_bar.setFixedHeight(6)
        self.upd_bar.hide()
        upd.body.addWidget(self.upd_bar)
        self.upd_msg = label("", "cardLine", wrap=True)
        upd.body.addWidget(self.upd_msg)
        self.content.addWidget(upd)

        # ---------------- Sensors help
        sensors = Card("Temperatures & fans")
        self.lhm_status = label("LibreHardwareMonitor: checking…", "cardLine")
        sensors.body.addWidget(self.lhm_status)
        help_ = label(
            "Windows has no built-in way for apps to read CPU temperature, fan speeds or motherboard "
            "sensors. That needs a hardware driver, which RYTWEAKS does not install. Instead:<br><br>"
            f"1. Download <a href='{LHM_URL}'>LibreHardwareMonitor</a> (free, open source).<br>"
            "2. Run it as administrator and leave it open (it can start minimized).<br>"
            "3. In LibreHardwareMonitor, turn on <b>Options → Remote Web Server → Run</b> "
            "(keep the default port 8085).<br>"
            "4. RYTWEAKS finds it within a few seconds and shows temperatures and fans.<br><br>"
            "Step 3 is needed for LibreHardwareMonitor 0.9.5 and newer. Older versions "
            "(0.9.4 and before) are detected without it.<br>"
            "NVIDIA GPU temperature works without LibreHardwareMonitor, through the NVIDIA driver.",
            "cardLine", wrap=True)
        help_.setOpenExternalLinks(True)
        sensors.body.addWidget(help_)
        self.content.addWidget(sensors)

        # ---------------- About
        about = Card("About")
        a = label(f"{APP_NAME} v{__version__}<br>Open source: <a href='{REPO_URL}'>{REPO_URL}</a>",
                  "cardLine", wrap=True)
        a.setOpenExternalLinks(True)
        about.body.addWidget(a)
        b_report = QPushButton("Report a problem")
        b_report.setToolTip("Copies your hardware report (no personal info) and opens a new GitHub issue.")
        b_report.clicked.connect(lambda: open_report_issue(self.ctx))
        about.body.addWidget(b_report)
        self.content.addWidget(about)
        self.finish()

    # ------------------------------------------------------------ appearance
    def apply_hex(self):
        text = self.hex.text().strip()
        if text and not text.startswith("#"):
            text = "#" + text
        if not HEX_RE.match(text):
            self.hex_msg.setText("Enter a color like #3b82f6 (6 hex digits).")
            return
        self.hex.setText(text.lower())
        self.hex_msg.setText("")
        self.ctx.set_custom_accent(text.lower())

    def clear_hex(self):
        self.hex.clear()
        self.hex_msg.setText("")
        self.ctx.set_custom_accent(None)

    # ------------------------------------------------------------ behavior
    def _start_page_changed(self, text):
        if text:
            self.ctx.set_setting("startup_page", text)

    def on_shown(self):
        current = self.ctx.settings.get("startup_page", "Dashboard")
        self.start_page.blockSignals(True)
        self.start_page.clear()
        self.start_page.addItems(self.ctx.page_names())
        self.start_page.setCurrentText(current)
        self.start_page.blockSignals(False)
        if autostart.available():
            self.run_task(autostart.is_enabled, on_done=self._show_autostart)

    def _show_autostart(self, enabled):
        self.autostart.blockSignals(True)
        self.autostart.setChecked(enabled is True)
        self.autostart.blockSignals(False)

    def toggle_autostart(self, on):
        self.beh_msg.setText("Updating…")

        def done(result):
            ok, msg = result
            self.beh_msg.setText(msg)
            self.ctx.log_action("Start with Windows", "On" if on else "Off", "Success" if ok else "Failed",
                                "" if ok else msg)
            if not ok:
                self._show_autostart(not on)

        self.run_task(autostart.set_enabled, on, self.minimized.isChecked(), on_done=done)

    def toggle_minimized(self, value):
        self.ctx.set_setting("start_minimized", value)
        if self.autostart.isChecked():  # re-create the sign-in task with/without --minimized
            self.toggle_autostart(True)

    # ------------------------------------------------------------ updates
    def check_updates(self, quiet=False):
        self.b_check.setEnabled(False)
        if not quiet:
            self.upd_msg.setText("Checking GitHub…")
        self.run_task(updater.check_for_update, on_done=lambda info: self._show_update(info, quiet))

    def _show_update(self, info, quiet=False):
        self.b_check.setEnabled(True)
        if not isinstance(info, dict) or "error" in info:
            if not quiet:
                self.upd_msg.setText(info.get("error", "Update check failed.") if isinstance(info, dict)
                                     else "Update check failed.")
            return
        self.update_info = info
        if info["available"]:
            self.b_page.show()
            if updater.can_self_update():
                self.upd_msg.setText(f"{info['version']} is available.")
                self.b_install.show()
            else:
                self.upd_msg.setText(f"{info['version']} is available. You're running from source: "
                                     "use git pull, or download the .exe from the release page.")
            self.ctx.show_update_available(info["version"])
        elif not quiet:
            self.upd_msg.setText(f"You're up to date (latest release is {info['version']}).")

    def open_release_page(self):
        if self.update_info and self.update_info.get("page"):
            QDesktopServices.openUrl(QUrl(self.update_info["page"]))

    def install_update(self):
        info = self.update_info
        if not info:
            return
        if QMessageBox.question(
                self, "Install update",
                f"Download {info['version']} from GitHub, check it, and restart RYTWEAKS?\n\n"
                "Your settings are kept. The current version is saved as RYTWEAKS.old.exe.") != QMessageBox.Yes:
            return
        self.b_install.setEnabled(False)
        self.upd_bar.setValue(0)
        self.upd_bar.show()
        self.upd_msg.setText("Downloading…")
        self._ctx_progress(f"Downloading {info['version']}…", 0, busy=True)
        self._progress = 0
        self._downloading = True
        # The progress callback runs on the worker thread, so it only stores a number;
        # a timer on the UI thread shows it.
        self.run_task(updater.download_update, info, lambda p: setattr(self, "_progress", p),
                      on_done=self._downloaded)
        self._poll_progress()

    def _poll_progress(self):
        if self._downloading:
            self.upd_bar.setValue(self._progress)
            self._ctx_progress(f"Downloading {self.update_info['version']}… {int(self._progress)}%",
                               self._progress, busy=True)
            QTimer.singleShot(200, self._poll_progress)

    def _downloaded(self, result):
        self._downloading = False
        ok, value = result
        if not ok:
            self.b_install.setEnabled(True)
            self.upd_bar.hide()
            self.upd_msg.setText(value)
            self._ctx_progress(f"The update couldn't be downloaded: {value}", None)
            self.ctx.log_action("Update", self.update_info["version"], "Failed", value)
            return
        self.upd_bar.setValue(100)
        ok, msg = updater.install_and_restart(value)
        self.upd_msg.setText(msg)
        self._ctx_progress(msg if not ok else "Installing and restarting RYTWEAKS…", None if not ok else 100,
                           busy=ok)
        self.ctx.log_action("Update", self.update_info["version"], "Success" if ok else "Failed", "" if ok else msg)
        if ok:
            self.ctx.quit_for_update()
        else:
            self.b_install.setEnabled(True)

    def _ctx_progress(self, text, percent=None, busy=False):
        if hasattr(self.ctx, "update_progress"):
            self.ctx.update_progress(text, percent, busy)

    def on_sources(self, src):
        lhm = src.get("lhm")
        self.lhm_status.setText(f"{lhm}: connected ✔" if lhm else "LibreHardwareMonitor: not running")
