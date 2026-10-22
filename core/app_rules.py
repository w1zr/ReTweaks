# core/app_rules.py
"""Per-program rules ("choose your own .exe") and auto game mode.

Saved Windows settings for a program (they stay even when RYTWEAKS is closed):
- GPU preference: the same value Windows Settings → System → Display → Graphics writes
  (HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences, "GpuPreference=2;" = high performance).
- Disable fullscreen optimizations: the same value as the checkbox on the .exe's
  Properties → Compatibility tab (AppCompatFlags\\Layers, DISABLEDXMAXIMIZEDWINDOWEDMODE).

While the program runs (only while RYTWEAKS is open; it can start minimized with Windows):
- CPU priority: set when the program starts. Some anti-cheat protected games don't allow
  this; RYTWEAKS reports that instead of pretending it worked.
- Performance power plan: switched on when the program starts and switched back to your
  previous plan when the last watched program closes.

Every registry change saves the previous value so removing a rule puts it back.
"""

import json
import os
from pathlib import Path

import psutil

from core.tweaks import REG, REG_SZ, set_dx_option
from core.winutil import IS_WINDOWS, run

GPU_PATH = r"HKCU\Software\Microsoft\DirectX\UserGpuPreferences"
LAYERS_PATH = r"HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
FSO_FLAG = "DISABLEDXMAXIMIZEDWINDOWEDMODE"

GPU_CHOICES = {"Let Windows decide": 0, "Power saving GPU": 1, "High performance GPU": 2}
PRIORITY_CHOICES = ["Normal (don't change)", "Above normal", "High"]
ULTIMATE_GUID = "8c5e7fda-e8bf-496d-815a-8813f8763104"


def _store():
    return Path(os.getenv("APPDATA") or Path.home()) / "RYTWEAKS" / "app_rules.json"


def load_rules():
    try:
        data = json.loads(_store().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_rules(rules):
    p = _store()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rules, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def new_rule(exe_path):
    return {"exe": os.path.normpath(exe_path), "name": Path(exe_path).stem,
            "gpu": None, "fso_off": False, "priority": PRIORITY_CHOICES[0], "boost": False,
            "backup": {}}  # original registry values, saved before RYTWEAKS first changes them


# ---------------------------------------------------------------- saved Windows settings

def _backup(rule, path):
    """Remember the original value of (path, exe) once."""
    key = f"{path}|{rule['exe']}"
    if key not in rule["backup"]:
        cur = REG.get(path, rule["exe"])
        rule["backup"][key] = None if cur is None else [cur[0], cur[1]]


def set_gpu(rule, choice):
    """choice: one of GPU_CHOICES keys, or None to put back the original."""
    try:
        _backup(rule, GPU_PATH)
        if choice is None:
            return _restore_one(rule, GPU_PATH)
        cur = REG.get(GPU_PATH, rule["exe"])
        REG.set(GPU_PATH, rule["exe"], REG_SZ,
                set_dx_option(cur[1] if cur else "", "GpuPreference", str(GPU_CHOICES[choice])))
        rule["gpu"] = choice
        return True, f"{rule['name']}: {choice}. Takes effect the next time it starts."
    except Exception as e:
        return False, str(e)


def get_gpu(rule):
    try:
        cur = REG.get(GPU_PATH, rule["exe"])
    except Exception:
        return None
    if not cur:
        return "Let Windows decide"
    for part in str(cur[1]).split(";"):
        k, _, v = part.partition("=")
        if k.strip() == "GpuPreference":
            return next((n for n, val in GPU_CHOICES.items() if str(val) == v.strip()), None)
    return "Let Windows decide"


def set_fso(rule, disable):
    try:
        _backup(rule, LAYERS_PATH)
        cur = REG.get(LAYERS_PATH, rule["exe"])
        flags = [f for f in (cur[1] if cur else "").split() if f and f != "~"]
        flags = [f for f in flags if f != FSO_FLAG] + ([FSO_FLAG] if disable else [])
        if flags:
            REG.set(LAYERS_PATH, rule["exe"], REG_SZ, "~ " + " ".join(flags))
        else:
            REG.delete(LAYERS_PATH, rule["exe"])
        rule["fso_off"] = disable
        return True, f"{rule['name']}: fullscreen optimizations {'off' if disable else 'on'}."
    except Exception as e:
        return False, str(e)


def get_fso_off(rule):
    try:
        cur = REG.get(LAYERS_PATH, rule["exe"])
    except Exception:
        return False
    return bool(cur and FSO_FLAG in str(cur[1]).split())


def _restore_one(rule, path):
    key = f"{path}|{rule['exe']}"
    if key not in rule["backup"]:
        return True, "Nothing to restore."
    orig = rule["backup"].pop(key)
    if orig is None:
        REG.delete(path, rule["exe"])
    else:
        REG.set(path, rule["exe"], orig[0], orig[1])
    if path == GPU_PATH:
        rule["gpu"] = None
    return True, f"{rule['name']}: original setting restored."


def remove_rule_settings(rule):
    """Put back every original value this rule changed."""
    msgs = []
    for path in (GPU_PATH, LAYERS_PATH):
        try:
            msgs.append(_restore_one(rule, path)[1])
        except Exception as e:
            return False, str(e)
    return True, " ".join(m for m in msgs if m != "Nothing to restore.") or "Removed."


# ---------------------------------------------------------------- auto game mode

def _priority_class(name):
    if not IS_WINDOWS:
        return None
    return {"Above normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS, "High": psutil.HIGH_PRIORITY_CLASS}.get(name)


def _active_plan():
    try:
        import re
        out = run(["powercfg", "/getactivescheme"], timeout=10).stdout
        m = re.search(r"[0-9a-fA-F-]{36}", out)
        return m.group(0).lower() if m else None
    except Exception:
        return None


def _load_saved_plan():
    try:
        return json.loads(_store().with_name("auto_boost_restore.json").read_text(encoding="utf-8")).get("plan")
    except Exception:
        return None


class AutoGameMode:
    """Call poll() every few seconds (from a worker thread). Returns a list of event strings."""

    def __init__(self):
        self.running = {}           # exe path -> set of pids we've handled
        # Plan to restore when the last boosted program exits. Saved to disk too, so it's
        # restored on the next start if RYTWEAKS was closed or crashed during a game.
        self.saved_plan = _load_saved_plan()

    def _set_saved(self, plan):
        self.saved_plan = plan
        try:
            p = _store().with_name("auto_boost_restore.json")
            if plan:
                p.write_text(json.dumps({"plan": plan}), encoding="utf-8")
            elif p.exists():
                p.unlink()
        except Exception:
            pass

    def poll(self, rules):
        events = []
        watched = {os.path.normcase(r["exe"]): r for r in rules
                   if r.get("boost") or r.get("priority") not in (None, PRIORITY_CHOICES[0])}
        if not watched and not self.running:
            return self.restore()  # e.g. a plan left boosted after RYTWEAKS closed mid-game
        seen = {}
        for p in psutil.process_iter(["pid", "exe"]):
            try:
                exe = p.info.get("exe")
            except Exception:
                continue
            if exe and os.path.normcase(exe) in watched:
                seen.setdefault(os.path.normcase(exe), set()).add(p.info["pid"])

        for exe, pids in seen.items():
            rule = watched[exe]
            new_pids = pids - self.running.get(exe, set())
            if not new_pids:
                continue
            if exe not in self.running:
                events.append(f"{rule['name']} started.")
                if rule.get("boost") and self.saved_plan is None:
                    current = _active_plan()
                    if current is None:
                        events.append("Couldn't read your current power plan, so it wasn't changed "
                                      "(RYTWEAKS must be able to switch it back).")
                        self.running[exe] = pids
                        continue
                    r = run(["powercfg", "-duplicatescheme", "e9a42b02-d5df-448d-aa00-03f14749eb61",
                             ULTIMATE_GUID], timeout=15)
                    r = run(["powercfg", "/setactive", ULTIMATE_GUID], timeout=15)
                    if r.returncode == 0:
                        self._set_saved(current)
                        events.append("Switched to the Ultimate Performance power plan for this game.")
                    else:
                        events.append("Couldn't switch the power plan: " + (r.stderr or r.stdout).strip())
            prio = _priority_class(rule.get("priority"))
            if prio is not None:
                for pid in new_pids:
                    try:
                        psutil.Process(pid).nice(prio)
                        events.append(f"{rule['name']}: CPU priority set to {rule['priority']}.")
                    except psutil.AccessDenied:
                        events.append(f"{rule['name']}: Windows (or the game's anti-cheat) didn't allow "
                                      "changing its CPU priority.")
                    except psutil.NoSuchProcess:
                        pass
            self.running[exe] = pids

        for exe in list(self.running):
            if exe not in seen:
                rule = watched.get(exe)
                events.append(f"{rule['name'] if rule else os.path.basename(exe)} closed.")
                del self.running[exe]
        if not self.running:
            events += self.restore()
        return events

    def restore(self):
        """Put the power plan back (also called when RYTWEAKS closes)."""
        if self.saved_plan is None:
            return []
        plan = self.saved_plan
        self._set_saved(None)
        r = run(["powercfg", "/setactive", plan], timeout=15)
        if r.returncode == 0:
            return ["Switched back to your previous power plan."]
        return ["Couldn't switch the power plan back: " + (r.stderr or r.stdout).strip()]
