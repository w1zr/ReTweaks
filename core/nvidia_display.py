# core/nvidia_display.py
"""NVIDIA custom resolutions for the stretched resolution on Display & drivers (v1.5). Windows +
NVIDIA only.

Windows (and games) only use resolutions the graphics driver offers, and 1720x1080 (etc.) isn't
offered by default. This adds one through NVIDIA's public NVAPI (the same feature as NVIDIA Control Panel →
Change resolution → Customize → Create Custom Resolution):

  1. Read the timing the monitor uses now (e.g. 1920x1080 @ 165 Hz) with NvAPI_DISP_GetTiming.
  2. Build a custom display whose SOURCE is e.g. 1720x1080 but whose output TIMING stays the
     monitor's native one. The graphics card scales the picture to full screen (stretched), and
     the monitor keeps getting the signal it already supports.
  3. NvAPI_DISP_TryCustomDisplay switches to it for a test. The user must press Keep within a few
     seconds; otherwise NvAPI_DISP_RevertCustomDisplayTrial switches back (nothing can get stuck).
  4. On Keep: NvAPI_DISP_SaveCustomDisplay stores it, then the desktop goes back to its normal mode.

Function IDs and struct layouts come from NVIDIA's MIT-licensed NVAPI SDK (github.com/NVIDIA/nvapi:
nvapi_interface.h, nvapi.h); sizes were checked by compiling those definitions (tests check them).
"""

import ctypes
import sys
from ctypes import Structure, c_float, c_int32, c_uint8, c_uint16, c_uint32, c_char

# nvapi_interface.h
IDS = {
    "NvAPI_Initialize": 0x0150E828,
    "NvAPI_Unload": 0xD22BDD7E,
    "NvAPI_DISP_GetDisplayIdByDisplayName": 0xAE457190,
    "NvAPI_DISP_GetTiming": 0x175167E9,
    "NvAPI_DISP_TryCustomDisplay": 0x1F7DB630,
    "NvAPI_DISP_SaveCustomDisplay": 0x49882876,
    "NvAPI_DISP_RevertCustomDisplayTrial": 0xCBBD40F0,
}

# nvapi_lite_common.h (NvAPI_Status)
STATUS = {0: "OK", -1: "generic error", -2: "NVIDIA driver library not found", -4: "NVAPI not initialized",
          -5: "invalid argument", -6: "no NVIDIA graphics card driving a display",
          -9: "incompatible structure version (driver too old?)", -104: "not supported on this graphics card",
          -137: "needs administrator rights", -187: "this display doesn't support custom resolutions"}

NV_TIMING_OVERRIDE_CURRENT, NV_TIMING_OVERRIDE_AUTO = 0, 1


class NV_TIMINGEXT(Structure):
    _fields_ = [("flag", c_uint32), ("rr", c_uint16), ("rrx1k", c_uint32), ("aspect", c_uint32),
                ("rep", c_uint16), ("status", c_uint32), ("name", c_uint8 * 40)]


class NV_TIMING(Structure):
    _fields_ = [("HVisible", c_uint16), ("HBorder", c_uint16), ("HFrontPorch", c_uint16),
                ("HSyncWidth", c_uint16), ("HTotal", c_uint16), ("HSyncPol", c_uint8),
                ("VVisible", c_uint16), ("VBorder", c_uint16), ("VFrontPorch", c_uint16),
                ("VSyncWidth", c_uint16), ("VTotal", c_uint16), ("VSyncPol", c_uint8),
                ("interlaced", c_uint16), ("pclk", c_uint32), ("etc", NV_TIMINGEXT)]


class NV_TIMING_INPUT(Structure):
    # flag (NV_TIMING_FLAG, 12 bytes of bitfields) is left zero: progressive, default scaling
    _fields_ = [("version", c_uint32), ("width", c_uint32), ("height", c_uint32), ("rr", c_float),
                ("flag", c_uint32 * 3), ("type", c_int32)]


class NV_VIEWPORTF(Structure):
    _fields_ = [("x", c_float), ("y", c_float), ("w", c_float), ("h", c_float)]


class NV_CUSTOM_DISPLAY(Structure):
    _fields_ = [("version", c_uint32), ("width", c_uint32), ("height", c_uint32), ("depth", c_uint32),
                ("colorFormat", c_int32), ("srcPartition", NV_VIEWPORTF), ("xRatio", c_float),
                ("yRatio", c_float), ("timing", NV_TIMING), ("hwModeSetOnly", c_uint32)]


def make_version(struct, ver):
    """MAKE_NVAPI_VERSION(type, ver) = sizeof(type) | (ver << 16)."""
    return ctypes.sizeof(struct) | (ver << 16)


def build_custom(width, height, timing, depth=32):
    """The custom display: source width x height, scanned out with the monitor's own timing."""
    cd = NV_CUSTOM_DISPLAY()
    cd.version = make_version(NV_CUSTOM_DISPLAY, 1)
    cd.width, cd.height, cd.depth = int(width), int(height), int(depth)
    cd.colorFormat = 0                                   # NV_FORMAT_UNKNOWN: driver chooses
    cd.srcPartition = NV_VIEWPORTF(0.0, 0.0, 1.0, 1.0)   # whole screen (required for now, per nvapi.h)
    cd.xRatio = cd.yRatio = 1.0
    cd.timing = timing
    cd.hwModeSetOnly = 0
    return cd


class NvError(Exception):
    def __init__(self, what, code):
        self.code = code
        super().__init__(f"{what}: {STATUS.get(code, f'NVAPI error {code}')}")


class NvApi:
    """Loads nvapi64.dll (installed with every NVIDIA driver) and resolves functions by ID."""

    def __init__(self):
        if sys.platform != "win32":
            raise OSError("NVIDIA settings can only be changed on Windows.")
        try:
            self.dll = ctypes.CDLL("nvapi64.dll")
        except OSError:
            raise OSError("No NVIDIA driver found (nvapi64.dll is missing). This only works with NVIDIA graphics cards.")
        qi = self.dll.nvapi_QueryInterface
        qi.restype = ctypes.c_void_p
        qi.argtypes = [c_uint32]
        self._qi = qi
        self._fn = {}
        self.call("NvAPI_Initialize", [])

    def _get(self, name, argtypes):
        if name not in self._fn:
            ptr = self._qi(IDS[name])
            if not ptr:
                raise OSError(f"Your NVIDIA driver doesn't provide {name}. Update the driver.")
            self._fn[name] = ctypes.CFUNCTYPE(c_int32, *argtypes)(ptr)
        return self._fn[name]

    def call(self, name, argtypes, *args):
        rc = self._get(name, argtypes)(*args)
        if rc != 0:
            raise NvError(name.replace("NvAPI_", ""), rc)

    # ---- display operations
    def display_id(self, gdi_name):
        """\\\\.\\DISPLAY1 -> NVIDIA display id."""
        out = c_uint32(0)
        self.call("NvAPI_DISP_GetDisplayIdByDisplayName", [ctypes.c_char_p, ctypes.POINTER(c_uint32)],
                  gdi_name.encode("ascii"), ctypes.byref(out))
        return out.value

    def timing(self, display_id, width, height, hz):
        ti = NV_TIMING_INPUT()
        ti.version = make_version(NV_TIMING_INPUT, 1)
        ti.width, ti.height, ti.rr = int(width), int(height), float(hz)
        ti.type = NV_TIMING_OVERRIDE_AUTO
        t = NV_TIMING()
        self.call("NvAPI_DISP_GetTiming", [c_uint32, ctypes.POINTER(NV_TIMING_INPUT), ctypes.POINTER(NV_TIMING)],
                  display_id, ctypes.byref(ti), ctypes.byref(t))
        if not t.HVisible or not t.VVisible or not t.pclk:
            raise OSError("The NVIDIA driver returned an empty timing for your monitor.")
        return t

    def try_custom(self, display_id, custom):
        ids = (c_uint32 * 1)(display_id)
        arr = (NV_CUSTOM_DISPLAY * 1)(custom)
        self.call("NvAPI_DISP_TryCustomDisplay", [ctypes.POINTER(c_uint32), c_uint32, ctypes.POINTER(NV_CUSTOM_DISPLAY)],
                  ids, 1, arr)

    def save_custom(self, display_id):
        ids = (c_uint32 * 1)(display_id)
        # isThisOutputIdOnly=0, isThisMonitorIdOnly=1: keep it for this monitor
        self.call("NvAPI_DISP_SaveCustomDisplay", [ctypes.POINTER(c_uint32), c_uint32, c_uint32, c_uint32], ids, 1, 0, 1)

    def revert_trial(self, display_id):
        ids = (c_uint32 * 1)(display_id)
        self.call("NvAPI_DISP_RevertCustomDisplayTrial", [ctypes.POINTER(c_uint32), c_uint32], ids, 1)
