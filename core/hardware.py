# core/hardware.py
"""Static hardware inventory (things that don't change while the app runs).

Everything is collected with ONE PowerShell call plus DXGI for the GPU list, instead of
launching PowerShell once per component. Values that Windows does not expose on a given
PC are returned as None, and the UI shows "Unavailable". Nothing here
guesses or hardcodes a value for a specific model.

Live values (loads, clocks, temps) are in core/telemetry.py.
"""

import platform
import psutil

from core import gpu_dxgi
from core.winutil import IS_WINDOWS, run_powershell_json, as_list, is_admin

UNAVAILABLE = None  # the UI turns None into "Unavailable"

# SMBIOS memory type codes (Win32_PhysicalMemory.SMBIOSMemoryType), from the SMBIOS spec.
SMBIOS_MEMORY_TYPES = {
    18: "DDR", 19: "DDR2", 20: "DDR2 FB-DIMM", 24: "DDR3", 26: "DDR4", 27: "LPDDR",
    28: "LPDDR2", 29: "LPDDR3", 30: "LPDDR4", 34: "DDR5", 35: "LPDDR5",
}

# Board serial numbers are deliberately NOT collected: users attach hardware reports to
# public GitHub issues, and a serial number identifies their exact PC.
_STATIC_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$r = [ordered]@{}

try { $r.os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture } catch {}
try { $r.computer = Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer, Model, SystemType } catch {}
try { $r.cpu = @(Get-CimInstance Win32_Processor | Select-Object Name, Manufacturer, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, L2CacheSize, L3CacheSize, SocketDesignation, VirtualizationFirmwareEnabled) } catch {}
try { $r.board = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product } catch {}
try { $r.bios = Get-CimInstance Win32_BIOS | Select-Object Manufacturer, SMBIOSBIOSVersion, @{n='ReleaseDate';e={ if ($_.ReleaseDate) { $_.ReleaseDate.ToString('yyyy-MM-dd') } }} } catch {}
try { $r.ram_sticks = @(Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, Speed, ConfiguredClockSpeed, SMBIOSMemoryType, Manufacturer, PartNumber, DeviceLocator, BankLabel) } catch {}
try { $r.ram_slots = (Get-CimInstance Win32_PhysicalMemoryArray | Measure-Object -Property MemoryDevices -Sum).Sum } catch {}
try { $r.video = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, @{n='DriverDate';e={ if ($_.DriverDate) { $_.DriverDate.ToString('yyyy-MM-dd') } }}, PNPDeviceID, CurrentHorizontalResolution, CurrentVerticalResolution, CurrentRefreshRate) } catch {}
try {
  $r.disks = @(Get-PhysicalDisk | Select-Object DeviceId, FriendlyName, Size,
    @{n='MediaType';e={"$($_.MediaType)"}}, @{n='BusType';e={"$($_.BusType)"}}, @{n='Health';e={"$($_.HealthStatus)"}})
} catch {}
try { $r.partitions = @(Get-Partition | Where-Object DriveLetter | Select-Object DiskNumber, @{n='DriveLetter';e={"$($_.DriveLetter)"}}) } catch {}
try {
  $r.monitors = @(Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorID | ForEach-Object {
    [PSCustomObject]@{
      Name = (($_.UserFriendlyName | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ }) -join '')
      Maker = (($_.ManufacturerName | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ }) -join '')
      Year = $_.YearOfManufacture
    } })
} catch {}
try { $r.audio = @(Get-CimInstance Win32_SoundDevice | Select-Object Name, Manufacturer, Status) } catch {}
try { $r.net = @(Get-NetAdapter | Where-Object { $_.HardwareInterface } | Select-Object Name, InterfaceDescription, @{n='Status';e={"$($_.Status)"}}, LinkSpeed) } catch {}

$r | ConvertTo-Json -Depth 4 -Compress
"""


def _clean(value):
    """Trim strings and turn empty / placeholder values into None."""
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if not v or v.lower() in {"to be filled by o.e.m.", "default string", "system product name",
                                  "system manufacturer", "not applicable", "none", "unknown"}:
            return None
        return v
    return value


def _gb(num_bytes, digits=1):
    if not num_bytes:
        return None
    return round(float(num_bytes) / (1024 ** 3), digits)


def parse_static(raw):
    """Turn the PowerShell JSON (dict) into the structure the UI uses.

    Kept separate from the PowerShell call so it can be unit tested with saved output
    from different PCs (see tests/).
    """
    raw = raw or {}
    out = {}

    os_info = raw.get("os") or {}
    out["os"] = {
        "name": _clean(os_info.get("Caption")) or f"{platform.system()} {platform.release()}",
        "version": _clean(os_info.get("Version")) or platform.version(),
        "build": _clean(os_info.get("BuildNumber")),
        "arch": _clean(os_info.get("OSArchitecture")) or platform.machine(),
    }

    comp = raw.get("computer") or {}
    out["computer"] = {
        "manufacturer": _clean(comp.get("Manufacturer")),
        "model": _clean(comp.get("Model")),
    }

    cpus = as_list(raw.get("cpu"))
    cpu = cpus[0] if cpus else {}
    l2 = cpu.get("L2CacheSize")  # KB
    l3 = cpu.get("L3CacheSize")  # KB
    out["cpu"] = {
        "name": _clean(cpu.get("Name")) or _clean(platform.processor()),
        "manufacturer": _clean(cpu.get("Manufacturer")),
        "sockets": len(cpus) or 1,
        "cores": sum(int(c.get("NumberOfCores") or 0) for c in cpus) or psutil.cpu_count(logical=False),
        "threads": sum(int(c.get("NumberOfLogicalProcessors") or 0) for c in cpus) or psutil.cpu_count(logical=True),
        "base_mhz": cpu.get("MaxClockSpeed") or None,
        "l2_mb": round(l2 / 1024, 1) if l2 else None,
        "l3_mb": round(l3 / 1024, 1) if l3 else None,
        "socket": _clean(cpu.get("SocketDesignation")),
        "virtualization": (None if cpu.get("VirtualizationFirmwareEnabled") is None
                           else ("Enabled" if cpu.get("VirtualizationFirmwareEnabled") else "Disabled")),
    }

    board = raw.get("board") or {}
    bios = raw.get("bios") or {}
    out["motherboard"] = {
        "manufacturer": _clean(board.get("Manufacturer")),
        "model": _clean(board.get("Product")),
        "bios_vendor": _clean(bios.get("Manufacturer")),
        "bios_version": _clean(bios.get("SMBIOSBIOSVersion")),
        "bios_date": _clean(bios.get("ReleaseDate")),
    }

    sticks = []
    for s in as_list(raw.get("ram_sticks")):
        type_code = s.get("SMBIOSMemoryType")
        sticks.append({
            "slot": _clean(s.get("DeviceLocator")) or _clean(s.get("BankLabel")),
            "size_gb": _gb(s.get("Capacity"), 0),
            "type": SMBIOS_MEMORY_TYPES.get(type_code) if type_code else None,
            # Win32_PhysicalMemory reports these in MT/s (what RAM is sold as, e.g. DDR4-3200)
            "rated_mts": s.get("Speed") or None,
            "running_mts": s.get("ConfiguredClockSpeed") or None,
            "maker": _clean(s.get("Manufacturer")),
            "part": _clean(s.get("PartNumber")),
        })
    types = sorted({s["type"] for s in sticks if s["type"]})
    running = sorted({s["running_mts"] for s in sticks if s["running_mts"]})
    slots_total = raw.get("ram_slots")
    out["ram"] = {
        "total_gb": _gb(psutil.virtual_memory().total, 1),  # usable (some is reserved for iGPU/firmware)
        "installed_gb": sum(s["size_gb"] or 0 for s in sticks) or None,
        "type": "/".join(types) if types else None,
        # All sticks normally run at one speed; if Windows reports several, show the lowest
        "running_mts": running[0] if running else None,
        "sticks": sticks,
        "slots_used": len(sticks) or None,
        # Some laptops/VMs report 0 or nonsense; only trust it if it's >= sticks found
        "slots_total": slots_total if slots_total and slots_total >= len(sticks) else None,
    }

    # Storage: physical disks + which drive letters live on them
    letters = {}
    for p in as_list(raw.get("partitions")):
        letters.setdefault(str(p.get("DiskNumber")), []).append(f"{p.get('DriveLetter')}:")
    disks = []
    for d in as_list(raw.get("disks")):
        dev_id = str(d.get("DeviceId"))
        media = _clean(d.get("MediaType"))
        disks.append({
            "name": _clean(d.get("FriendlyName")) or f"Disk {dev_id}",
            "size_gb": _gb(d.get("Size"), 0),
            "media": None if media == "Unspecified" else media,
            "bus": _clean(d.get("BusType")),
            "health": _clean(d.get("Health")),  # Healthy / Warning / Unhealthy, straight from Windows
            "letters": sorted(letters.get(dev_id, [])),
        })
    out["disks"] = disks

    out["video_controllers"] = [{
        "name": _clean(v.get("Name")),
        "driver_version": _clean(v.get("DriverVersion")),
        "driver_date": _clean(v.get("DriverDate")),
        "pnp_id": _clean(v.get("PNPDeviceID")),
    } for v in as_list(raw.get("video"))]

    out["monitors"] = [{
        "name": _clean(m.get("Name")),
        "maker": _clean(m.get("Maker")),
        "year": m.get("Year") or None,
    } for m in as_list(raw.get("monitors"))]

    out["audio"] = [{
        "name": _clean(a.get("Name")),
        "manufacturer": _clean(a.get("Manufacturer")),
        "status": _clean(a.get("Status")),
    } for a in as_list(raw.get("audio"))]

    out["network"] = [{
        "name": _clean(n.get("Name")),
        "description": _clean(n.get("InterfaceDescription")),
        "status": _clean(n.get("Status")),
        "link_speed": _clean(n.get("LinkSpeed")),
    } for n in as_list(raw.get("net"))]

    return out


def merge_gpus(dxgi_adapters, video_controllers):
    """Combine the DXGI GPU list (correct 64-bit VRAM, any vendor) with driver info from WMI."""
    gpus = []
    unused = list(video_controllers or [])
    for a in gpu_dxgi.unique_adapters(dxgi_adapters or []):
        match = None
        for v in unused:
            if v.get("name") and v["name"].lower() == a["name"].lower():
                match = v
                break
        if match:
            unused.remove(match)
        gpus.append({
            **a,
            "driver_version": (match or {}).get("driver_version"),
            "driver_date": (match or {}).get("driver_date"),
        })
    if not gpus:
        # DXGI unavailable (very old Windows / remote session): fall back to WMI names only.
        # VRAM is left unknown on purpose: WMI's AdapterRAM is capped at 4 GB.
        for v in gpu_dxgi.unique_adapters(video_controllers or []):
            if not v.get("name"):
                continue
            gpus.append({
                "name": v["name"], "vendor": gpu_dxgi.vendor_from_name(v["name"]),
                "vram_gb": None, "luid": None,
                "driver_version": v.get("driver_version"), "driver_date": v.get("driver_date"),
            })
    return gpus


def scan_static():
    """Collect all static hardware info. Slow (1–5 s): call it from a worker thread."""
    raw = run_powershell_json(_STATIC_SCRIPT, timeout=60) if IS_WINDOWS else None
    data = parse_static(raw if isinstance(raw, dict) else {})
    data["gpus"] = merge_gpus(gpu_dxgi.list_adapters(), data["video_controllers"])
    data["is_admin"] = is_admin()
    return data


def get_system_info():
    """Kept for compatibility with older code."""
    return {
        'system': platform.system(),
        'release': platform.release(),
        'version': platform.version(),
        'machine': platform.machine(),
        'node': platform.node(),
        'processor': platform.processor(),
        'is_admin': is_admin(),
    }
