"""Scheduled-task parsing for the Startup apps page (sample PowerShell JSON, no Windows needed)."""

import json

from core import startup_manager as sm

SAMPLE = json.dumps([
    {"Name": "GoogleUpdateTaskMachineCore", "TaskPath": "\\", "State": "Ready", "Author": "Google LLC",
     "UserId": "SYSTEM", "Triggers": ["Logon"],
     "Actions": [{"Execute": "C:\\Program Files\\Google\\Update\\GoogleUpdate.exe", "Arguments": "/c"}]},
    {"Name": "MyBackup", "TaskPath": "\\Vendor\\", "State": "Disabled", "Author": None, "UserId": "PC\\ryder",
     "Triggers": ["Boot", "Logon"], "Actions": {"Execute": "C:\\bk.exe", "Arguments": None}},
    {"Name": "Consolidator", "TaskPath": "\\Microsoft\\Windows\\Customer Experience Improvement Program\\",
     "State": "Ready", "Author": "Microsoft", "UserId": "SYSTEM", "Triggers": ["Boot"],
     "Actions": [{"Execute": "%windir%\\system32\\wsqmcons.exe", "Arguments": None}]},
    {"Name": "RYTWEAKS", "TaskPath": "\\", "State": "Ready", "Author": "PC\\ryder", "UserId": "PC\\ryder",
     "Triggers": ["Logon"], "Actions": [{"Execute": "C:\\RYTWEAKS.exe", "Arguments": "--minimized"}]},
    {"Name": "NoTrigger", "TaskPath": "\\", "State": "Ready", "Triggers": [], "Actions": []},
])


def test_parse_hides_windows_tasks_by_default():
    entries = sm.parse_scheduled_tasks(SAMPLE)
    names = [e["task_name"] for e in entries]
    assert "Consolidator" not in names and "NoTrigger" not in names
    assert set(names) == {"GoogleUpdateTaskMachineCore", "MyBackup", "RYTWEAKS"}


def test_parse_includes_windows_tasks_when_asked():
    names = [e["task_name"] for e in sm.parse_scheduled_tasks(SAMPLE, include_windows_tasks=True)]
    assert "Consolidator" in names


def test_entry_fields():
    e = {x["task_name"]: x for x in sm.parse_scheduled_tasks(SAMPLE)}
    g = e["GoogleUpdateTaskMachineCore"]
    assert g["source"] == "Scheduled task" and g["scope"] == "All Users" and g["status"] == "Enabled"
    assert g["publisher"] == "Google LLC" and g["triggers"] == ["Logon"]
    assert g["path"].endswith("GoogleUpdate.exe /c") and g["id"] == "task_\\GoogleUpdateTaskMachineCore"
    b = e["MyBackup"]
    assert b["status"] == "Disabled" and b["scope"] == "Current User" and b["triggers"] == ["Boot", "Logon"]
    assert b["path"] == "C:\\bk.exe" and b["publisher"] == "Unknown"      # single action dict, no author


def test_own_autostart_task_is_managed():
    own = [x for x in sm.parse_scheduled_tasks(SAMPLE) if x["managed"]]
    assert len(own) == 1 and own[0]["name"] == "RYTWEAKS (managed in Settings)"


def test_single_object_and_bad_input():
    one = json.dumps({"Name": "T", "TaskPath": "\\", "State": "Ready", "UserId": "SYSTEM", "Triggers": "Boot",
                      "Actions": None})
    e = sm.parse_scheduled_tasks(one)
    assert len(e) == 1 and e[0]["path"] == "Unavailable"
    assert sm.parse_scheduled_tasks("") == [] and sm.parse_scheduled_tasks("not json") == []
    assert sm.parse_scheduled_tasks("\ufeff[]") == []


def test_task_id_roundtrip():
    tid = sm.task_entry_id("\\Vendor\\Sub\\", "My Task")
    assert sm.split_task_id(tid) == ("\\Vendor\\Sub\\", "My Task")
    assert sm.split_task_id("task_\\Root") == ("\\", "Root")


def test_cannot_toggle_own_task():
    own = [x for x in sm.parse_scheduled_tasks(SAMPLE) if x["managed"]][0]
    ok, msg = sm.disable_startup_entry(own)
    assert not ok and "Settings" in msg
    ok, msg = sm.enable_startup_entry(own["id"])
    assert not ok and "Settings" in msg


def test_quote_is_injection_safe():
    import base64, re
    for name in ["it's", "it\u2019s'; Remove-Item C:\\ -Recurse #", "a*b?[c]", "\u00e9t\u00e9"]:
        expr = sm._ps_quote(name)
        b64 = re.search(r"FromBase64String\('([A-Za-z0-9+/=]*)'\)", expr).group(1)
        assert base64.b64decode(b64).decode("utf-8") == name
        # nothing from the name appears raw in the script, so it can't break out of the string
        assert "'" not in expr.replace(f"'{b64}'", "")


def test_find_task_matches_literally():
    script = sm._ps_find_task("\\Vendor\\", "Up*date")
    assert "-eq $p" in script and "-eq $n" in script and "Up*date" not in script
