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


def _restore_path():
    return _store().with_name("auto_boost_restore.json")


def _read_state():
    """The crash-recovery file: {"plan": <power plan guid>, "calm": [<calming records>]}."""
    try:
        data = json.loads(_restore_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(state):
    p = _restore_path()
    try:
        state = {k: v for k, v in state.items() if v}
        if state:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(state), encoding="utf-8")
            os.replace(tmp, p)        # atomic: a crash never leaves a half-written file
        elif p.exists():
            p.unlink()
    except Exception:
        pass


def _load_saved_plan():
    return _read_state().get("plan")


# ---------------------------------------------------------------- background calming
# While a game runs, lower the CPU priority of ONLY the programs the user picked, then put
# it back. The original priority is written to the crash-recovery file before it is lowered.

CALM_LEVELS = {"Below normal": ("BELOW_NORMAL_PRIORITY_CLASS", 0x4000),
               "Idle": ("IDLE_PRIORITY_CLASS", 0x40)}
CALM_DEFAULT = "Below normal"
# Never lowered, whatever the user types: system-critical processes and RYTWEAKS itself.
PROTECTED = frozenset({"csrss", "wininit", "winlogon", "services", "lsass", "smss", "svchost", "dwm",
                       "explorer", "audiodg", "system", "registry", "msmpeng", "rytweaks",
                       "rytweaks.old", "system idle process", "memory compression", "secure system",
                       # anti-cheat services: never touched (CLAUDE.md section 9)
                       "easyanticheat", "easyanticheat_eos", "beservice", "beservice_x64", "vgc", "vgtray",
                       "faceit", "faceitservice", "esportal", "gameguard", "nprotect", "xigncode",
                       "ricochet", "eaanticheat.gameservice"})


def normalize_name(name):
    """'Discord.EXE ' -> 'discord'. Returns '' for anything that isn't a plain program name."""
    if not isinstance(name, str):
        return ""
    n = name.strip().lower()
    if n.endswith(".exe"):
        n = n[:-4]
    if not n or len(n) > 100 or any(c in n for c in '\\/:*?"<>|') or any(ord(c) < 32 for c in n):
        return ""
    return n


def is_protected(name):
    return normalize_name(name) in PROTECTED


def validate_calm_name(name):
    """(ok, normalized_name_or_message). Used when adding, and again before every change."""
    n = normalize_name(name)
    if not n:
        return False, "Type a program name such as discord or chrome (no folders)."
    if n in PROTECTED:
        return False, f"{n} is protected: RYTWEAKS never lowers system-critical programs or itself."
    return True, n


def calm_priority_value(level):
    """psutil priority constant for a level name (works on any OS; None if unknown)."""
    if level not in CALM_LEVELS:
        return None
    attr, fallback = CALM_LEVELS[level]
    return getattr(psutil, attr, fallback)


def _config_path():
    return _store().with_name("calm_config.json")


def load_calm_config():
    """{"enabled": bool, "apps": [names], "priority": level}. Mirrors the "calm_enabled" setting
    (the background worker has no access to the window's settings)."""
    cfg = {"enabled": False, "apps": [], "priority": CALM_DEFAULT}
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg["enabled"] = bool(data.get("enabled", False))
            apps = []
            for a in data.get("apps", []) if isinstance(data.get("apps"), list) else []:
                ok, n = validate_calm_name(a)
                if ok and n not in apps:
                    apps.append(n)
            cfg["apps"] = apps
            if data.get("priority") in CALM_LEVELS:
                cfg["priority"] = data["priority"]
    except Exception:
        pass
    return cfg


def save_calm_config(cfg):
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"enabled": bool(cfg.get("enabled")), "apps": list(cfg.get("apps", [])),
                               "priority": cfg.get("priority", CALM_DEFAULT)}, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def load_calm_records():
    """Programs that are lowered right now (or were when RYTWEAKS last closed)."""
    recs = _read_state().get("calm")
    return [r for r in recs if isinstance(r, dict) and {"pid", "name", "create_time", "original", "set"} <= set(r)] \
        if isinstance(recs, list) else []


def calm_apply(processes, names, level, records, own_pid=None):
    """Lower the priority of running processes whose name is in `names`.

    processes: iterable of objects with pid, name(), create_time(), nice(value=None) (psutil.Process
    or a fake). records: list of dicts already lowered (updated in place, so the caller can save
    it right after each change). Returns a list of event strings."""
    target = calm_priority_value(level)
    if target is None:
        return [f"Background calming: unknown priority “{level}”, nothing changed."]
    wanted = {normalize_name(n) for n in names} - {""}
    events = []
    for p in processes:
        raw = ""
        try:
            raw = p.name()
            n = normalize_name(raw)
            if n not in wanted:
                continue
            if n in PROTECTED or p.pid == own_pid or p.pid == os.getpid():
                continue                                    # protected, even if it got into the list
            ctime = p.create_time()
            if any(r["pid"] == p.pid and abs(r["create_time"] - ctime) < 0.01 for r in records):
                continue                                    # already calmed
            original = p.nice()
            if original == target:
                continue                                    # nothing to change, nothing to restore
            rec = {"pid": p.pid, "name": n, "create_time": ctime, "original": original, "set": target}
            records.append(rec)                             # recorded BEFORE it is changed
            _save_calm(records)
            try:
                p.nice(target)
            except Exception:
                records.remove(rec)
                _save_calm(records)
                raise
            events.append(f"Background calming: {raw} (PID {p.pid}) lowered to {level}.")
        except Exception as e:
            if type(e).__name__ == "AccessDenied":
                events.append(f"Background calming: Windows didn't allow changing {normalize_name(raw) or 'a program'}.")
            # NoSuchProcess / ZombieProcess / anything else: it just isn't there any more
    return events


def calm_restore(get_process, records, only=None):
    """Put priorities back. get_process(pid) -> process object or None. Only processes that are
    still the SAME process (PID + creation time) and still at the priority we set are restored;
    if the user changed it meanwhile it is left alone. `only`: restore just these names.
    Mutates `records` (removes the handled ones); returns event strings."""
    events = []
    for rec in list(records):
        if only is not None and rec["name"] not in only:
            continue
        records.remove(rec)
        try:
            p = get_process(rec["pid"])
            if p is None or abs(p.create_time() - rec["create_time"]) >= 0.01:
                continue                                    # gone, or the PID now belongs to another program
            if p.nice() != rec["set"]:
                events.append(f"Background calming: {rec['name']} (PID {rec['pid']}) was changed by you, "
                              "so RYTWEAKS left its priority alone.")
                continue
            p.nice(rec["original"])
            events.append(f"Background calming: {rec['name']} (PID {rec['pid']}) restored to its original priority.")
        except Exception as e:
            if type(e).__name__ == "AccessDenied":
                events.append(f"Background calming: Windows didn't allow restoring {rec['name']}.")
    return events


def _save_calm(records):
    state = _read_state()
    state["calm"] = list(records)
    _write_state(state)


def _get_process(pid):
    try:
        return psutil.Process(pid)
    except Exception:
        return None


class AutoGameMode:
    """Call poll() every few seconds (from a worker thread). Returns a list of event strings."""

    def __init__(self):
        self.running = {}           # exe path -> set of pids we've handled
        # Plan to restore when the last boosted program exits. Saved to disk too, so it's
        # restored on the next start if RYTWEAKS was closed or crashed during a game.
        self.saved_plan = _load_saved_plan()
        # Programs lowered by background calming; also on disk, so a crash can be undone.
        self.calm_records = load_calm_records()

    def _set_saved(self, plan):
        self.saved_plan = plan
        state = _read_state()
        state["plan"] = plan
        _write_state(state)

    def poll(self, rules):
        events = self._poll_power(rules)
        try:
            events += self._poll_calm(rules)
        except Exception as e:
            events.append(f"Background calming: error: {e}")
        return events

    def _poll_calm(self, rules):
        """Calm the picked programs while a game from Program rules is running.

        A "game" is a rule with auto game mode or a CPU priority set, the same rules that
        trigger auto game mode. Rules that only set the graphics card don't count.
        """
        cfg = load_calm_config()
        game_rules = [r for r in rules
                      if r.get("boost") or r.get("priority") not in (None, PRIORITY_CHOICES[0])]
        if not self.calm_records and not (cfg["enabled"] and cfg["apps"] and game_rules):
            return []
        game_exes = {os.path.normcase(r["exe"]) for r in game_rules}
        # Never calm a program that has its own rule (that includes the game itself)
        ruled_names = {normalize_name(os.path.basename(r["exe"])) for r in rules}
        cfg = dict(cfg, apps=[a for a in cfg["apps"] if normalize_name(a) not in ruled_names])
        procs, game_up = [], False
        for p in psutil.process_iter(["pid", "name", "exe"]):
            try:
                exe = p.info.get("exe")
                if exe and os.path.normcase(exe) in game_exes:
                    game_up = True
                procs.append(p)
            except Exception:
                continue
        if not (cfg["enabled"] and game_up and IS_WINDOWS):
            return self.calm_restore_all()                  # game closed, or switched off
        events = calm_restore(_get_process, self.calm_records, only={r["name"] for r in self.calm_records
                                                                    if r["name"] not in cfg["apps"]})
        _save_calm(self.calm_records)
        events += calm_apply(procs, cfg["apps"], cfg["priority"], self.calm_records)
        return events

    def calm_restore_all(self):
        if not self.calm_records:
            return []
        events = calm_restore(_get_process, self.calm_records)
        _save_calm(self.calm_records)
        return events

    def _poll_power(self, rules):
        events = []
        watched = {os.path.normcase(r["exe"]): r for r in rules
                   if r.get("boost") or r.get("priority") not in (None, PRIORITY_CHOICES[0])}
        if not watched and not self.running:
            return self.restore_power()  # e.g. a plan left boosted after RYTWEAKS closed mid-game
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
            events += self.restore_power()
        return events

    def restore(self):
        """Put the power plan and calmed priorities back (called when RYTWEAKS closes)."""
        return self.restore_power() + self.calm_restore_all()

    def restore_power(self):
        if self.saved_plan is None:
            return []
        plan = self.saved_plan
        self._set_saved(None)
        r = run(["powercfg", "/setactive", plan], timeout=15)
        if r.returncode == 0:
            return ["Switched back to your previous power plan."]
        return ["Couldn't switch the power plan back: " + (r.stderr or r.stdout).strip()]
