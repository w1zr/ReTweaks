# core/telemetry.py
"""Live readings: CPU/GPU load, clocks, VRAM use, RAM, disk and network speed, sensors.

Sources (best available is used, and the UI shows which one):
- GPU load + VRAM in use: Windows "GPU Engine" / "GPU Adapter Memory" performance counters.
  Task Manager uses the same counters, so the numbers match it on NVIDIA, AMD and Intel.
  (Windows 10 1709 or newer.)
- NVIDIA extras (temperature, clocks, power, fan): NVML, which ships with every NVIDIA driver.
- CPU clock: "% Processor Performance" x "Processor Frequency" counters, like Task Manager.
  psutil.cpu_freq() is NOT used for this on Windows: it only returns the fixed base clock.
- CPU/GPU temps and fans for every brand: LibreHardwareMonitor, if the user runs it.

Counters are added with their English names (PdhAddEnglishCounter), so this also works on
Windows installed in other languages, where counter names are translated.

Nothing is ever estimated. If a value can't be read it is None.
"""

import re
import time

import psutil

from core import gpu_dxgi
from core.sensors_lhm import LhmReader
from core.winutil import IS_WINDOWS

try:
    import win32pdh  # from pywin32
except ImportError:
    win32pdh = None

try:
    import pynvml  # from nvidia-ml-py
except ImportError:
    pynvml = None


# ---------------------------------------------------------------- pure helpers (unit tested)

_ENGINE_RE = re.compile(
    r"luid_0x([0-9a-f]+)_0x([0-9a-f]+)_phys_(\d+)_eng_(\d+)_engtype_(.*)$", re.IGNORECASE)
_ADAPTER_RE = re.compile(r"luid_0x([0-9a-f]+)_0x([0-9a-f]+)_phys_(\d+)", re.IGNORECASE)


def _norm_luid(high_hex, low_hex):
    return gpu_dxgi.luid_key(int(high_hex, 16), int(low_hex, 16))


def aggregate_gpu_engines(instances):
    """Per-GPU load from "GPU Engine(*)\\Utilization Percentage" instances.

    Each instance is one process on one engine of one GPU, e.g.
      pid_1234_luid_0x00000000_0x0000D1A3_phys_0_eng_0_engtype_3D
    Like Task Manager: add up all processes per engine, then the GPU's load is its busiest
    engine. Returns {luid: {"load": 0-100, "engine": "3D"}}.
    """
    per_engine = {}
    for name, value in instances.items():
        m = _ENGINE_RE.search(name)
        if not m or value is None:
            continue
        luid = _norm_luid(m.group(1), m.group(2))
        key = (luid, int(m.group(3)), int(m.group(4)))
        entry = per_engine.setdefault(key, [0.0, m.group(5)])
        entry[0] += float(value)

    gpus = {}
    for (luid, _phys, _eng), (total, engtype) in per_engine.items():
        total = min(total, 100.0)
        best = gpus.get(luid)
        if best is None or total > best["load"]:
            gpus[luid] = {"load": round(total, 1), "engine": engtype}
    return gpus


def aggregate_gpu_memory(instances):
    """{luid: bytes} from "GPU Adapter Memory(*)\\Dedicated Usage" instances."""
    out = {}
    for name, value in instances.items():
        m = _ADAPTER_RE.search(name)
        if not m or value is None:
            continue
        luid = _norm_luid(m.group(1), m.group(2))
        out[luid] = out.get(luid, 0.0) + float(value)
    return out


def cpu_mhz_from_counters(base_mhz, perf_percent):
    """Live CPU clock the way Task Manager calculates it."""
    if not base_mhz or perf_percent is None:
        return None
    return round(base_mhz * perf_percent / 100.0)


# ---------------------------------------------------------------- Windows performance counters

class _Pdh:
    COUNTERS = {
        "cpu_perf": r"\Processor Information(_Total)\% Processor Performance",
        "cpu_base": r"\Processor Information(_Total)\Processor Frequency",
        "gpu_engine": r"\GPU Engine(*)\Utilization Percentage",
        "gpu_mem": r"\GPU Adapter Memory(*)\Dedicated Usage",
    }
    WILDCARD = {"gpu_engine", "gpu_mem"}

    def __init__(self):
        self.query = None
        self.handles = {}
        if not (IS_WINDOWS and win32pdh):
            return
        try:
            self.query = win32pdh.OpenQuery()
        except Exception:
            self.query = None
            return
        add = getattr(win32pdh, "AddEnglishCounter", None) or win32pdh.AddCounter
        for key, path in self.COUNTERS.items():
            try:
                self.handles[key] = add(self.query, path)
            except Exception:
                pass  # e.g. GPU counters on Windows 10 older than 1709
        try:
            win32pdh.CollectQueryData(self.query)  # rate counters need a first sample
        except Exception:
            pass

    @property
    def available(self):
        return bool(self.handles)

    def has(self, key):
        return key in self.handles

    def collect(self):
        if not self.query:
            return {}
        try:
            win32pdh.CollectQueryData(self.query)
        except Exception:
            return {}
        values = {}
        for key, handle in self.handles.items():
            try:
                if key in self.WILDCARD:
                    values[key] = win32pdh.GetFormattedCounterArray(handle, win32pdh.PDH_FMT_DOUBLE)
                else:
                    values[key] = win32pdh.GetFormattedCounterValue(handle, win32pdh.PDH_FMT_DOUBLE)[1]
            except Exception:
                values[key] = None
        return values


# ---------------------------------------------------------------- NVIDIA (NVML)

class _Nvml:
    def __init__(self):
        self.devices = []
        if not pynvml:
            return
        try:
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(h)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", "replace")
                self.devices.append((name, h))
        except Exception:
            self.devices = []  # no NVIDIA GPU or driver: completely normal

    def read(self, handle):
        def safe(fn, *args):
            try:
                return fn(handle, *args)
            except Exception:
                return None
        util = safe(pynvml.nvmlDeviceGetUtilizationRates)
        mem = safe(pynvml.nvmlDeviceGetMemoryInfo)
        power = safe(pynvml.nvmlDeviceGetPowerUsage)
        return {
            "load": float(util.gpu) if util else None,
            "temp_c": safe(pynvml.nvmlDeviceGetTemperature, pynvml.NVML_TEMPERATURE_GPU),
            "core_mhz": safe(pynvml.nvmlDeviceGetClockInfo, pynvml.NVML_CLOCK_GRAPHICS),
            "mem_mhz": safe(pynvml.nvmlDeviceGetClockInfo, pynvml.NVML_CLOCK_MEM),
            "power_w": round(power / 1000.0, 1) if power is not None else None,
            "fan_pct": safe(pynvml.nvmlDeviceGetFanSpeed),
            "vram_used_gb": round(mem.used / 1024 ** 3, 2) if mem else None,
            "vram_total_gb": round(mem.total / 1024 ** 3, 1) if mem else None,
        }


def _match_nvml(adapters, nvml_devices):
    """Pair NVML devices with DXGI adapters by name, in order. Returns {luid: handle}."""
    remaining = list(nvml_devices)
    pairs = {}
    for a in adapters:
        if a.get("vendor") != "NVIDIA":
            continue
        for item in remaining:
            if item[0].lower() == a["name"].lower():
                pairs[a["luid"]] = item[1]
                remaining.remove(item)
                break
    # Two identical NVIDIA cards: we can't tell which NVML device is which DXGI adapter
    # without PCI bus IDs, so don't pair them (showing card A's temperature on card B
    # would be wrong data). Load/VRAM still come from the Windows counters.
    names = [a["name"].lower() for a in adapters if a.get("vendor") == "NVIDIA"]
    if len(names) != len(set(names)):
        return {}
    return pairs


# ---------------------------------------------------------------- public API

class Telemetry:
    """Create once on a worker thread and call sample() about once a second."""

    def __init__(self, gpu_adapters=None):
        self.adapters = gpu_adapters if gpu_adapters is not None else gpu_dxgi.list_adapters()
        self.pdh = _Pdh()
        self.nvml = _Nvml()
        self.nvml_by_luid = _match_nvml(self.adapters, self.nvml.devices)
        self.lhm = LhmReader()
        self._last_lhm = None
        self._last_lhm_time = 0.0
        self._last_io = None
        psutil.cpu_percent(percpu=True)  # first call primes the counters

    def _rates(self):
        now = time.monotonic()
        try:
            disk = psutil.disk_io_counters()
        except Exception:
            disk = None
        try:
            net = psutil.net_io_counters()
        except Exception:
            net = None
        rates = {"disk_read_bps": None, "disk_write_bps": None, "net_down_bps": None, "net_up_bps": None}
        if self._last_io:
            t0, d0, n0 = self._last_io
            dt = max(now - t0, 1e-3)
            if disk and d0:
                rates["disk_read_bps"] = max(disk.read_bytes - d0.read_bytes, 0) / dt
                rates["disk_write_bps"] = max(disk.write_bytes - d0.write_bytes, 0) / dt
            if net and n0:
                rates["net_down_bps"] = max(net.bytes_recv - n0.bytes_recv, 0) / dt
                rates["net_up_bps"] = max(net.bytes_sent - n0.bytes_sent, 0) / dt
        self._last_io = (now, disk, net)
        return rates

    def sample(self):
        counters = self.pdh.collect()
        per_core = psutil.cpu_percent(percpu=True)
        vm = psutil.virtual_memory()

        # CPU clock
        mhz, mhz_source = None, None
        if counters.get("cpu_perf") is not None and counters.get("cpu_base"):
            mhz = cpu_mhz_from_counters(counters["cpu_base"], counters["cpu_perf"])
            mhz_source = "Windows performance counters"
        elif not IS_WINDOWS:
            f = psutil.cpu_freq()
            if f and f.current:
                mhz, mhz_source = round(f.current), "psutil"

        # Sensors from LibreHardwareMonitor: WMI is slower, so read every 2 s
        now = time.monotonic()
        if now - self._last_lhm_time >= 2.0:
            self._last_lhm = self.lhm.read()
            self._last_lhm_time = now
        lhm = self._last_lhm

        raw_engines = counters.get("gpu_engine")  # None = counter couldn't be read this second
        engines = aggregate_gpu_engines(raw_engines) if isinstance(raw_engines, dict) else {}
        gpu_mem = aggregate_gpu_memory(counters.get("gpu_mem") or {})
        gpus = []
        for a in self.adapters:
            g = {"luid": a["luid"], "name": a["name"], "vendor": a.get("vendor"),
                 "vram_total_gb": a.get("vram_gb"), "load": None, "load_source": None,
                 "engine": None, "vram_used_gb": None, "temp_c": None, "temp_source": None,
                 "hotspot_c": None, "core_mhz": None, "mem_mhz": None, "power_w": None, "fan_pct": None}
            if isinstance(raw_engines, dict):
                e = engines.get(a["luid"])
                # Counter set exists but this GPU has no active engines right now = idle
                g["load"] = e["load"] if e else 0.0
                g["engine"] = e["engine"] if e else None
                g["load_source"] = "Windows GPU counters"
            if a["luid"] in gpu_mem:
                g["vram_used_gb"] = round(gpu_mem[a["luid"]] / 1024 ** 3, 2)
            handle = self.nvml_by_luid.get(a["luid"])
            if handle is not None:
                n = self.nvml.read(handle)
                for k in ("core_mhz", "mem_mhz", "power_w", "fan_pct"):
                    g[k] = n[k]
                if n["temp_c"] is not None:
                    g["temp_c"], g["temp_source"] = n["temp_c"], "NVIDIA driver"
                if g["load"] is None and n["load"] is not None:
                    g["load"], g["load_source"] = n["load"], "NVIDIA driver"
                if g["vram_used_gb"] is None:
                    g["vram_used_gb"] = n["vram_used_gb"]
            if lhm:
                t = _match_lhm_gpu(a["name"], lhm["gpu_temps"])
                if t:
                    if g["temp_c"] is None and t.get("core") is not None:
                        g["temp_c"], g["temp_source"] = round(t["core"], 1), lhm["source"]
                    g["hotspot_c"] = t.get("hotspot")
            gpus.append(g)

        return {
            "time": time.time(),
            "cpu": {
                "load": round(sum(per_core) / len(per_core), 1) if per_core else psutil.cpu_percent(),
                "per_core": per_core,
                "mhz": mhz,
                "mhz_source": mhz_source,
                "temp_c": round(lhm["cpu_temp"], 1) if lhm and lhm.get("cpu_temp") is not None else None,
            },
            "ram": {
                "percent": vm.percent,
                "used_gb": round((vm.total - vm.available) / 1024 ** 3, 1),
                "total_gb": round(vm.total / 1024 ** 3, 1),
            },
            "gpus": gpus,
            "io": self._rates(),
            "sensors": lhm,  # None = LibreHardwareMonitor not running
        }

    def sources(self):
        """What this PC supports. Shown on the Hardware page and in the hardware report."""
        return {
            "windows_counters": self.pdh.available,
            "gpu_counters": self.pdh.has("gpu_engine"),
            "nvml_gpus": len(self.nvml.devices),
            "lhm": self._last_lhm["source"] if self._last_lhm else None,
        }


def _match_lhm_gpu(adapter_name, gpu_temps):
    if not gpu_temps:
        return None
    name = adapter_name.lower()
    for hw_name, temps in gpu_temps.items():
        h = hw_name.lower()
        if h == name or h in name or name in h:
            return temps
    return None
