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
