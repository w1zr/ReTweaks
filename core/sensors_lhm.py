# core/sensors_lhm.py
r"""Optional temperatures and fan speeds from LibreHardwareMonitor.

Windows has no standard API for CPU temperature, fan RPM or motherboard sensors; reading
them needs a kernel driver. RETWEAKS does NOT ship one. Instead it reads them from the free,
open source LibreHardwareMonitor (https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
when the user runs it. Two ways, tried in this order:

1. LHM's "Remote Web Server" (Options -> Remote Web Server -> Run), which serves
   http://localhost:8085/data.json. This is the only way for LHM v0.9.5 and newer:
   those versions REMOVED the WMI provider (commit aaf65f5, "Add .NET 10 build").
2. The WMI namespace root\LibreHardwareMonitor, published by LHM v0.9.4 and older
   (and root\OpenHardwareMonitor by the old OpenHardwareMonitor).

If neither is available, read() returns None and the UI says so.

Combined app (2026-10-22, owner request): the base app's v1.5 bundled LibreHardwareMonitor 0.9.6 sensor host
(ai/sensors/SensorHost.exe, run by temperatures.Temperatures) is tried first, so temperatures and fan speeds
show without the user running LHM. Its readings come from the same LHM library; CPU/motherboard sensors still
need the PawnIO driver the user installs.
"""

import json
import time
import urllib.request

from core.winutil import IS_WINDOWS

LHM_HTTP_URL = "http://127.0.0.1:8085/data.json"  # LHM's default port

NAMESPACES = (("LibreHardwareMonitor", r"root\LibreHardwareMonitor"),
              ("OpenHardwareMonitor", r"root\OpenHardwareMonitor"))
RETRY_SECONDS = 15  # how often to check again whether the user has started it

CPU_TEMP_PRIORITY = ("cpu package", "core (tctl/tdie)", "core (tctl)", "tdie", "tctl",
                     "core max", "core average", "cpu cores", "cpu")


def _plausible_temp(v):
    return v is not None and 0 < v < 150


def _kind(hardware_type):
    t = (hardware_type or "").lower()
    if t == "cpu":
        return "cpu"
    if t.startswith("gpu"):
        return "gpu"
    if t in ("superio", "motherboard", "mainboard", "embeddedcontroller"):
        return "board"
    if t in ("storage", "hdd"):
        return "storage"
    return t


def parse_lhm(hardware_rows, sensor_rows, source="LibreHardwareMonitor"):
    """Turn raw WMI rows into the sensors the UI shows. Pure function (unit tested)."""
    hw = {h.get("Identifier"): h for h in hardware_rows}
    result = {"source": source, "cpu_temp": None, "gpu_temps": {}, "fans": [],
              "board_temps": [], "storage_temps": {}}
    cpu_temps = {}

    for s in sensor_rows:
        value = s.get("Value")
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        parent = hw.get(s.get("Parent"), {})
        kind = _kind(parent.get("HardwareType"))
        stype = (s.get("SensorType") or "").lower()
        name = s.get("Name") or ""

        if stype == "temperature":
            if not _plausible_temp(value):
                continue
            if kind == "cpu":
                cpu_temps[name.lower()] = value
            elif kind == "gpu":
                g = result["gpu_temps"].setdefault(parent.get("Name") or "GPU", {})
                lname = name.lower()
                if "hot spot" in lname or "hotspot" in lname:
                    g["hotspot"] = value
                elif "memory" in lname:
                    g["memory"] = value
                elif "core" in lname or lname == "gpu":
                    g["core"] = value
                else:
                    g.setdefault("other", value)
            elif kind == "board":
                result["board_temps"].append({"name": name, "celsius": value})
            elif kind == "storage":
                result["storage_temps"].setdefault(parent.get("Name") or "Drive", value)
        elif stype == "fan" and value > 0:
            result["fans"].append({"name": f"{parent.get('Name') or ''} {name}".strip(), "rpm": value})

    for g in result["gpu_temps"].values():
        other = g.pop("other", None)
        if "core" not in g and other is not None:
            g["core"] = other

    for key in CPU_TEMP_PRIORITY:
        if key in cpu_temps:
            result["cpu_temp"] = cpu_temps[key]
            break
    else:
        if cpu_temps:
            result["cpu_temp"] = max(cpu_temps.values())

    return result


_BUNDLED = None            # temperatures.Temperatures from the app (set_bundled_provider)
BUNDLED_SOURCE = "LibreHardwareMonitor (built in)"
_PART_TYPE = {"CPU": "Cpu", "GPU": "GpuNvidia", "Motherboard": "Motherboard", "Storage": "Storage",
              "Memory": "Memory"}


def set_bundled_provider(provider):
    """provider: an object with .extended (temperature rows), .fans and .extended_time (time.monotonic())."""
    global _BUNDLED
    _BUNDLED = provider


def bundled_to_lhm(rows, fans, source=BUNDLED_SOURCE):
    """Sensor-host rows ({part, hardware, name 'HW / sensor', c}) and fans ({name, hardware, rpm}) -> the same
    dict parse_lhm returns. Pure function (unit tested)."""
    hardware, sensors = {}, []
    for r in rows or []:
        hw = str(r.get("hardware") or str(r.get("name", "")).split(" / ")[0] or r.get("part") or "Hardware")
        hardware.setdefault(hw, {"Identifier": hw, "Name": hw, "HardwareType": _PART_TYPE.get(r.get("part"), "Motherboard")})
        sensors.append({"Name": str(r.get("name", "")).split(" / ", 1)[-1], "SensorType": "Temperature",
                        "Value": r.get("c"), "Parent": hw})
    for f in fans or []:
        hw = str(f.get("hardware") or "Fan controller")
        is_gpu = "gpu" in (str(f.get("id", "")) + hw + str(f.get("name", ""))).lower()
        hardware.setdefault(hw, {"Identifier": hw, "Name": hw, "HardwareType": "GpuNvidia" if is_gpu else "Motherboard"})
        sensors.append({"Name": f.get("name") or "Fan", "SensorType": "Fan", "Value": f.get("rpm"), "Parent": hw})
    if not sensors:
        return None
    return parse_lhm(list(hardware.values()), sensors, source)


def read_bundled(max_age=15.0):
    p = _BUNDLED
    if p is None or time.monotonic() - (getattr(p, "extended_time", 0) or 0) > max_age:
        return None
    try:
        return bundled_to_lhm(list(getattr(p, "extended", None) or []), list(getattr(p, "fans", None) or []))
    except Exception:
        return None


def _kind_from_id(hardware_id):
    """LHM web JSON has no hardware type field; derive it from the identifier, e.g.
    /amdcpu/0, /intelcpu/0, /gpu-nvidia/0, /gpu-amd/0, /lpc/nct6798d, /nvme/0, /hdd/1."""
    first = (hardware_id or "").lower().strip("/").split("/")[0]
    if "cpu" in first:
        return "Cpu"
    if first.startswith("gpu"):
        return "Gpu"
    if first in ("lpc", "motherboard", "mainboard", "ec"):
        return "SuperIO"
    if first in ("nvme", "hdd", "ssd", "storage", "ata"):
        return "Storage"
    return "Other"


def _number(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):  # older LHM: formatted text like "45.0 °C" or "1,150 RPM"
        num = "".join(ch for ch in v.split(" ")[0] if ch.isdigit() or ch in ".-")
        try:
            return float(num)
        except ValueError:
            return None
    return None


def flatten_lhm_json(tree):
    """Turn LHM's data.json node tree into (hardware_rows, sensor_rows) for parse_lhm()."""
    hardware, sensors = [], []

    def walk(node, parent_hw):
        hw_id = node.get("HardwareId")
        if hw_id:
            hardware.append({"Identifier": hw_id, "Name": node.get("Text"),
                             "HardwareType": _kind_from_id(hw_id)})
            parent_hw = hw_id
        if node.get("SensorId") and node.get("Type"):
            raw = node.get("RawValue")
            value = raw if raw is not None else node.get("Value")
            sensors.append({"Name": node.get("Text"), "SensorType": node.get("Type"),
                            "Value": _number(value), "Parent": parent_hw})
        for child in node.get("Children") or []:
            walk(child, parent_hw)

    walk(tree or {}, None)
    return hardware, sensors


def read_lhm_http(url=LHM_HTTP_URL, timeout=0.6):
    """Read LHM's web server. Returns parsed sensors or None (not running / not enabled)."""
    try:
        # No proxy: some PCs have a system proxy that would intercept localhost requests
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=timeout) as resp:
            tree = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None
    hardware, sensors = flatten_lhm_json(tree)
    if not hardware:
        return None
    return parse_lhm(hardware, sensors, "LibreHardwareMonitor (web server)")


class LhmReader:
    """Reads LibreHardwareMonitor's WMI sensors. Create and use it on ONE thread."""

    def __init__(self):
        self._service = None
        self._source = None
        self._next_try = 0.0
        self._com_ready = False

    def _connect(self):
        import pythoncom
        import win32com.client
        if not self._com_ready:
            pythoncom.CoInitialize()
            self._com_ready = True
        for source, ns in NAMESPACES:
            try:
                svc = win32com.client.GetObject(f"winmgmts:\\\\.\\{ns}")
                # The namespace can exist but be empty after LHM closes; check for hardware
                if len(list(svc.ExecQuery("SELECT Identifier FROM Hardware"))) > 0:
                    self._service, self._source = svc, source
                    return True
            except Exception:
                continue
        return False

    def read(self):
        if not IS_WINDOWS:
            return None
        # 0) The bundled sensor host (combined app), when it is running and fresh
        result = read_bundled()
        if result:
            return result
        # 1) Web server (LHM v0.9.5+). Local and fast, so it's tried every time.
        result = read_lhm_http()
        if result:
            return result
        # 2) WMI (LHM v0.9.4 and older, OpenHardwareMonitor)
        now = time.monotonic()
        if self._service is None:
            if now < self._next_try:
                return None
            self._next_try = now + RETRY_SECONDS
            try:
                if not self._connect():
                    return None
            except Exception:
                return None
        try:
            hardware = [{"Identifier": h.Identifier, "Name": h.Name, "HardwareType": h.HardwareType}
                        for h in self._service.ExecQuery(
                            "SELECT Identifier, Name, HardwareType FROM Hardware")]
            sensors = [{"Name": s.Name, "SensorType": s.SensorType, "Value": s.Value, "Parent": s.Parent}
                       for s in self._service.ExecQuery(
                           "SELECT Name, SensorType, Value, Parent FROM Sensor "
                           "WHERE SensorType='Temperature' OR SensorType='Fan'")]
            if not hardware:
                raise RuntimeError("LibreHardwareMonitor stopped")
            return parse_lhm(hardware, sensors, self._source)
        except Exception:
            # LHM was closed; try to reconnect later
            self._service = None
            self._next_try = now + RETRY_SECONDS
            return None
