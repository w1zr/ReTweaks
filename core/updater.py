# core/updater.py
"""Update check and in-app updates.

- check_for_update(): asks GitHub for the latest release of w1zr/ReTweaks (read-only).
- download_update(): downloads RETWEAKS.exe and its .sha256 file from THAT release only,
  and refuses the file unless its SHA-256 matches. The .sha256 file is created by the
  GitHub Actions build (.github/workflows/build.yml), so a damaged or swapped download
  is never installed.
- install_and_restart(): only for the packaged .exe. A small script waits for RETWEAKS to
  close, keeps the old exe as RETWEAKS.old.exe (so it can be restored), puts the new one
  in place and starts it (if the swap fails, the old exe is put back). User settings in %APPDATA%\\RETWEAKS are not touched.
- install_release_copy() (v2.0.6): when RETWEAKS runs from source (python retweaks.py), updates still come from
  the GitHub release: the verified RETWEAKS.exe goes to %LOCALAPPDATA%\\RETWEAKS\\app and starts after this copy
  closes. The source folder (the user's own files) is never changed and git is never used.
- install_update(): picks install_and_restart (packaged) or install_release_copy (source).

Nothing is downloaded or installed without the user clicking a button.
"""

import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.request

from core.version import __version__
from core.winutil import CREATE_NO_WINDOW, IS_WINDOWS

REPO = "w1zr/ReTweaks"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
EXE_NAME = "RETWEAKS.exe"
# Downloads are only accepted from these hosts (GitHub release assets)
ALLOWED_HOSTS = ("https://github.com/", "https://objects.githubusercontent.com/",
                 "https://release-assets.githubusercontent.com/", "https://api.github.com/")


def parse_version(text):
    """'v1.3' / '1.3.0' -> (1, 3, 0). Returns None if it doesn't look like a version."""
    m = re.match(r"^v?(\d+(?:\.\d+)*)$", (text or "").strip())
    if not m:
        return None
    parts = [int(p) for p in m.group(1).split(".")]
    return tuple(parts + [0] * (3 - len(parts)))[:3]


def is_newer(remote, local=__version__):
    r, l = parse_version(remote), parse_version(local)
    return bool(r and l and r > l)


def _get(url, timeout=15, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": f"RETWEAKS/{__version__}", "Accept": accept})
    return urllib.request.urlopen(req, timeout=timeout)


def check_for_update():
    """Returns a dict: {"available": bool, "version", "notes", "exe_url", "sha_url", "page"}
    or {"error": "..."} if GitHub couldn't be reached."""
    try:
        with _get(LATEST_URL) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": f"Couldn't reach GitHub: {e}"}
    tag = data.get("tag_name", "")
    assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
    return {
        "available": is_newer(tag),
        "version": tag,
        "notes": data.get("body") or "",
        "page": data.get("html_url"),
        "exe_url": assets.get(EXE_NAME),
        "sha_url": assets.get(EXE_NAME + ".sha256"),
    }


def _allowed(url):
    return bool(url) and url.startswith(ALLOWED_HOSTS)


def parse_sha256_file(text):
    """Accepts 'HASH', 'HASH  RETWEAKS.exe' or PowerShell-style output; returns lowercase hex."""
    m = re.search(r"\b([0-9a-fA-F]{64})\b", text or "")
    return m.group(1).lower() if m else None


def download_update(info, progress=None):
    """Download and verify. Returns (ok, path_or_error_message)."""
    exe_url, sha_url = info.get("exe_url"), info.get("sha_url")
    if not exe_url or not sha_url:
        return False, ("This release has no verified download (missing RETWEAKS.exe or its .sha256 file). "
                       "Download it from the release page instead.")
    if not (_allowed(exe_url) and _allowed(sha_url)):
        return False, "Refusing to download from an unexpected address."
    try:
        with _get(sha_url, accept="application/octet-stream") as resp:
            expected = parse_sha256_file(resp.read().decode("utf-8", "replace"))
        if not expected:
            return False, "The release's checksum file is not readable."
        dest = os.path.join(tempfile.gettempdir(), f"RETWEAKS_update_{info.get('version', 'new')}.exe")
        digest = hashlib.sha256()
        with _get(exe_url, timeout=60, accept="application/octet-stream") as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress and total:
                    progress(int(done * 100 / total))
        if digest.hexdigest() != expected:
            os.remove(dest)
            return False, "The download didn't match the release's SHA-256 checksum, so it was deleted."
        return True, dest
    except Exception as e:
        return False, f"Download failed: {e}"


def UPDATE_STATUS_FILE():
    from pathlib import Path
    base = Path(os.getenv("APPDATA") or Path.home()) / "RETWEAKS"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "update_status.txt")


def read_update_status():
    """'OK', 'FAILED' or None. Reads and clears the result the update script left behind."""
    path = UPDATE_STATUS_FILE()
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            value = f.read().strip()
        os.remove(path)
        return value or None
    except OSError:
        return None


def can_self_update():
    """True only when running as the packaged RETWEAKS.exe (not from python main.py)."""
    return IS_WINDOWS and getattr(sys, "frozen", False)


def can_download_release():
    """True on Windows: the GitHub release RETWEAKS.exe can be downloaded and started, packaged or from source."""
    return IS_WINDOWS


def release_install_dir():
    """Where a from-source run keeps the released RETWEAKS.exe (never inside the source folder)."""
    base = os.getenv("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "RETWEAKS", "app")


def install_release_copy(new_exe):
    """From-source run: move the verified release exe to release_install_dir()\\RETWEAKS.exe (the previous one is
    kept as RETWEAKS.old.exe there) and start it once this process has exited. Returns (ok, message);
    the caller must then quit the app."""
    if not IS_WINDOWS:
        return False, "Updates can only be installed on Windows."
    folder = release_install_dir()
    target = os.path.join(folder, EXE_NAME)
    backup = os.path.join(folder, "RETWEAKS.old.exe")
    try:
        os.makedirs(folder, exist_ok=True)
        if os.path.exists(target):
            if os.path.exists(backup):
                os.remove(backup)
            os.replace(target, backup)
        import shutil
        shutil.move(new_exe, target)
    except OSError as e:
        return False, f"Couldn't save the update in {folder}: {e}"

    def q(path):
        return "'" + path.replace("'", "''") + "'"
    ps = (f"Wait-Process -Id {os.getpid()} -Timeout 90 -ErrorAction SilentlyContinue; "
          f"Start-Process -FilePath {q(target)}")
    try:
        import base64
        import subprocess
        encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
        env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-EncodedCommand", encoded],
                         creationflags=CREATE_NO_WINDOW, close_fds=True, env=env)
        return True, f"Starting the new RETWEAKS.exe from {folder}."
    except Exception as e:
        return False, f"Couldn't start the new RETWEAKS.exe: {e}"


def install_update(new_exe):
    """Install a verified download: swap the running exe, or (from source) start the released exe."""
    if can_self_update():
        return install_and_restart(new_exe)
    return install_release_copy(new_exe)


def install_and_restart(new_exe):
    """Start the swap script; the caller must then quit the app. Returns (ok, message)."""
    if not can_self_update():
        return False, "Replacing the running exe only works in RETWEAKS.exe."
    current = sys.executable
    backup = os.path.join(os.path.dirname(current), "RETWEAKS.old.exe")

    def q(path):  # PowerShell single-quoted string (handles ' and non-English characters)
        return "'" + path.replace("'", "''") + "'"

    # A --onefile exe runs as TWO processes: the bootloader (parent) and Python (this one).
    # The parent keeps RETWEAKS.exe open until it has cleaned up its temp folder, so wait
    # for both. Then rename the old exe to RETWEAKS.old.exe (retrying while Windows still has
    # it locked), move the new one in, and start it. If anything fails, put the old exe back
    # and write a note that RETWEAKS shows on its next start, so it never claims success falsely.
    status = os.path.join(os.path.dirname(UPDATE_STATUS_FILE()), "update_status.txt")
    ps = (
        f"Wait-Process -Id {os.getpid()},{os.getppid()} -Timeout 90 -ErrorAction SilentlyContinue; "
        f"$ok = $false; "
        f"for ($i = 0; $i -lt 40 -and -not $ok; $i++) {{ "
        f"  try {{ "
        f"    if (Test-Path -LiteralPath {q(backup)}) {{ Remove-Item -LiteralPath {q(backup)} -Force -ErrorAction Stop }}; "
        f"    Rename-Item -LiteralPath {q(current)} -NewName 'RETWEAKS.old.exe' -ErrorAction Stop; "
        f"    try {{ Move-Item -LiteralPath {q(new_exe)} -Destination {q(current)} -Force -ErrorAction Stop; $ok = $true }} "
        f"    catch {{ Rename-Item -LiteralPath {q(backup)} -NewName {q(os.path.basename(current))}; throw }} "
        f"  }} catch {{ Start-Sleep -Milliseconds 500 }} "
        f"}}; "
        f"if ($ok) {{ Set-Content -LiteralPath {q(status)} -Value 'OK' }} "
        f"else {{ Set-Content -LiteralPath {q(status)} -Value 'FAILED' }}; "
        f"Start-Process -FilePath {q(current)}"
    )
    try:
        import base64
        import subprocess
        encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
        # PYINSTALLER_RESET_ENVIRONMENT: the restarted exe must unpack fresh instead of
        # reusing this run's temp folder, which is being deleted (PyInstaller 6.9+).
        env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-EncodedCommand", encoded],
                         creationflags=CREATE_NO_WINDOW, close_fds=True, env=env)
        return True, "Installing the update. RETWEAKS will restart in a few seconds."
    except Exception as e:
        return False, f"Couldn't start the installer: {e}"
