# C:\pc_optimizer\core\storage_manager.py

import heapq
import os
import re
import shutil
import sys
import threading
import time
import psutil
from pathlib import Path

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
        
        # Qt is imported here, not at module level, so the Tk app can use this module without PySide6
        from PySide6.QtWidgets import QFileIconProvider
        from PySide6.QtCore import QFileInfo
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


# ======================================================================================
# v1.4: Storage Explorer + disk space analyzer helpers.
# Everything below is plain Python (no Qt, no Windows-only imports) so it can be tested
# anywhere. Nothing here deletes or modifies files.
# ======================================================================================

_WIN = sys.platform == "win32"
_ATTR_HIDDEN = 0x2
_ATTR_SYSTEM = 0x4
_ATTR_REPARSE = 0x400   # symlinks, junctions, OneDrive placeholders and other reparse points


def human_size(n):
    """Bytes -> '12.3 MB'. None -> 'Unavailable'."""
    if n is None:
        return "Unavailable"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def format_mtime(ts):
    if not ts:
        return ""
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except (OverflowError, OSError, ValueError):
        return ""


def long_path(path, windows=None):
    """Add the extended-length (backslash-backslash-question) prefix on Windows so paths over 260 characters work. No-op elsewhere."""
    win = _WIN if windows is None else windows
    if not win or not path:
        return path
    if path.startswith("\\\\?\\"):
        return path
    p = path.replace("/", "\\")
    if p.startswith("\\\\"):                      # UNC share
        return "\\\\?\\UNC\\" + p[2:]
    if re.match(r"^[A-Za-z]:", p):
        if len(p) == 2:
            p += "\\"
        return "\\\\?\\" + p
    return path                                   # relative path: leave as is


def split_breadcrumbs(path):
    """Split a path into clickable segments: [(label, full_path), ...].

    'C:\\Users\\me' -> [('C:\\', 'C:\\'), ('Users', 'C:\\Users'), ('me', 'C:\\Users\\me')]
    UNC shares and POSIX paths work too. Pure string logic.
    """
    if not path:
        return []
    p = path.strip()
    windows_style = bool(re.match(r"^[A-Za-z]:", p)) or p.startswith("\\\\") or ("\\" in p and "/" not in p)
    if windows_style:
        sep = "\\"
        p = p.replace("/", "\\")
        crumbs = []
        if p.startswith("\\\\"):
            parts = [x for x in p[2:].split("\\") if x]
            if len(parts) < 2:
                return [(p, p)] if parts else []
            root = "\\\\" + parts[0] + "\\" + parts[1]
            crumbs.append((root, root))
            rest = parts[2:]
            cur = root
        else:
            m = re.match(r"^([A-Za-z]:)(.*)$", p)
            if m:
                root = m.group(1) + "\\"
                crumbs.append((root, root))
                rest = [x for x in m.group(2).split("\\") if x]
                cur = m.group(1)
            else:
                rest = [x for x in p.split("\\") if x]
                cur = ""
        for part in rest:
            cur = cur + sep + part if cur and not cur.endswith(sep) else cur + part
            crumbs.append((part, cur))
        return crumbs
    parts = [x for x in p.split("/") if x]
    crumbs = [("/", "/")]
    cur = ""
    for part in parts:
        cur += "/" + part
        crumbs.append((part, cur))
    return crumbs


def _attrs(st):
    return getattr(st, "st_file_attributes", 0) or 0


def is_reparse_entry(entry, st=None):
    """True for symlinks, junctions and other reparse points (never followed)."""
    try:
        if entry.is_symlink():
            return True
        if st is None:
            st = entry.stat(follow_symlinks=False)
        return bool(_attrs(st) & _ATTR_REPARSE)
    except OSError:
        return False


def is_hidden_entry(name, st=None):
    if st is not None and _attrs(st) & (_ATTR_HIDDEN | _ATTR_SYSTEM):
        return True
    return name.startswith(".")


def list_directory(path, show_hidden=True):
    """List one folder for the explorer. Raises PermissionError/OSError if it can't be read.

    Items: name, path, is_dir, is_link, hidden, size (bytes; None for folders), mtime, type.
    """
    items = []
    with os.scandir(long_path(path)) as it:
        for e in it:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                st = None
            link = is_reparse_entry(e, st)
            hidden = is_hidden_entry(e.name, st)
            if hidden and not show_hidden:
                continue
            try:
                is_dir = e.is_dir(follow_symlinks=False) or (link and e.is_dir())
            except OSError:
                is_dir = False
            ext = os.path.splitext(e.name)[1]
            items.append({
                "name": e.name,
                "path": os.path.join(path, e.name),
                "is_dir": is_dir,
                "is_link": link,
                "hidden": hidden,
                "size": None if is_dir or st is None else st.st_size,
                "mtime": st.st_mtime if st else 0,
                "type": "Folder" if is_dir else (ext.upper().lstrip(".") + " File" if ext else "File"),
            })
    return items


def sort_items(items, key="name", descending=False):
    """Sort explorer items. Folders stay above files, except when sorting by size."""
    def k(i):
        if key == "size":
            return (i.get("size") or 0, i["name"].lower())
        if key == "modified":
            return (i.get("mtime") or 0, i["name"].lower())
        if key == "type":
            return (i.get("type", "").lower(), i["name"].lower())
        return i["name"].lower()
    if key == "size":
        return sorted(items, key=k, reverse=descending)
    dirs = sorted((i for i in items if i["is_dir"]), key=k, reverse=descending)
    files = sorted((i for i in items if not i["is_dir"]), key=k, reverse=descending)
    return dirs + files


class ScanState:
    """Progress shared between a scan thread (writes) and the UI timer (reads)."""

    def __init__(self):
        self.items = 0
        self.bytes = 0
        self.current = ""
        self.skipped = 0
        self.skipped_paths = []
        self.link_count = 0
        self.links = []
        self.done = False
        self.cancelled = False
        self.error = ""
        self.result = None


def scan_tree(root, stop, state=None, track_depth=3, top_files=50, top_folders=25):
    """Size a folder tree without recursion. Never follows symlinks/junctions (counted as 0).

    Folders that can't be read are counted in 'skipped'. Returns a dict:
      total, files, folders, skipped, link_count, links, cancelled,
      children (top-level entries with sizes, largest first),
      top_folders ([(path, bytes)] cumulative, depth 2..track_depth, largest first),
      top_files ([(bytes, path)] largest first).
    track_depth=0 gives just the totals (used for folder sizes in the explorer).
    """
    state = state or ScanState()
    sizes = {}                 # cumulative bytes of folders down to track_depth
    tdepth = {}                # folder -> depth below root (1..track_depth)
    child_links = set()
    child_files = {}
    files_heap = []
    total = files = folders = 0
    stack = [(root, 0, ())]
    root_error = ""
    counter = 0
    while stack:
        if stop.is_set():
            break
        path, depth, anc = stack.pop()
        state.current = path
        try:
            it = os.scandir(long_path(path))
        except OSError as e:
            if depth == 0:
                root_error = e.strerror or str(e)
            state.skipped += 1
            if len(state.skipped_paths) < 200:
                state.skipped_paths.append(path)
            continue
        try:
            with it:
                for e in it:
                    counter += 1
                    state.items = counter
                    if counter % 500 == 0 and stop.is_set():
                        break
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        st = None
                    if is_reparse_entry(e, st):
                        state.link_count += 1
                        if len(state.links) < 200:
                            state.links.append(os.path.join(path, e.name))
                        if depth == 0:
                            child_links.add(e.name)
                        continue
                    try:
                        is_dir = e.is_dir(follow_symlinks=False)
                    except OSError:
                        continue
                    if is_dir:
                        folders += 1
                        child = os.path.join(path, e.name)
                        if len(anc) < track_depth:
                            new_anc = anc + (child,)
                            sizes[child] = 0
                            tdepth[child] = len(new_anc)
                        else:
                            new_anc = anc
                        stack.append((child, depth + 1, new_anc))
                    elif st is not None:
                        sz = st.st_size
                        files += 1
                        total += sz
                        state.bytes = total
                        for a in anc:
                            sizes[a] = sizes.get(a, 0) + sz
                        if depth == 0:
                            child_files[e.name] = sz
                        if top_files:
                            item = (sz, os.path.join(path, e.name))
                            if len(files_heap) < top_files:
                                heapq.heappush(files_heap, item)
                            elif sz > files_heap[0][0]:
                                heapq.heapreplace(files_heap, item)
        except OSError:
            state.skipped += 1
            if len(state.skipped_paths) < 200:
                state.skipped_paths.append(path)
    children = []
    if track_depth >= 1:
        for p, sz in sizes.items():
            if tdepth.get(p) == 1:
                children.append({"name": os.path.basename(p), "path": p, "size": sz, "is_dir": True, "is_link": False})
        for n, sz in child_files.items():
            children.append({"name": n, "path": os.path.join(root, n), "size": sz, "is_dir": False, "is_link": False})
        for n in child_links:
            children.append({"name": n, "path": os.path.join(root, n), "size": 0, "is_dir": False, "is_link": True})
        children.sort(key=lambda c: c["size"], reverse=True)
    deep = sorted(((p, sz) for p, sz in sizes.items() if tdepth.get(p, 0) >= 2),
                  key=lambda x: x[1], reverse=True)[:top_folders]
    state.cancelled = stop.is_set()
    return {
        "root": root, "total": total, "files": files, "folders": folders, "skipped": state.skipped,
        "skipped_paths": list(state.skipped_paths), "link_count": state.link_count, "links": list(state.links),
        "cancelled": state.cancelled, "error": root_error, "children": children, "top_folders": deep,
        "top_files": sorted(files_heap, reverse=True),
    }


def search_files(root, query, recursive, stop, state, show_hidden=True, limit=1000):
    """Find entries whose name contains `query` (case-insensitive). Appends to state.results.

    state needs: results (list), items (int), current (str), done flag handled by the caller.
    Symlinks/junctions are listed but not entered.
    """
    q = query.lower()
    stack = [root]
    while stack and not stop.is_set():
        path = stack.pop()
        state.current = path
        try:
            it = os.scandir(long_path(path))
        except OSError:
            continue
        with it:
            for e in it:
                state.items += 1
                if state.items % 500 == 0 and stop.is_set():
                    return
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    st = None
                hidden = is_hidden_entry(e.name, st)
                if hidden and not show_hidden:
                    continue
                link = is_reparse_entry(e, st)
                try:
                    is_dir = e.is_dir(follow_symlinks=False)
                except OSError:
                    is_dir = False
                if q in e.name.lower():
                    state.results.append({
                        "name": e.name, "path": os.path.join(path, e.name), "is_dir": is_dir, "is_link": link,
                        "hidden": hidden, "size": None if is_dir or st is None else st.st_size,
                        "mtime": st.st_mtime if st else 0,
                        "type": "Folder" if is_dir else (os.path.splitext(e.name)[1].upper().lstrip(".") + " File"
                                                         if os.path.splitext(e.name)[1] else "File"),
                    })
                    if len(state.results) >= limit:
                        return
                if recursive and is_dir and not link:
                    stack.append(os.path.join(path, e.name))


class BackgroundJob:
    """Runs fn(stop_event) on a daemon thread. cancel() sets the flag; join() waits for it."""

    def __init__(self, fn):
        self.stop = threading.Event()
        self.done = False
        self.error = ""
        self._fn = fn
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            self._fn(self.stop)
        except Exception as e:   # surfaced to the UI instead of dying silently
            self.error = str(e)
        finally:
            self.done = True

    def start(self):
        self._thread.start()
        return self

    def cancel(self):
        self.stop.set()

    def join(self, timeout=5):
        if self._thread.is_alive():
            self._thread.join(timeout)
