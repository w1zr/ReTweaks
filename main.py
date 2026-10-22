# C:\pc_optimizer\main.py

import sys
import os
import ctypes
from multiprocessing import freeze_support
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from ui.main_window import MainWindow
from ui.splash import RytweaksSplash

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def main():
    # Set explicit AppUserModelID so Windows Taskbar uses the custom icon
    try:
        myappid = 'rytweaks.pcoptimizer.suite.v1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    app = QApplication(sys.argv)

    # Only one RYTWEAKS at a time (two copies would fight over auto game mode and settings)
    from core.winutil import single_instance
    instance_lock = single_instance()
    if instance_lock is None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(None, "RYTWEAKS", "RYTWEAKS is already running. Check the taskbar or the "
                                "system tray (it may have started minimized with Windows).")
        sys.exit(0)
    
    # Apply app icon globally across all windows
    # Window + taskbar use the v1.4 drawing (owner preference); the .exe file keeps icon.ico
    icon_path = resource_path("assets/taskbar.ico")
    if not os.path.exists(icon_path):
        icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # Started by "Start with Windows" with "Start minimized" on: no splash, just the taskbar
    if "--minimized" in sys.argv:
        window = MainWindow()
        window.start_hidden()        # tray if "Keep running in the tray" is on, else minimized
        sys.exit(app.exec())

    # Chip-scan splash plays while the window really loads (no added waiting)
    splash = RytweaksSplash()
    splash.start()
    try:
        window = MainWindow(progress=splash.pump)
    except Exception:
        splash.abort()       # never leave the splash stuck on screen
        raise
    splash.finish(window)

    sys.exit(app.exec())

if __name__ == "__main__":
    freeze_support()  # Crucial for PyInstaller executables on Windows
    main()