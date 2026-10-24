"""Install missing feature dependencies; never reinstall a working component."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

PRESENTMON_URL = 'https://github.com/GameTechDev/PresentMon/releases/download/v2.3.1/PresentMon-2.3.1-x64.exe'
PRESENTMON_SHA256 = '364e5d98d4d134bd54dd25c22ed2ca2f4883f8bc3ed6502bee0c151e3436d30c'
PAWNIO_URL = 'https://github.com/namazso/PawnIO.Setup/releases/download/2.2.0/PawnIO_setup.exe'
PAWNIO_SHA256 = '1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032'
WEBVIEW_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
TITLES = {'webview2':'Microsoft WebView2 Runtime', 'pawnio':'PawnIO sensor driver',
          'presentmon':'PresentMon console', 'lively':'Lively Wallpaper'}


def enabled(hub):
    return os.name == 'nt' and hub.settings.get('automatic_dependencies', True) and (
        getattr(sys, 'frozen', False) or Path(sys.argv[0]).name.lower() == 'retweaks.py' or os.environ.get('RETWEAKS_AUTO_DEPENDENCIES') == '1')


def presentmon_path():
    from core.fps import find_presentmon_near_exe
    return find_presentmon_near_exe() or str(cache_dir() / 'PresentMon.exe')


def cache_dir():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'RETWEAKS' / 'Dependencies'


def available(key):
    if key == 'presentmon':
        path = Path(presentmon_path())
        if not path.is_file():return False
        # The managed console must still match the verified download after a restart.
        if path == cache_dir() / 'PresentMon.exe':
            return hashlib.sha256(path.read_bytes()).hexdigest() == PRESENTMON_SHA256
        return True
    if key == 'lively':
        from core.lively_wallpaper import find_executable
        return bool(find_executable())
    if key == 'pawnio':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Services\PawnIO'):
                return True
        except OSError:return False
    if key == 'webview2':
        for base in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
            folder = Path(os.environ.get(base, '')) / 'Microsoft' / 'EdgeWebView' / 'Application'
            if folder.is_dir() and any(folder.glob('*/msedgewebview2.exe')):return True
        return False
    raise ValueError('Unknown dependency')


def download(url, path, expected=None):
    """Only fixed publisher URLs enter this function; installer redirects use HTTPS."""
    from urllib.parse import urlsplit
    allowed = ('github.com','githubusercontent.com','microsoft.com','sfx.ms','msedge.net')
    with urlopen(Request(url, headers={'User-Agent':'ReTweaks dependency setup'}), timeout=45) as response:
        host = (urlsplit(response.url).hostname or '').lower()
        if urlsplit(response.url).scheme != 'https' or not any(host == d or host.endswith('.'+d) for d in allowed):
            raise OSError('Dependency download left the publisher download servers.')
        total=0
        with open(path, 'wb') as output:
            while True:
                chunk=response.read(256*1024)
                if not chunk:break
                total += len(chunk)
                if total > 200*1024*1024:raise OSError('Dependency download exceeds the size limit.')
                output.write(chunk)
    if expected and hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
        raise OSError('Dependency checksum failed; nothing was installed.')


def run_installer(command):
    result=subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=1200,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode not in (0, 3010, 1641):
        raise OSError(f'Installer failed with code {result.returncode}. Retry or use the official installer.')
    return result.returncode in (3010,1641)


def install(key):
    if available(key):return 'Already installed.'
    if key == 'lively':
        from core.lively_wallpaper import install as install_lively
        install_lively()
    else:
        cache_dir().mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='setup-',dir=cache_dir()) as temp:
            path=Path(temp)/'setup.exe'
            reboot=False
            if key == 'presentmon':
                download(PRESENTMON_URL,path,PRESENTMON_SHA256)
                os.replace(path,cache_dir()/'PresentMon.exe')
            elif key == 'pawnio':
                download(PAWNIO_URL,path,PAWNIO_SHA256)
                reboot=run_installer([str(path),'-install','-silent'])
            elif key == 'webview2':
                download(WEBVIEW_URL,path)
                # Evergreen bootstrapper changes; verify Microsoft's signature before running it.
                from core.winutil import run_powershell
                literal=str(path).replace("'","''")
                check=run_powershell("$s=Get-AuthenticodeSignature -LiteralPath '"+literal+"'; "
                    "if($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'O=Microsoft Corporation'){ 'verified' }",timeout=30)
                if str(check).strip() != 'verified':raise OSError('Microsoft installer signature could not be verified.')
                reboot=run_installer([str(path),'/silent','/install'])
            else:raise ValueError('Unknown dependency')
            if reboot:return 'Installed. Restart Windows to finish setup.'
    if not available(key):raise OSError('Setup finished, but the component was not detected. Restart Windows or retry.')
    return 'Installed and verified.'
