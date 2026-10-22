# core/etw_frames.py
"""Built-in frame timing for the FPS overlay (v1.4.3): no PresentMon needed.

Windows logs an event every time a program presents a frame (Event Tracing for Windows, ETW).
RETWEAKS starts its own real-time trace session, listens for those events and measures the time
between one frame and the next, for the game you picked. Nothing is injected into the game; this
is the same Windows data PresentMon reads.

Events used (IDs from Intel PresentMon's published ETW headers, PresentData/ETW/*.h):
  Microsoft-Windows-DXGI    {CA11C036-0102-4A2D-A6AD-F03CFED5D3C9}  Present_Start 42,
                                                                       PresentMultiplaneOverlay_Start 55
  Microsoft-Windows-D3D9    {783ACA0A-790E-4D7F-8451-AA850511C6B9}  Present_Start 1
  Microsoft-Windows-DxgKrnl {802EC45A-1E99-4B83-9920-87C98277BA9D}  Present_Info 184
DirectX 9/10/11/12 games give DXGI or D3D9 events. For other games (OpenGL, some Vulkan) the
graphics kernel's Present_Info is used instead and the overlay says so ("kernel").

What is measured: time between presents (what PresentMon calls MsBetweenPresents), i.e. how
often the game hands a frame to Windows. It does not measure when the frame reached the screen.
Needs administrator rights (RETWEAKS runs as admin).
"""

import ctypes
import sys
import threading
import time
from ctypes import POINTER, Structure, c_int32, c_int64, c_uint8, c_uint16, c_uint32, c_uint64, c_void_p

from core.overlay_fps import STALE_S, RollingMetrics, process_running

SESSION_NAME = "RETWEAKS_frames"
GAP_RESET_MS = 1000.0          # a pause longer than this (loading, alt-tab) is not a frame
API_PREFERRED_S = 2.0          # if a process sent DXGI/D3D9 presents recently, ignore its kernel ones

# ---------------------------------------------------------------- providers and events


class GUID(Structure):
    _fields_ = [("Data1", c_uint32), ("Data2", c_uint16), ("Data3", c_uint16), ("Data4", c_uint8 * 8)]

    @classmethod
    def parse(cls, text):
        h = text.strip("{}").replace("-", "")
        g = cls()
        g.Data1 = int(h[0:8], 16)
        g.Data2 = int(h[8:12], 16)
        g.Data3 = int(h[12:16], 16)
        for i in range(8):
            g.Data4[i] = int(h[16 + 2 * i:18 + 2 * i], 16)
        return g

    def key(self):
        return (self.Data1, self.Data2, self.Data3, bytes(self.Data4))


DXGI = "{CA11C036-0102-4A2D-A6AD-F03CFED5D3C9}"
D3D9 = "{783ACA0A-790E-4D7F-8451-AA850511C6B9}"
DXGKRNL = "{802EC45A-1E99-4B83-9920-87C98277BA9D}"

# provider -> (source name, present event ids, keyword mask)
PROVIDERS = {
    DXGI: ("api", (42, 55), 0x8000000000000002),
    D3D9: ("api", (1,), 0x8000000000000002),
    DXGKRNL: ("kernel", (184,), 0x4000000008000001),
}
_BY_KEY = {GUID.parse(g).key(): (src, frozenset(ids)) for g, (src, ids, _kw) in PROVIDERS.items()}


def classify(provider_key, event_id):
    """'api' / 'kernel' when this event is a frame present, else None."""
    hit = _BY_KEY.get(provider_key)
    if hit and event_id in hit[1]:
        return hit[0]
    return None


# ---------------------------------------------------------------- frame aggregation (pure)
class FrameAggregator:
    """Turns present events (pid, source, timestamp in 100 ns units) into per-process frame times.
    Thread-safe. Time comes from the event timestamps, so delivery delays don't change the numbers."""

    def __init__(self):
        self._lock = threading.Lock()
        self._procs = {}       # pid -> dict(metrics, last_ts, api_seen_ts, source, wall, frames)

    def feed(self, pid, source, ts):
        with self._lock:
            p = self._procs.get(pid)
            if p is None:
                p = self._procs[pid] = {"metrics": RollingMetrics(), "last": {}, "api_ts": None,
                                        "source": source, "wall": None, "frames": 0}
            if source == "api":
                p["api_ts"] = ts
            elif p["api_ts"] is not None and (ts - p["api_ts"]) / 1e7 < API_PREFERRED_S:
                return      # DXGI/D3D9 already reports this process's frames; don't count twice
            last = p["last"].get(source)
            p["last"][source] = ts
            if last is None:
                return
            ms = (ts - last) / 1e4
            if ms <= 0 or ms > GAP_RESET_MS:
                return
            p["metrics"].add(ms)
            p["source"] = source
            p["wall"] = time.monotonic()
            p["frames"] += 1

    def snapshot(self, pids):
        """(metrics dict, source) for the busiest of `pids` with recent frames; (None, None) if none."""
        best = None
        with self._lock:
            now = time.monotonic()
            for pid in pids:
                p = self._procs.get(pid)
                if not p or p["wall"] is None or now - p["wall"] > STALE_S:
                    continue
                snap = p["metrics"].snapshot()
                if best is None or (snap["fps"] or 0) > (best[0]["fps"] or 0):
                    best = (snap, p["source"])
        return best if best else (None, None)

    def total_frames(self, pids):
        with self._lock:
            return sum(self._procs[p]["frames"] for p in pids if p in self._procs)

    def forget_except(self, pids):
        with self._lock:
            for pid in list(self._procs):
                if pid not in pids:
                    del self._procs[pid]


# ---------------------------------------------------------------- Windows ETW structures
# Fixed-width types only, so the layouts (and their sizes, checked in tests) match 64-bit Windows.

class WNODE_HEADER(Structure):
    _fields_ = [("BufferSize", c_uint32), ("ProviderId", c_uint32), ("HistoricalContext", c_uint64),
                ("TimeStamp", c_int64), ("Guid", GUID), ("ClientContext", c_uint32), ("Flags", c_uint32)]


class EVENT_TRACE_PROPERTIES(Structure):
    _fields_ = [("Wnode", WNODE_HEADER), ("BufferSize", c_uint32), ("MinimumBuffers", c_uint32),
                ("MaximumBuffers", c_uint32), ("MaximumFileSize", c_uint32), ("LogFileMode", c_uint32),
                ("FlushTimer", c_uint32), ("EnableFlags", c_uint32), ("AgeLimit", c_int32),
                ("NumberOfBuffers", c_uint32), ("FreeBuffers", c_uint32), ("EventsLost", c_uint32),
                ("BuffersWritten", c_uint32), ("LogBuffersLost", c_uint32), ("RealTimeBuffersLost", c_uint32),
                ("LoggerThreadId", c_void_p), ("LogFileNameOffset", c_uint32), ("LoggerNameOffset", c_uint32)]


class EVENT_DESCRIPTOR(Structure):
    _fields_ = [("Id", c_uint16), ("Version", c_uint8), ("Channel", c_uint8), ("Level", c_uint8),
                ("Opcode", c_uint8), ("Task", c_uint16), ("Keyword", c_uint64)]


class EVENT_HEADER(Structure):
    _fields_ = [("Size", c_uint16), ("HeaderType", c_uint16), ("Flags", c_uint16), ("EventProperty", c_uint16),
                ("ThreadId", c_uint32), ("ProcessId", c_uint32), ("TimeStamp", c_int64), ("ProviderId", GUID),
                ("EventDescriptor", EVENT_DESCRIPTOR), ("ProcessorTime", c_uint64), ("ActivityId", GUID)]


class EVENT_RECORD(Structure):
    _fields_ = [("EventHeader", EVENT_HEADER), ("ProcessorNumber", c_uint8), ("Alignment", c_uint8),
                ("LoggerId", c_uint16), ("ExtendedDataCount", c_uint16), ("UserDataLength", c_uint16),
                ("ExtendedData", c_void_p), ("UserData", c_void_p), ("UserContext", c_void_p)]


class EVENT_TRACE_LOGFILEW(Structure):
    # CurrentEvent (EVENT_TRACE, 88 bytes) and LogfileHeader (TRACE_LOGFILE_HEADER, 280 bytes) are
    # output-only here, so they are kept as raw bytes.
    _fields_ = [("LogFileName", c_void_p), ("LoggerName", c_void_p), ("CurrentTime", c_int64),
                ("BuffersRead", c_uint32), ("ProcessTraceMode", c_uint32), ("CurrentEvent", c_uint8 * 88),
                ("LogfileHeader", c_uint8 * 280), ("BufferCallback", c_void_p), ("BufferSize", c_uint32),
                ("Filled", c_uint32), ("EventsLost", c_uint32), ("EventRecordCallback", c_void_p),
                ("IsKernelTrace", c_uint32), ("Context", c_void_p)]


class EVENT_FILTER_DESCRIPTOR(Structure):
    _fields_ = [("Ptr", c_uint64), ("Size", c_uint32), ("Type", c_uint32)]


class ENABLE_TRACE_PARAMETERS(Structure):
    _fields_ = [("Version", c_uint32), ("EnableProperty", c_uint32), ("ControlFlags", c_uint32),
                ("SourceId", GUID), ("EnableFilterDesc", POINTER(EVENT_FILTER_DESCRIPTOR)),
                ("FilterDescCount", c_uint32)]


WNODE_FLAG_TRACED_GUID = 0x00020000
EVENT_TRACE_REAL_TIME_MODE = 0x00000100
EVENT_TRACE_USE_MS_FLUSH_TIMER = 0x00000010
PROCESS_TRACE_MODE_REAL_TIME = 0x00000100
PROCESS_TRACE_MODE_EVENT_RECORD = 0x10000000
EVENT_TRACE_CONTROL_STOP = 1
EVENT_CONTROL_CODE_ENABLE_PROVIDER = 1
TRACE_LEVEL_INFORMATION = 4
EVENT_FILTER_TYPE_EVENT_ID = 0x80000200
ENABLE_TRACE_PARAMETERS_VERSION_2 = 2
INVALID_PROCESSTRACE_HANDLE = 0xFFFFFFFFFFFFFFFF
ERROR_SUCCESS, ERROR_ACCESS_DENIED, ERROR_ALREADY_EXISTS = 0, 5, 183
ERROR_NO_SYSTEM_RESOURCES = 1450
NAME_BYTES = 1024

ADMIN_MSG = ("Windows refused to start the frame trace (access denied). Run RETWEAKS as administrator "
             "(right-click RETWEAKS.exe → Run as administrator).")


def _props_buffer():
    size = ctypes.sizeof(EVENT_TRACE_PROPERTIES) + NAME_BYTES
    buf = ctypes.create_string_buffer(size)
    props = EVENT_TRACE_PROPERTIES.from_buffer(buf)
    props.Wnode.BufferSize = size
    props.Wnode.Flags = WNODE_FLAG_TRACED_GUID
    props.Wnode.ClientContext = 1                      # QPC timestamps (converted to FILETIME for us)
    props.LogFileMode = EVENT_TRACE_REAL_TIME_MODE | EVENT_TRACE_USE_MS_FLUSH_TIMER
    props.FlushTimer = 200                             # deliver events every 200 ms
    props.BufferSize = 64                              # KB
    props.MinimumBuffers = 8
    props.MaximumBuffers = 64
    props.LoggerNameOffset = ctypes.sizeof(EVENT_TRACE_PROPERTIES)
    return buf, props


def _event_id_filter(ids):
    """EVENT_FILTER_EVENT_ID blob: FilterIn=1, Reserved, Count, then the ids."""
    blob = bytes([1, 0]) + len(ids).to_bytes(2, "little") + b"".join(i.to_bytes(2, "little") for i in ids)
    return ctypes.create_string_buffer(blob, len(blob))


class EtwSession:
    """Real-time ETW session that calls on_event(pid, source, timestamp_100ns) for every present.
    Windows only. start() raises OSError with a plain message; stop() is safe to call twice."""

    def __init__(self, on_event, name=SESSION_NAME):
        self.on_event, self.name = on_event, name
        self._handle = c_uint64(0)
        self._trace = None
        self._thread = None
        self._cb = None
        self._keep = []
        self.events_lost = 0
        self.error = ""

    def start(self):
        if sys.platform != "win32":
            raise OSError("The built-in frame counter only works on Windows.")
        adv = ctypes.windll.advapi32
        buf, props = _props_buffer()
        rc = adv.StartTraceW(ctypes.byref(self._handle), ctypes.c_wchar_p(self.name), ctypes.byref(props))
        if rc == ERROR_ALREADY_EXISTS:               # left over from a crash: stop it and retry
            self._stop_by_name()
            buf, props = _props_buffer()
            rc = adv.StartTraceW(ctypes.byref(self._handle), ctypes.c_wchar_p(self.name), ctypes.byref(props))
        if rc == ERROR_ACCESS_DENIED:
            raise OSError(ADMIN_MSG)
        if rc == ERROR_NO_SYSTEM_RESOURCES:
            raise OSError("Windows has too many trace sessions running. Close other monitoring tools and try again.")
        if rc != ERROR_SUCCESS:
            raise OSError(f"Windows couldn't start the frame trace (error {rc}).")
        try:
            for guid, (_src, ids, kw) in PROVIDERS.items():
                self._enable(adv, guid, ids, kw)
            self._open(adv)
        except Exception:
            self._stop_by_name()
            raise
        self._thread = threading.Thread(target=self._process, name="etw-frames", daemon=True)
        self._thread.start()

    def _enable(self, adv, guid, ids, keyword):
        g = GUID.parse(guid)
        blob = _event_id_filter(ids)
        desc = EVENT_FILTER_DESCRIPTOR(ctypes.addressof(blob), len(blob.raw), EVENT_FILTER_TYPE_EVENT_ID)
        params = ENABLE_TRACE_PARAMETERS()
        params.Version = ENABLE_TRACE_PARAMETERS_VERSION_2
        params.EnableFilterDesc = ctypes.pointer(desc)
        params.FilterDescCount = 1
        self._keep += [g, blob, desc, params]
        rc = adv.EnableTraceEx2(self._handle, ctypes.byref(g), EVENT_CONTROL_CODE_ENABLE_PROVIDER,
                                TRACE_LEVEL_INFORMATION, c_uint64(keyword), c_uint64(0), 0, ctypes.byref(params))
        if rc != ERROR_SUCCESS:      # older Windows without event-id filters: enable without it
            rc = adv.EnableTraceEx2(self._handle, ctypes.byref(g), EVENT_CONTROL_CODE_ENABLE_PROVIDER,
                                    TRACE_LEVEL_INFORMATION, c_uint64(keyword), c_uint64(0), 0, None)
        if rc == ERROR_ACCESS_DENIED:
            raise OSError(ADMIN_MSG)
        if rc != ERROR_SUCCESS:
            raise OSError(f"Windows couldn't turn on frame events (error {rc}).")

    def _open(self, adv):
        CB = ctypes.WINFUNCTYPE(None, POINTER(EVENT_RECORD))
        self._cb = CB(self._on_record)
        name = ctypes.create_unicode_buffer(self.name)
        log = EVENT_TRACE_LOGFILEW()
        log.LoggerName = ctypes.cast(name, c_void_p)
        log.ProcessTraceMode = PROCESS_TRACE_MODE_REAL_TIME | PROCESS_TRACE_MODE_EVENT_RECORD
        log.EventRecordCallback = ctypes.cast(self._cb, c_void_p)
        self._keep += [name, log]
        adv.OpenTraceW.restype = c_uint64
        h = adv.OpenTraceW(ctypes.byref(log))
        if h == INVALID_PROCESSTRACE_HANDLE:
            raise OSError(f"Windows couldn't open the frame trace (error {ctypes.GetLastError()}).")
        self._trace = c_uint64(h)

    def _on_record(self, rec):
        try:
            h = rec.contents.EventHeader
            src = classify(h.ProviderId.key(), h.EventDescriptor.Id)
            if src:
                self.on_event(h.ProcessId, src, h.TimeStamp)
        except Exception:
            pass        # never let an exception cross back into Windows

    def _process(self):
        rc = ctypes.windll.advapi32.ProcessTrace(ctypes.byref(self._trace), 1, None, None)
        if rc not in (ERROR_SUCCESS, 1223):          # 1223 = cancelled (normal on stop)
            self.error = f"The frame trace stopped (error {rc})."

    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def _stop_by_name(self):
        try:
            buf, props = _props_buffer()
            ctypes.windll.advapi32.ControlTraceW(c_uint64(0), ctypes.c_wchar_p(self.name), ctypes.byref(props),
                                                 EVENT_TRACE_CONTROL_STOP)
            self.events_lost = props.EventsLost
        except Exception:
            pass

    def stop(self):
        if sys.platform != "win32":
            return
        self._stop_by_name()
        if self._trace is not None:
            try:
                ctypes.windll.advapi32.CloseTrace(self._trace)
            except Exception:
                pass
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        self._trace = None


# ---------------------------------------------------------------- overlay stream (same interface)
def pids_for(process_name):
    import psutil
    low = (process_name or "").lower()
    try:
        return {p.pid for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").lower() == low}
    except Exception:
        return set()


class BuiltinOverlayStream:
    """Drop-in replacement for overlay_fps.OverlayStream that needs no PresentMon.
    state: 'idle', 'running', 'closed' (game exited), 'error' (see .error)."""

    def __init__(self, process_name, alive_check=process_running, session_factory=EtwSession,
                 pid_lookup=pids_for):
        self.process_name = process_name
        self._alive_check, self._pid_lookup = alive_check, pid_lookup
        self.agg = FrameAggregator()
        self.session = session_factory(self.agg.feed)
        self.state = "idle"
        self.error = ""
        self.source = None
        self._pids = set()
        self._stop = threading.Event()
        self._watcher = None

    def start(self):
        if not self.process_name or not str(self.process_name).strip():
            raise ValueError("No process selected.")
        self._pids = self._pid_lookup(self.process_name)
        self.session.start()
        self.state = "running"
        self._watcher = threading.Thread(target=self._watch, name="overlay-builtin-watch", daemon=True)
        self._watcher.start()

    def _watch(self):
        while not self._stop.wait(2.0):
            if self.state != "running":
                return
            if not self._alive_check(self.process_name):
                self.state = "closed"
                self._stop.set()
                self.session.stop()
                return
            self._pids = self._pid_lookup(self.process_name) or self._pids   # game may restart
            self.agg.forget_except(self._pids)
            if self.session.error:
                self.error, self.state = self.session.error, "error"
                return

    def snapshot(self):
        snap, src = self.agg.snapshot(self._pids)
        if snap is None:
            snap = {"fps": None, "low1": None, "frame_ms": None}
        else:
            self.source = src
        return snap, self.state

    def has_frames(self):
        return self.agg.total_frames(self._pids) > 0

    def stop(self):
        self._stop.set()
        self.session.stop()
        if self._watcher and self._watcher.is_alive() and self._watcher is not threading.current_thread():
            self._watcher.join(timeout=5)
        if self.state == "running":
            self.state = "idle"
