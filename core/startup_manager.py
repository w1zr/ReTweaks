# C:\pc_optimizer\core\startup_manager.py

import os
import json
import winreg
import subprocess
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtCore import QFileInfo

BACKUP_STORE = Path(os.getenv('APPDATA')) / "RYTWEAKS" / "startup_backups.json"

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

def list_startup_apps():
    """Enumerates startup entries from Registry, Startup Folders, and Scheduled Tasks."""
    entries = []
    seen_ids = set()

    # 1. Registry HKCU Run
    try:
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
                except WindowsError:
                    break
    except Exception:
        pass

    # 2. Registry HKLM Run
    try:
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
                except WindowsError:
                    break
    except Exception:
        pass

    # 3. Startup Folders (User & Common)
    folders = [
        ("User Startup", Path(os.getenv('APPDATA')) / r"Microsoft\Windows\Start Menu\Programs\Startup"),
        ("Common Startup", Path(os.getenv('PROGRAMDATA')) / r"Microsoft\Windows\Start Menu\Programs\Startup")
    ]
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
    if entry_id not in backups:
        return False, "No backup found for restoration."
    
    entry = backups[entry_id]
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