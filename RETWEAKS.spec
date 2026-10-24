# -*- mode: python ; coding: utf-8 -*-
# RETWEAKS single-file build (combined app). Run through build.py, which compiles the ai\ helpers first.
import importlib.util
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Fail before packaging if a browser component or its local pages are absent.
for browser_file in ('ai/EmbeddedBrowser.exe', 'ai/Microsoft.Web.WebView2.Core.dll',
                     'ai/Microsoft.Web.WebView2.WinForms.dll', 'ai/WebView2Loader.dll',
                     'assets/browser-home.html', 'assets/browser-settings.html'):
    if not os.path.isfile(browser_file) or os.path.getsize(browser_file) == 0:
        raise RuntimeError('Required browser component is missing: ' + browser_file)


datas = [
    ('assets', 'assets'),                     # chip logo, startup frames, sidebar icons, app artwork, .ico files
    ('renderbench.html', '.'),
    ('ai/GeminiChat.exe', 'ai'), ('ai/EmbeddedAI.exe', 'ai'), ('ai/EmbeddedAI.exe.config', 'ai'),
    ('ai/DriverAI.exe', 'ai'), ('ai/ValueAI.exe', 'ai'), ('ai/ValueAI.exe.config', 'ai'),
    ('ai/EmbeddedSite.exe', 'ai'), ('ai/Microsoft.Web.WebView2.Core.dll', 'ai'),
    # Browser page: the RETWEAKS Browser program (the base app's v1.5 EmbeddedBrowser, own process; its pages
    # browser-home/settings/library.html live in assets)
    ('ai/EmbeddedBrowser.exe', 'ai'),
    ('ai/Microsoft.Web.WebView2.WinForms.dll', 'ai'), ('ai/WebView2Loader.dll', 'ai'),
    ('ai/WebView2-LICENSE.txt', 'ai'), ('ai/WebView2-NOTICE.txt', 'ai'),
    # Hardware engines (owner decision 2026-10-22: bundled): LibreHardwareMonitor 0.9.6 + the
    # SensorHost bridge (temperatures, fans, fan control) and OpenRGB 1.1 portable (RGB lighting), with licenses
    ('ai/sensors', 'ai/sensors'), ('ai/openrgb', 'ai/openrgb'),
    ('LICENSE', '.'),
    # translations (rt_i18n): Spanish, French, German, Brazilian Portuguese; i18n/work and strings_en.json stay out
    ('i18n/es.json', 'i18n'), ('i18n/fr.json', 'i18n'), ('i18n/de.json', 'i18n'), ('i18n/pt-BR.json', 'i18n'),
]

hiddenimports = (['retweaks_data', 'hubplus', 'rt_shell', 'rt_sidebar', 'rt_crashlog', 'rt_search', 'rt_splash_client', 'rt_traymenu', 'rt_perf', 'embedded_browser', 'rt_splash_qt', 'ui.splash', 'ui.widgets.brand', 'PIL._imaging', 'PIL._imagingtk',
                  'pycaw.utils', 'comtypes.stream', 'comtypes.persist', 'pystray._win32',
                  'win32pipe', 'win32file', 'win32pdh', 'win32com.client', 'pynvml']
                 + collect_submodules('rt_pages')   # loaded by name from rt_pages.REGISTRY
                 + collect_submodules('core')
                 + collect_submodules('pycaw')
                 + ['temperatures', 'gpu_metrics', 'thermal_dashboard', 'rgb_service', 'rgb_sync', 'cooling_panel',
                    'run_panel'] + collect_submodules('openrgb'))     # fans / RGB / sensors / Run

a = Analysis(
    ['retweaks.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Qt is only used for the v1.6 startup screen (rt_splash_qt -> ui.splash, ui.widgets.brand); the rest of
    # the legacy Qt UI isn't imported, and the big Qt modules are kept out.
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtQml', 'PySide6.QtQuick',
              'PySide6.QtNetwork', 'PySide6.QtMultimedia', 'PySide6.Qt3DCore', 'PySide6.QtPdf',
              'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtSql', 'PySide6.QtOpenGL'],
    noarchive=False,
    optimize=0,
)
# OpenRGB keeps its own Qt runtime beside its executable. Analysis also hoists
# its DLLs to the root, which Windows searches before PySide6's directory.
# Root Qt DLLs must match PySide6; OpenRGB's private copies remain unchanged.
import PySide6
qt_runtime = os.path.dirname(PySide6.__file__)
qt_binaries = []
for destination, source, kind in a.binaries:
    if (os.path.basename(destination) == destination
            and destination.lower().startswith('qt6')
            and 'openrgb' in source.lower()):
        source = os.path.join(qt_runtime, destination)
        if not os.path.isfile(source):
            raise RuntimeError('Missing matching PySide6 runtime: ' + destination)
    qt_binaries.append((destination, source, kind))
# Qt 6 uses the Windows ICU API. A Poppler ICU from the build machine has
# different exports despite the same filename and must not shadow System32.
a.binaries = [entry for entry in qt_binaries
              if not (entry[0].lower() == 'icuuc.dll'
                      and 'poppler' in entry[1].lower())]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RETWEAKS',
    icon='assets/icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
)
