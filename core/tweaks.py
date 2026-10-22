# core/tweaks.py
"""Individual Windows tweaks with real state, previous-value backup and undo.

Every tweak:
- reads its real current state from Windows (get_state),
- before its FIRST change, saves the exact previous values (including "didn't exist"),
- can be undone on its own, or all at once with undo_everything().

Only documented Windows settings are used (the same values the Settings app or
Control Panel change). No "FPS boost" folklore. Each tweak says what it does, its
trade-off, whether it needs administrator rights, and whether a restart is needed.
"""

import ctypes
import json
import os
import threading
from pathlib import Path

from core.winutil import IS_WINDOWS, run, run_powershell

STANDARD, ADVANCED = "Standard", "Advanced"

# ---------------------------------------------------------------- registry backend
# Swappable so tests can run without Windows (tests/test_tweaks.py uses a dict).


class _WinReg:
    HIVES = {"HKCU": "HKEY_CURRENT_USER", "HKLM": "HKEY_LOCAL_MACHINE"}

    def _split(self, path):
        import winreg
        hive, _, sub = path.partition("\\")
        return getattr(winreg, self.HIVES[hive]), sub

    def get(self, path, name):
        """(type, data) or None if the value doesn't exist."""
        import winreg
        root, sub = self._split(path)
        try:
            with winreg.OpenKey(root, sub, 0, winreg.KEY_READ) as k:
                data, typ = winreg.QueryValueEx(k, name)
                return typ, data
        except FileNotFoundError:
            return None

    def set(self, path, name, typ, data):
        import winreg
        root, sub = self._split(path)
        with winreg.CreateKeyEx(root, sub, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, typ, data)

    def delete(self, path, name):
        import winreg
        root, sub = self._split(path)
        try:
            with winreg.OpenKey(root, sub, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except FileNotFoundError:
            pass

    def delete_key(self, path):
        """Delete one EMPTY key (no subkeys). Missing keys are fine; non-empty keys are left alone."""
        import winreg
        root, sub = self._split(path)
        try:
            winreg.DeleteKey(root, sub)
        except FileNotFoundError:
            pass
        except OSError:
            pass   # not empty: never delete anything else


REG = _WinReg()

# Tweaks run on background threads; this stops two of them from writing the backup file
# at the same time (which could lose a saved original value).
_LOCK = threading.RLock()
REG_SZ, REG_DWORD = 1, 4


# ---------------------------------------------------------------- saved previous values

def _state_path():
    return Path(os.getenv("APPDATA") or Path.home()) / "RETWEAKS" / "tweak_backups.json"


def load_backups():
    try:
        with open(_state_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_backups(data):
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)  # never leave a half-written backup file


# ---------------------------------------------------------------- tweak definitions

class Tweak:
    """A tweak made of registry values. on/off are {(path, name): (type, data)}."""

    def __init__(self, tid, name, level, description, tradeoff, values_on, values_off,
                 admin=False, restart=None, after_change=None):
        self.id, self.name, self.level = tid, name, level
        self.description, self.tradeoff = description, tradeoff
        self.values_on, self.values_off = values_on, values_off
        self.admin, self.restart = admin, restart
        self.after_change = after_change  # e.g. tell Windows to reload mouse settings now

    def keys(self):
        return list(self.values_on.keys())

    def get_state(self):
        """'On', 'Off', or 'Windows default' when none of the values exist."""
        try:
            current = {k: REG.get(*k) for k in self.keys()}
        except Exception:
            return "Unknown"
        if all(v is None for v in current.values()):
            return "Windows default"
        if all(current[k] is not None and current[k][1] == self.values_on[k][1] for k in self.keys()):
            return "On"
        if all(current[k] is not None and current[k][1] == self.values_off[k][1] for k in self.keys()):
            return "Off"
        return "Custom"

    def _backup_once(self):
        backups = load_backups()
        if self.id in backups:
            return  # keep the ORIGINAL values from before RETWEAKS first touched it
        saved = []
        for path, name in self.keys():
            cur = REG.get(path, name)
            saved.append([path, name, None if cur is None else [cur[0], cur[1]]])
        backups[self.id] = {"name": self.name, "values": saved}
        _save_backups(backups)

    def apply(self, on):
        with _LOCK:
            return self._apply(on)

    def _values_for(self, on):
        return self.values_on if on else self.values_off

    def _apply(self, on):
        try:
            self._backup_once()
            for (path, name), (typ, data) in self._values_for(on).items():
                REG.set(path, name, typ, data)
            if self.after_change:
                self.after_change()
        except PermissionError:
            return False, "Windows refused the change. Run RETWEAKS as administrator."
        except Exception as e:
            return False, str(e)
        note = {"signout": " Sign out and back in for it to take full effect.",
                "restart": " Restart your PC for it to take effect."}.get(self.restart, "")
        return True, f"{self.name}: {'on' if on else 'off'}.{note}"

    def undo(self):
        with _LOCK:
            return self._undo()

    def _undo(self):
        backups = load_backups()
        entry = backups.get(self.id)
        if not entry:
            return False, "Nothing to undo: RETWEAKS hasn't changed this setting."
        try:
            for path, name, value in entry["values"]:
                if value is None:
                    REG.delete(path, name)       # it didn't exist before
                else:
                    REG.set(path, name, value[0], value[1])
            if self.after_change:
                self.after_change()
        except PermissionError:
            return False, "Windows refused the change. Run RETWEAKS as administrator."
        except Exception as e:
            return False, str(e)
        del backups[self.id]
        _save_backups(backups)
        return True, f"{self.name}: restored to how it was before."


def _refresh_mouse():
    """Make Windows apply the mouse acceleration values now (same as the Control Panel)."""
    if not IS_WINDOWS:
        return
    try:
        cur = [int(REG.get(r"HKCU\Control Panel\Mouse", n)[1]) for n in
               ("MouseThreshold1", "MouseThreshold2", "MouseSpeed")]
        arr = (ctypes.c_int * 3)(*cur)
        ctypes.windll.user32.SystemParametersInfoW(0x0004, 0, arr, 0x03)  # SPI_SETMOUSE
    except Exception:
        pass


def _merge_dx(on):
    """'Optimizations for windowed games' lives inside one string with other DirectX
    settings (e.g. 'VRROptimizeEnable=0;SwapEffectUpgradeEnable=1;'). Change only ours."""
    def build():
        cur = REG.get(DX_PATH, DX_NAME)
        return set_dx_option(cur[1] if cur else "", "SwapEffectUpgradeEnable", "1" if on else "0")
    return build


DX_PATH, DX_NAME = r"HKCU\Software\Microsoft\DirectX\UserGpuPreferences", "DirectXUserGlobalSettings"


def set_dx_option(text, key, value):
    parts = [p for p in (text or "").split(";") if p.strip()]
    out, found = [], False
    for p in parts:
        k, _, _v = p.partition("=")
        if k.strip() == key:
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(p.strip())
    if not found:
        out.append(f"{key}={value}")
    return ";".join(out) + ";"


class WindowedGamesTweak(Tweak):
    """Special case: one value shared with other DirectX options."""

    def __init__(self):
        super().__init__(
            "windowed_games", "Optimizations for windowed games", STANDARD,
            "Lets older DirectX 10/11 games running in windowed or borderless mode use the same faster "
            "presentation path as fullscreen, which can lower latency. Same switch as Settings → "
            "Display → Graphics (Windows 11).",
            "Rarely, an older game can show glitches; turn it off for that game if so.",
            {(DX_PATH, DX_NAME): (REG_SZ, None)}, {(DX_PATH, DX_NAME): (REG_SZ, None)})

    def get_state(self):
        try:
            cur = REG.get(DX_PATH, DX_NAME)
        except Exception:
            return "Unknown"
        text = cur[1] if cur else ""
        for p in text.split(";"):
            k, _, v = p.partition("=")
            if k.strip() == "SwapEffectUpgradeEnable":
                return "On" if v.strip() == "1" else "Off"
        return "Windows default"

    def _values_for(self, on):
        return {(DX_PATH, DX_NAME): (REG_SZ, _merge_dx(on)())}


class AccessibilityShortcutsTweak(Tweak):
    """Only flips the "shortcut is active" bit (0x4, SKF_HOTKEYACTIVE / FKF_HOTKEYACTIVE /
    TKF_HOTKEYACTIVE) in each Flags value, so a user's own Sticky/Filter/Toggle Keys settings
    (including having the feature itself turned on) are kept."""

    DEFAULTS = {"StickyKeys": "510", "Keyboard Response": "126", "ToggleKeys": "62"}

    def __init__(self):
        keys = {(ACCESS + "\\" + k, "Flags"): (REG_SZ, None) for k in self.DEFAULTS}
        super().__init__(
            "sticky_keys_popup", "Sticky/Filter/Toggle Keys shortcut pop-ups", STANDARD,
            "When on, pressing Shift 5 times (or holding it) opens an accessibility pop-up, which can kick "
            "you out of a game. Turning it off only removes the shortcut, not the features.",
            "You can still turn these features on from Settings → Accessibility.",
            keys, keys, restart="signout")

    def _flags(self, path):
        cur = REG.get(path, "Flags")
        try:
            return int(cur[1]) if cur else int(self.DEFAULTS[path.rsplit("\\", 1)[1]])
        except (TypeError, ValueError):
            return int(self.DEFAULTS[path.rsplit("\\", 1)[1]])

    def _values_for(self, on):
        out = {}
        for (path, name) in self.keys():
            flags = self._flags(path)
            out[(path, name)] = (REG_SZ, str(flags | 0x4 if on else flags & ~0x4))
        return out

    def get_state(self):
        try:
            if all(REG.get(p, n) is None for p, n in self.keys()):
                return "Windows default"
            hot = [bool(self._flags(p) & 0x4) for p, _ in self.keys()]
        except Exception:
            return "Unknown"
        return "On" if all(hot) else ("Off" if not any(hot) else "Custom")


class CommandTweak(Tweak):
    """Tweak changed by a Windows command, with state read from the registry."""

    def __init__(self, tid, name, level, description, tradeoff, state_key, cmd_on, cmd_off,
                 admin=True, restart=None):
        super().__init__(tid, name, level, description, tradeoff, {state_key: (REG_DWORD, 1)},
                         {state_key: (REG_DWORD, 0)}, admin=admin, restart=restart)
        self.cmd_on, self.cmd_off = cmd_on, cmd_off

    def _run(self, on):
        r = run(self.cmd_on if on else self.cmd_off, timeout=60)
        if r.returncode != 0:
            raise PermissionError((r.stderr or r.stdout).strip())

    def _apply(self, on):
        try:
            self._backup_once()
            self._run(on)
        except PermissionError as e:
            return False, str(e) or "Windows refused the change. Run RETWEAKS as administrator."
        except Exception as e:
            return False, str(e)
        return True, f"{self.name}: {'on' if on else 'off'}."

    def _undo(self):
        backups = load_backups()
        entry = backups.get(self.id)
        if not entry:
            return False, "Nothing to undo: RETWEAKS hasn't changed this setting."
        prev = entry["values"][0][2]
        try:
            # value missing before = Windows default, which is ON
            self._run(True if prev is None else bool(prev[1]))
        except Exception as e:
            return False, str(e) or "Windows refused the change."
        del backups[self.id]
        _save_backups(backups)
        return True, f"{self.name}: restored to how it was before."


GAMEBAR = r"HKCU\Software\Microsoft\GameBar"
GAMEDVR = r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR"
MOUSE = r"HKCU\Control Panel\Mouse"
ACCESS = r"HKCU\Control Panel\Accessibility"

TWEAKS = [
    Tweak("game_mode", "Game Mode", STANDARD,
          "Windows gives the game you're playing priority over background tasks and Windows Update.",
          "On most PCs it helps or does nothing; on a few it can lower FPS. Test both ways.",
          {(GAMEBAR, "AutoGameModeEnabled"): (REG_DWORD, 1), (GAMEBAR, "AllowAutoGameMode"): (REG_DWORD, 1)},
          {(GAMEBAR, "AutoGameModeEnabled"): (REG_DWORD, 0), (GAMEBAR, "AllowAutoGameMode"): (REG_DWORD, 0)}),
    Tweak("xbox_capture", "Xbox Game Bar background recording", STANDARD,
          "When on, Game Bar can record the last minutes of gameplay in the background.",
          "Background recording costs some performance. Turning it off means no instant replays.",
          {(r"HKCU\System\GameConfigStore", "GameDVR_Enabled"): (REG_DWORD, 1),
           (GAMEDVR, "AppCaptureEnabled"): (REG_DWORD, 1), (GAMEDVR, "HistoricalCaptureEnabled"): (REG_DWORD, 1)},
          {(r"HKCU\System\GameConfigStore", "GameDVR_Enabled"): (REG_DWORD, 0),
           (GAMEDVR, "AppCaptureEnabled"): (REG_DWORD, 0), (GAMEDVR, "HistoricalCaptureEnabled"): (REG_DWORD, 0)}),
    Tweak("mouse_accel", "Mouse acceleration (Enhance pointer precision)", STANDARD,
          "When on, the pointer moves farther if you move the mouse faster. Many players turn it off so "
          "the same hand movement always gives the same aim.",
          "Off can feel slower on the desktop at first. Same setting as Control Panel → Mouse.",
          {(MOUSE, "MouseSpeed"): (REG_SZ, "1"), (MOUSE, "MouseThreshold1"): (REG_SZ, "6"),
           (MOUSE, "MouseThreshold2"): (REG_SZ, "10")},
          {(MOUSE, "MouseSpeed"): (REG_SZ, "0"), (MOUSE, "MouseThreshold1"): (REG_SZ, "0"),
           (MOUSE, "MouseThreshold2"): (REG_SZ, "0")},
          after_change=_refresh_mouse),
    Tweak("transparency", "Transparency effects", STANDARD,
          "See-through taskbar, Start menu and windows.",
          "Off uses slightly fewer GPU resources on the desktop; it doesn't change in-game FPS. "
          "Same switch as Settings → Personalization → Colors.",
          {(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency"): (REG_DWORD, 1)},
          {(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency"): (REG_DWORD, 0)}),
    AccessibilityShortcutsTweak(),
    WindowedGamesTweak(),
    Tweak("hags", "Hardware-accelerated GPU scheduling (HAGS)", ADVANCED,
          "Lets the GPU manage its own memory scheduling. Can lower latency on newer GPUs; on others it "
          "makes no difference. Needed for NVIDIA Frame Generation.",
          "Some older drivers have issues with it. Needs administrator rights.",
          {(r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode"): (REG_DWORD, 2)},
          {(r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode"): (REG_DWORD, 1)},
          admin=True, restart="restart"),
    Tweak("fast_startup", "Fast Startup", ADVANCED,
          "When on, “Shut down” saves part of Windows to disk so the next boot is faster.",
          "Off makes every shutdown a full one (can fix driver and update problems) but boots a bit "
          "slower. Needs administrator rights.",
          {(r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HiberbootEnabled"): (REG_DWORD, 1)},
          {(r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HiberbootEnabled"): (REG_DWORD, 0)},
          admin=True),
    CommandTweak("hibernation", "Hibernation", ADVANCED,
                 "Lets the PC hibernate. Windows keeps a file (hiberfil.sys) as large as several GB for it.",
                 "Off frees that disk space, but also turns off Hibernate and Fast Startup. "
                 "Needs administrator rights.",
                 (r"HKLM\SYSTEM\CurrentControlSet\Control\Power", "HibernateEnabled"),
                 ["powercfg", "/hibernate", "on"], ["powercfg", "/hibernate", "off"]),
]

# v1.4.3: more tweaks, grouped by category (see core/tweaks_catalog.py)
from core.tweaks_catalog import CATEGORY_ORDER, EXISTING_CATEGORY, KEYWORDS, more_tweaks  # noqa: E402,F401

for _t in TWEAKS:
    _t.category = EXISTING_CATEGORY.get(_t.id, "Gaming")
TWEAKS += more_tweaks()

BY_ID = {t.id: t for t in TWEAKS}


def changed_tweaks():
    """Tweaks RETWEAKS changed that still have a saved original."""
    backups = load_backups()
    return [BY_ID[i] for i in backups if i in BY_ID]


def undo_everything():
    """Restore every saved original: tweaks, power plan and DNS. Returns [(name, ok, msg)]."""
    from core.optimizer import WindowsOptimizer as W, _load_state
    results = []
    for t in changed_tweaks():
        ok, msg = t.undo()
        results.append((t.name, ok, msg))
    state = _load_state()
    if state.get("previous_power_plan"):
        ok, msg = W.restore_previous_power_plan()
        results.append(("Power plan", ok, msg))
    for adapter in list(state.get("previous_dns", {})):
        ok, msg = W.restore_previous_dns(adapter)
        results.append((f"DNS ({adapter})", ok, msg))
    return results


def create_restore_point():
    """Windows System Restore point. Windows allows one every 24 hours by default and
    needs System Protection turned on, so this checks that one was really created."""
    if not IS_WINDOWS:
        return False, "This only works on Windows."
    script = (
        "$before = @(Get-ComputerRestorePoint -ErrorAction SilentlyContinue).Count; "
        "try { Checkpoint-Computer -Description 'RETWEAKS' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop } "
        "catch { 'ERR:' + $_.Exception.Message; exit }; "
        "$after = @(Get-ComputerRestorePoint -ErrorAction SilentlyContinue).Count; "
        "if ($after -gt $before) { 'OK' } else { 'SKIPPED' }")
    out = run_powershell(script, timeout=180).strip()
    if out.endswith("OK"):
        return True, "Restore point created. You can return to it from Windows System Restore."
    if "SKIPPED" in out:
        return False, ("Windows didn't create a new restore point. It only allows one every 24 hours, "
                       "and System Protection must be on for drive C:.")
    return False, out.replace("ERR:", "").strip() or "Windows couldn't create a restore point (needs administrator rights)."
