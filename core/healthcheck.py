# core/healthcheck.py
"""RETWEAKS Health Check: independent, read-only checks of real Windows state.

Every check returns a dict:
    {id, name, status: "good"|"warn"|"bad"|"unavailable", detail, fix_id, fix_label}
Checks never change anything. A fix runs only when the user clicks it (see apply_fix), and the
page then re-runs that one check to show the real new state. A check that raises is shown as
"unavailable" with the error text, never as a crash.
"""

import os
import re
from datetime import datetime

from core.winutil import IS_WINDOWS, run, run_powershell, run_powershell_json, as_list

GOOD, WARN, BAD, NA = "good", "warn", "bad", "unavailable"
STATUSES = (GOOD, WARN, BAD, NA)

# Thresholds
STARTUP_WARN_COUNT = 12
TEMP_WARN_BYTES = 1 * 1024 ** 3
TEMP_BAD_BYTES = 10 * 1024 ** 3
FREE_WARN_PCT = 15.0
FREE_BAD_PCT = 5.0
UPDATE_WARN_DAYS = 45
RAM_WARN_PCT = 85.0
RAM_BAD_PCT = 95.0

HIGH_PERFORMANCE_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"   # Windows built-in High performance


def result(cid, name, status, detail, fix_id=None, fix_label=""):
    return {"id": cid, "name": name, "status": status, "detail": detail,
            "fix_id": fix_id, "fix_label": fix_label if fix_id else ""}


def fmt_bytes(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


# ---------------------------------------------------------------- pure classifiers (unit tested)

def classify_startup(count):
    status = WARN if count > STARTUP_WARN_COUNT else GOOD
    return status, f"{count} app{'s' if count != 1 else ''} start{'s' if count == 1 else ''} with Windows"


def classify_temp(total_bytes, items):
    if total_bytes >= TEMP_BAD_BYTES:
        status = BAD
    elif total_bytes >= TEMP_WARN_BYTES:
        status = WARN
    else:
        status = GOOD
    return status, f"{fmt_bytes(total_bytes)} in {items} temporary item{'s' if items != 1 else ''}"


def classify_power(plan_name, has_battery):
    name = (plan_name or "").strip()
    if not name:
        return NA, "Windows did not report the active power plan."
    if not has_battery and name.lower() == "power saver":
        return WARN, f"Active plan: {name} (this PC has no battery, so it limits performance for no power-saving benefit on battery)"
    return GOOD, f"Active plan: {name}"


def classify_disks(disks):
    """disks: list of (name, health_status) tuples."""
    if not disks:
        return NA, "Windows reported no physical disks."
    bad = [f"{n}: {h}" for n, h in disks if str(h).strip().lower() != "healthy"]
    if bad:
        return BAD, "Not healthy: " + "; ".join(bad)
    return GOOD, f"{len(disks)} disk{'s' if len(disks) != 1 else ''} report Healthy"


def classify_free_space(free, total, drive="C:"):
    if not total:
        return NA, "Windows did not report the drive size."
    pct = free * 100.0 / total
    text = f"{drive} has {fmt_bytes(free)} free of {fmt_bytes(total)} ({pct:.0f}%)"
    if pct < FREE_BAD_PCT:
        return BAD, text
    if pct < FREE_WARN_PCT:
        return WARN, text
    return GOOD, text


def classify_reboot(pending_sources):
    if pending_sources:
        return WARN, "A restart is pending (" + ", ".join(pending_sources) + ")"
    return GOOD, "No restart is pending"


def classify_update_age(days):
    if days is None:
        return NA, "Windows did not report an update history."
    if days > UPDATE_WARN_DAYS:
        return WARN, f"Last installed update was {days} days ago"
    return GOOD, f"Last installed update was {days} day{'s' if days != 1 else ''} ago"


def classify_game_mode(state):
    s = (state or "").strip()
    if not s or s == "Not Windows":
        return NA, "Windows did not report the Game Mode state."
    return GOOD, f"Game Mode: {s}. Shown for information only; RETWEAKS never forces it on because it can lower FPS on some PCs."


def classify_refresh(current_hz, max_hz, label="Display"):
    if not current_hz or not max_hz:
        return NA, f"{label}: refresh rate not reported."
    if current_hz < max_hz:
        return WARN, f"{label} runs at {current_hz} Hz; this resolution supports up to {max_hz} Hz"
    return GOOD, f"{label} runs at {current_hz} Hz (its maximum at this resolution)"


def max_rate_for(modes, width, height):
    """modes: iterable of (w, h, hz). Highest real rate at the given resolution (0/1 mean 'default')."""
    rates = [hz for w, h, hz in modes if w == width and h == height and hz > 1]
    return max(rates) if rates else None


def classify_ram(percent, used, total):
    text = f"{percent:.0f}% in use ({fmt_bytes(used)} of {fmt_bytes(total)}) right now"
    if percent >= RAM_BAD_PCT:
        return BAD, text
    if percent >= RAM_WARN_PCT:
        return WARN, text
    return GOOD, text


def summarize(results):
    """Counts and the one-line summary, e.g. '7 good · 2 to look at · 1 unavailable'."""
    good = sum(1 for r in results if r["status"] == GOOD)
    look = sum(1 for r in results if r["status"] in (WARN, BAD))
    na = sum(1 for r in results if r["status"] == NA)
    parts = [f"{good} good", f"{look} to look at"]
    if na:
        parts.append(f"{na} unavailable")
    return {"good": good, "look": look, "unavailable": na, "text": " · ".join(parts)}


# ---------------------------------------------------------------- readers (Windows)

def _need_windows():
    if not IS_WINDOWS:
        raise RuntimeError("Only available on Windows")


def check_startup():
    _need_windows()
    from core.startup_manager import list_startup_apps
    entries = list_startup_apps()
    count = sum(1 for e in entries if e.get("status", "Enabled") == "Enabled")
    status, detail = classify_startup(count)
    return result("startup", "Startup apps", status, detail,
                  "open_startup" if status != GOOD else None, "Open Startup apps")


def check_temp():
    from core.storage_manager import preview_temp_files
    items, total = preview_temp_files()
    status, detail = classify_temp(total, items)
    return result("temp", "Temporary files", status, detail,
                  "open_storage" if status != GOOD else None, "Open Storage & cleanup")


def _has_battery():
    import psutil
    return psutil.sensors_battery() is not None


def check_power():
    _need_windows()
    from core.optimizer import WindowsOptimizer
    name = WindowsOptimizer.get_active_power_plan()
    if name in ("Unknown", "Not Windows"):
        name = ""
    status, detail = classify_power(name, _has_battery())
    return result("power", "Power plan", status, detail,
                  "power_high" if status == WARN else None, "Switch to High performance")


def read_disks():
    _need_windows()
    data = run_powershell_json(
        "Get-PhysicalDisk | Select-Object FriendlyName,HealthStatus | ConvertTo-Json -Compress", timeout=30)
    return [(d.get("FriendlyName") or "Disk", d.get("HealthStatus") or "Unknown") for d in as_list(data)]


def check_disk_health():
    status, detail = classify_disks(read_disks())
    return result("disk", "Disk health", status, detail)


def check_free_space():
    import shutil
    drive = os.environ.get("SystemDrive", "C:") if IS_WINDOWS else os.path.abspath(os.sep)
    usage = shutil.disk_usage(drive + "\\" if IS_WINDOWS else drive)
    status, detail = classify_free_space(usage.free, usage.total, drive)
    return result("space", "Free space on system drive", status, detail,
                  "open_storage" if status != GOOD else None, "Open Storage & cleanup")


def read_pending_reboot():
    """Names of the documented Windows markers that say a restart is pending."""
    _need_windows()
    import winreg
    keys = [
        (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
         "Component Based Servicing"),
        (r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
         "Windows Update"),
    ]
    found = []
    for path, label in keys:
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ))
            found.append(label)
        except FileNotFoundError:
            pass
    return found


def check_reboot():
    status, detail = classify_reboot(read_pending_reboot())
    return result("reboot", "Pending restart", status, detail)


_UPDATE_PS = r"""
$latest = $null
try {
  $s = New-Object -ComObject Microsoft.Update.Session
  $h = $s.CreateUpdateSearcher()
  $n = $h.GetTotalHistoryCount()
  if ($n -gt 0) {
    foreach ($e in $h.QueryHistory(0, [Math]::Min($n, 100))) {
      if ($e.ResultCode -eq 2 -and ($latest -eq $null -or $e.Date -gt $latest)) { $latest = $e.Date }
    }
  }
} catch {}
if ($latest -eq $null) {
  try { $latest = (Get-HotFix | Where-Object { $_.InstalledOn } | Sort-Object InstalledOn -Descending |
                   Select-Object -First 1).InstalledOn } catch {}
}
if ($latest -ne $null) { ([datetime]$latest).ToString('yyyy-MM-dd') }
"""


def days_since(date_text, now=None):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_text or "")
    if not m:
        return None
    then = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return max(0, ((now or datetime.now()) - then).days)


def check_updates():
    _need_windows()
    days = days_since(run_powershell(_UPDATE_PS, timeout=60))
    status, detail = classify_update_age(days)
    return result("updates", "Windows Update", status, detail)


def check_game_mode():
    _need_windows()
    from core.optimizer import WindowsOptimizer
    status, detail = classify_game_mode(WindowsOptimizer.get_game_mode())
    return result("gamemode", "Game Mode", status, detail)


def read_display_modes():
    """Per attached display: {name, width, height, current_hz, modes:[(w,h,hz)]} via EnumDisplaySettings."""
    _need_windows()
    import ctypes
    from ctypes import wintypes

    class DEVMODEW(ctypes.Structure):
        _fields_ = [("dmDeviceName", wintypes.WCHAR * 32), ("dmSpecVersion", wintypes.WORD),
                    ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
                    ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
                    ("dmPositionX", wintypes.LONG), ("dmPositionY", wintypes.LONG),
                    ("dmDisplayOrientation", wintypes.DWORD), ("dmDisplayFixedOutput", wintypes.DWORD),
                    ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
                    ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
                    ("dmCollate", ctypes.c_short), ("dmFormName", wintypes.WCHAR * 32),
                    ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
                    ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
                    ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
                    ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
                    ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
                    ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
                    ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD)]

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                    ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                    ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]

    user32 = ctypes.windll.user32
    ENUM_CURRENT = -1
    displays, i = [], 0
    while True:
        dev = DISPLAY_DEVICEW()
        dev.cb = ctypes.sizeof(dev)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dev), 0):
            break
        i += 1
        if not (dev.StateFlags & 1):          # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP
            continue
        cur = DEVMODEW()
        cur.dmSize = ctypes.sizeof(cur)
        if not user32.EnumDisplaySettingsW(dev.DeviceName, ENUM_CURRENT, ctypes.byref(cur)):
            continue
        modes, n = [], 0
        while True:
            m = DEVMODEW()
            m.dmSize = ctypes.sizeof(m)
            if not user32.EnumDisplaySettingsW(dev.DeviceName, n, ctypes.byref(m)):
                break
            n += 1
            modes.append((int(m.dmPelsWidth), int(m.dmPelsHeight), int(m.dmDisplayFrequency)))
        displays.append({"name": dev.DeviceString or dev.DeviceName, "width": int(cur.dmPelsWidth),
                         "height": int(cur.dmPelsHeight), "current_hz": int(cur.dmDisplayFrequency),
                         "modes": modes})
    return displays


def check_refresh(displays=None):
    displays = read_display_modes() if displays is None else displays
    if not displays:
        return result("refresh", "Display refresh rate", NA, "Windows reported no active displays.")
    statuses, details, below = [], [], False
    for n, d in enumerate(displays, 1):
        label = f"Display {n}" if len(displays) > 1 else "Display"
        s, text = classify_refresh(d.get("current_hz"), max_rate_for(d.get("modes", []), d["width"], d["height"]), label)
        statuses.append(s)
        details.append(text)
        below = below or s == WARN
    if below:
        status = WARN
    elif all(s == NA for s in statuses):
        status = NA
    else:
        status = GOOD
    return result("refresh", "Display refresh rate", status, "; ".join(details),
                  "open_display" if below else None, "Open Windows display settings")


def check_ram():
    import psutil
    vm = psutil.virtual_memory()
    status, detail = classify_ram(vm.percent, vm.used, vm.total)
    return result("ram", "Memory (RAM) in use", status, detail)


CHECKS = [
    ("startup", "Startup apps", check_startup),
    ("temp", "Temporary files", check_temp),
    ("power", "Power plan", check_power),
    ("disk", "Disk health", check_disk_health),
    ("space", "Free space on system drive", check_free_space),
    ("reboot", "Pending restart", check_reboot),
    ("updates", "Windows Update", check_updates),
    ("gamemode", "Game Mode", check_game_mode),
    ("refresh", "Display refresh rate", check_refresh),
    ("ram", "Memory (RAM) in use", check_ram),
]


def run_check(cid, name, fn):
    """Run one check; a failure becomes an 'unavailable' result carrying the error."""
    try:
        r = fn()
        if not isinstance(r, dict) or r.get("status") not in STATUSES:
            raise ValueError("check returned an invalid result")
        r.setdefault("id", cid)
        r.setdefault("name", name)
        return r
    except Exception as e:
        return result(cid, name, NA, f"Could not be read: {e}")


def run_one(cid, checks=None):
    for c_id, name, fn in (checks or CHECKS):
        if c_id == cid:
            return run_check(c_id, name, fn)
    return result(cid, cid, NA, "Unknown check")


def run_all(checks=None, on_result=None):
    out = []
    for cid, name, fn in (checks or CHECKS):
        r = run_check(cid, name, fn)
        out.append(r)
        if on_result:
            on_result(r)
    return out


# ---------------------------------------------------------------- fixes

def apply_power_high():
    """Switch to Windows' built-in High performance plan, saving the current plan first so
    'Restore previous power plan' (Tweaks page) still works. Returns (ok, message)."""
    if not IS_WINDOWS:
        return False, "Only available on Windows"
    from core import optimizer as opt
    current = opt.WindowsOptimizer.get_active_power_plan_guid()
    if current == HIGH_PERFORMANCE_GUID:
        return True, "High performance is already active."
    if current:
        state = opt._load_state()
        state["previous_power_plan"] = {"guid": current, "name": opt.WindowsOptimizer.get_active_power_plan()}
        opt._save_state(state)
    r = run(["powercfg", "/setactive", HIGH_PERFORMANCE_GUID], timeout=15)
    if r.returncode != 0:
        return False, ((r.stderr or r.stdout).strip()
                       or "powercfg failed (this PC may not offer the High performance plan).")
    return True, "High performance power plan is now active. Laptops will use more battery."
