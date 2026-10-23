"""One-time desktop shortcut offer for packaged RETWEAKS builds."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from tkinter import messagebox

SHORTCUT_SCRIPT = r'''
$ErrorActionPreference='Stop'
[Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$request=[Console]::In.ReadToEnd() | ConvertFrom-Json
$desktopPath=if($request.desktop){[string]$request.desktop}else{[Environment]::GetFolderPath('DesktopDirectory')}
if(-not $desktopPath -or -not (Test-Path -LiteralPath $desktopPath -PathType Container)){throw 'The desktop folder could not be found.'}
$shortcutPath=Join-Path $desktopPath 'RETWEAKS.lnk'
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath=[string]$request.target
$shortcut.WorkingDirectory=[IO.Path]::GetDirectoryName([string]$request.target)
$shortcut.Arguments=''
$shortcut.Description='Open RETWEAKS'
$shortcut.IconLocation=([string]$request.target)+',0'
$shortcut.Save()
if(-not (Test-Path -LiteralPath $shortcutPath -PathType Leaf)){throw 'Windows did not create the shortcut.'}
[Console]::Out.WriteLine($shortcutPath)
'''

def create_desktop_shortcut(target, desktop=None):
    target = Path(target).resolve()
    if target.suffix.lower() != '.exe' or not target.is_file():
        raise OSError('The RETWEAKS executable could not be found.')
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',SHORTCUT_SCRIPT],
                            input=json.dumps({'target':str(target),'desktop':str(Path(desktop).resolve()) if desktop else None}),
                            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20,
                            creationflags=0x08000000 if os.name=='nt' else 0)
    if result.returncode:
        raise OSError('Windows could not create the desktop shortcut. Check that your desktop folder is writable.')
    path = Path(result.stdout.lstrip('\ufeff').strip())
    if not path.is_file():
        raise OSError('The desktop shortcut could not be verified.')
    return path

def offer_desktop_shortcut(parent, settings_root, target=None):
    state_path = Path(settings_root) / 'first_run.json'
    try:
        state = json.loads(state_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        state = {}
    if isinstance(state, dict) and state.get('desktop_shortcut_prompted') is True:
        return False
    accepted = messagebox.askyesno('Welcome to RETWEAKS', 'Would you like to create a RETWEAKS desktop shortcut?', parent=parent)
    try:
        shortcut = create_desktop_shortcut(target or sys.executable) if accepted else None
    except (OSError, subprocess.TimeoutExpired) as exc:
        detail = 'Windows took too long creating the shortcut.' if isinstance(exc, subprocess.TimeoutExpired) else str(exc)
        messagebox.showerror('Desktop shortcut', detail + '\nRETWEAKS will ask again next time.', parent=parent)
        return False
    temporary = state_path.with_name('first_run.' + uuid.uuid4().hex + '.tmp')
    try:
        state_path.parent.mkdir(parents=True,exist_ok=True)
        temporary.write_text(json.dumps({'desktop_shortcut_prompted':True,'desktop_shortcut_created':bool(shortcut)},indent=2),encoding='utf-8')
        os.replace(temporary,state_path)
    except OSError:
        messagebox.showwarning('First-run preference', 'Your shortcut choice could not be saved. RETWEAKS may ask again next time.', parent=parent)
    finally:
        if temporary.exists():
            try:temporary.unlink()
            except OSError:pass
    return bool(shortcut)
