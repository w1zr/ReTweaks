# core/autostart.py
"""Start RYTWEAKS when you sign in to Windows.

RYTWEAKS.exe always runs as administrator (--uac-admin). A normal "Run" registry entry
would show a UAC prompt at every sign-in, so this uses a Task Scheduler task with
"run with highest privileges" instead, the standard way for admin apps. Only works for
the packaged .exe.
"""

import sys

from core.winutil import IS_WINDOWS, run

TASK_NAME = "RYTWEAKS"


def available():
    return IS_WINDOWS and getattr(sys, "frozen", False)


def is_enabled():
    if not IS_WINDOWS:
        return False
    try:
        return run(["schtasks", "/Query", "/TN", TASK_NAME], timeout=15).returncode == 0
    except Exception:
        return False


def set_enabled(enable, minimized=True):
    if not available():
        return False, "Start with Windows only works in RYTWEAKS.exe."
    if enable:
        target = f'"{sys.executable}"' + (" --minimized" if minimized else "")
        r = run(["schtasks", "/Create", "/TN", TASK_NAME, "/TR", target, "/SC", "ONLOGON",
                 "/RL", "HIGHEST", "/F"], timeout=20)
    else:
        if not is_enabled():
            return True, "RYTWEAKS won't start with Windows."
        r = run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], timeout=20)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip() or "Task Scheduler refused the change."
    return True, "RYTWEAKS will start when you sign in." if enable else "RYTWEAKS won't start with Windows."
