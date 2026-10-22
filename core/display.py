# core/display.py
"""Display modes and GPU driver age.

Monitors: EnumDisplayDevicesW lists the active displays and EnumDisplaySettingsExW lists
every mode each one supports (ctypes only, no extra library). The max refresh rate is
taken from the modes the display really reports at the CURRENT resolution.
Drivers: CIM Win32_VideoController gives DriverVersion and DriverDate (DMTF format).

Everything that touches Windows is guarded so this module imports on any OS.
"""

import ctypes
import re
import sys
from datetime import date, datetime

from core.winutil import IS_WINDOWS, as_list, run_powershell_json

ENUM_CURRENT_SETTINGS = -1
DM_BITSPERPEL = 0x00040000
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000
DM_DISPLAYFIXEDOUTPUT = 0x20000000
DMDFO_STRETCH = 1          # DEVMODE dmDisplayFixedOutput: stretch a lower resolution to fill the screen
DM_INTERLACED = 2          # dmDisplayFlags value
CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002
DISP_CHANGE_SUCCESSFUL = 0
DISP_CHANGE_RESTART = 1
DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x1
DISPLAY_DEVICE_MIRRORING_DRIVER = 0x8

DISP_CHANGE_TEXT = {
    0: "Success", 1: "Restart required", -1: "Failed", -2: "Mode not supported",
    -3: "Settings could not be written", -4: "Invalid flags", -5: "Invalid parameter",
    -6: "Dual-view conflict",
}

DRIVER_PAGES = {
    "NVIDIA": "https://www.nvidia.com/Download/index.aspx",
    "AMD": "https://www.amd.com/en/support/download/drivers.html",
    "Intel": "https://www.intel.com/content/www/us/en/download-center/home.html",
}


# ------------------------------------------------------------------ pure logic

def max_refresh_at(modes, width, height, bpp=None):
    """Highest refresh rate (Hz) in `modes` at width x height, or None.

    modes: iterable of dicts/tuples (width, height, bpp, hz). Rates of 0 or 1 mean
    "hardware default" in Windows, not a real rate, so they are ignored. If `bpp` is given
    and some modes match it, only those are used (so 16-bit legacy modes don't count).
    """
    rows = []
    for m in modes or []:
        if isinstance(m, dict):
            w, h, b, hz = m.get("width"), m.get("height"), m.get("bpp"), m.get("hz")
        else:
            w, h, b, hz = m
        if w == width and h == height and isinstance(hz, (int, float)) and hz > 1:
            rows.append((b, int(hz)))
    if not rows:
        return None
    if bpp is not None:
        same = [hz for b, hz in rows if b == bpp]
        if same:
            return max(same)
    return max(hz for _, hz in rows)


def parse_cim_date(text):
    """Parse a CIM/DMTF datetime 'yyyymmddHHMMSS.ffffff+zzz' (also plain 'yyyy-mm-dd').

    Returns a datetime.date, or None when the text is empty or not a valid date.
    """
    if not text:
        return None
    s = str(text).strip()
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\.\d+)?(?:[+-]\d{3})?$", s)
    if not m:
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
        if not m:
            return None
    try:
        y, mo, d = (int(g) for g in m.groups()[:3])
        if y < 1990:        # 1601/1970 placeholders are not real driver dates
            return None
        return date(y, mo, d)
    except ValueError:
        return None


def driver_age_days(driver_date, today=None):
    """Whole days between the driver date and today, or None."""
    if driver_date is None:
        return None
    today = today or date.today()
    return (today - driver_date).days


def driver_age_text(days):
    """'Driver is N days old' (age only; this is not a claim that a newer one exists)."""
    if days is None:
        return "Unavailable"
    if days < 0:
        return "Driver date is in the future"
    return f"Driver is {days} days old"


def vendor_driver_url(vendor_or_name):
    n = (vendor_or_name or "").lower()
    if "nvidia" in n or "geforce" in n or "quadro" in n or "rtx" in n:
        return DRIVER_PAGES["NVIDIA"]
    if "amd" in n or "radeon" in n or "advanced micro" in n:
        return DRIVER_PAGES["AMD"]
    if "intel" in n:
        return DRIVER_PAGES["Intel"]
    return None


# ------------------------------------------------------------------ Windows: displays

if IS_WINDOWS or sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class POINTL(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class DEVMODEW(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", ctypes.c_wchar * 32),
            ("dmSpecVersion", wintypes.WORD),
            ("dmDriverVersion", wintypes.WORD),
            ("dmSize", wintypes.WORD),
            ("dmDriverExtra", wintypes.WORD),
            ("dmFields", wintypes.DWORD),
            ("dmPosition", POINTL),
            ("dmDisplayOrientation", wintypes.DWORD),
            ("dmDisplayFixedOutput", wintypes.DWORD),
            ("dmColor", ctypes.c_short),
            ("dmDuplex", ctypes.c_short),
            ("dmYResolution", ctypes.c_short),
            ("dmTTOption", ctypes.c_short),
            ("dmCollate", ctypes.c_short),
            ("dmFormName", ctypes.c_wchar * 32),
            ("dmLogPixels", wintypes.WORD),
            ("dmBitsPerPel", wintypes.DWORD),
            ("dmPelsWidth", wintypes.DWORD),
            ("dmPelsHeight", wintypes.DWORD),
            ("dmDisplayFlags", wintypes.DWORD),
            ("dmDisplayFrequency", wintypes.DWORD),
            ("dmICMMethod", wintypes.DWORD),
            ("dmICMIntent", wintypes.DWORD),
            ("dmMediaType", wintypes.DWORD),
            ("dmDitherType", wintypes.DWORD),
            ("dmReserved1", wintypes.DWORD),
            ("dmReserved2", wintypes.DWORD),
            ("dmPanningWidth", wintypes.DWORD),
            ("dmPanningHeight", wintypes.DWORD),
        ]

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("DeviceName", ctypes.c_wchar * 32),
            ("DeviceString", ctypes.c_wchar * 128),
            ("StateFlags", wintypes.DWORD),
            ("DeviceID", ctypes.c_wchar * 128),
            ("DeviceKey", ctypes.c_wchar * 128),
        ]

    def _user32():
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                          ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
        u.EnumDisplayDevicesW.restype = wintypes.BOOL
        u.EnumDisplaySettingsExW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                             ctypes.POINTER(DEVMODEW), wintypes.DWORD]
        u.EnumDisplaySettingsExW.restype = wintypes.BOOL
        u.ChangeDisplaySettingsExW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(DEVMODEW),
                                               wintypes.HWND, wintypes.DWORD, wintypes.LPVOID]
        u.ChangeDisplaySettingsExW.restype = ctypes.c_long
        return u

    def _new_devmode():
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        return dm

    def _current_devmode(user32, device):
        dm = _new_devmode()
        if not user32.EnumDisplaySettingsExW(device, ENUM_CURRENT_SETTINGS, ctypes.byref(dm), 0):
            return None
        return dm


# ------------------------------------------------------------------ monitor names / native size (v1.5)
# Windows' documented display-configuration API (QueryDisplayConfig + DisplayConfigGetDeviceInfo):
# for each active \\.\DISPLAYn it gives the monitor's real name (from its EDID), its preferred
# (native) resolution and its rotation. Works for every graphics card brand. Struct sizes were checked
# against the Windows SDK headers (mingw-w64) and are tested in tests/test_display.py.
QDC_ONLY_ACTIVE_PATHS = 2
GET_SOURCE_NAME, GET_TARGET_NAME, GET_TARGET_PREFERRED_MODE = 1, 2, 3
ROTATED = (2, 4)            # DISPLAYCONFIG_ROTATION_ROTATE90 / ROTATE270


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]   # DWORD, LONG


class _RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", ctypes.c_uint32), ("Denominator", ctypes.c_uint32)]


class _PATH_SOURCE(ctypes.Structure):
    _fields_ = [("adapterId", _LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32),
                ("statusFlags", ctypes.c_uint32)]


class _PATH_TARGET(ctypes.Structure):
    _fields_ = [("adapterId", _LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32),
                ("outputTechnology", ctypes.c_uint32), ("rotation", ctypes.c_uint32),
                ("scaling", ctypes.c_uint32), ("refreshRate", _RATIONAL),
                ("scanLineOrdering", ctypes.c_uint32), ("targetAvailable", ctypes.c_int32),
                ("statusFlags", ctypes.c_uint32)]


class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
    _fields_ = [("sourceInfo", _PATH_SOURCE), ("targetInfo", _PATH_TARGET), ("flags", ctypes.c_uint32)]


class DISPLAYCONFIG_MODE_INFO(ctypes.Structure):
    _fields_ = [("infoType", ctypes.c_uint32), ("id", ctypes.c_uint32), ("adapterId", _LUID),
                ("data", ctypes.c_uint8 * 48)]


class _HEADER(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("size", ctypes.c_uint32), ("adapterId", _LUID),
                ("id", ctypes.c_uint32)]


class DISPLAYCONFIG_SOURCE_DEVICE_NAME(ctypes.Structure):
    _fields_ = [("header", _HEADER), ("viewGdiDeviceName", ctypes.c_wchar * 32)]


class DISPLAYCONFIG_TARGET_DEVICE_NAME(ctypes.Structure):
    _fields_ = [("header", _HEADER), ("flags", ctypes.c_uint32), ("outputTechnology", ctypes.c_uint32),
                ("edidManufactureId", ctypes.c_uint16), ("edidProductCodeId", ctypes.c_uint16),
                ("connectorInstance", ctypes.c_uint32), ("monitorFriendlyDeviceName", ctypes.c_wchar * 64),
                ("monitorDevicePath", ctypes.c_wchar * 128)]


class _2DREGION(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_uint32), ("cy", ctypes.c_uint32)]


class _VIDEO_SIGNAL_INFO(ctypes.Structure):
    _fields_ = [("pixelRate", ctypes.c_uint64), ("hSyncFreq", _RATIONAL), ("vSyncFreq", _RATIONAL),
                ("activeSize", _2DREGION), ("totalSize", _2DREGION), ("videoStandard", ctypes.c_uint32),
                ("scanLineOrdering", ctypes.c_uint32)]


class DISPLAYCONFIG_TARGET_PREFERRED_MODE(ctypes.Structure):
    _fields_ = [("header", _HEADER), ("width", ctypes.c_uint32), ("height", ctypes.c_uint32),
                ("targetMode", _VIDEO_SIGNAL_INFO)]


def _device_info(user32, struct, kind, adapter_id, target_id):
    info = struct()
    info.header.type, info.header.size = kind, ctypes.sizeof(struct)
    info.header.adapterId, info.header.id = adapter_id, target_id
    return info if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info)) == 0 else None


def display_config():
    """{"\\\\.\\DISPLAY1": {"name": "LG HDR 4K", "native": (3840, 2160), "rotated": False}} for every
    active display, from Windows' display configuration. Missing pieces are None; {} if unavailable."""
    if not IS_WINDOWS:
        return {}
    try:
        user32 = _user32()
        n_paths, n_modes = ctypes.c_uint32(0), ctypes.c_uint32(0)
        for _ in range(3):           # the configuration can change between the two calls
            if user32.GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, ctypes.byref(n_paths),
                                                  ctypes.byref(n_modes)) != 0:
                return {}
            paths = (DISPLAYCONFIG_PATH_INFO * n_paths.value)()
            modes = (DISPLAYCONFIG_MODE_INFO * n_modes.value)()
            rc = user32.QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, ctypes.byref(n_paths), paths,
                                           ctypes.byref(n_modes), modes, None)
            if rc == 0:
                break
            if rc != 122:            # ERROR_INSUFFICIENT_BUFFER: try again
                return {}
        else:
            return {}
        out = {}
        for path in paths[:n_paths.value]:
            src = _device_info(user32, DISPLAYCONFIG_SOURCE_DEVICE_NAME, GET_SOURCE_NAME,
                               path.sourceInfo.adapterId, path.sourceInfo.id)
            if src is None or not src.viewGdiDeviceName:
                continue
            tgt = _device_info(user32, DISPLAYCONFIG_TARGET_DEVICE_NAME, GET_TARGET_NAME,
                               path.targetInfo.adapterId, path.targetInfo.id)
            pref = _device_info(user32, DISPLAYCONFIG_TARGET_PREFERRED_MODE, GET_TARGET_PREFERRED_MODE,
                                path.targetInfo.adapterId, path.targetInfo.id)
            rotated = path.targetInfo.rotation in ROTATED
            native = None
            if pref is not None and pref.width and pref.height:
                native = (pref.width, pref.height)
            out.setdefault(src.viewGdiDeviceName, {
                "name": (tgt.monitorFriendlyDeviceName.strip() or None) if tgt is not None else None,
                "native": native, "rotated": rotated})
        return out
    except Exception:
        return {}


def list_displays():
    """Active displays with current mode and the best refresh rate at that resolution.

    Returns a list of dicts: device (e.g. \\\\.\\DISPLAY1), adapter, monitor (device string),
    primary, width, height, bpp, hz, max_hz. Empty list when not on Windows.
    """
    if not IS_WINDOWS:
        return []
    try:
        user32 = _user32()
    except Exception:
        return []
    config = display_config()
    out = []
    i = 0
    while i < 32:
        adapter = DISPLAY_DEVICEW()
        adapter.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(adapter), 0):
            break
        i += 1
        flags = adapter.StateFlags
        if not flags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP or flags & DISPLAY_DEVICE_MIRRORING_DRIVER:
            continue
        cur = _current_devmode(user32, adapter.DeviceName)
        if cur is None:
            continue
        mon = DISPLAY_DEVICEW()
        mon.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        mon_name = None
        if user32.EnumDisplayDevicesW(adapter.DeviceName, 0, ctypes.byref(mon), 0):
            mon_name = mon.DeviceString or None
        modes, n = [], 0
        while n < 4096:
            dm = _new_devmode()
            if not user32.EnumDisplaySettingsExW(adapter.DeviceName, n, ctypes.byref(dm), 0):
                break
            n += 1
            if dm.dmDisplayFlags & DM_INTERLACED:
                continue
            modes.append((int(dm.dmPelsWidth), int(dm.dmPelsHeight),
                          int(dm.dmBitsPerPel), int(dm.dmDisplayFrequency)))
        w, h, b, hz = (int(cur.dmPelsWidth), int(cur.dmPelsHeight),
                       int(cur.dmBitsPerPel), int(cur.dmDisplayFrequency))
        out.append({
            "device": adapter.DeviceName, "adapter": adapter.DeviceString,
            "monitor": mon_name, "primary": bool(flags & 0x4),
            "width": w, "height": h, "bpp": b, "hz": hz if hz > 1 else None,
            "max_hz": max_refresh_at(modes, w, h, b),
            "modes": modes,        # every mode the driver offers (v1.5: stretched-resolution check)
        })
        info = config.get(adapter.DeviceName) or {}
        out[-1]["name"] = info.get("name")          # the monitor's own name (EDID), per display
        out[-1]["native"] = info.get("native")      # its preferred (native) resolution
        out[-1]["rotated"] = bool(info.get("rotated") or getattr(cur, "dmDisplayOrientation", 0) in (1, 3))
    return out


# ------------------------------------------------------------------ stretched resolution (v1.5)
# Global, like NVIDIA Control Panel: the whole desktop runs at e.g. 1720x1080 and the picture is
# stretched to fill the monitor. Games in Windowed Fullscreen (borderless) use the desktop resolution,
# so they're stretched too, without touching any game file.
STRETCH_WIDTHS_1080 = [1720, 1680, 1650, 1600, 1440]


def native_size(display):
    """The monitor's native resolution: its preferred mode reported by Windows (from the monitor's
    EDID). Only if that's unavailable: the largest mode in the driver's list (which can be too big
    when the driver offers super-resolution modes like NVIDIA DSR / AMD VSR)."""
    if display.get("native"):
        return tuple(display["native"])
    sizes = [(m[0], m[1]) for m in display.get("modes") or [] if m[0] and m[1]]
    if not sizes:
        return display.get("width"), display.get("height")
    return max(sizes, key=lambda s: (s[0] * s[1], s[0]))


def stretch_choices(display):
    """[(width, height, max_hz or None)]: narrower resolutions at the native height. max_hz None means
    the graphics card doesn't offer it yet (it has to be added as a custom resolution first)."""
    nw, nh = native_size(display)
    if not nw or not nh:
        return []
    modes = display.get("modes") or []
    offered = sorted({m[0] for m in modes if m[1] == nh and m[0] < nw and m[0] >= nh}, reverse=True)
    wanted = list(offered)
    if nh == 1080:
        wanted += [w for w in STRETCH_WIDTHS_1080 if w not in offered and w < nw]
    four_three = int(round(nh * 4 / 3))
    if four_three < nw and four_three not in wanted:
        wanted.append(four_three)
    out = []
    for w in sorted(set(wanted), reverse=True):
        out.append((w, nh, max_refresh_at(modes, w, nh, display.get("bpp"))))
    return out


def set_resolution(device, width, height, hz=None, stretch=True, persist=False):
    """Switch a display to width x height. stretch asks the driver to fill the screen (DMDFO_STRETCH).
    persist=False is a trial that isn't saved (restore_saved_mode() undoes it); persist=True saves it.
    Returns (ok, message)."""
    if not IS_WINDOWS:
        return False, "Only available on Windows."
    try:
        user32 = _user32()
        dm = _current_devmode(user32, device)
        if dm is None:
            return False, "Could not read the current display mode."
        dm.dmPelsWidth, dm.dmPelsHeight = int(width), int(height)
        fields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_BITSPERPEL
        if hz:
            dm.dmDisplayFrequency = int(hz)
            fields |= DM_DISPLAYFREQUENCY
        tries = [True, False] if stretch else [False]
        code = None
        for want_stretch in tries:
            dm.dmFields = fields | (DM_DISPLAYFIXEDOUTPUT if want_stretch else 0)
            dm.dmDisplayFixedOutput = DMDFO_STRETCH if want_stretch else 0
            code = user32.ChangeDisplaySettingsExW(device, ctypes.byref(dm), None, CDS_TEST, None)
            if code == DISP_CHANGE_SUCCESSFUL:
                break
        if code != DISP_CHANGE_SUCCESSFUL:
            return False, f"Windows rejected {width}×{height}: {DISP_CHANGE_TEXT.get(code, code)}."
        code = user32.ChangeDisplaySettingsExW(device, ctypes.byref(dm), None,
                                               CDS_UPDATEREGISTRY if persist else 0, None)
        if code != DISP_CHANGE_SUCCESSFUL:
            return False, f"Couldn't switch to {width}×{height}: {DISP_CHANGE_TEXT.get(code, code)}."
        now = _current_devmode(user32, device)
        if now is None or (int(now.dmPelsWidth), int(now.dmPelsHeight)) != (int(width), int(height)):
            return False, "Windows didn't switch to that resolution."
        return True, f"Now running {width}×{height} at {int(now.dmDisplayFrequency)} Hz."
    except Exception as e:
        return False, f"Display change failed: {e}"


def restore_saved_mode(device):
    """Put a display back to the mode saved in Windows settings (its normal desktop resolution).
    Used after the NVIDIA custom-resolution test. Returns (ok, message)."""
    if not IS_WINDOWS:
        return False, "Only available on Windows."
    try:
        user32 = _user32()
        dm = _new_devmode()
        if not user32.EnumDisplaySettingsExW(device, 0xFFFFFFFE, ctypes.byref(dm), 0):   # ENUM_REGISTRY_SETTINGS
            return False, "Couldn't read your saved display mode."
        dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_BITSPERPEL | DM_DISPLAYFREQUENCY
        code = user32.ChangeDisplaySettingsExW(device, ctypes.byref(dm), None, 0, None)
        if code != DISP_CHANGE_SUCCESSFUL:
            return False, f"Windows couldn't switch back: {DISP_CHANGE_TEXT.get(code, code)}."
        return True, f"Desktop is back to {dm.dmPelsWidth}×{dm.dmPelsHeight} at {dm.dmDisplayFrequency} Hz."
    except Exception as e:
        return False, f"Display change failed: {e}"


def set_refresh_rate(device, hz):
    """Change one display's refresh rate at its current resolution.

    Runs CDS_TEST first, then CDS_UPDATEREGISTRY. Returns (ok, message, previous_hz).
    The caller keeps previous_hz so it can revert with the same function.
    """
    if not IS_WINDOWS:
        return False, "Only available on Windows.", None
    try:
        user32 = _user32()
        dm = _current_devmode(user32, device)
        if dm is None:
            return False, "Could not read the current display mode.", None
        previous = int(dm.dmDisplayFrequency)
        dm.dmDisplayFrequency = int(hz)
        dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_BITSPERPEL | DM_DISPLAYFREQUENCY
        code = user32.ChangeDisplaySettingsExW(device, ctypes.byref(dm), None, CDS_TEST, None)
        if code != DISP_CHANGE_SUCCESSFUL:
            return False, f"Windows rejected {hz} Hz: {DISP_CHANGE_TEXT.get(code, code)}.", previous
        code = user32.ChangeDisplaySettingsExW(device, ctypes.byref(dm), None, CDS_UPDATEREGISTRY, None)
        if code == DISP_CHANGE_RESTART:
            # Windows saved the new rate for the next restart instead of switching now. Put the
            # saved setting back, so nothing changes behind the user's back after a reboot.
            dm.dmDisplayFrequency = previous
            back = user32.ChangeDisplaySettingsExW(device, ctypes.byref(dm), None, CDS_UPDATEREGISTRY, None)
            undone = back in (DISP_CHANGE_SUCCESSFUL, DISP_CHANGE_RESTART)
            return False, (f"Windows can only switch to {hz} Hz after a restart, so nothing was changed"
                           + ("." if undone else " now, but it may apply after a restart. Check Windows "
                              "display settings.")), previous
        if code != DISP_CHANGE_SUCCESSFUL:
            return False, f"Could not apply {hz} Hz: {DISP_CHANGE_TEXT.get(code, code)}.", previous
        # Verify what Windows is really running now.
        now = _current_devmode(user32, device)
        actual = int(now.dmDisplayFrequency) if now is not None else None
        if actual != int(hz):
            return False, f"Windows reports {actual} Hz after the change (requested {hz} Hz).", previous
        return True, f"Refresh rate is now {actual} Hz.", previous
    except Exception as e:
        return False, f"Display change failed: {e}", None


# ------------------------------------------------------------------ GPU drivers

_DRIVER_SCRIPT = r"""
$r = @(Get-CimInstance Win32_VideoController | ForEach-Object {
  [PSCustomObject]@{
    Name = $_.Name
    DriverVersion = $_.DriverVersion
    DriverDate = if ($_.DriverDate) { [Management.ManagementDateTimeConverter]::ToDmtfDateTime($_.DriverDate) } else { $null }
    AdapterCompatibility = $_.AdapterCompatibility
  } })
ConvertTo-Json -InputObject $r -Compress
"""


def nvml_driver_version():
    """NVIDIA driver version from NVML, or None when pynvml / an NVIDIA GPU isn't there."""
    try:
        import pynvml
    except Exception:
        return None
    try:
        pynvml.nvmlInit()
        v = pynvml.nvmlSystemGetDriverVersion()
        return v.decode() if isinstance(v, bytes) else str(v)
    except Exception:
        return None
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


def list_gpu_drivers(today=None):
    """One dict per GPU: name, vendor, version, date (date or None), age_days, url, nvml_version."""
    if not IS_WINDOWS:
        return []
    from core.gpu_dxgi import vendor_from_name
    raw = as_list(run_powershell_json(_DRIVER_SCRIPT, timeout=45))
    nvml = None
    out = []
    for v in raw:
        if not isinstance(v, dict) or not v.get("Name"):
            continue
        name = str(v["Name"])
        vendor = vendor_from_name(name) or vendor_from_name(str(v.get("AdapterCompatibility") or ""))
        d = parse_cim_date(v.get("DriverDate"))
        entry = {
            "name": name, "vendor": vendor,
            "version": v.get("DriverVersion") or None,
            "date": d, "age_days": driver_age_days(d, today),
            "url": vendor_driver_url(vendor or name),
            "nvml_version": None,
        }
        if vendor == "NVIDIA":
            if nvml is None:
                nvml = nvml_driver_version() or ""
            entry["nvml_version"] = nvml or None
        out.append(entry)
    return out
