# core/browser_engine.py
"""Loads Microsoft's Edge engine (WebView2) for the Browser page (v1.5). Windows only.

WebView2 is the Edge engine that ships with Windows 11 (and with Microsoft Edge on Windows 10);
RYTWEAKS draws its own browser frame (tabs, address bar, bookmarks) around it. RYTWEAKS talks to it
through Microsoft's WebView2 SDK (Microsoft.Web.WebView2.Core.dll + WebView2Loader.dll, ~1 MB,
redistributable; taken from the pywebview package) using pythonnet on .NET Framework 4.8, which is
part of Windows 10 and 11.

Nothing here runs at app start: the engine is loaded the first time the Browser page is opened.
"""

import os
import sys
from pathlib import Path

RUNTIME_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"
SDK_DIR_NAME = "webview2"           # folder inside the .exe bundle (see build.py)
CORE_DLL = "Microsoft.Web.WebView2.Core.dll"
LOADER_DLL = "WebView2Loader.dll"


class EngineUnavailable(Exception):
    """The Edge engine can't be used here; the message is shown to the user as-is."""


class Engine:
    """Namespace of the .NET types the browser uses, filled in by load()."""
    version = ""


_engine = None


def sdk_dir():
    """Folder that holds the WebView2 SDK DLLs: inside the .exe when frozen, else pywebview's."""
    base = getattr(sys, "_MEIPASS", None)
    if base and (Path(base) / SDK_DIR_NAME / CORE_DLL).exists():
        return Path(base) / SDK_DIR_NAME
    try:
        import importlib.util
        spec = importlib.util.find_spec("webview")          # pywebview; not imported, only located
        if spec and spec.submodule_search_locations:
            d = Path(list(spec.submodule_search_locations)[0]) / "lib"
            if (d / CORE_DLL).exists():
                return d
    except Exception:
        pass
    raise EngineUnavailable("RYTWEAKS couldn't find the Edge engine files (Microsoft.Web.WebView2.Core.dll). "
                            "Download RYTWEAKS again from GitHub Releases.")


def loader_path(d):
    for p in (Path(d) / LOADER_DLL, Path(d) / "runtimes" / "win-x64" / "native" / LOADER_DLL):
        if p.exists():
            return p
    raise EngineUnavailable("RYTWEAKS couldn't find WebView2Loader.dll. Download RYTWEAKS again from GitHub Releases.")


def load():
    """Loads the SDK once and returns Engine (with .NET types as attributes). Raises EngineUnavailable."""
    global _engine
    if _engine is not None:
        return _engine
    if sys.platform != "win32":
        raise EngineUnavailable("The browser only works on Windows.")
    d = sdk_dir()
    import ctypes
    try:
        # Load the native loader by full path first, so the SDK's later LoadLibrary("WebView2Loader.dll")
        # finds the already-loaded module instead of searching the PATH.
        ctypes.WinDLL(str(loader_path(d)))
    except OSError as e:
        raise EngineUnavailable(f"Windows couldn't load WebView2Loader.dll: {e}")
    try:
        try:
            import pythonnet
            pythonnet.load("netfx")
        except Exception:
            pass        # already loaded, or older pythonnet that loads on "import clr"
        import clr
        clr.AddReference(str(d / CORE_DLL))
        clr.AddReference("System.Drawing")
        from Microsoft.Web.WebView2 import Core as C
        import System
        from System.Drawing import Rectangle
    except Exception as e:
        raise EngineUnavailable(f"Couldn't start .NET for the browser ({type(e).__name__}: {e}). "
                                ".NET Framework 4.8 is part of Windows 10 and 11; run Windows Update.")
    try:
        version = C.CoreWebView2Environment.GetAvailableBrowserVersionString()
    except Exception:
        version = None
    if not version:
        raise EngineUnavailable("The Microsoft Edge WebView2 Runtime isn't installed. It's part of Windows 11; "
                                f"on Windows 10 install the Evergreen Runtime from {RUNTIME_URL}")
    e = Engine()
    e.C, e.System, e.Rectangle, e.IntPtr = C, System, Rectangle, System.IntPtr
    e.version = str(version)
    _engine = e
    return e


def user_data_dir():
    from core.browser_data import user_data_dir as u
    p = u()
    os.makedirs(p, exist_ok=True)
    return p
