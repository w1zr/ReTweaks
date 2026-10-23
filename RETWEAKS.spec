# -*- mode: python ; coding: utf-8 -*-
# RETWEAKS single-file build (combined app). Run through build.py, which compiles the ai\ helpers first.
import importlib.util
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules


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
