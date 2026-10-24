# C:\pc_optimizer\build.py
"""Builds dist\\RETWEAKS.exe (the combined app: the base app base + RETWEAKS). Windows only.

1. installs requirements.txt
2. compiles the C# helpers in ai\\ (GeminiChat, EmbeddedAI, DriverAI, ValueAI, EmbeddedSite, EmbeddedBrowser,
   sensors\\SensorHost)
   with the .NET Framework compiler that ships with Windows
3. runs PyInstaller with RETWEAKS.spec (single file, administrator, chip icon embedded)
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CSC = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), r"Microsoft.NET\Framework64\v4.0.30319\csc.exe")
REFS = ["System.Windows.Forms.dll", "System.Drawing.dll", "System.Web.Extensions.dll", "System.Net.Http.dll"]
HELPERS = [  # (output, target, platform, extra references, source) - same as the base app's build_exe.bat
    ("EmbeddedAI.exe", "exe", "anycpu", [], "EmbeddedAI.cs"),
    ("DriverAI.exe", "winexe", "anycpu", [], "DriverAI.cs"),
    ("ValueAI.exe", "exe", "anycpu", [], "ValueAI.cs"),
    ("EmbeddedSite.exe", "exe", "x64", [r"ai\Microsoft.Web.WebView2.Core.dll", r"ai\Microsoft.Web.WebView2.WinForms.dll"],
     "EmbeddedSite.cs"),
]


def run(cmd):
    print(">", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def build_sensor_host():
    """ai\\sensors\\SensorHost.exe (base app v1.5: LibreHardwareMonitor bridge for temperatures and fan control).
    The prebuilt copy from base app v1.5 (built from the SensorHost.cs next to it) is used as is; it is only
    compiled here if it's missing."""
    src, out = r"ai\sensors\SensorHost.cs", r"ai\sensors\SensorHost.exe"
    if os.path.isfile(os.path.join(ROOT, out)):
        return
    tmp = r"ai\sensors\SensorHost.new.exe"
    cmd = [CSC, "/nologo", "/target:exe", "/platform:anycpu", f"/out:{tmp}",
           r"/reference:ai\sensors\LibreHardwareMonitorLib.dll", "/reference:System.Web.Extensions.dll", src]
    print(">", " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode == 0 and os.path.isfile(os.path.join(ROOT, tmp)):
        os.replace(os.path.join(ROOT, tmp), os.path.join(ROOT, out))
    else:
        try:
            os.remove(os.path.join(ROOT, tmp))
        except OSError:
            pass
        sys.exit("ai\\sensors\\SensorHost.exe is missing and SensorHost.cs could not be compiled.")


def build_browser():
    """ai\\EmbeddedBrowser.exe: the RETWEAKS Browser program (the base app's v1.5 EmbeddedBrowser with RETWEAKS branding).
    Compiled from EmbeddedBrowser.cs every build; if that fails, the copy already in ai\\ is used (the build only
    stops when there is none)."""
    out, tmp = r"ai\EmbeddedBrowser.exe", r"ai\EmbeddedBrowser.new.exe"
    cmd = [CSC, "/nologo", "/target:exe", "/platform:x64", f"/out:{tmp}",
           *[f"/reference:{r}" for r in REFS + [r"ai\Microsoft.Web.WebView2.Core.dll", r"ai\Microsoft.Web.WebView2.WinForms.dll"]],
           r"ai\EmbeddedBrowser.cs"]
    print(">", " ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode == 0 and os.path.isfile(os.path.join(ROOT, tmp)):
        os.replace(os.path.join(ROOT, tmp), os.path.join(ROOT, out))
        return
    try:
        os.remove(os.path.join(ROOT, tmp))
    except OSError:
        pass
    if not os.path.isfile(os.path.join(ROOT, out)):
        sys.exit("ai\\EmbeddedBrowser.cs could not be compiled and there is no ai\\EmbeddedBrowser.exe to use.")
    print("EmbeddedBrowser.cs could not be compiled; using the existing ai\\EmbeddedBrowser.exe.")


def gemini_key():
    """The built-in AI keys for this build, joined with "|": the RETWEAKS_GEMINI_KEY environment variable (the
    private GitHub Actions secret GEMINI_API_KEY on the release build) or the untracked file ai\\gemini_key.txt on a
    local PC. One key per line (commas or spaces also work). The AI switches to the next key when Google says one
    no longer works. Never stored in the public source code (Google disabled a key minutes after it appeared on
    GitHub)."""
    import re
    raw = os.environ.get("RETWEAKS_GEMINI_KEY", "")
    path = os.path.join(ROOT, "ai", "gemini_key.txt")
    if not raw.strip() and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    keys = []
    for k in re.split(r"[\s,|]+", raw.strip()):
        if k and k not in keys:
            if not all(c.isalnum() or c in "._-" for c in k):
                sys.exit("A Gemini key contains unexpected characters; check RETWEAKS_GEMINI_KEY / ai\\gemini_key.txt.")
            keys.append(k)
    return "|".join(keys)


def build_gemini_chat():
    """ai\\GeminiChat.exe (the AI helper) from GeminiChat.cs with the built-in key filled in. The filled-in copy
    is a temporary file that is deleted right after compiling. With no key the app still builds; AI responses remain unavailable until a shared key is configured at build time."""
    key = gemini_key()
    count = len(key.split("|")) if key else 0
    print("Built-in AI keys:", count if count else "none (AI responses unavailable until a shared build key is configured)")
    src = os.path.join(ROOT, "ai", "GeminiChat.cs")
    tmp = os.path.join(ROOT, "ai", "GeminiChat.build.cs")
    with open(src, "rb") as f:
        code = f.read()
    with open(tmp, "wb") as f:
        f.write(code.replace(b"@@RETWEAKS_GEMINI_KEY@@", key.encode("ascii")) if key else code)
    try:
        run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join("ai", "build.ps1"),
             "-Source", tmp])
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def build_app():
    if sys.platform != "win32":
        sys.exit("RETWEAKS.exe must be built on Windows.")
    print("Starting RETWEAKS single-file build...")
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    if not os.path.isfile(CSC):
        sys.exit(f"The .NET Framework C# compiler was not found at {CSC}.")
    build_gemini_chat()
    for out, target, platform, extra, src in HELPERS:
        refs = REFS + extra
        run([CSC, "/nologo", f"/target:{target}", f"/platform:{platform}", f"/out:ai\\{out}",
             *[f"/reference:{r}" for r in refs], f"ai\\{src}"])
    build_browser()
    build_sensor_host()
    run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "RETWEAKS.spec"])
    print("Build complete! Check " + os.path.join(ROOT, "dist", "RETWEAKS.exe"))


if __name__ == "__main__":
    build_app()
