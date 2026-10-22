# C:\pc_optimizer\ui\splash.py

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplashScreen, QLabel, QVBoxLayout, QWidget, QProgressBar
from PySide6.QtGui import QFont, QGuiApplication, QCursor

class RytweaksSplash(QSplashScreen):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.resize(600, 360)
        
        # Center precisely on active display work area
        self.center_on_screen()
        
        # Professional Black & Grey theme widget
        self.widget = QWidget(self)
        self.widget.resize(600, 360)
        self.widget.setStyleSheet("background-color: #0d0d0d; border: 1px solid #222222; border-radius: 8px;")
        
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignCenter)
        
        title = QLabel("RYTWEAKS")
        title.setFont(QFont("Segoe UI", 26, QFont.Bold))
        title.setStyleSheet("color: #ffffff; letter-spacing: 4px;")
        layout.addWidget(title, alignment=Qt.AlignCenter)
        
        subtitle = QLabel("Windows performance & optimization")
        subtitle.setFont(QFont("Segoe UI", 11))
        subtitle.setStyleSheet("color: #888888; margin-bottom: 30px;")
        layout.addWidget(subtitle, alignment=Qt.AlignCenter)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate loading bar
        self.progress.setFixedWidth(400)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("""
            QProgressBar { background-color: #1a1a1a; border: none; border-radius: 2px; }
            QProgressBar::chunk { background-color: #888888; border-radius: 2px; }
        """)
        layout.addWidget(self.progress, alignment=Qt.AlignCenter)
        
        status_lbl = QLabel("Initializing system modules...")
        status_lbl.setFont(QFont("Segoe UI", 9))
        status_lbl.setStyleSheet("color: #666666; margin-top: 15px;")
        layout.addWidget(status_lbl, alignment=Qt.AlignCenter)

    def center_on_screen(self):
        """Centers the splash screen accurately on the user's active monitor work area."""
        cursor_pos = QCursor.pos()
        active_screen = QGuiApplication.screenAt(cursor_pos)
        if not active_screen:
            active_screen = QGuiApplication.primaryScreen()
            
        screen_geometry = active_screen.availableGeometry()
        x = screen_geometry.x() + (screen_geometry.width() - 600) // 2
        y = screen_geometry.y() + (screen_geometry.height() - 360) // 2
        self.move(x, y)