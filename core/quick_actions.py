# core/quick_actions.py
"""One-click maintenance actions (v1.4.3, Essentials). Each returns (ok, message) with the real result.

Nothing is deleted without a preview: the Windows Update cache size is shown first and the user
confirms in the UI.
"""

import os
from pathlib import Path

from core.winutil import IS_WINDOWS, run


def flush_dns():
    """Clears Windows' DNS cache (ipconfig /flushdns). Harmless; sites are looked up again."""
    if not IS_WINDOWS:
        return False, "Only available on Windows."
    r = run(["ipconfig", "/flushdns"], timeout=30)
    if r.returncode == 0:
        return True, "DNS cache cleared."
    return False, (r.stdout or r.stderr or "ipconfig failed.").strip()


def _wu_download_dir():
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "SoftwareDistribution" / "Download"


def wu_cache_preview():
    """(ok, bytes, file_count, message) for the Windows Update download cache."""
    folder = _wu_download_dir()
    if not folder.exists():
        return True, 0, 0, "The Windows Update download folder doesn't exist (nothing to clear)."
    total = count = 0
    for root, _dirs, files in os.walk(folder):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                count += 1
            except OSError:
                pass
    return True, total, count, f"{count} files, {total / 1024 ** 2:.1f} MB in {folder}"


def clear_wu_cache():
    """Stops Windows Update and BITS, empties SoftwareDistribution\\Download, starts them again.
    Windows re-downloads whatever it still needs. Needs administrator rights."""
    if not IS_WINDOWS:
        return False, "Only available on Windows."
    folder = _wu_download_dir()
    stopped = []
    for svc in ("wuauserv", "bits"):
        r = run(["net", "stop", svc], timeout=60)
        if r.returncode == 0:
            stopped.append(svc)
    removed = failed = freed = 0
    try:
        for root, dirs, files in os.walk(folder, topdown=False):
            for f in files:
                p = os.path.join(root, f)
                try:
                    size = os.path.getsize(p)
                    os.remove(p)
                    removed += 1
                    freed += size
                except OSError:
                    failed += 1
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass
    finally:
        for svc in stopped:
            run(["net", "start", svc], timeout=60)
    msg = f"Removed {removed} files ({freed / 1024 ** 2:.1f} MB)."
    if failed:
        msg += f" {failed} files were in use and were skipped."
    return True, msg


def sfc_scan():
    """System File Checker: checks protected Windows files and repairs damaged ones.
    Takes 5-20 minutes. Needs administrator rights."""
    if not IS_WINDOWS:
        return False, "Only available on Windows."
    r = run(["sfc", "/scannow"], timeout=3600)
    # sfc prints UTF-16 text with odd spacing; normalize it before reading
    text = (r.stdout or "").replace("\x00", "")
    low = " ".join(text.lower().split())
    if "did not find any integrity violations" in low:
        return True, "No problems found. Your Windows system files are OK."
    if "successfully repaired" in low:
        return True, "Windows found damaged files and repaired them. Restart your PC."
    if "found corrupt files but was unable to fix" in low:
        return False, ("Windows found damaged files it couldn't repair. Run "
                       "“DISM /Online /Cleanup-Image /RestoreHealth” in an admin terminal, then run this again.")
    if "must be an administrator" in low:
        return False, "Needs administrator rights."
    if r.returncode == 0:
        return True, "Scan finished."
    return False, (text.strip()[-300:] or "The scan didn't finish.")
