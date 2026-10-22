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

def _handle_running_copy():
    """Another RYTWEAKS holds the single-instance lock. Usually it's in the tray; sometimes a copy got
    stuck while closing (invisible, but it keeps the lock and locks the .exe file). Offer to close it."""
    from PySide6.QtWidgets import QMessageBox
    from core.winutil import close_other_instances, other_instances, single_instance
    box = QMessageBox(QMessageBox.Information, "RYTWEAKS",
                      "RYTWEAKS is already running. Check the taskbar or the system tray (it may have "
                      "started minimized with Windows).")
    close_btn = None
    if other_instances():
        box.setInformativeText("Can't find it? A copy may be stuck in the background. "
                               "Close it and start RYTWEAKS again?")
        close_btn = box.addButton("Close it and start", QMessageBox.AcceptRole)
    box.addButton("OK" if close_btn is None else "Cancel", QMessageBox.RejectRole)
    box.exec()
    if close_btn is None or box.clickedButton() is not close_btn:
        sys.exit(0)
    ok, msg = close_other_instances()
    lock = single_instance() if ok else None
    if lock is None:
        QMessageBox.warning(None, "RYTWEAKS", msg if not ok else
                            "The other copy closed, but the lock is still held. Restart the PC and try again.")
        sys.exit(0)
    return lock


def _exit(code):
    """Leave the process for sure: if something (e.g. the Edge engine's .NET threads) blocks
    Python's normal shutdown for more than a few seconds, end it anyway, so no invisible copy keeps
    the single-instance lock or locks the .exe. Settings are already saved on every change."""
    import threading
    t = threading.Timer(6.0, os._exit, args=(int(code or 0),))
    t.daemon = True
    t.start()
    sys.exit(code)


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
        instance_lock = _handle_running_copy()
    
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
        _exit(app.exec())

    # Chip-scan splash plays while the window really loads (no added waiting)
    splash = RytweaksSplash()
    splash.start()
    try:
        window = MainWindow(progress=splash.pump)
    except Exception:
        splash.abort()       # never leave the splash stuck on screen
        raise
    splash.finish(window)

    _exit(app.exec())

if __name__ == "__main__":
    freeze_support()  # Crucial for PyInstaller executables on Windows
    main()