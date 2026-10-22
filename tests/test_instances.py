"""Stuck-copy detection and closing (core.winutil.other_instances / close_other_instances)."""
import sys
import types

from core import winutil


class P:
    def __init__(self, pid, name, parent=None):
        self.pid, self.info, self._parent, self.killed = pid, {"pid": pid, "name": name}, parent, False

    def parent(self):
        return self._parent

    def name(self):
        return self.info["name"]

    def kill(self):
        self.killed = True


def fake_psutil(me, procs, alive=()):
    m = types.SimpleNamespace()
    m.Process = lambda: me
    m.process_iter = lambda attrs=None: list(procs)
    m.NoSuchProcess = Exception
    m.wait_procs = lambda ps, timeout=0: ([p for p in ps if p not in alive], [p for p in ps if p in alive])
    return m


def setup(monkeypatch, alive_pids=()):
    launcher = P(10, "RYTWEAKS.exe")
    me = P(11, "RYTWEAKS.exe", parent=launcher)
    stuck_a, stuck_b, other = P(20, "RYTWEAKS.exe"), P(21, "rytweaks.exe"), P(30, "python.exe")
    procs = [launcher, me, stuck_a, stuck_b, other]
    alive = [p for p in procs if p.pid in alive_pids]
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil(me, procs, alive))
    monkeypatch.setattr(winutil, "IS_WINDOWS", True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\RYTWEAKS.exe")
    return launcher, me, stuck_a, stuck_b, other


def test_finds_only_other_copies(monkeypatch):
    launcher, me, a, b, other = setup(monkeypatch)
    assert {p.pid for p in winutil.other_instances()} == {20, 21}   # never itself or its own launcher


def test_close_reports_real_result(monkeypatch):
    launcher, me, a, b, other = setup(monkeypatch)
    ok, msg = winutil.close_other_instances()
    assert ok and a.killed and b.killed and not me.killed and not launcher.killed and not other.killed
    setup(monkeypatch, alive_pids=(20,))
    ok, msg = winutil.close_other_instances()
    assert not ok and "could not be closed" in msg


def test_source_runs_never_kill_python(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert winutil.other_instances() == []
    assert winutil.close_other_instances()[0] is False


def test_existing_mutex_handle_is_closed(monkeypatch):
    """CreateMutexW opens the existing mutex even when it reports ALREADY_EXISTS; that handle must be
    closed, or this process itself keeps the lock alive and the retry after closing a stuck copy fails."""
    import ctypes
    closed = []

    class K32:
        def CreateMutexW(self, *a):
            return 1234

        def CloseHandle(self, h):
            closed.append(h)

    monkeypatch.setattr(winutil, "IS_WINDOWS", True)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: K32(), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 183, raising=False)
    assert winutil.single_instance() is None and closed == [1234]
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)
    assert winutil.single_instance() == 1234 and closed == [1234]


def test_second_launch_brings_running_copy_to_front(monkeypatch, tmp_path):
    """Real local-socket round trip: a second process asks, the running copy shows its window and
    answers. Without a running copy the request reports failure."""
    import os
    import subprocess
    import time
    import pytest
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import main
    name = "RYTWEAKS_test_" + str(os.getpid())
    monkeypatch.setattr(main, "_show_server_name", lambda: name)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    client = ("import sys, os; sys.path.insert(0, %r); os.environ['QT_QPA_PLATFORM']='offscreen';"
              "from PySide6.QtCore import QCoreApplication; a = QCoreApplication([]); import main;"
              "main._show_server_name = lambda: %r; print('RESULT', main._ask_running_copy_to_show())") % (root, name)

    def run_client():
        p = subprocess.Popen([sys.executable, "-c", client], stdout=subprocess.PIPE, text=True)
        end = time.time() + 15
        while p.poll() is None and time.time() < end:
            QCoreApplication.processEvents()
            time.sleep(0.01)
        return p.communicate(timeout=5)[0]

    assert "RESULT False" in run_client()             # nothing running yet

    from PySide6.QtWidgets import QWidget

    class Win(QWidget):
        shown = 0

        def show_from_tray(self):
            Win.shown += 1

    w = Win()
    server = main._listen_for_show(w)
    assert server is not None
    assert "RESULT True" in run_client() and Win.shown == 1
    server.close()
