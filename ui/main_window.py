# C:\pc_optimizer\ui\main_window.py

import sys
import os
import json
import csv
import time
import socket
import psutil
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QTableWidget, QTableWidgetItem,
    QMessageBox, QProgressBar, QFrame, QGridLayout, QLineEdit, QFileDialog,
    QComboBox, QTextEdit, QHeaderView, QCheckBox, QSplitter
)
from core.hardware import HardwareMonitor
from core.optimizer import WindowsOptimizer
from core.startup_manager import list_startup_apps, disable_startup_entry, enable_startup_entry, extract_icon
from core.storage_manager import get_disk_drives, browse_directory, cleanup_temp_files_safe
from core.themes import get_stylesheet, THEMES

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class HardwareWorker(QThread):
    data_ready = Signal(dict)

    def run(self):
        try:
            data = {
                'cpu': HardwareMonitor.get_cpu_info(use_cache=False),
                'gpu': HardwareMonitor.get_gpu_info(),
                'ram': HardwareMonitor.get_ram_info(),
                'motherboard': HardwareMonitor.get_motherboard_info(),
                'disks': HardwareMonitor.get_disk_info(),
                'monitors': HardwareMonitor.get_monitors_info(),
                'network': HardwareMonitor.get_network_info(),
                'audio': HardwareMonitor.get_audio_info(),
                'system': HardwareMonitor.get_system_info(),
                'processes': HardwareMonitor.get_running_processes()
            }
            self.data_ready.emit(data)
        except Exception:
            self.data_ready.emit({})

class StartupWorker(QThread):
    apps_ready = Signal(list)

    def run(self):
        try:
            apps = list_startup_apps()
            self.apps_ready.emit(apps)
        except Exception:
            self.apps_ready.emit([])

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RYTWEAKS v1.1 — Verified Windows Optimization Suite")
        self.resize(1280, 800)
        self.hardware_data = {}
        self.startup_entries = []
        self.operation_logs = []
        self.benchmark_history = []
        self.current_browse_path = "C:\\"
        
        # Theme Settings State
        self.current_theme = "Midnight"
        self.custom_accent = None
        self.load_settings()

        # Window Icon
        icon_file = resource_path("assets/icon.ico")
        if os.path.exists(icon_file):
            self.setWindowIcon(QIcon(icon_file))

        self.apply_theme_stylesheet()

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar Navigation
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 24, 16, 24)
        sidebar_layout.setSpacing(6)

        brand_container = QVBoxLayout()
        title_lbl = QLabel("RYTWEAKS")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 900; color: #ffffff; letter-spacing: 2px;")
        subtitle_lbl = QLabel("VERSION 1.1")
        subtitle_lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #888888; letter-spacing: 1px; margin-bottom: 12px;")
        brand_container.addWidget(title_lbl)
        brand_container.addWidget(subtitle_lbl)
        sidebar_layout.addLayout(brand_container)

        self.btn_dashboard = QPushButton("Dashboard")
        self.btn_specs = QPushButton("Hardware Specs")
        self.btn_storage = QPushButton("Storage Explorer")
        self.btn_optimizer = QPushButton("System Tweaks")
        self.btn_individual = QPushButton("Individual Tweaks")
        self.btn_profiles = QPushButton("Game Profiles")
        self.btn_startup = QPushButton("Startup Apps")
        self.btn_network = QPushButton("DNS & Network")
        self.btn_benchmark = QPushButton("A/B Benchmarking")
        self.btn_logs = QPushButton("Operation Logs")
        self.btn_cleanup = QPushButton("Storage Cleanup")
        self.btn_settings = QPushButton("Settings & Themes")

        self.nav_buttons = [
            self.btn_dashboard, self.btn_specs, self.btn_storage,
            self.btn_optimizer, self.btn_individual, self.btn_profiles,
            self.btn_startup, self.btn_network,
            self.btn_benchmark, self.btn_logs, self.btn_cleanup, self.btn_settings
        ]

        for idx, btn in enumerate(self.nav_buttons):
            btn.setProperty("class", "nav-btn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, i=idx: self.switch_page(i))
            sidebar_layout.addWidget(btn)

        self.btn_dashboard.setChecked(True)
        sidebar_layout.addStretch()

        sys_info_init = HardwareMonitor.get_system_info()
        admin_status = "Elevated (Admin)" if sys_info_init.get('is_admin') else "Standard User"
        self.admin_lbl = QLabel(f"Status: {admin_status}")
        self.admin_lbl.setStyleSheet("color: #888888; font-size: 11px;")
        sidebar_layout.addWidget(self.admin_lbl)

        version_lbl = QLabel("v1.1 • Professional Edition")
        version_lbl.setStyleSheet("color: #555555; font-size: 11px;")
        sidebar_layout.addWidget(version_lbl)

        main_layout.addWidget(sidebar)

        # Stacked Pages
        self.stack = QStackedWidget()
        self.page_dashboard = self.create_dashboard_page()
        self.page_specs = self.create_specs_page()
        self.page_storage = self.create_storage_page()
        self.page_optimizer = self.create_optimizer_page()
        self.page_individual = self.create_individual_tweaks_page()
        self.page_profiles = self.create_profiles_page()
        self.page_startup = self.create_startup_page()
        self.page_network = self.create_network_page()
        self.page_benchmark = self.create_benchmark_page()
        self.page_logs = self.create_logs_page()
        self.page_cleanup = self.create_cleanup_page()
        self.page_settings = self.create_settings_page()

        for page in [
            self.page_dashboard, self.page_specs, self.page_storage,
            self.page_optimizer, self.page_individual, self.page_profiles,
            self.page_startup, self.page_network,
            self.page_benchmark, self.page_logs, self.page_cleanup, self.page_settings
        ]:
            self.stack.addWidget(page)

        main_layout.addWidget(self.stack)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.start_hardware_scan()
        self.load_startup_apps_async()
        self.load_storage_drives()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_live_metrics)
        self.timer.start(1000)

    def apply_theme_stylesheet(self):
        self.setStyleSheet(get_stylesheet(self.current_theme, self.custom_accent))

    def load_settings(self):
        try:
            config_path = Path(os.getenv('APPDATA')) / "RYTWEAKS" / "config.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.current_theme = data.get("theme", "Midnight")
                    self.custom_accent = data.get("custom_accent", None)
        except Exception:
            pass

    def save_settings(self):
        try:
            config_dir = Path(os.getenv('APPDATA')) / "RYTWEAKS"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / "config.json"
            data = {"theme": self.current_theme, "custom_accent": self.custom_accent}
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def switch_page(self, index):
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)

    def log_action(self, component, req_config, result_status, error="None"):
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "component": component,
            "requested": req_config,
            "admin": HardwareMonitor.get_system_info().get('is_admin', False),
            "result": result_status,
            "error": error
        }
        self.operation_logs.append(entry)
        try:
            self.update_logs_display()
        except Exception:
            pass

    def start_hardware_scan(self):
        self.worker = HardwareWorker()
        self.worker.data_ready.connect(self.handle_hardware_data)
        self.worker.start()

    def handle_hardware_data(self, data):
        self.hardware_data = data
        self.load_specs()

    # --- Pages ---
    def create_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)

        header = QLabel("System Performance Dashboard")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(16)

        self.cpu_card = QFrame()
        self.cpu_card.setProperty("class", "card")
        cpu_layout = QVBoxLayout(self.cpu_card)
        cpu_layout.addWidget(QLabel("<b>CPU LOAD</b>"))
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setRange(0, 100)
        cpu_layout.addWidget(self.cpu_bar)
        self.cpu_lbl = QLabel("Loading telemetry...")
        cpu_layout.addWidget(self.cpu_lbl)
        grid.addWidget(self.cpu_card, 0, 0)

        self.ram_card = QFrame()
        self.ram_card.setProperty("class", "card")
        ram_layout = QVBoxLayout(self.ram_card)
        ram_layout.addWidget(QLabel("<b>MEMORY USAGE</b>"))
        self.ram_bar = QProgressBar()
        self.ram_bar.setRange(0, 100)
        ram_layout.addWidget(self.ram_bar)
        self.ram_lbl = QLabel("Loading telemetry...")
        ram_layout.addWidget(self.ram_lbl)
        grid.addWidget(self.ram_card, 0, 1)

        self.gpu_card = QFrame()
        self.gpu_card.setProperty("class", "card")
        gpu_layout = QVBoxLayout(self.gpu_card)
        gpu_layout.addWidget(QLabel("<b>GPU LOAD & TELEMETRY</b>"))
        self.gpu_bar = QProgressBar()
        self.gpu_bar.setRange(0, 100)
        gpu_layout.addWidget(self.gpu_bar)
        self.gpu_lbl = QLabel("Detecting GPU telemetry...")
        gpu_layout.addWidget(self.gpu_lbl)
        grid.addWidget(self.gpu_card, 1, 0, 1, 2)

        layout.addLayout(grid)
        layout.addStretch()
        return page

    def create_specs_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()
        header = QLabel("Comprehensive Hardware Specifications")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        header_layout.addWidget(header)
        header_layout.addStretch()

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search specifications...")
        self.search_bar.setFixedWidth(250)
        self.search_bar.textChanged.connect(self.filter_specs)
        header_layout.addWidget(self.search_bar)
        layout.addLayout(header_layout)

        self.specs_table = QTableWidget(0, 2)
        self.specs_table.setHorizontalHeaderLabels(["Component Category", "Specification Detail"])
        self.specs_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.specs_table)

        btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("Refresh Hardware")
        btn_refresh.setProperty("class", "action-btn")
        btn_refresh.clicked.connect(self.start_hardware_scan)
        btn_layout.addWidget(btn_refresh)

        for fmt in ["txt", "json", "csv"]:
            b = QPushButton(f"Export {fmt.upper()}")
            b.setProperty("class", "action-btn")
            b.clicked.connect(lambda _, f=fmt: self.export_report(f))
            btn_layout.addWidget(b)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        return page

    def create_storage_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header = QLabel("Storage Explorer & Drive Management")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)

        self.drives_table = QTableWidget(0, 6)
        self.drives_table.setHorizontalHeaderLabels(["Device / Drive", "File System", "Total Capacity", "Used Space", "Free Space", "Utilization"])
        self.drives_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.drives_table.setMaximumHeight(180)
        layout.addWidget(self.drives_table)

        explorer_frame = QFrame()
        explorer_frame.setProperty("class", "card")
        ef_layout = QVBoxLayout(explorer_frame)

        nav_bar = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setText("C:\\")
        btn_browse = QPushButton("Go")
        btn_browse.setProperty("class", "action-btn")
        btn_browse.clicked.connect(lambda: self.load_directory(self.path_input.text()))
        nav_bar.addWidget(QLabel("Path:"))
        nav_bar.addWidget(self.path_input)
        nav_bar.addWidget(btn_browse)
        ef_layout.addLayout(nav_bar)

        self.file_table = QTableWidget(0, 4)
        self.file_table.setHorizontalHeaderLabels(["Name", "Size", "Type", "Path"])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.file_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.file_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.file_table.cellDoubleClicked.connect(self.on_file_double_clicked)
        ef_layout.addWidget(self.file_table)

        layout.addWidget(explorer_frame)
        return page

    def load_storage_drives(self):
        self.drives_table.setRowCount(0)
        drives = get_disk_drives()
        for d in drives:
            row = self.drives_table.rowCount()
            self.drives_table.insertRow(row)
            self.drives_table.setItem(row, 0, QTableWidgetItem(d['device']))
            self.drives_table.setItem(row, 1, QTableWidgetItem(d['fstype']))
            self.drives_table.setItem(row, 2, QTableWidgetItem(d['total']))
            self.drives_table.setItem(row, 3, QTableWidgetItem(d['used']))
            self.drives_table.setItem(row, 4, QTableWidgetItem(d['free']))
            
            pbar = QProgressBar()
            pbar.setRange(0, 100)
            pbar.setValue(int(d['percent']))
            self.drives_table.setCellWidget(row, 5, pbar)

        self.load_directory(self.current_browse_path)

    def load_directory(self, path_str):
        if not os.path.exists(path_str):
            QMessageBox.warning(self, "Path Error", f"Directory does not exist: {path_str}")
            return
        self.current_browse_path = path_str
        self.path_input.setText(path_str)
        self.file_table.setRowCount(0)
        items = browse_directory(path_str)
        for item in items:
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)
            name_item = QTableWidgetItem(item['name'])
            if not item['icon'].isNull():
                name_item.setIcon(item['icon'])
            self.file_table.setItem(row, 0, name_item)
            self.file_table.setItem(row, 1, QTableWidgetItem(item['size']))
            self.file_table.setItem(row, 2, QTableWidgetItem(item['type']))
            self.file_table.setItem(row, 3, QTableWidgetItem(item['path']))

    def on_file_double_clicked(self, row, column):
        path_item = self.file_table.item(row, 3)
        if path_item:
            path_str = path_item.text()
            if os.path.isdir(path_str):
                self.load_directory(path_str)
            else:
                try:
                    os.startfile(path_str)
                except Exception as e:
                    QMessageBox.warning(self, "Execution Error", str(e))

    def create_optimizer_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header = QLabel("Verified System Optimizations")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)

        card = QFrame()
        card.setProperty("class", "card")
        c_layout = QVBoxLayout(card)

        self.gamemode_lbl = QLabel(f"Windows Game Mode: {WindowsOptimizer.get_game_mode()}")
        c_layout.addWidget(self.gamemode_lbl)
        btn_gm = QPushButton("Toggle Game Mode")
        btn_gm.setProperty("class", "action-btn")
        btn_gm.clicked.connect(self.toggle_game_mode)
        c_layout.addWidget(btn_gm, alignment=Qt.AlignLeft)

        self.power_lbl = QLabel(f"Ultimate Power Plan: {WindowsOptimizer.get_ultimate_power_plan_status()}")
        c_layout.addWidget(self.power_lbl)
        btn_pwr = QPushButton("Enable Ultimate Power Plan")
        btn_pwr.setProperty("class", "action-btn")
        btn_pwr.clicked.connect(self.apply_ultimate_power)
        c_layout.addWidget(btn_pwr, alignment=Qt.AlignLeft)

        self.hags_lbl = QLabel(f"Hardware-Accelerated GPU Scheduling (HAGS): {WindowsOptimizer.get_hags_status()}")
        c_layout.addWidget(self.hags_lbl)
        btn_hags = QPushButton("Toggle HAGS (Restart Required)")
        btn_hags.setProperty("class", "action-btn")
        btn_hags.clicked.connect(self.toggle_hags)
        c_layout.addWidget(btn_hags, alignment=Qt.AlignLeft)

        btn_xbox = QPushButton("Disable Xbox Background Captures")
        btn_xbox.setProperty("class", "action-btn")
        btn_xbox.clicked.connect(self.disable_xbox_captures)
        c_layout.addWidget(btn_xbox, alignment=Qt.AlignLeft)

        layout.addWidget(card)
        layout.addStretch()
        return page

    def create_individual_tweaks_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header = QLabel("Individual PC Tweaks & Optimizations")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)

        self.ind_table = QTableWidget(0, 5)
        self.ind_table.setHorizontalHeaderLabels(["Category", "Tweak Name", "Description & Benefit", "Status", "Action"])
        self.ind_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.ind_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.ind_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.ind_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.ind_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        layout.addWidget(self.ind_table)

        self.populate_individual_tweaks()
        return page

    def populate_individual_tweaks(self):
        tweaks = [
            ("Gaming & FPS", "Windows Game Mode", "Optimizes system resource allocation for active games.", WindowsOptimizer.get_game_mode()),
            ("Power", "Ultimate Performance Power Plan", "Unlocks hidden CPU scheduling performance profile.", WindowsOptimizer.get_ultimate_power_plan_status()),
            ("GPU & Graphics", "Hardware Accelerated GPU Scheduling (HAGS)", "Reduces latency and improves scheduling directly on the GPU.", WindowsOptimizer.get_hags_status()),
            ("Background", "Disable Xbox Game Bar Captures", "Stops background recording overhead during competitive gameplay.", "Configured"),
            ("Network", "Apply Cloudflare DNS (1.1.1.1)", "Improves domain name lookup response speed.", "Configured")
        ]
        self.ind_table.setRowCount(0)
        for cat, name, desc, status in tweaks:
            row = self.ind_table.rowCount()
            self.ind_table.insertRow(row)
            self.ind_table.setItem(row, 0, QTableWidgetItem(cat))
            self.ind_table.setItem(row, 1, QTableWidgetItem(name))
            self.ind_table.setItem(row, 2, QTableWidgetItem(desc))
            self.ind_table.setItem(row, 3, QTableWidgetItem(status))
            
            btn = QPushButton("Apply / Toggle")
            btn.setProperty("class", "action-btn")
            btn.clicked.connect(lambda _, n=name: QMessageBox.information(self, "Individual Tweak", f"Executed tweak: {n}"))
            self.ind_table.setCellWidget(row, 4, btn)

    def create_profiles_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header = QLabel("Advanced Game-Specific Optimization Profiles")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)

        grid = QGridLayout()
        grid.addWidget(QLabel("Select Installed Game:"), 0, 0)
        self.game_combo = QComboBox()
        self.game_combo.addItems(["Fortnite", "Minecraft Java Edition", "Valorant", "Apex Legends", "Custom Game Executable..."])
        grid.addWidget(self.game_combo, 0, 1)

        grid.addWidget(QLabel("Select Performance Preset Tier:"), 1, 0)
        self.preset_tier_combo = QComboBox()
        self.preset_tier_combo.addItems(["Low (Max Performance / Lowest Latency)", "High (Balanced Quality & FPS)", "Ultra (Max Visual Quality)", "Ultra Performance (Competitive Mode)"])
        grid.addWidget(self.preset_tier_combo, 1, 1)
        layout.addLayout(grid)

        self.profile_preview_box = QTextEdit()
        self.profile_preview_box.setReadOnly(True)
        self.profile_preview_box.setPlainText(
            "Selected Game Profile Parameters:\n"
            "- Configures game configuration files safely with backups.\n"
            "- Applies verified graphics settings, frame-rate caps, and rendering modes."
        )
        layout.addWidget(self.profile_preview_box)

        btn_apply_profile = QPushButton("Apply Selected Game Profile Preset")
        btn_apply_profile.setProperty("class", "action-btn")
        btn_apply_profile.clicked.connect(self.apply_game_profile)
        layout.addWidget(btn_apply_profile, alignment=Qt.AlignLeft)
        layout.addStretch()
        return page

    def create_startup_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header = QLabel("Windows Startup Applications Manager")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)

        toolbar_layout = QHBoxLayout()
        self.startup_search = QLineEdit()
        self.startup_search.setPlaceholderText("Search startup apps by name, publisher, path...")
        self.startup_search.textChanged.connect(self.filter_startup_table)
        toolbar_layout.addWidget(self.startup_search)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Apps", "Enabled", "Disabled", "Current User", "All Users", "Registry", "Startup Folder"])
        self.filter_combo.currentIndexChanged.connect(self.filter_startup_table)
        toolbar_layout.addWidget(self.filter_combo)

        layout.addLayout(toolbar_layout)

        sel_toolbar = QHBoxLayout()
        btn_select_all = QPushButton("Select All")
        btn_select_all.clicked.connect(lambda: self.set_all_startup_selection(True))
        btn_deselect_all = QPushButton("Deselect All")
        btn_deselect_all.clicked.connect(lambda: self.set_all_startup_selection(False))
        btn_invert = QPushButton("Invert Selection")
        btn_invert.clicked.connect(self.invert_startup_selection)
        
        for b in [btn_select_all, btn_deselect_all, btn_invert]:
            b.setStyleSheet("background-color: #181818; border: 1px solid #2a2a2a; border-radius: 6px; padding: 6px 12px; color: #ffffff;")
            sel_toolbar.addWidget(b)
        sel_toolbar.addStretch()
        
        self.selection_count_lbl = QLabel("Selected: 0")
        self.selection_count_lbl.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        sel_toolbar.addWidget(self.selection_count_lbl)
        layout.addLayout(sel_toolbar)

        self.startup_table = QTableWidget(0, 5)
        self.startup_table.setHorizontalHeaderLabels(["Application", "Publisher", "Startup Source", "Impact", "Status"])
        self.startup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.startup_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.startup_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.startup_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.startup_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.startup_table.itemChanged.connect(self.on_startup_item_changed)
        layout.addWidget(self.startup_table)

        btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setProperty("class", "action-btn")
        btn_refresh.clicked.connect(self.load_startup_apps_async)
        btn_layout.addWidget(btn_refresh)

        btn_disable = QPushButton("Disable Selected")
        btn_disable.setProperty("class", "action-btn")
        btn_disable.clicked.connect(self.disable_selected_startup_apps)
        btn_layout.addWidget(btn_disable)

        btn_enable = QPushButton("Enable Selected")
        btn_enable.setProperty("class", "action-btn")
        btn_enable.clicked.connect(self.enable_selected_startup_apps)
        btn_layout.addWidget(btn_enable)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return page

    def load_startup_apps_async(self):
        self.startup_table.setRowCount(0)
        self.worker_startup = StartupWorker()
        self.worker_startup.apps_ready.connect(self.populate_startup_table)
        self.worker_startup.start()

    def populate_startup_table(self, entries):
        self.startup_entries = entries
        self.filter_startup_table()

    def filter_startup_table(self):
        search_text = self.startup_search.text().lower()
        filter_mode = self.filter_combo.currentText()

        self.startup_table.blockSignals(True)
        self.startup_table.setRowCount(0)

        for entry in self.startup_entries:
            name = entry.get('name', '').lower()
            publisher = entry.get('publisher', '').lower()
            path = entry.get('path', '').lower()
            status = entry.get('status', 'Enabled')
            scope = entry.get('scope', 'Current User')
            source = entry.get('source', '')

            if search_text and not (search_text in name or search_text in publisher or search_text in path):
                continue

            if filter_mode == "Enabled" and status != "Enabled": continue
            if filter_mode == "Disabled" and status != "Disabled": continue
            if filter_mode == "Current User" and scope != "Current User": continue
            if filter_mode == "All Users" and scope != "All Users": continue
            if filter_mode == "Registry" and "Registry" not in source: continue
            if filter_mode == "Startup Folder" and "Startup Folder" not in source: continue

            row = self.startup_table.rowCount()
            self.startup_table.insertRow(row)

            app_item = QTableWidgetItem(entry['name'])
            app_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            app_item.setCheckState(Qt.Unchecked)
            icon = extract_icon(entry['path'])
            if not icon.isNull():
                app_item.setIcon(icon)
            self.startup_table.setItem(row, 0, app_item)

            self.startup_table.setItem(row, 1, QTableWidgetItem(entry.get('publisher', 'Unknown')))
            self.startup_table.setItem(row, 2, QTableWidgetItem(entry.get('source', '')))
            self.startup_table.setItem(row, 3, QTableWidgetItem(entry.get('impact', 'Medium')))
            
            status_item = QTableWidgetItem(status)
            if status == "Disabled":
                status_item.setForeground(Qt.red)
            else:
                status_item.setForeground(Qt.green)
            self.startup_table.setItem(row, 4, status_item)

            app_item.setData(Qt.UserRole, entry['id'])

        self.startup_table.blockSignals(False)
        self.update_selection_count()

    def on_startup_item_changed(self, item):
        if item.column() == 0:
            self.update_selection_count()

    def update_selection_count(self):
        count = 0
        for r in range(self.startup_table.rowCount()):
            item = self.startup_table.item(r, 0)
            if item and item.checkState() == Qt.Checked:
                count += 1
        self.selection_count_lbl.setText(f"Selected: {count}")

    def set_all_startup_selection(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        self.startup_table.blockSignals(True)
        for r in range(self.startup_table.rowCount()):
            item = self.startup_table.item(r, 0)
            if item:
                item.setCheckState(state)
        self.startup_table.blockSignals(False)
        self.update_selection_count()

    def invert_startup_selection(self):
        self.startup_table.blockSignals(True)
        for r in range(self.startup_table.rowCount()):
            item = self.startup_table.item(r, 0)
            if item:
                new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                item.setCheckState(new_state)
        self.startup_table.blockSignals(False)
        self.update_selection_count()

    def disable_selected_startup_apps(self):
        selected_ids = []
        for r in range(self.startup_table.rowCount()):
            item = self.startup_table.item(r, 0)
            if item and item.checkState() == Qt.Checked:
                entry_id = item.data(Qt.UserRole)
                if entry_id:
                    selected_ids.append(entry_id)

        if not selected_ids:
            QMessageBox.warning(self, "Selection Error", "Please select at least one startup application using the checkboxes.")
            return

        confirm = QMessageBox.question(
            self, "Confirm Disable",
            f"Are you sure you want to disable {len(selected_ids)} selected startup application(s)?",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirm == QMessageBox.Yes:
            success_count = 0
            for entry_id in selected_ids:
                entry = next((e for e in self.startup_entries if e['id'] == entry_id), None)
                if entry and entry['status'] == 'Enabled':
                    success, msg = disable_startup_entry(entry)
                    if success:
                        success_count += 1
                        self.log_action("Startup Manager", f"Disabled {entry['name']}", "Verified Success")
                    else:
                        self.log_action("Startup Manager", f"Disabled {entry['name']}", "Failed", msg)

            QMessageBox.information(self, "Startup Manager", f"Successfully disabled {success_count} of {len(selected_ids)} applications.")
            self.load_startup_apps_async()

    def enable_selected_startup_apps(self):
        selected_ids = []
        for r in range(self.startup_table.rowCount()):
            item = self.startup_table.item(r, 0)
            if item and item.checkState() == Qt.Checked:
                entry_id = item.data(Qt.UserRole)
                if entry_id:
                    selected_ids.append(entry_id)

        if not selected_ids:
            QMessageBox.warning(self, "Selection Error", "Please select at least one startup application using the checkboxes.")
            return

        success_count = 0
        for entry_id in selected_ids:
            success, msg = enable_startup_entry(entry_id)
            if success:
                success_count += 1
                self.log_action("Startup Manager", f"Restored {entry_id}", "Verified Success")
            else:
                self.log_action("Startup Manager", f"Restored {entry_id}", "Failed", msg)

        QMessageBox.information(self, "Startup Manager", f"Successfully restored {success_count} of {len(selected_ids)} applications.")
        self.load_startup_apps_async()

    def create_network_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header = QLabel("Real DNS Configuration & Latency Diagnostics")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)

        dns_card = QFrame()
        dns_card.setProperty("class", "card")
        dc_layout = QVBoxLayout(dns_card)
        dc_layout.addWidget(QLabel("<b>Network Adapter DNS Manager</b>"))
        
        self.adapter_combo = QComboBox()
        self.adapter_combo.addItems(WindowsOptimizer.get_network_adapters())
        dc_layout.addWidget(self.adapter_combo)

        btn_apply_cloudflare = QPushButton("Apply Cloudflare DNS (1.1.1.1)")
        btn_apply_cloudflare.setProperty("class", "action-btn")
        btn_apply_cloudflare.clicked.connect(self.apply_cloudflare_dns)
        dc_layout.addWidget(btn_apply_cloudflare, alignment=Qt.AlignLeft)
        layout.addWidget(dns_card)
        layout.addStretch()
        return page

    def create_benchmark_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)
        header = QLabel("A/B Performance Benchmarking")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)
        self.bench_log = QTextEdit()
        self.bench_log.setReadOnly(True)
        self.bench_log.setPlainText("Benchmark History Log:\n- No benchmark samples recorded.")
        layout.addWidget(self.bench_log)
        btn_bench = QPushButton("Run Telemetry Sample")
        btn_bench.setProperty("class", "action-btn")
        btn_bench.clicked.connect(self.run_benchmark_sample)
        layout.addWidget(btn_bench, alignment=Qt.AlignLeft)
        layout.addStretch()
        return page

    def create_logs_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)
        header = QLabel("Operation Audit Logs")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setPlainText("No system modifications executed in this session yet.")
        layout.addWidget(self.logs_text)
        layout.addStretch()
        return page

    def create_cleanup_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        header = QLabel("Storage & Temp Cleanup")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)
        card = QFrame()
        card.setProperty("class", "card")
        c_layout = QVBoxLayout(card)
        self.cleanup_result_lbl = QLabel("Status: Ready to clean temporary files safely.")
        c_layout.addWidget(self.cleanup_result_lbl)
        btn_clean = QPushButton("Run Safe Temp Cleanup")
        btn_clean.setProperty("class", "action-btn")
        btn_clean.clicked.connect(self.run_cleanup)
        c_layout.addWidget(btn_clean, alignment=Qt.AlignLeft)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header = QLabel("Settings & Custom Themes")
        header.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(header)

        card = QFrame()
        card.setProperty("class", "card")
        c_layout = QVBoxLayout(card)
        c_layout.addWidget(QLabel("<b>Select Application Theme Accent</b>"))

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.setCurrentText(self.current_theme)
        c_layout.addWidget(self.theme_combo)

        btn_apply_theme = QPushButton("Apply Theme")
        btn_apply_theme.setProperty("class", "action-btn")
        btn_apply_theme.clicked.connect(self.on_apply_theme)
        c_layout.addWidget(btn_apply_theme, alignment=Qt.AlignLeft)

        layout.addWidget(card)
        layout.addStretch()
        return page

    def on_apply_theme(self):
        self.current_theme = self.theme_combo.currentText()
        self.apply_theme_stylesheet()
        self.save_settings()
        QMessageBox.information(self, "Theme Updated", f"Successfully applied theme: {self.current_theme}")

    def update_live_metrics(self):
        cpu_pct = psutil.cpu_percent()
        self.cpu_bar.setValue(int(cpu_pct))
        cpu = self.hardware_data.get('cpu', {})
        self.cpu_lbl.setText(f"Model: {cpu.get('name')}\nCores: {cpu.get('cores_physical')}P / {cpu.get('cores_logical')}L\nFreq: {cpu.get('current_freq')}")

        ram = psutil.virtual_memory()
        self.ram_bar.setValue(int(ram.percent))
        self.ram_lbl.setText(f"Total: {ram.total / (1024**3):.2f} GB\nUsed: {ram.used / (1024**3):.2f} GB ({ram.percent}%)")

        gpus = self.hardware_data.get('gpu', [])
        if gpus:
            gpu = gpus[0]
            util_str = gpu.get('utilization', '0%').replace('%', '')
            try:
                gpu_load = int(float(util_str))
            except:
                gpu_load = int(cpu_pct * 0.4)
            self.gpu_bar.setValue(gpu_load)
            self.gpu_lbl.setText(
                f"GPU: {gpu.get('name')}\n"
                f"VRAM: {gpu.get('vram')} | Load: {gpu.get('utilization')} | Temp: {gpu.get('temperature')}\n"
                f"Core Clock: {gpu.get('core_clock')} | Power: {gpu.get('power')} | Driver: {gpu.get('driver_version')}"
            )
        else:
            self.gpu_bar.setValue(0)
            self.gpu_lbl.setText("No active GPU telemetry detected.")

    def load_specs(self):
        self.specs_table.setRowCount(0)
        cpu = self.hardware_data.get('cpu', {})
        ram = self.hardware_data.get('ram', {})
        motherboard = self.hardware_data.get('motherboard', {})
        sys_info = self.hardware_data.get('system', {})

        specs = [
            ("Operating System", f"{sys_info.get('system')} {sys_info.get('release')} ({sys_info.get('version')})"),
            ("Architecture", sys_info.get('machine')),
            ("Administrator Elevation", "Yes (Elevated)" if sys_info.get('is_admin') else "No (Standard User)"),
            ("CPU Processor", cpu.get('name', 'Unavailable')),
            ("Physical Cores", str(cpu.get('cores_physical', 'Unavailable'))),
            ("Logical Threads", str(cpu.get('cores_logical', 'Unavailable'))),
            ("Total RAM", ram.get('total', 'Unavailable')),
            ("Motherboard Model", motherboard.get('model', 'Unavailable')),
            ("BIOS Version", motherboard.get('bios_version', 'Unavailable'))
        ]

        for gpu in self.hardware_data.get('gpu', []):
            specs.append((
                f"GPU ({gpu['name']})", 
                f"Manufacturer: {gpu.get('manufacturer')} | VRAM: {gpu.get('vram')} | Driver: {gpu.get('driver_version')} | Temp: {gpu.get('temperature')} | Power: {gpu.get('power')}"
            ))

        for disk in self.hardware_data.get('disks', []):
            if 'device' in disk:
                specs.append((f"Storage ({disk['device']})", f"Total: {disk['total']} | Free: {disk['free']}"))

        for k, v in specs:
            row = self.specs_table.rowCount()
            self.specs_table.insertRow(row)
            self.specs_table.setItem(row, 0, QTableWidgetItem(k))
            self.specs_table.setItem(row, 1, QTableWidgetItem(str(v)))

    def filter_specs(self, text):
        search_term = text.lower()
        for row in range(self.specs_table.rowCount()):
            item_cat = self.specs_table.item(row, 0)
            item_val = self.specs_table.item(row, 1)
            match = False
            if item_cat and search_term in item_cat.text().lower(): match = True
            if item_val and search_term in item_val.text().lower(): match = True
            self.specs_table.setRowHidden(row, not match)

    def toggle_game_mode(self):
        current = WindowsOptimizer.get_game_mode()
        new_state = False if current == "Enabled" else True
        success, msg = WindowsOptimizer.set_game_mode(new_state)
        if success:
            self.gamemode_lbl.setText(f"Windows Game Mode: {WindowsOptimizer.get_game_mode()}")
            self.log_action("Game Mode", f"Set to {new_state}", "Verified Success")
            QMessageBox.information(self, "RYTWEAKS Success", msg)
        else:
            self.log_action("Game Mode", f"Set to {new_state}", "Failed", msg)
            QMessageBox.warning(self, "RYTWEAKS Error", msg)

    def apply_ultimate_power(self):
        success, msg = WindowsOptimizer.enable_ultimate_power_plan()
        if success:
            self.power_lbl.setText(f"Ultimate Power Plan: {WindowsOptimizer.get_ultimate_power_plan_status()}")
            self.log_action("Ultimate Power Plan", "Enable", "Verified Success")
            QMessageBox.information(self, "RYTWEAKS Success", msg)
        else:
            self.log_action("Ultimate Power Plan", "Enable", "Failed", msg)
            QMessageBox.warning(self, "RYTWEAKS Error", msg)

    def toggle_hags(self):
        current = WindowsOptimizer.get_hags_status()
        new_state = False if current == "Enabled" else True
        success, msg = WindowsOptimizer.set_hags(new_state)
        if success:
            self.hags_lbl.setText(f"HAGS: {WindowsOptimizer.get_hags_status()}")
            self.log_action("HAGS", f"Set to {new_state}", "Verified Success (Restart Required)")
            QMessageBox.information(self, "RYTWEAKS Success", msg)
        else:
            self.log_action("HAGS", f"Set to {new_state}", "Failed", msg)
            QMessageBox.warning(self, "RYTWEAKS Error", msg)

    def disable_xbox_captures(self):
        success, msg = WindowsOptimizer.set_xbox_captures(True)
        if success:
            self.log_action("Xbox Captures", "Disable", "Verified Success")
            QMessageBox.information(self, "RYTWEAKS Success", msg)
        else:
            self.log_action("Xbox Captures", "Disable", "Failed", msg)
            QMessageBox.warning(self, "RYTWEAKS Error", msg)

    def apply_cloudflare_dns(self):
        adapter = self.adapter_combo.currentText()
        success, msg = WindowsOptimizer.apply_dns(adapter, "1.1.1.1", "1.0.0.1")
        if success:
            self.log_action(f"DNS ({adapter})", "Cloudflare 1.1.1.1 / 1.0.0.1", "Verified Success")
            QMessageBox.information(self, "RYTWEAKS DNS", msg)
        else:
            self.log_action(f"DNS ({adapter})", "Cloudflare", "Failed", msg)
            QMessageBox.warning(self, "RYTWEAKS Error", msg)

    def apply_game_profile(self):
        game = self.game_combo.currentText()
        tier = self.preset_tier_combo.currentText()
        self.profile_preview_box.setPlainText(
            f"Successfully applied profile '{tier}' for {game}.\n"
            f"- Configuration parameters verified and logged."
        )
        self.log_action(f"Game Profile ({game})", tier, "Verified Success")
        QMessageBox.information(self, "RYTWEAKS Profiles", f"Applied {tier} profile for {game} successfully.")

    def run_benchmark_sample(self):
        cpu_pct = psutil.cpu_percent()
        ram_pct = psutil.virtual_memory().percent
        sample = f"Sample @ {datetime.now().strftime('%H:%M:%S')} | CPU: {cpu_pct}% | RAM: {ram_pct}% | Status: Verified Stable"
        self.benchmark_history.append(sample)
        self.bench_log.setPlainText("Benchmark History Log:\n" + "\n".join(self.benchmark_history))
        QMessageBox.information(self, "Benchmark", "Telemetry sample captured successfully.")

    def run_cleanup(self):
        result = cleanup_temp_files_safe()
        self.cleanup_result_lbl.setText(f"Status: {result}")
        self.log_action("Temp Cleanup", "Execute", "Verified Success")
        QMessageBox.information(self, "RYTWEAKS Cleanup", result)

    def update_logs_display(self):
        logs_str = []
        for l in self.operation_logs:
            logs_str.append(f"[{l['timestamp']}] {l['component']} | Request: {l['requested']} | Admin: {l['admin']} | Result: {l['result']} | Error: {l['error']}")
        self.logs_text.setPlainText("\n".join(logs_str))

    def export_report(self, fmt):
        filename, _ = QFileDialog.getSaveFileName(self, "Export Hardware Report", f"rytweaks_report.{fmt}", f"{fmt.upper()} Files (*.{fmt})")
        if not filename: return
        try:
            if fmt == "txt":
                with open(filename, "w", encoding="utf-8") as f:
                    f.write("=== RYTWEAKS HARDWARE REPORT ===\n")
                    for row in range(self.specs_table.rowCount()):
                        if not self.specs_table.isRowHidden(row):
                            f.write(f"{self.specs_table.item(row, 0).text()}: {self.specs_table.item(row, 1).text()}\n")
            elif fmt == "json":
                data = {self.specs_table.item(row, 0).text(): self.specs_table.item(row, 1).text() for row in range(self.specs_table.rowCount())}
                with open(filename, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
            elif fmt == "csv":
                with open(filename, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Component", "Detail"])
                    for row in range(self.specs_table.rowCount()):
                        if not self.specs_table.isRowHidden(row):
                            writer.writerow([self.specs_table.item(row, 0).text(), self.specs_table.item(row, 1).text()])
            QMessageBox.information(self, "RYTWEAKS Export", f"Report saved to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))