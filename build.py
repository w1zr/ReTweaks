# C:\pc_optimizer\build.py

import os
import subprocess
import sys

def build_app():
    print("Starting RYTWEAKS single-file build process...")
    
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # Browser (v1.5): Microsoft's WebView2 SDK DLLs, taken from the pywebview package.
    import importlib.util
    spec = importlib.util.find_spec("webview")
    lib = os.path.join(list(spec.submodule_search_locations)[0], "lib")
    webview2 = [
        f"--add-data={os.path.join(lib, 'Microsoft.Web.WebView2.Core.dll')};webview2",
        f"--add-data={os.path.join(lib, 'runtimes', 'win-x64', 'native', 'WebView2Loader.dll')};webview2",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--uac-admin",
        "--icon=assets/icon.ico",  # Embeds the icon into RYTWEAKS.exe for Windows Explorer
        "--add-data=assets/icon.ico;assets", # Fallback runtime icon
        "--add-data=assets/taskbar.ico;assets",  # Window + taskbar icon (the v1.4 drawing)
        "--add-data=assets/tray.ico;assets",     # System tray icon (v1.5): chip with pins at 16-48 px
        "--collect-submodules=pycaw",        # Audio mixer: pycaw's COM interface modules
        "--hidden-import=comtypes.stream",
        "--collect-all=pythonnet",           # Browser: .NET bridge (Python.Runtime.dll)
        "--collect-all=clr_loader",
        "--hidden-import=clr",
        *webview2,
        "--name=RYTWEAKS",
        "main.py"
    ]

    subprocess.check_call(cmd)
    print("Build complete! Check C:\\pc_optimizer\\dist\\RYTWEAKS.exe")

if __name__ == "__main__":
    build_app()