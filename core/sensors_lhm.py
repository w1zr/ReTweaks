# core/sensors_lhm.py
"""Optional temperatures and fan speeds from LibreHardwareMonitor.

Windows has no standard API for CPU temperature, fan RPM or motherboard sensors; reading
them needs a kernel driver. RyTweaks does NOT ship one. Instead, if the user runs the free,
open source LibreHardwareMonitor (https://github.com/LibreHardwareMonitor/LibreHardwareMonitor),
it publishes every sensor to WMI and RyTweaks reads them from there.

If LibreHardwareMonitor isn't running, read() returns None and the UI says so.
The older OpenHardwareMonitor publishes the same layout and is also supported.
"""

import time

from core.winutil import IS_WINDOWS

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
