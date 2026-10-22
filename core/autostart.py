# core/autostart.py
"""Start RETWEAKS when you sign in to Windows.

RETWEAKS.exe always runs as administrator (--uac-admin). A normal "Run" registry entry
would show a UAC prompt at every sign-in, so this uses a Task Scheduler task with
"run with highest privileges" instead, the standard way for admin apps. Only works for
the packaged .exe.
"""

import sys

from core.winutil import IS_WINDOWS, run, run_powershell

TASK_NAME = "RETWEAKS"


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
        return False, "Start with Windows only works in RETWEAKS.exe."
    if enable:
        # Register-ScheduledTask instead of schtasks: schtasks tasks don't start on battery,
        # are stopped when a laptop is unplugged and are killed after 72 hours.
        exe = sys.executable.replace("'", "''")
        arg = "-Argument '--minimized' " if minimized else ""
        out = run_powershell(
            "try { "
            f"$a = New-ScheduledTaskAction -Execute '{exe}' {arg}; "
            "$t = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME; "
            "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
            "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew; "
            "$p = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest; "
            f"Register-ScheduledTask -TaskName '{TASK_NAME}' -Action $a -Trigger $t -Settings $s -Principal $p "
            "-Force -ErrorAction Stop | Out-Null; 'OK' } catch { $_.Exception.Message }", timeout=40).strip()
        if out != "OK":
            return False, out or "Task Scheduler refused the change."
        return True, "RETWEAKS will start when you sign in."
    else:
        if not is_enabled():
            return True, "RETWEAKS won't start with Windows."
        r = run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], timeout=20)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip() or "Task Scheduler refused the change."
    return True, "RETWEAKS will start when you sign in." if enable else "RETWEAKS won't start with Windows."
