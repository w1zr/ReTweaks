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
    
    # Apply app icon globally across all windows
    icon_path = resource_path("assets/icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # Show Splash Screen
    splash = RytweaksSplash()
    splash.show()
    app.processEvents()
    
    # Initialize Main Window
    window = MainWindow()
    
    # Smooth Transition from Splash to Main Window
    splash.finish(window)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    freeze_support()  # Crucial for PyInstaller executables on Windows
    main()