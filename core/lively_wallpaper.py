"""Optional Lively integration. Commands are requests, not playback confirmation."""
import os
from pathlib import Path
import shutil
import subprocess

from core.winutil import run
from core.wallpaper import WallpaperError

NAMES = ('Lively.exe', 'Livelywpf.exe', 'livelycu.exe', 'Lively.Utility.Commandline.exe')
MEDIA = {'.mp4', '.webm', '.mkv', '.avi', '.mov', '.gif'}


def find_executable(custom=None):
    if custom and Path(custom).is_file() and Path(custom).name.lower() in {n.lower() for n in NAMES}:
        return str(Path(custom))
    for name in NAMES:
        found = shutil.which(name)
        if found:
            return found
    folders = [Path(os.environ.get(variable, '')) / suffix for variable, suffix in (
        ('ProgramFiles', 'Lively Wallpaper'), ('ProgramFiles(x86)', 'Lively Wallpaper'),
        ('LOCALAPPDATA', 'Programs/Lively Wallpaper'), ('LOCALAPPDATA', 'Lively Wallpaper'))]
    for folder in folders:
        for name in NAMES:
            if (folder / name).is_file():
                return str(folder / name)
    return None


def command(executable, action, source=None, monitor=None):
    if not executable:
        raise WallpaperError('Install Lively Wallpaper or locate its executable first.')
    if action == 'open':
        from core.winutil import CREATE_NO_WINDOW
        subprocess.Popen([executable, 'app', '--showApp', 'true'], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        return 'Lively launch requested. Finish its first-run setup before sending wallpaper commands.'
    import psutil
    if not any((p.info.get('name') or '').lower() in {'lively.exe','livelywpf.exe'} for p in psutil.process_iter(['name'])):
        raise WallpaperError('Open Lively and finish its setup first, then try again.')
    if action == 'set':
        path = Path(source or '')
        if not path.is_file() or path.suffix.lower() not in MEDIA:
            raise WallpaperError('Choose a local video or GIF supported by Lively.')
        args = ['setwp', '--file', str(path.resolve())]
        if monitor is not None:
            if not isinstance(monitor, int) or not 1 <= monitor <= 32:
                raise WallpaperError('Choose a valid Lively screen number.')
            args += ['--monitor', str(monitor)]
    else:
        controls = {'open': ['app', '--showApp', 'true'], 'pause': ['app', '--play', 'false'],
                    'resume': ['app', '--play', 'true'], 'mute': ['app', '--volume', '0'],
                    'stop': ['closewp', '--monitor', '-1']}
        if action not in controls:
            raise WallpaperError('Unknown Lively action.')
        args = controls[action]
    result = run([executable, *args], timeout=45, encoding='utf-8')
    if result.returncode:
        raise WallpaperError('Lively did not accept the command. Open Lively, finish its first-run setup, then try again.')
    return 'Request sent to Lively. Check the desktop or Lively library for playback status.'


def install():
    from app_starter import winget_path
    winget = winget_path()
    if not winget:
        raise WallpaperError('Windows Package Manager is unavailable. Install App Installer from Microsoft Store first.')
    result = run([winget, 'install', '--id', 'rocksdanister.LivelyWallpaper', '--exact', '--source', 'winget',
                  '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity', '--silent'],
                 timeout=900, encoding='utf-8')
    executable = find_executable()
    if not executable and result.returncode:
        raise WallpaperError('Lively installation did not finish. Try again or use the official download page.')
    return executable
