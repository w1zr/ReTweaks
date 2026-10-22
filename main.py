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

def _show_server_name():
    import getpass
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return "RYTWEAKS_show_" + "".join(c for c in user if c.isalnum())[:40]


def _ask_running_copy_to_show():
    """Opening RYTWEAKS while it's already running (e.g. in the tray) brings that window to the front,
    like most apps. Returns True only if the running copy really received the request."""
    from PySide6.QtNetwork import QLocalSocket
    try:   # let the running copy take the foreground (Windows blocks it otherwise)
        ctypes.windll.user32.AllowSetForegroundWindow(-1)    # ASFW_ANY
    except Exception:
        pass
    sock = QLocalSocket()
    sock.connectToServer(_show_server_name())
    if not sock.waitForConnected(1500):
        return False
    sock.write(b"show\n")
    sock.waitForBytesWritten(1500)
    # Only a copy whose app is really running answers "ok" after showing its window; a copy that's
    # stuck while closing may still accept the connection but never answers.
    ok = sock.waitForReadyRead(2000) and b"ok" in bytes(sock.readAll())
    sock.disconnectFromServer()
    return ok


def _listen_for_show(window):
    """The running copy: show the window when another launch asks for it."""
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer(window)
    server.setSocketOptions(QLocalServer.UserAccessOption)
    name = _show_server_name()
    if not server.listen(name):
        QLocalServer.removeServer(name)     # a leftover from a crashed copy
        if not server.listen(name):
            return None

    def on_conn():
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            def read(c=conn):
                if b"show" in bytes(c.readAll()):
                    window.show_from_tray()
                    c.write(b"ok\n")
                    c.flush()
                c.disconnectFromServer()
            conn.readyRead.connect(read)
    server.newConnection.connect(on_conn)
    return server


def _handle_running_copy():
    """Another RYTWEAKS holds the single-instance lock. Normally it's running (often in the tray) and
    simply comes to the front. If it doesn't answer, it's stuck (e.g. hung while closing): it's
    invisible but keeps the lock and locks the .exe file, so offer to close it."""
    if _ask_running_copy_to_show():
        sys.exit(0)                       # the running copy came to the front
    import time
    from PySide6.QtWidgets import QMessageBox
    from core.winutil import close_other_instances, other_instances, single_instance
    if not other_instances():
        # Nothing to close from here (e.g. running from source): say what's going on.
        QMessageBox.information(None, "RYTWEAKS", "RYTWEAKS is already running. Check the taskbar or the "
                                "system tray (it may have started minimized with Windows).")
        sys.exit(0)
    box = QMessageBox(QMessageBox.Warning, "RYTWEAKS",
                      "Another RYTWEAKS is running but isn't responding (it may be stuck in the background).")
    box.setInformativeText("Close it and start RYTWEAKS again?")
    close_btn = box.addButton("Close it and start", QMessageBox.AcceptRole)
    box.addButton("Cancel", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is not close_btn:
        sys.exit(0)
    ok, msg = close_other_instances()
    lock = None
    if ok:
        for _ in range(20):               # Windows frees the lock as the closed process is cleaned up
            lock = single_instance()
            if lock is not None:
                break
            time.sleep(0.15)
    if lock is None:
        QMessageBox.warning(None, "RYTWEAKS", msg if not ok else
                            "The other copy closed, but Windows hasn't released its lock yet. "
                            "Open RYTWEAKS again in a few seconds.")
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
        window._show_server = _listen_for_show(window)
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
    window._show_server = _listen_for_show(window)

    _exit(app.exec())

if __name__ == "__main__":
    freeze_support()  # Crucial for PyInstaller executables on Windows
    main()