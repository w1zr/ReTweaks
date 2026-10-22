# C:\pc_optimizer\core\storage_manager.py

import os
import shutil
import psutil
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtCore import QFileInfo

def get_disk_drives():
    """Detects and returns metadata for all available storage drives."""
    drives = []
    try:
        partitions = psutil.disk_partitions(all=False)
        for p in partitions:
            try:
                usage = psutil.disk_usage(p.mountpoint)
                total_gb = usage.total / (1024**3)
                used_gb = usage.used / (1024**3)
                free_gb = usage.free / (1024**3)
                percent = usage.percent
                
                drives.append({
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "opts": p.opts,
                    "total": f"{total_gb:.2f} GB",
                    "used": f"{used_gb:.2f} GB",
                    "free": f"{free_gb:.2f} GB",
                    "percent": percent,
                    "model": f"Local Disk ({p.device})"
                })
            except PermissionError:
                continue
    except Exception as e:
        print(f"Error scanning drives: {e}")
    return drives

def browse_directory(path_str):
    """Enumerates files and folders in a given directory path safely."""
    path = Path(path_str)
    items = []
    try:
        if not path.exists() or not path.is_dir():
            return items
        
        provider = QFileIconProvider()
        for entry in path.iterdir():
            try:
                is_dir = entry.is_dir()
                stat = entry.stat()
                size_str = "-" if is_dir else f"{stat.st_size / 1024:.1f} KB"
                if not is_dir and stat.st_size > 1024*1024:
                    size_str = f"{stat.st_size / (1024**2):.1f} MB"
                
                items.append({
                    "name": entry.name,
                    "path": str(entry.resolve()),
                    "is_dir": is_dir,
                    "size": size_str,
                    "type": "Folder" if is_dir else entry.suffix.upper() + " File",
                    "icon": provider.icon(QFileInfo(str(entry)))
                })
            except Exception:
                continue
    except Exception as e:
        print(f"Error browsing directory: {e}")
    return items

def _temp_dirs():
    dirs = [Path(os.getenv('TEMP', r"C:\Windows\Temp")), Path(r"C:\Windows\Temp")]
    seen, out = set(), []
    for d in dirs:
        key = str(d).lower()
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def preview_temp_files():
    """Count what cleanup would delete, without deleting anything. Returns (items, bytes)."""
    items, total = 0, 0
    for d in _temp_dirs():
        if not d.is_dir():
            continue
        for item in d.glob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
                elif item.is_dir():
                    total += sum(f.stat().st_size for f in item.glob('**/*') if f.is_file())
                items += 1
            except Exception:
                continue
    return items, total


def cleanup_temp_files_safe():
    """Performs safe temporary files cleanup."""
    temp_dirs = _temp_dirs()
    freed_bytes = 0
    files_cleaned = 0

    for d in temp_dirs:
        if d.exists() and d.is_dir():
            for item in d.glob("*"):
                try:
                    if item.is_file():
                        size = item.stat().st_size
                        item.unlink()
                        freed_bytes += size
                        files_cleaned += 1
                    elif item.is_dir():
                        size = sum(f.stat().st_size for f in item.glob('**/*') if f.is_file())
                        shutil.rmtree(item, ignore_errors=True)
                        freed_bytes += size
                        files_cleaned += 1
                except Exception:
                    continue
                    
    return f"Cleaned {files_cleaned} items. Freed {freed_bytes / (1024**2):.2f} MB of space."