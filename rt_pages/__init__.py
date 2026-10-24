"""RETWEAKS pages added to the Tk-based app (owner decision 2026-10-22).

REGISTRY entries: (key, module, class). hubplus builds one tab per entry (hub.rt_tabs[key] = tab index,
hub.rt_pages[key] = page object). The sidebar order lives in rt_sidebar.py. A module that fails to
import shows the real error on its page and in the Activity log, never a fake page.
Pages may define on_shown() / on_hidden() (called when their tab is shown / left) and close()."""
REGISTRY = [
    ("Dashboard", "rt_pages.monitor", "MonitorPage"),          # home screen (RETWEAKS dashboard)
    ("Hardware", "rt_pages.hardware", "HardwarePage"),
    ("Health Check", "rt_pages.health", "HealthPage"),
    ("FPS overlay", "rt_pages.fps", "FpsPage"),     # was "FPS test" (renamed 2026-10-22)
    ("Display", "rt_pages.display", "DisplayPage"),
    ("Exact-undo tweaks", "rt_pages.tweaks_exact", "ExactTweaksPage"),
    ("Game config files", "rt_pages.game_files", "GameFilesPage"),
    ("Program rules", "rt_pages.rules", "RulesPage"),
    ("Startup apps", "rt_pages.startup", "StartupPage"),
    ("Network", "rt_pages.network", "NetworkPage"),
    ("Cleanup", "rt_pages.cleanup", "CleanupPage"),
    ("Browser", "rt_pages.browser", "BrowserPage"),
    ("Snapshots", "rt_pages.snapshots", "SnapshotsPage"),
    ("Fun tools", "rt_pages.fun", "FunPage"),
    # From base app v1.5 (owner request 2026-10-22): rt_pages/cooling.py
    ("Temperatures", "rt_pages.cooling", "TemperaturesPage"),
    ("Fan control", "rt_pages.cooling", "FanControlPage"),
    ("RGB lighting", "rt_pages.cooling", "LightingPage"),
    ("Run", "rt_pages.cooling", "RunLauncherPage"),
    ("Crosshair", "rt_pages.crosshair", "CrosshairPage"),
    ("About", "rt_pages.about", "AboutPage"),
    ("Settings", "rt_pages.settings_page", "SettingsPage"),
    ("Transparent TB (taskbar)", "rt_pages.taskbar", "TaskbarPage"),
    ("File Transfers", "rt_pages.file_transfers", "FileTransfersPage"),
    ("Backgrounds", "rt_pages.wallpaper", "WallpaperPage"),
]


# page key -> attribute on the hub of the frame the page is built into instead of its own tab
EMBEDDED = {"Exact-undo tweaks": "tweaks_exact_holder"}
TWEAKS_TAB = 1            # Individual tweaks (the base app's tab index)


def open_exact_undo(hub, search=None):
    """Open Individual tweaks on its Exact undo tab (optionally filling that tab's search box)."""
    hub.show_tab(TWEAKS_TAB)
    if callable(getattr(hub, "show_tweaks_tab", None)):
        hub.show_tweaks_tab("exact")
    if search is not None:
        page = getattr(hub, "rt_pages", {}).get("Exact-undo tweaks")
        var = getattr(page, "query", None)
        if var is not None:
            try:
                var.set(search)
            except Exception:
                pass


def build_pages(hub, g, make_tab):
    """make_tab() -> (frame, index). Fills hub.rt_tabs / hub.rt_pages."""
    import importlib
    import tkinter as tk
    import traceback
    hub.rt_tabs, hub.rt_pages = {}, {}
    intro = getattr(hub, "intro", None)
    for key, module, cls in REGISTRY:
        if intro is not None and not intro.closed:
            intro.pump(f"Loading {key}\u2026")      # keeps the startup animation moving
        tab, index = make_tab()
        hub.rt_tabs[key] = index
        # Exact-undo tweaks are shown inside Individual tweaks (second tab, owner request 2026-10-22). The page keeps
        # its own (empty) tab index so old links still work: hub.show_tab redirects it to Individual tweaks.
        if key in EMBEDDED and getattr(hub, EMBEDDED[key], None) is not None:
            tab = getattr(hub, EMBEDDED[key])
        try:
            page = getattr(importlib.import_module(module), cls)(hub, tab, g)
            hub.rt_pages[key] = page
        except Exception as e:
            err = "".join(traceback.format_exception_only(type(e), e)).strip()
            tk.Label(tab, text=f"{key} could not load: {err}", bg=g["BG"], fg="#ff5c5c", font=(g["UI"], 10),
                     justify="left", wraplength=700).pack(anchor="w", padx=20, pady=20)
            hub.rt_pages[key] = None
    if callable(getattr(hub, "show_tweaks_tab", None)):
        settings = getattr(hub, "settings", None) or {}
        hub.show_tweaks_tab(settings.get("tweaks_tab", "all"), save=False)
