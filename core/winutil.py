# core/winutil.py
"""Small helpers for talking to Windows safely from a --windowed exe."""

import base64
import json
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


def is_admin():
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False
