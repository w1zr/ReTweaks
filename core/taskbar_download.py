"""Download the official TranslucentTB App Installer and install for this user."""
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import xml.etree.ElementTree as ET


SOURCE = 'https://github.com/TranslucentTB/TranslucentTB/releases/latest/download/TranslucentTB.appinstaller'
INSTALL = r'''$ErrorActionPreference='Stop'
try {
  Add-AppxPackage -AppInstallerFile $env:RETWEAKS_TB_INSTALLER -ErrorAction Stop
  $p = Get-AppxPackage -Name $env:RETWEAKS_TB_PACKAGE -ErrorAction Stop
  if (-not $p) { throw 'Windows did not confirm the installed package.' }
  Write-Output ('Installed TranslucentTB ' + $p.Version + '. Open TranslucentTB from Start to choose the taskbar appearance.')
} catch { Write-Output $_.Exception.Message; exit 1 }
'''


def official_url(url):
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
            return False
        host = (p.hostname or '').lower()
        if host == 'github.com':
            return p.path.lower().startswith('/translucenttb/translucenttb/releases/')
        return host in ('release-assets.githubusercontent.com', 'objects.githubusercontent.com')
    except ValueError:
        return False


def package_identity(data):
    root = ET.fromstring(data)
    for item in root:
        if item.tag.rsplit('}', 1)[-1] in ('MainPackage', 'MainBundle'):
            name = item.get('Name', '')
            if 'translucenttb' not in name.lower() or not official_url(item.get('Uri', '')):
                break
            return name
    raise ValueError('The official download did not contain a TranslucentTB package.')


def download_and_install(progress, destination=None, opener=None, runner=None):
    class Guard(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not official_url(newurl):
                raise ValueError('TranslucentTB download redirected outside its official release servers.')
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    destination = Path(destination or Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) /
                       'RETWEAKS' / 'Downloads' / 'TranslucentTB')
    destination.mkdir(parents=True, exist_ok=True)
    progress('Downloading the official TranslucentTB installer…')
    open_url = opener or build_opener(Guard()).open
    with open_url(Request(SOURCE, headers={'User-Agent': 'RETWEAKS'}), timeout=30) as response:
        if not official_url(response.geturl()):
            raise ValueError('Unexpected TranslucentTB download source.')
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('Unexpected installer descriptor size.')
    identity = package_identity(data)
    path = destination / 'TranslucentTB.appinstaller'
    path.write_bytes(data)
    progress('Installing TranslucentTB through Windows…')
    result = (runner or subprocess.run)(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', INSTALL],
        env={**os.environ, 'RETWEAKS_TB_INSTALLER': str(path), 'RETWEAKS_TB_PACKAGE': identity},
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900,
        creationflags=0x08000000)
    message = (result.stdout or result.stderr or '').strip()
    if result.returncode:
        raise OSError(message or 'Windows could not install TranslucentTB. Check App Installer and try again.')
    return message or 'TranslucentTB installed.'
