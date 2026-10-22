# core/audio.py
"""Audio mixer backend: Windows Core Audio through pycaw + comtypes.

Everything that talks to COM lives in AudioBackend and is meant to be called from ONE
thread (the UI thread, which already has COM initialised by Qt). The calls are fast.
If you ever call it from another thread, wrap the work in com_scope().

Pure helpers (clamp_percent, percent_to_scalar, ...) have no Windows dependency and are
covered by tests/test_audio.py.
"""

import contextlib
import sys

# ------------------------------------------------------------------ pure helpers


def clamp_percent(value):
    """Any number-like -> int 0..100. Bad input (None, text, NaN) -> 0."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0
    if v != v:  # NaN
        return 0
    return int(round(max(0.0, min(100.0, v))))


def percent_to_scalar(percent):
    """Slider percent (0..100) -> Windows scalar (0.0..1.0)."""
    return clamp_percent(percent) / 100.0


def scalar_to_percent(scalar):
    """Windows scalar (0.0..1.0) -> slider percent (0..100). Out-of-range is clamped."""
    try:
        s = float(scalar)
    except (TypeError, ValueError):
        return 0
    if s != s:
        return 0
    return clamp_percent(s * 100.0)


def session_label(pid, process_name, display_name):
    """Name shown for an audio session: process name first, then display name, then PID."""
    if pid == 0:
        return "System sounds"
    if process_name:
        return process_name
    if display_name:
        return display_name
    return f"Process {pid}"


def sessions_key(sessions):
    """Stable identity of a session list; the UI rebuilds rows only when this changes."""
    return tuple((s.pid, s.identifier) for s in sessions)


# ------------------------------------------------------------------ data


class DeviceInfo:
    def __init__(self, dev_id, name, is_default):
        self.id, self.name, self.is_default = dev_id, name, is_default


class SessionInfo:
    def __init__(self, pid, identifier, name, volume, muted, active, handle):
        self.pid, self.identifier, self.name = pid, identifier, name
        self.volume, self.muted, self.active = volume, muted, active
        self.handle = handle  # pycaw AudioSession (UI thread only)


# ------------------------------------------------------------------ availability

AVAILABLE = False
UNAVAILABLE_REASON = ""
AudioUtilities = None
_ERole = None

if sys.platform != "win32":
    UNAVAILABLE_REASON = "The audio mixer uses Windows Core Audio and only works on Windows."
else:
    try:
        import comtypes  # noqa: F401
        from pycaw.pycaw import AudioUtilities  # noqa: F811
        try:
            from pycaw.constants import ERole as _ERole
        except Exception:  # very old pycaw
            _ERole = None
        AVAILABLE = True
    except Exception as exc:  # ImportError or a comtypes load failure
        UNAVAILABLE_REASON = (f"The audio libraries (pycaw, comtypes) could not be loaded: "
                              f"{exc}. Reinstall RYTWEAKS or run: pip install pycaw comtypes")


@contextlib.contextmanager
def com_scope():
    """Initialise COM on the current (non-UI) thread and release it afterwards."""
    if not AVAILABLE:
        yield
        return
    import comtypes
    comtypes.CoInitialize()
    try:
        yield
    finally:
        comtypes.CoUninitialize()


# ------------------------------------------------------------------ backend


def _device_name(dev):
    try:
        name = dev.FriendlyName
    except Exception:
        name = None
    return name or "Unknown device"


def _is_active(dev):
    """True for a plugged-in/enabled device. Handles enum and int states."""
    state = getattr(dev, "state", None)
    if state is None:
        return True
    value = getattr(state, "value", state)
    try:
        return int(value) == 1  # DEVICE_STATE_ACTIVE
    except (TypeError, ValueError):
        return "active" in str(state).lower()


RENDER, CAPTURE = 0, 1       # EDataFlow: eRender (speakers), eCapture (microphones)


def _default_id(flow=RENDER):
    """Id of the default playback (or recording) device. New pycaw returns an AudioDevice (.id),
    old pycaw returned the raw IMMDevice (.GetId())."""
    dev = AudioUtilities.GetSpeakers() if flow == RENDER else AudioUtilities.GetMicrophone()
    if dev is None:
        return None
    if hasattr(dev, "id"):
        return dev.id
    return dev.GetId()


def _default_render_id():
    return _default_id(RENDER)


def _all_render_devices():
    return _all_devices(RENDER)


def _all_devices(flow=RENDER):
    """Active playback (or recording) devices as pycaw AudioDevice objects (new and old pycaw)."""
    try:
        devs = AudioUtilities.GetAllDevices(flow, 1)  # EDataFlow, DEVICE_STATE_ACTIVE
    except TypeError:  # old signature: no arguments, returns every flow
        devs = AudioUtilities.GetAllDevices()
    out = []
    for d in devs:
        if d is None or not _is_active(d):
            continue
        try:
            f = AudioUtilities.GetEndpointDataFlow(d.id, 1)
            if f != flow:  # keep only the requested direction
                continue
        except AttributeError:  # old pycaw without that helper
            pass
        except Exception:
            continue
        out.append(d)
    return out


def _endpoint_volume(dev):
    """IAudioEndpointVolume for an AudioDevice, with a fallback for old pycaw."""
    vol = getattr(dev, "EndpointVolume", None)
    if vol is not None:
        return vol
    import comtypes
    from ctypes import POINTER, cast
    from pycaw.api.endpointvolume import IAudioEndpointVolume
    iface = dev._dev.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


class AudioBackend:
    """Thin, honest wrapper. Methods raise on COM failure; the page catches and shows it."""

    def __init__(self):
        if not AVAILABLE:
            raise RuntimeError(UNAVAILABLE_REASON)

    # ---- devices
    def devices(self):
        default_id = _default_render_id()
        out = [DeviceInfo(d.id, _device_name(d), d.id == default_id)
               for d in _all_render_devices()]
        out.sort(key=lambda d: (not d.is_default, d.name.lower()))
        return out

    def default_device(self):
        """The default playback AudioDevice, or None when there is no output device."""
        default_id = _default_render_id()
        for d in _all_render_devices():
            if d.id == default_id:
                return d
        return None

    # ---- master volume (default device)
    def master_state(self):
        """(volume_percent, muted) of the default output, or None if there is none."""
        dev = self.default_device()
        if dev is None:
            return None
        ev = _endpoint_volume(dev)
        return (scalar_to_percent(ev.GetMasterVolumeLevelScalar()), bool(ev.GetMute()))

    def set_master_volume(self, percent):
        dev = self.default_device()
        if dev is None:
            raise RuntimeError("No default output device.")
        _endpoint_volume(dev).SetMasterVolumeLevelScalar(percent_to_scalar(percent), None)

    def set_master_mute(self, muted):
        dev = self.default_device()
        if dev is None:
            raise RuntimeError("No default output device.")
        _endpoint_volume(dev).SetMute(1 if muted else 0, None)

    # ---- per-app sessions (on the default output device)
    def sessions(self):
        out = []
        for s in AudioUtilities.GetAllSessions():
            try:
                if s.State == 2:  # AudioSessionStateExpired
                    continue
                pid = s.ProcessId
                try:
                    proc = s.Process
                    pname = proc.name() if proc is not None else ""
                except Exception:
                    pname = ""
                try:
                    dname = s.DisplayName
                except Exception:
                    dname = ""
                sv = s.SimpleAudioVolume
                out.append(SessionInfo(
                    pid, str(s.Identifier), session_label(pid, pname, dname),
                    scalar_to_percent(sv.GetMasterVolume()), bool(sv.GetMute()),
                    s.State == 1, s))
            except Exception:
                continue  # a session that vanished while we read it
        out.sort(key=lambda x: (not x.active, x.name.lower()))
        return out

    @staticmethod
    def set_session_volume(info, percent):
        info.handle.SimpleAudioVolume.SetMasterVolume(percent_to_scalar(percent), None)

    @staticmethod
    def set_session_mute(info, muted):
        info.handle.SimpleAudioVolume.SetMute(1 if muted else 0, None)

    @staticmethod
    def read_session(info):
        """Fresh (percent, muted) for an existing session handle."""
        sv = info.handle.SimpleAudioVolume
        return scalar_to_percent(sv.GetMasterVolume()), bool(sv.GetMute())

    # ---- input (microphones), v1.5
    def input_devices(self):
        default_id = _default_id(CAPTURE)
        out = [DeviceInfo(d.id, _device_name(d), d.id == default_id) for d in _all_devices(CAPTURE)]
        out.sort(key=lambda d: (not d.is_default, d.name.lower()))
        return out

    def default_input(self):
        """The default recording AudioDevice, or None when there is no microphone."""
        default_id = _default_id(CAPTURE)
        for d in _all_devices(CAPTURE):
            if d.id == default_id:
                return d
        return None

    def input_state(self):
        """(volume_percent, muted) of the default microphone, or None if there is none."""
        dev = self.default_input()
        if dev is None:
            return None
        ev = _endpoint_volume(dev)
        return (scalar_to_percent(ev.GetMasterVolumeLevelScalar()), bool(ev.GetMute()))

    def set_input_volume(self, percent):
        dev = self.default_input()
        if dev is None:
            raise RuntimeError("No default input device.")
        _endpoint_volume(dev).SetMasterVolumeLevelScalar(percent_to_scalar(percent), None)

    def set_input_mute(self, muted):
        dev = self.default_input()
        if dev is None:
            raise RuntimeError("No default input device.")
        _endpoint_volume(dev).SetMute(1 if muted else 0, None)

    def set_default_input(self, dev_id):
        """Same as set_default_device, for the default microphone."""
        return self.set_default_device(dev_id, flow=CAPTURE)

    # ---- switch default output (undocumented IPolicyConfig)
    def set_default_device(self, dev_id, flow=RENDER):
        """Switch the default playback device for all three roles using pycaw's
        AudioUtilities.SetDefaultDevice, which calls the UNDOCUMENTED IPolicyConfig COM
        interface (widely used, but Microsoft does not support it). Returns
        (ok, message); ok is only True if re-reading the default shows the change."""
        fn = getattr(AudioUtilities, "SetDefaultDevice", None)
        if fn is None or _ERole is None:
            return False, ("This pycaw version cannot switch devices. "
                           "Use Windows Sound settings instead.")
        try:
            fn(dev_id, roles=[_ERole.eConsole, _ERole.eMultimedia, _ERole.eCommunications])
        except Exception as exc:
            return False, f"Windows refused the switch ({exc})."
        try:
            now = _default_id(flow)
        except Exception as exc:
            return False, f"Switch sent, but the result could not be verified ({exc})."
        kind = "output" if flow == RENDER else "input"
        if now == dev_id:
            return True, f"Default {kind} device changed."
        return False, "Windows did not change the default device."
