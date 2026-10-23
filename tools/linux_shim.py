"""Linux-only test harness: lets the Windows-only Tk app import and draw on Linux (Xvfb) so pages can
be screenshotted and checked. Windows calls are replaced with inert fakes that return 0/None.
NOT used by the real app. Usage:  xvfb-run -a python3.12 tools/linux_shim.py check_startup.py
"""
import ctypes
import os
import runpy
import sys
import types
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class _Fn:
    def __init__(self, name=""):
        self.name = name
        self.argtypes = None
        self.restype = None
        self.errcheck = None

    def __call__(self, *a, **k):
        return 0


class _Dll:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        f = _Fn(name)
        setattr(self, name, f)
        return f


class _Loader:
    def __getattr__(self, name):
        return _Dll()

    def LoadLibrary(self, *a):
        return _Dll()


ctypes.WinDLL = _Dll
ctypes.OleDLL = _Dll
ctypes.windll = _Loader()
ctypes.oledll = _Loader()
ctypes.WINFUNCTYPE = ctypes.CFUNCTYPE
ctypes.get_last_error = lambda: 0
ctypes.FormatError = lambda *a: ""
ctypes.HRESULT = ctypes.c_long
try:
    import ctypes.wintypes  # noqa: F401
except Exception:
    pass

for mod in ("winreg", "pycaw", "pycaw.pycaw", "pycaw.utils", "comtypes", "comtypes.client", "win32api",
            "win32con", "win32gui", "win32pdh", "win32com", "win32com.client", "pythoncom", "pynvml"):
    sys.modules.setdefault(mod, MagicMock(name=mod))

if __name__ == "__main__":
    script = sys.argv[1]
    sys.argv = sys.argv[1:]
    runpy.run_path(os.path.join(ROOT, script) if not os.path.isabs(script) else script, run_name="__main__")
