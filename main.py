# C:\pc_optimizer\main.py

import sys
import os
import ctypes
from multiprocessing import freeze_support
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
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


def _talk(command, timeout_ms=1500):
    """Sends one command to the running RYTWEAKS and returns its reply (bytes) or None if it doesn't
    answer. Commands: b"ver" (its version), b"show" (bring the window back), b"quit" (close fully).
    Copies from before v1.5.1 only understand "show" and don't answer the others."""
    from PySide6.QtNetwork import QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(_show_server_name())
    if not sock.waitForConnected(timeout_ms):
        return None
    sock.write(command + b"\n")
    sock.waitForBytesWritten(timeout_ms)
    reply = None
    if sock.waitForReadyRead(timeout_ms):
        reply = bytes(sock.readAll()).strip()
    sock.disconnectFromServer()
    return reply


def _running_version():
    """Version of the running copy, or None if it doesn't answer (older than v1.5.1, or stuck)."""
    reply = _talk(b"ver", 1000)
    if reply and reply.startswith(b"ver "):
        return reply[4:].decode("utf-8", "replace").strip() or None
    return None


def _ask_running_copy_to_show():
    """Opening RYTWEAKS while it's already running (e.g. in the tray) brings that window to the front,
    like most apps. Returns True only if the running copy really answered after showing it."""
    try:   # let the running copy take the foreground (Windows blocks it otherwise)
        ctypes.windll.user32.AllowSetForegroundWindow(-1)    # ASFW_ANY
    except Exception:
        pass
    reply = _talk(b"show", 2000)
    return bool(reply and reply.startswith(b"ok"))


def _reopen(window):
    """Opened again while running (owner choice 2026-10-22): if the window is hidden in the tray or
    minimized, play the chip startup animation and fade into it, like a fresh start. A window that's
    already on screen is just brought to the front."""
    if getattr(window, "_reopen_splash", None) is not None:
        return                                   # the animation is already playing
    if window.isVisible() and not window.isMinimized():
        window.show_from_tray()
        return
    splash = RytweaksSplash()
    window._reopen_splash = splash      # keeps the splash alive until its fade has fully finished

    def finished():
        window.setWindowOpacity(1.0)    # never leave the window see-through
        window._reopen_splash = None
    splash.done.connect(finished)

    def failsafe():
        # If the animation is ever interrupted, the window must still end up fully visible
        # (only acts when the animation never finished, so it can't undo a later close to the tray)
        if window._reopen_splash is splash:
            splash.abort()                      # emits done -> opacity 1
            window.show_from_tray()
    QTimer.singleShot(8000, failsafe)
    splash.start()
    splash.finish(window, show=window.show_from_tray)


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
                data = bytes(c.readAll())
                if b"ver" in data:
                    from core.version import __version__
                    c.write(b"ver " + __version__.encode() + b"\n")
                elif b"show" in data:
                    _reopen(window)
                    c.write(b"ok\n")
                elif b"quit" in data:
                    c.write(b"bye\n")
                    QTimer.singleShot(0, window.quit_from_tray)   # closes fully, with normal cleanup
                c.flush()
                c.disconnectFromServer()
            conn.readyRead.connect(read)
    server.newConnection.connect(on_conn)
    return server


def _wait_for_lock(seconds):
    """After the other copy was told to close: wait until Windows frees the single-instance lock."""
    import time
    from core.winutil import single_instance
    end = time.time() + seconds
    while True:
        lock = single_instance()
        if lock is not None or time.time() >= end:
            return lock
        time.sleep(0.15)


def _handle_running_copy():
    """Another RYTWEAKS holds the single-instance lock.
    - Same version, answering: bring its window back (with the startup animation) and exit.
    - Different version (e.g. you just downloaded an update): offer to close it and open this one.
    - Not answering (a version before v1.5.1, or stuck in the background): offer to close it.
    """
    from PySide6.QtWidgets import QMessageBox
    from core.version import __version__ as mine
    from core.winutil import close_other_instances, other_instances
    theirs = _running_version()
    if theirs == mine and _ask_running_copy_to_show():
        sys.exit(0)

    if theirs and theirs != mine:
        box = QMessageBox(QMessageBox.Question, "RYTWEAKS",
                          f"RYTWEAKS v{theirs} is already running (this is v{mine}).")
        box.setInformativeText(f"Close v{theirs} and open v{mine}?")
        switch_btn = box.addButton(f"Open v{mine}", QMessageBox.AcceptRole)
        box.addButton(f"Keep v{theirs}", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not switch_btn:
            _ask_running_copy_to_show()
            sys.exit(0)
        lock = None
        if _talk(b"quit", 2000) == b"bye":
            lock = _wait_for_lock(10)       # it closes normally (restores power plan etc.) first
        if lock is None:
            close_other_instances()
            lock = _wait_for_lock(4)
        if lock is None:
            QMessageBox.warning(None, "RYTWEAKS", f"RYTWEAKS v{theirs} didn't close. Right-click its tray "
                                "icon, choose Quit RYTWEAKS, then open RYTWEAKS again.")
            sys.exit(0)
        return lock

    if not other_instances():
        # Nothing to close from here (e.g. running from source): say what's going on.
        QMessageBox.information(None, "RYTWEAKS", "RYTWEAKS is already running. Check the taskbar or the "
                                "system tray (it may have started minimized with Windows).")
        sys.exit(0)
    box = QMessageBox(QMessageBox.Warning, "RYTWEAKS",
                      "Another RYTWEAKS is running but isn't responding. It's an older version or it's "
                      "stuck in the background.")
    box.setInformativeText("Close it and start this RYTWEAKS?")
    close_btn = box.addButton("Close it and start", QMessageBox.AcceptRole)
    box.addButton("Cancel", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is not close_btn:
        sys.exit(0)
    ok, msg = close_other_instances()
    lock = _wait_for_lock(3) if ok else None
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