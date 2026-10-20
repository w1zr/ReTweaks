import os
import subprocess
import sys

def build_app():
    print("Starting RYTWEAKS build process with UAC elevation...")
    
    # Ensure dependencies are installed
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # Run pyinstaller safely via python module flag
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--uac-admin",
        "--name=RYTWEAKS",
        "--manifest=rytweaks.manifest",
        "main.py"
    ]

    subprocess.check_call(cmd)
    print("Build complete! Check C:\\pc_optimizer\\dist\\RYTWEAKS\\RYTWEAKS.exe")

if __name__ == "__main__":
    build_app()