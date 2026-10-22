# C:\pc_optimizer\core\startup_manager.py

import os
import json
import re
import sys
import subprocess
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtCore import QFileInfo

try:                      # winreg only exists on Windows; the module must still import elsewhere (tests)
    import winreg
except ImportError:
    winreg = None

from core.autostart import TASK_NAME as OWN_TASK_NAME

SCHED_SOURCE = "Scheduled task"
BACKUP_STORE = Path(os.getenv('APPDATA') or str(Path.home())) / "RYTWEAKS" / "startup_backups.json"

def _ensure_backup_store():
    BACKUP_STORE.parent.mkdir(parents=True, exist_ok=True)
    if not BACKUP_STORE.exists():
        with open(BACKUP_STORE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def load_backups():
    _ensure_backup_store()
    try:
        with open(BACKUP_STORE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_backup(entry_id, data):
    backups = load_backups()
    backups[entry_id] = data
    with open(BACKUP_STORE, "w", encoding="utf-8") as f:
        json.dump(backups, f, indent=4)

def remove_backup(entry_id):
    backups = load_backups()
    if entry_id in backups:
        del backups[entry_id]
        with open(BACKUP_STORE, "w", encoding="utf-8") as f:
            json.dump(backups, f, indent=4)

def get_publisher(file_path):
    """Attempts to extract file version company name as publisher."""
    try:
        if not file_path or not os.path.exists(file_path):
            return "Unknown"
        # Clean quotes from path
        clean_path = file_path.strip('"').split('.exe')[0] + '.exe'
        if not os.path.exists(clean_path):
            clean_path = file_path.strip('"')
            
        info = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion") # Dummy test or use win32api if available
        # Simple fallback using file properties or standard naming
        import win32api
        ver_info = win32api.GetFileVersionInfo(clean_path, '\\')
        string_FileInfo = win32api.GetFileVersionInfo(clean_path, f'\\StringFileInfo\\{win32api.GetFileVersionInfo(clean_path, "\\VarFileInfo\\Translation")[0][0]:04x}{win32api.GetFileVersionInfo(clean_path, "\\VarFileInfo\\Translation")[0][1]:04x}\\CompanyName')
        return string_FileInfo.strip() if string_FileInfo else "Verified Publisher"
    except Exception:
        return "Local Application"

def extract_icon(file_path):
    """Extracts native system icon using Qt QFileIconProvider."""
    try:
        clean_path = file_path.strip('"').split('.exe')[0] + '.exe'
        if not os.path.exists(clean_path):
            clean_path = file_path.strip('"')
        if os.path.exists(clean_path):
            provider = QFileIconProvider()
            return provider.icon(QFileInfo(clean_path))
    except Exception:
        pass
    return QIcon()

def list_startup_apps(include_windows_tasks=False):
    """Enumerates startup entries from Registry, Startup Folders, and Scheduled Tasks.

    Scheduled tasks under \\Microsoft\\ (Windows' own) are left out unless include_windows_tasks.
    """
    entries = []
    seen_ids = set()

    # 1. Registry HKCU Run
    try:
        if winreg is None:
            raise OSError("not Windows")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    entry_id = f"reg_hkcu_{name}"
                    if entry_id not in seen_ids:
                        seen_ids.add(entry_id)
                        entries.append({
                            "id": entry_id,
                            "name": name,
                            "path": value,
                            "source": "Registry (HKCU)",
                            "scope": "Current User",
                            "status": "Enabled",
                            "publisher": get_publisher(value),
                            "impact": "Medium"
                        })
                    i += 1
                except OSError:
                    break
    except Exception:
        pass

    # 2. Registry HKLM Run
    try:
        if winreg is None:
            raise OSError("not Windows")
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    entry_id = f"reg_hklm_{name}"
                    if entry_id not in seen_ids:
                        seen_ids.add(entry_id)
                        entries.append({
                            "id": entry_id,
                            "name": name,
                            "path": value,
                            "source": "Registry (HKLM)",
                            "scope": "All Users",
                            "status": "Enabled",
                            "publisher": get_publisher(value),
                            "impact": "High"
                        })
                    i += 1
                except OSError:
                    break
    except Exception:
        pass

    # 3. Startup Folders (User & Common)
    folders = []
    if os.getenv('APPDATA'):
        folders.append(("User Startup", Path(os.getenv('APPDATA')) / r"Microsoft\Windows\Start Menu\Programs\Startup"))
    if os.getenv('PROGRAMDATA'):
        folders.append(("Common Startup", Path(os.getenv('PROGRAMDATA')) / r"Microsoft\Windows\Start Menu\Programs\Startup"))
    for source_label, folder_path in folders:
        if folder_path.exists():
            for item in folder_path.iterdir():
                if item.suffix.lower() in ['.lnk', '.url', '.exe', '.bat']:
                    name = item.stem
                    entry_id = f"folder_{source_label}_{name}"
                    if entry_id not in seen_ids:
                        seen_ids.add(entry_id)
                        entries.append({
                            "id": entry_id,
                            "name": name,
                            "path": str(item),
                            "source": f"Startup Folder ({source_label})",
                            "scope": "Current User" if "User" in source_label else "All Users",
                            "status": "Enabled",
                            "publisher": get_publisher(str(item)),
                            "impact": "Low"
                        })

    # 3b. Scheduled tasks that run at sign-in or boot
    for t in list_scheduled_startup_tasks(include_windows_tasks):
        if t["id"] not in seen_ids:
            seen_ids.add(t["id"])
            entries.append(t)

    # 4. Check Disabled Backups in Store
    backups = load_backups()
    for entry_id, bdata in backups.items():
        if not any(e['id'] == entry_id for e in entries):
            bdata['status'] = 'Disabled'
            entries.append(bdata)

    return entries

def disable_startup_entry(entry):
    """Reversibly disables a startup entry by backing it up and removing/disabling it."""
    entry_id = entry['id']
    source = entry['source']
    name = entry['name']
    path = entry['path']

    if source == SCHED_SOURCE:
        return disable_scheduled_task(entry)

    # Backup first
    save_backup(entry_id, entry)

    try:
        if "Registry (HKCU)" in source:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
            return True, "Successfully disabled via HKCU Registry."
        elif "Registry (HKLM)" in source:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
                winreg.DeleteValue(key, name)
            return True, "Successfully disabled via HKLM Registry."
        elif "Startup Folder" in source:
            target_path = Path(path)
            if target_path.exists():
                disabled_path = target_path.with_suffix(target_path.suffix + ".disabled")
                target_path.rename(disabled_path)
                return True, "Successfully disabled via Startup Folder relocation."
    except Exception as e:
        return False, str(e)
    return False, "Unsupported startup source."

def enable_startup_entry(entry_id):
    """Restores a disabled startup entry from backup."""
    backups = load_backups()
    if entry_id not in backups and entry_id.startswith(TASK_ID_PREFIX):
        # a task someone else disabled: the user picked it explicitly, so re-enable it
        return enable_scheduled_task(entry_id)
    if entry_id not in backups:
        return False, "No backup found for restoration."
    
    entry = backups[entry_id]
    if entry.get('source') == SCHED_SOURCE:
        return enable_scheduled_task(entry_id)
    source = entry['source']
    name = entry['name']
    path = entry['path']

    try:
        if "Registry (HKCU)" in source:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, path)
            remove_backup(entry_id)
            return True, "Successfully restored HKCU registry entry."
        elif "Registry (HKLM)" in source:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, path)
            remove_backup(entry_id)
            return True, "Successfully restored HKLM registry entry."
        elif "Startup Folder" in source:
            disabled_path = Path(path + ".disabled")
            original_path = Path(path)
            if disabled_path.exists():
                disabled_path.rename(original_path)
                remove_backup(entry_id)
                return True, "Successfully restored Startup Folder shortcut."
    except Exception as e:
        return False, str(e)
    return False, "Restoration failed."


# ======================================================================================
# Scheduled tasks (v1.4). Tasks are never deleted, only disabled/enabled, and the real
# state is read back after every change.
# ======================================================================================

TASK_ID_PREFIX = "task_"
OWN_TASK_LABEL = "RYTWEAKS (managed in Settings)"
TASK_WARNING = ("Some scheduled tasks are needed by apps (updaters, drivers, backup or security tools). "
                "Disabling one can stop that app from updating or working. You can turn it back on here.")

_LIST_TASKS_PS = r"""
$out = @()
foreach ($t in Get-ScheduledTask -ErrorAction SilentlyContinue) {
  $kinds = @()
  foreach ($tr in $t.Triggers) {
    $c = $tr.CimClass.CimClassName
    if ($c -eq 'MSFT_TaskLogonTrigger') { $kinds += 'Logon' }
    elseif ($c -eq 'MSFT_TaskBootTrigger') { $kinds += 'Boot' }
  }
  if ($kinds.Count -eq 0) { continue }
  $acts = @()
  foreach ($a in $t.Actions) { $acts += [pscustomobject]@{ Execute = $a.Execute; Arguments = $a.Arguments } }
  $out += [pscustomobject]@{
    Name = $t.TaskName; TaskPath = $t.TaskPath; State = $t.State.ToString();
    Author = $t.Author; UserId = $t.Principal.UserId; Triggers = $kinds; Actions = $acts
  }
}
$out | ConvertTo-Json -Depth 5 -Compress
"""

_SYSTEM_USERS = {"system", "nt authority\\system", "s-1-5-18", "local service", "nt authority\\local service",
                 "network service", "nt authority\\network service", "s-1-5-19", "s-1-5-20"}


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def task_entry_id(task_path, name):
    return f"{TASK_ID_PREFIX}{task_path}{name}"


def split_task_id(entry_id):
    """'task_\\Vendor\\Updater' -> ('\\Vendor\\', 'Updater')."""
    full = entry_id[len(TASK_ID_PREFIX):] if entry_id.startswith(TASK_ID_PREFIX) else entry_id
    cut = full.rfind("\\") + 1
    return full[:cut] or "\\", full[cut:]


def parse_scheduled_tasks(data, include_windows_tasks=False):
    """Turn the PowerShell JSON (text, dict or list) into startup-list entries. Pure function."""
    if isinstance(data, (str, bytes)):
        text = data.decode("utf-8", "replace") if isinstance(data, bytes) else data
        text = text.strip().lstrip("\ufeff")
        if not text:
            return []
        try:
            data = json.loads(text)
        except ValueError:
            return []
    entries = []
    for t in _as_list(data):
        if not isinstance(t, dict):
            continue
        name = t.get("Name") or ""
        tpath = t.get("TaskPath") or "\\"
        if not name:
            continue
        kinds = [str(k) for k in _as_list(t.get("Triggers"))]
        if not kinds:
            continue
        if tpath.lower().startswith("\\microsoft\\") and not include_windows_tasks:
            continue
        actions = [a for a in _as_list(t.get("Actions")) if isinstance(a, dict)]
        action_txt = "; ".join(" ".join(x for x in (str(a.get("Execute") or "").strip(),
                                                    str(a.get("Arguments") or "").strip()) if x)
                               for a in actions if a.get("Execute")) or "Unavailable"
        state = str(t.get("State") or "Unknown")
        user = str(t.get("UserId") or "")
        scope = "All Users" if (user.lower() in _SYSTEM_USERS or not user) else "Current User"
        managed = (tpath == "\\" and name == OWN_TASK_NAME)
        entries.append({
            "id": task_entry_id(tpath, name),
            "name": OWN_TASK_LABEL if managed else name,
            "path": action_txt,
            "source": SCHED_SOURCE,
            "scope": scope,
            "status": "Disabled" if state.lower() == "disabled" else "Enabled",
            "publisher": str(t.get("Author") or "") or "Unknown",
            "impact": "Medium",
            "task_name": name,
            "task_path": tpath,
            "task_state": state,
            "triggers": sorted(set(kinds)),
            "run_as": user,
            "managed": managed,
        })
    entries.sort(key=lambda e: e["name"].lower())
    return entries


def list_scheduled_startup_tasks(include_windows_tasks=False):
    """Scheduled tasks that run at logon or boot. Empty list off Windows or if PowerShell fails."""
    if sys.platform != "win32":
        return []
    try:
        from core.winutil import run_powershell
        out = run_powershell(_LIST_TASKS_PS, timeout=60)
        entries = parse_scheduled_tasks(out, include_windows_tasks)
    except Exception:
        return []
    for e in entries:
        if e["publisher"] == "Unknown" and e["path"] != "Unavailable":
            e["publisher"] = get_publisher(e["path"])
    return entries


def _ps_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def get_task_state(task_path, name):
    """Real current state of one task ('Ready', 'Disabled', ...) or None if it can't be read."""
    if sys.platform != "win32":
        return None
    try:
        from core.winutil import run_powershell
        out = run_powershell(
            f"try {{ (Get-ScheduledTask -TaskPath {_ps_quote(task_path)} -TaskName {_ps_quote(name)} "
            "-ErrorAction Stop).State.ToString() } catch { 'ERR: ' + $_.Exception.Message }", timeout=30).strip()
    except Exception:
        return None
    if not out or out.startswith("ERR:"):
        return None
    return out.splitlines()[-1].strip()


def _set_task_enabled(task_path, name, enable):
    """Run Enable/Disable-ScheduledTask, then read the state back. Returns (ok, message)."""
    if sys.platform != "win32":
        return False, "Scheduled tasks can only be changed on Windows."
    from core.winutil import run_powershell
    cmd = "Enable-ScheduledTask" if enable else "Disable-ScheduledTask"
    out = run_powershell(
        f"try {{ {cmd} -TaskPath {_ps_quote(task_path)} -TaskName {_ps_quote(name)} -ErrorAction Stop | Out-Null; 'OK' }} "
        "catch { $_.Exception.Message }", timeout=40).strip()
    state = get_task_state(task_path, name)
    wanted_ok = (state is not None and state.lower() != "disabled") if enable else (state or "").lower() == "disabled"
    if wanted_ok:
        return True, f"Task is now {state}."
    if out and out != "OK":
        return False, out
    return False, f"Windows did not confirm the change (state is {state or 'unavailable'})."


def disable_scheduled_task(entry):
    task_path = entry.get("task_path") or split_task_id(entry["id"])[0]
    name = entry.get("task_name") or split_task_id(entry["id"])[1]
    if entry.get("managed") or (task_path == "\\" and name == OWN_TASK_NAME):
        return False, "This is RYTWEAKS's own start-with-Windows task. Change it in Settings."
    before = get_task_state(task_path, name)
    if before is None:
        return False, "Could not read the task's current state, so nothing was changed."
    if before.lower() == "disabled":
        return False, "The task is already disabled."
    backup = dict(entry)
    backup["original_state"] = before
    save_backup(entry["id"], backup)          # record the previous state first
    ok, msg = _set_task_enabled(task_path, name, False)
    if not ok:
        remove_backup(entry["id"])            # nothing changed, so don't leave a stale backup
    return ok, msg


def enable_scheduled_task(entry_id):
    task_path, name = split_task_id(entry_id)
    if task_path == "\\" and name == OWN_TASK_NAME:
        return False, "This is RYTWEAKS's own start-with-Windows task. Change it in Settings."
    ok, msg = _set_task_enabled(task_path, name, True)
    if ok:
        remove_backup(entry_id)
    return ok, msg
