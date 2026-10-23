# core/rename_migration.py
"""One-time moves of data from earlier versions of the app (its previous name, v1.6, and the base app it was
combined with, v2.0; owner decisions 2026-10-22).

Runs at every start and is repeat-safe: each step only acts when the old item exists and the new
one doesn't yet, and nothing old is deleted except the old Start-with-Windows task after its
replacement was created. Old data folders are copied (not moved), so they stay as a backup.

  %APPDATA%\\<OLD>        -> %APPDATA%\\RETWEAKS        (settings, tweak undo data, game backups,
                                                     bookmarks/history, program rules, ...)
  %LOCALAPPDATA%\\<OLD>   -> %LOCALAPPDATA%\\RETWEAKS   (browser cookies/cache, start page)
  Credential <OLD>/GeminiAPIKey -> RETWEAKS/GeminiAPIKey (the AI Assistant key)
  Scheduled task "<OLD>"  -> "RETWEAKS"              (Start with Windows, pointing at this .exe)
  %APPDATA%\\<BASE_APP>, %LOCALAPPDATA%\\<BASE_APP> -> the RETWEAKS folders (missing files only)
"""

import os
import shutil
import sys
from pathlib import Path

from core.winutil import IS_WINDOWS

OLD = "RY" + "TWEAKS"                         # the app's previous name (folders, credential, task)
NEW = "RETWEAKS"
OLD_EXE = OLD.lower() + ".exe"                 # lower case, for process-name checks
OLD_SHOW_SERVER_PREFIX = OLD + "_show_"        # v1.5.1's local socket (answers "quit")
MARKER = "migrated_from_" + OLD + ".txt"


def _bases():
    out = []
    for var in ("APPDATA", "LOCALAPPDATA"):
        base = os.getenv(var)
        if base:
            out.append(Path(base))
    return out


def _write_marker(old, new):
    (new / MARKER).write_text(
        f"Copied from {old} when the app was renamed to RETWEAKS. The old folder was kept "
        "as a backup and can be deleted once everything works.\n", encoding="utf-8")


def _copy_missing(src, dst):
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for f in files:
            target = dst / rel / f
            if not target.exists():
                shutil.copy2(Path(root) / f, target)


def migrate_folders(bases=None):
    """Copies each old data folder to the new name if the new one doesn't exist yet.
    Returns a list of (old, new, ok, message)."""
    results = []
    for base in bases if bases is not None else _bases():
        old, new = base / OLD, base / NEW
        if not old.is_dir() or (new / MARKER).exists():
            continue
        if new.exists():
            # The new folder already exists (e.g. created by the new version before the move ran):
            # copy only what's missing, never overwriting anything newer.
            try:
                _copy_missing(old, new)
                _write_marker(old, new)
                results.append((str(old), str(new), True, "merged"))
            except Exception as e:
                results.append((str(old), str(new), False, f"{type(e).__name__}: {e}"))
            continue
        tmp = base / (NEW + ".migrating")
        try:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)     # a copy interrupted last time
            shutil.copytree(old, tmp, symlinks=True)
            os.replace(tmp, new)                           # appears all at once, never half-copied
            _write_marker(old, new)
            results.append((str(old), str(new), True, "copied"))
        except Exception as e:
            shutil.rmtree(tmp, ignore_errors=True)
            results.append((str(old), str(new), False, f"{type(e).__name__}: {e}"))
    return results


BASE_APP = "Perf" + "Hub"                      # data folder name of the base app RETWEAKS v2.0 was combined with
BASE_MARKER = "migrated_from_" + BASE_APP + ".txt"
# Base-app file names that collide with RETWEAKS' own files get a new name when copied over.
BASE_RENAMES = {"custom_presets.json": "tweak_custom_presets.json"}


def migrate_base_app(bases=None):
    """v2.0 (owner decision 2026-10-22): copies the base app's data (appearance, history, benchmarks,
    driver links, first-run choice, custom tweak presets; embedded-site browser profiles) into the RETWEAKS
    folders. Only copies files RETWEAKS doesn't have yet; the old folders are kept. One time per folder."""
    results = []
    for base in bases if bases is not None else _bases():
        old, new = base / BASE_APP, base / NEW
        if not old.is_dir() or (new / BASE_MARKER).exists():
            continue
        try:
            new.mkdir(parents=True, exist_ok=True)
            for root, dirs, files in os.walk(old):
                rel = Path(root).relative_to(old)
                (new / rel).mkdir(parents=True, exist_ok=True)
                for f in files:
                    name = BASE_RENAMES.get(f, f) if rel == Path(".") else f
                    target = new / rel / name
                    if not target.exists():
                        shutil.copy2(Path(root) / f, target)
            (new / BASE_MARKER).write_text(
                f"Copied from {old} by RETWEAKS v2.0. The old folder was kept as a backup and can be deleted "
                "once everything works.\n", encoding="utf-8")
            results.append((str(old), str(new), True, "copied"))
        except Exception as e:
            results.append((str(old), str(new), False, f"{type(e).__name__}: {e}"))
    return results


def migrate_credential(read=None, write=None):
    """Copies the saved Gemini key to the new credential name. Returns True if it copied one."""
    if read is None or write is None:
        if not IS_WINDOWS:
            return False
        from core import ai_assistant as ai
        if ai._advapi is None:
            return False
        read = read or ai._cred_read
        write = write or (lambda target, blob: ai._cred_write(target, blob, "RETWEAKS AI Assistant (Gemini API key)"))
    try:
        if read(f"{NEW}/GeminiAPIKey") is not None:
            return False
        blob = read(f"{OLD}/GeminiAPIKey")
        if not blob:
            return False
        write(f"{NEW}/GeminiAPIKey", blob)
        return read(f"{NEW}/GeminiAPIKey") == blob
    except Exception:
        return False


def migrate_autostart(run=None, set_enabled=None):
    """If the old-name sign-in task exists: create the new one for this .exe (keeping the
    "start minimized" choice), and only then delete the old one. Returns (ok, message) or None."""
    from core import autostart
    if not autostart.available():
        return None
    if run is None:
        from core.winutil import run as run
    set_enabled = set_enabled or autostart.set_enabled
    try:
        q = run(["schtasks", "/Query", "/TN", OLD, "/XML"], timeout=15)
    except Exception:
        return None
    if q.returncode != 0:
        return None                                     # no old task: nothing to do
    minimized = "--minimized" in (q.stdout or "")
    ok, msg = set_enabled(True, minimized=minimized)
    if not ok:
        return False, f"Couldn't move Start with Windows to RETWEAKS: {msg}"
    run(["schtasks", "/Delete", "/TN", OLD, "/F"], timeout=20)
    return True, "Start with Windows now opens RETWEAKS."


def legacy_processes():
    """Running copies of the app under its previous name. Only checked in the packaged .exe."""
    if not IS_WINDOWS or not getattr(sys, "frozen", False):
        return []
    try:
        import psutil
        return [p for p in psutil.process_iter(["pid", "name"]) if (p.info["name"] or "").lower() == OLD_EXE]
    except Exception:
        return []


def migrate_all():
    """Data folders, the AI key and the sign-in task. Never raises; returns a short log."""
    log = []
    for old, new, ok, msg in migrate_folders() + migrate_base_app():
        log.append(f"Copied your data from an earlier version into {new}" if ok
                   else f"Could not copy data from an earlier version into {new} ({msg})")
    try:
        if migrate_credential():
            log.append("Moved the AI Assistant key to RETWEAKS/GeminiAPIKey")
    except Exception:
        pass
    try:
        r = migrate_autostart()
        if r:
            log.append(r[1])
    except Exception:
        pass
    return log
