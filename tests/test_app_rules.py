import core.app_rules as R
import core.tweaks as tw
from tests.test_tweaks import FakeReg


def test_gpu_and_fso_keep_other_flags_and_restore(monkeypatch):
    reg = FakeReg()
    monkeypatch.setattr(R, "REG", reg)
    rule = R.new_rule(r"C:\Games\Fortnite\FortniteClient-Win64-Shipping.exe")
    exe = rule["exe"]
    reg.set(R.LAYERS_PATH, exe, tw.REG_SZ, "~ RUNASADMIN")          # user's own compatibility flag
    assert R.set_gpu(rule, "High performance GPU")[0]
    assert reg.get(R.GPU_PATH, exe)[1] == "GpuPreference=2;"
    assert R.get_gpu(rule) == "High performance GPU"
    assert R.set_fso(rule, True)[0]
    assert reg.get(R.LAYERS_PATH, exe)[1] == "~ RUNASADMIN DISABLEDXMAXIMIZEDWINDOWEDMODE"
    assert R.get_fso_off(rule)
    assert R.remove_rule_settings(rule)[0]
    assert reg.get(R.GPU_PATH, exe) is None                         # didn't exist before
    assert reg.get(R.LAYERS_PATH, exe)[1] == "~ RUNASADMIN"         # user's flag kept


def test_fso_off_then_on_removes_value_if_it_was_the_only_flag(monkeypatch):
    reg = FakeReg()
    monkeypatch.setattr(R, "REG", reg)
    rule = R.new_rule(r"C:\x\game.exe")
    R.set_fso(rule, True)
    R.set_fso(rule, False)
    assert reg.get(R.LAYERS_PATH, rule["exe"]) is None


# ---------------------------------------------------------------- background calming
import json

import pytest


class FakeProc:
    def __init__(self, pid, name, ctime=100.0, nice=0x20):
        self.pid, self._name, self._ctime, self._nice = pid, name, ctime, nice
        self.fail_set = False

    def name(self):
        return self._name

    def create_time(self):
        return self._ctime

    def nice(self, value=None):
        if value is None:
            return self._nice
        if self.fail_set:
            raise type("AccessDenied", (Exception,), {})()
        self._nice = value


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(R.Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


@pytest.mark.parametrize("name", ["csrss", "WinLogon.exe", "svchost", "System", "Registry", "MsMpEng.exe",
                                  "explorer", "dwm", "audiodg", "lsass", "smss", "wininit", "services",
                                  "RETWEAKS.exe", "retweaks"])
def test_protected_names_refused(name):
    assert R.is_protected(name)
    ok, msg = R.validate_calm_name(name)
    assert not ok and "protected" in msg


def test_validate_calm_name_normalizes_and_rejects_paths():
    assert R.validate_calm_name(" Discord.EXE ") == (True, "discord")
    assert not R.validate_calm_name(r"C:\Windows\x.exe")[0]
    assert not R.validate_calm_name("")[0]
    assert not R.validate_calm_name(None)[0]


def test_calm_apply_only_picked_and_records_original(appdata):
    chrome, game, svc = FakeProc(10, "chrome.exe"), FakeProc(11, "game.exe"), FakeProc(12, "svchost.exe")
    records = []
    ev = R.calm_apply([chrome, game, svc], ["chrome", "svchost"], "Idle", records)
    assert chrome._nice == R.calm_priority_value("Idle")
    assert game._nice == 0x20 and svc._nice == 0x20           # unpicked and protected untouched
    assert len(records) == 1 and records[0]["original"] == 0x20 and records[0]["pid"] == 10
    assert len(ev) == 1
    # recorded in the crash-recovery file
    assert R.load_calm_records()[0]["name"] == "chrome"
    # second poll does not record twice
    R.calm_apply([chrome], ["chrome"], "Idle", records)
    assert len(records) == 1


def test_calm_apply_skips_own_pid_and_already_at_target(appdata):
    me = FakeProc(os_pid := __import__("os").getpid(), "tool.exe")
    low = FakeProc(5, "chrome.exe", nice=R.calm_priority_value("Below normal"))
    records = []
    R.calm_apply([me, low], ["tool", "chrome"], "Below normal", records)
    assert records == [] and me._nice == 0x20


def test_calm_apply_denied_leaves_no_record(appdata):
    p = FakeProc(7, "chrome.exe")
    p.fail_set = True
    records = []
    ev = R.calm_apply([p], ["chrome"], "Below normal", records)
    assert records == [] and "didn't allow" in ev[0]
    assert R.load_calm_records() == []


def test_calm_restore_same_process_at_our_priority(appdata):
    p = FakeProc(10, "chrome.exe")
    records = []
    R.calm_apply([p], ["chrome"], "Below normal", records)
    ev = R.calm_restore(lambda pid: p, records)
    assert p._nice == 0x20 and records == [] and "restored" in ev[0]


def test_calm_restore_leaves_user_change_pid_reuse_and_gone(appdata):
    a, b, c = FakeProc(1, "a.exe"), FakeProc(2, "b.exe"), FakeProc(3, "c.exe")
    records = []
    R.calm_apply([a, b, c], ["a", "b", "c"], "Idle", records)
    a._nice = 0x8000                       # user changed it meanwhile
    b._ctime = 999.0                       # same PID, different program
    procs = {1: a, 2: b}                   # 3 has exited
    ev = R.calm_restore(procs.get, records)
    assert a._nice == 0x8000 and b._nice == R.calm_priority_value("Idle")
    assert records == [] and any("changed by you" in e for e in ev)


def test_calm_restore_only_names(appdata):
    a, b = FakeProc(1, "a.exe"), FakeProc(2, "b.exe")
    records = []
    R.calm_apply([a, b], ["a", "b"], "Idle", records)
    R.calm_restore({1: a, 2: b}.get, records, only={"a"})
    assert a._nice == 0x20 and b._nice == R.calm_priority_value("Idle") and len(records) == 1


def test_crash_recovery_file_keeps_power_plan_and_calm(appdata):
    records = []
    R.calm_apply([FakeProc(1, "a.exe")], ["a"], "Idle", records)
    mode = R.AutoGameMode()
    mode._set_saved("plan-guid")
    data = json.loads(R._restore_path().read_text())
    assert data["plan"] == "plan-guid" and data["calm"][0]["name"] == "a"
    assert R.AutoGameMode().calm_records[0]["pid"] == 1       # reloaded after a "crash"
    mode._set_saved(None)
    assert "calm" in json.loads(R._restore_path().read_text())
    R.calm_restore(lambda pid: None, records)
    R._save_calm(records)
    assert not R._restore_path().exists()


def test_calm_config_roundtrip_drops_protected(appdata):
    R.save_calm_config({"enabled": True, "apps": ["discord", "csrss", "discord"], "priority": "Idle"})
    cfg = R.load_calm_config()
    assert cfg == {"enabled": True, "apps": ["discord"], "priority": "Idle"}
    assert R.load_calm_config()["priority"] in R.CALM_LEVELS
