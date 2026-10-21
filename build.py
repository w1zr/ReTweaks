# C:\pc_optimizer\build.py

import os
import subprocess
import sys

def build_app():
    print("Starting RYTWEAKS single-file build process...")
    
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--uac-admin",
        "--icon=assets/icon.ico",  # Embeds the icon into RYTWEAKS.exe for Windows Explorer
        "--add-data=assets/icon.ico;assets", # Bundles the icon for runtime taskbar loading
        "--name=RYTWEAKS",
        "main.py"
    ]

    subprocess.check_call(cmd)
    print("Build complete! Check C:\\pc_optimizer\\dist\\RYTWEAKS.exe")

if __name__ == "__main__":
    build_app()