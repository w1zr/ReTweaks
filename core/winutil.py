# core/winutil.py
"""Small helpers for talking to Windows safely from a --windowed exe."""

import base64
import os
import sys
import json
import ntpath
import platform
import subprocess

IS_WINDOWS = platform.system() == "Windows"

# Stops a black console window flashing up every time we run powershell/reg/powercfg
# from the windowed .exe.
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0


def run(cmd, timeout=30, check=False, encoding=None):
    """Run a command without a console window. Returns CompletedProcess (text mode).

    reg.exe / powercfg.exe print in the console's OEM code page, so that's the default on
    Windows ("oem" is a Windows-only Python codec). Otherwise accents and Cyrillic in
    localized output would come out garbled.
    """
    if encoding is None:
        encoding = "oem" if IS_WINDOWS else "utf-8"
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding=encoding,
        errors="replace",
        timeout=timeout,
        check=check,
        creationflags=CREATE_NO_WINDOW,
    )


def run_powershell(script, timeout=45):
    """Run a PowerShell script and return its stdout.

    The script is sent with -EncodedCommand, so quotes, $ signs and braces never need
    escaping. Output is forced to UTF-8 so non-English device names survive.
    """
    full = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n" + script
    encoded = base64.b64encode(full.encode("utf-16-le")).decode("ascii")
    result = run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", encoded],
        timeout=timeout,
        encoding="utf-8",  # forced to UTF-8 at the top of the script
    )
    return result.stdout


def run_powershell_json(script, timeout=45):
    """Run a PowerShell script that ends in ConvertTo-Json and parse the result.

    Returns None if PowerShell printed nothing or the output was not valid JSON.
    """
    out = run_powershell(script, timeout=timeout)
    out = (out or "").strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def as_list(value):
    """ConvertTo-Json returns a dict for one item and a list for many. Always give a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def elevated_as_other_user():
    """True if RETWEAKS was started as administrator using a DIFFERENT account's password.
    Then "current user" settings would change that other account, not the person at the PC."""
    if not IS_WINDOWS:
        return False
    try:
        import psutil
        me = psutil.Process().username().lower()
        session_users = set()
        for p in psutil.process_iter(["name", "username"]):
            if (p.info.get("name") or "").lower() == "explorer.exe" and p.info.get("username"):
                session_users.add(p.info["username"].lower())
        return bool(session_users) and me not in session_users
    except Exception:
        return False


def single_instance():
    """Returns a handle if this is the only RETWEAKS running, or None if another one is."""
    if not IS_WINDOWS:
        return True
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)   # reliable GetLastError from ctypes
        handle = k32.CreateMutexW(None, False, "Local\\RETWEAKS_single_instance")
        if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS
            # CreateMutexW still opened the existing mutex: close our handle, otherwise this process
            # itself keeps the mutex alive and a later retry (after the other copy closed) fails.
            if handle:
                k32.CloseHandle(handle)
            return None
        return handle
    except Exception:
        return True


def other_instances():
    """Other running copies of this RETWEAKS .exe (e.g. one stuck while closing), as psutil processes.
    Only works for the built .exe: when running from source every copy is just python.exe, so nothing
    is returned rather than risk closing an unrelated Python program. Our own process and our own
    one-file launcher (the parent RETWEAKS.exe that PyInstaller starts first) are never included."""
    if not IS_WINDOWS or not getattr(sys, "frozen", False):
        return []
    try:
        import psutil
        me = psutil.Process()
        exe_name = ntpath.basename(sys.executable).lower()   # Windows path rules on any OS
        mine = {me.pid}
        try:
            parent = me.parent()
            if parent and (parent.name() or "").lower() == exe_name:
                mine.add(parent.pid)
        except Exception:
            pass
        found = []
        for p in psutil.process_iter(["pid", "name"]):
            if p.info["pid"] not in mine and (p.info["name"] or "").lower() == exe_name:
                found.append(p)
        return found
    except Exception:
        return []


def close_other_instances(timeout=5.0):
    """Force-closes other_instances(). Returns (ok, message) after checking they really exited."""
    procs = other_instances()
    if not procs:
        return False, "No other RETWEAKS process was found."
    try:
        import psutil
        for p in procs:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
        gone, alive = psutil.wait_procs(procs, timeout=timeout)
        if alive:
            return False, (f"{len(alive)} RETWEAKS process(es) could not be closed. Restart the PC, "
                           "or run 'taskkill /F /IM RETWEAKS.exe' in an administrator PowerShell.")
        return True, f"Closed {len(gone)} stuck RETWEAKS process(es)."
    except Exception as e:
        return False, f"Couldn't close the other RETWEAKS: {e}"


def is_admin():
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False
