# core/tweaks_catalog.py
"""More individual tweaks (v1.4.3): gaming, privacy, interface, services and maintenance.

Rules (CLAUDE.md section 8): only documented Windows settings, i.e. the values the Settings app,
Control Panel or official Group Policy write, and standard service start types. Each tweak says
what it does, its trade-off, whether it needs admin rights or a restart, and can be undone
exactly (the original values are saved before the first change by core.tweaks.Tweak).

"On" always means what the tweak's name says.
"""

import core.tweaks as _tw
from core.tweaks import ADVANCED, REG_DWORD, REG_SZ, STANDARD, Tweak

GAMING, PRIVACY, INTERFACE, SERVICES, MAINTENANCE = "Gaming", "Privacy", "Interface", "Services", "Maintenance"
CATEGORY_ORDER = [GAMING, PRIVACY, INTERFACE, SERVICES, MAINTENANCE]

CU = r"HKCU\Software\Microsoft\Windows\CurrentVersion"
CDM = CU + r"\ContentDeliveryManager"
ADV = CU + r"\Explorer\Advanced"
POL = r"HKLM\SOFTWARE\Policies\Microsoft\Windows"
SVC = r"HKLM\SYSTEM\CurrentControlSet\Services"


def _d(path, name, on, off):
    return {(path, name): (REG_DWORD, on)}, {(path, name): (REG_DWORD, off)}


def _many(pairs):
    """pairs: [(path, name, on, off)] -> (values_on, values_off)."""
    on = {(p, n): (REG_DWORD, a) for p, n, a, _ in pairs}
    off = {(p, n): (REG_DWORD, b) for p, n, _, b in pairs}
    return on, off


def T(tid, name, cat, level, desc, tradeoff, values, admin=False, restart=None):
    t = Tweak(tid, name, level, desc, tradeoff, values[0], values[1], admin=admin, restart=restart)
    t.category = cat
    return t


def Service(tid, svc, name, desc, tradeoff, default_start):
    """Turning a Windows service off = start type Disabled (4). Undo restores the exact original
    start type. Changes apply after a restart (RYTWEAKS never force-stops services)."""
    t = Tweak(tid, name, ADVANCED, desc, tradeoff,
              {(SVC + "\\" + svc, "Start"): (REG_DWORD, default_start)},
              {(SVC + "\\" + svc, "Start"): (REG_DWORD, 4)}, admin=True, restart="restart")
    t.category = SERVICES
    return t


class ClassicMenuTweak(Tweak):
    """Windows 11: show the full right-click menu right away instead of "Show more options".
    It works by registering an empty handler key that Windows 11's new menu checks for; turning
    it off removes that key again."""

    KEY = r"HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"

    def __init__(self):
        super().__init__(
            "classic_menu", "Full right-click menu (Windows 11)", STANDARD,
            "Shows the full classic right-click menu immediately, without clicking "
            "“Show more options”.",
            "Windows 11 only. Takes effect after you sign out, or restart Windows Explorer. "
            "A future Windows update could stop supporting it.",
            {(self.KEY + r"\InprocServer32", ""): (REG_SZ, "")},
            {(self.KEY + r"\InprocServer32", ""): (REG_SZ, None)}, restart="signout")
        self.category = INTERFACE

    def get_state(self):
        try:
            return "On" if _tw.REG.get(self.KEY + r"\InprocServer32", "") is not None else "Off"
        except Exception:
            return "Unknown"

    def _remove(self):
        _tw.REG.delete(self.KEY + r"\InprocServer32", "")
        if hasattr(_tw.REG, "delete_key"):
            _tw.REG.delete_key(self.KEY + r"\InprocServer32")
            _tw.REG.delete_key(self.KEY)

    def _apply(self, on):
        try:
            self._backup_once()
            if on:
                _tw.REG.set(self.KEY + r"\InprocServer32", "", REG_SZ, "")
            else:
                self._remove()
        except PermissionError:
            return False, "Windows refused the change."
        except Exception as e:
            return False, str(e)
        return True, f"{self.name}: {'on' if on else 'off'}. Sign out and back in for it to take effect."

    def _undo(self):
        from core.tweaks import _save_backups, load_backups
        backups = load_backups()
        entry = backups.get(self.id)
        if not entry:
            return False, "Nothing to undo: RYTWEAKS hasn't changed this setting."
        try:
            if entry["values"][0][2] is None:
                self._remove()
            else:
                _tw.REG.set(self.KEY + r"\InprocServer32", "", REG_SZ, entry["values"][0][2][1])
        except Exception as e:
            return False, str(e)
        del backups[self.id]
        _save_backups(backups)
        return True, f"{self.name}: restored to how it was before."


def more_tweaks():
    return [
        # ------------------------------------------------------------ Gaming
        T("background_apps", "Let Store apps run in the background", GAMING, ADVANCED,
          "Microsoft Store apps (Mail, Weather, Phone Link, etc.) can keep running and updating while "
          "you play. Off is the official policy “Let Windows apps run in the background: Force Deny”.",
          "Off means those apps can't notify you or sync until you open them. Normal desktop programs "
          "(Discord, Steam) are not affected.",
          _d(POL + r"\AppPrivacy", "LetAppsRunInBackground", 0, 2), admin=True),
        T("menu_delay", "Faster menus", GAMING, STANDARD,
          "Cuts the pause before menus and submenus open on the desktop from 400 ms to 100 ms.",
          "Purely a desktop feel thing; it doesn't change in-game FPS. Sign out to apply everywhere.",
          ({(r"HKCU\Control Panel\Desktop", "MenuShowDelay"): (REG_SZ, "100")},
           {(r"HKCU\Control Panel\Desktop", "MenuShowDelay"): (REG_SZ, "400")}), restart="signout"),
        T("animations", "Window animations", GAMING, STANDARD,
          "The minimize/maximize animation of windows.",
          "Off makes windows snap instantly; it doesn't change in-game FPS. Sign out to apply.",
          ({(r"HKCU\Control Panel\Desktop\WindowMetrics", "MinAnimate"): (REG_SZ, "1")},
           {(r"HKCU\Control Panel\Desktop\WindowMetrics", "MinAnimate"): (REG_SZ, "0")}), restart="signout"),

        # ------------------------------------------------------------ Privacy
        T("ad_id", "Advertising ID", PRIVACY, STANDARD,
          "A per-user ID apps can use to show you personalized ads.",
          "Off: you still see ads in some apps, just not personalized ones. Same as Settings → Privacy.",
          _d(CU + r"\AdvertisingInfo", "Enabled", 1, 0)),
        T("tailored", "Tailored experiences", PRIVACY, STANDARD,
          "Lets Microsoft use your diagnostic data for personalized tips, ads and recommendations.",
          "Off: nothing breaks. Same as Settings → Privacy → Diagnostics & feedback.",
          _d(CU + r"\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 1, 0)),
        T("diag_data", "Optional diagnostic data", PRIVACY, STANDARD,
          "Sends extra data about how you use Windows and apps to Microsoft. Off keeps only the "
          "required diagnostic data (the official AllowTelemetry policy = 1).",
          "Off: Windows Insider builds need optional data. Otherwise nothing breaks.",
          _d(POL + r"\DataCollection", "AllowTelemetry", 3, 1), admin=True),
        T("activity_history", "Activity history", PRIVACY, STANDARD,
          "Windows records the apps, files and sites you use, and can upload it to your Microsoft account.",
          "Off: Timeline-style “pick up where you left off” features stop working.",
          _many([(POL + r"\System", "PublishUserActivities", 1, 0),
                 (POL + r"\System", "UploadUserActivities", 1, 0)]), admin=True),
        T("web_search_start", "Web results in Start search", PRIVACY, STANDARD,
          "Typing in Start also searches Bing and shows web suggestions.",
          "Off: Start only searches your PC and apps. Sign out to apply.",
          _d(r"HKCU\Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", 0, 1),
          restart="signout"),
        T("online_speech", "Online speech recognition", PRIVACY, STANDARD,
          "Sends your voice to Microsoft's cloud for dictation and voice typing.",
          "Off: voice typing (Win+H) won't work. Same as Settings → Privacy → Speech.",
          _d(r"HKCU\Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy", "HasAccepted", 1, 0)),
        T("inking_typing", "Inking & typing personalization", PRIVACY, STANDARD,
          "Windows learns from what you type and write to build a personal dictionary.",
          "Off: text suggestions are less personal and the learned dictionary stops growing.",
          _many([(r"HKCU\Software\Microsoft\InputPersonalization", "RestrictImplicitTextCollection", 0, 1),
                 (r"HKCU\Software\Microsoft\InputPersonalization", "RestrictImplicitInkCollection", 0, 1),
                 (r"HKCU\Software\Microsoft\InputPersonalization\TrainedDataStore", "HarvestContacts", 1, 0)])),
        T("suggested_content", "Suggested content in Settings", PRIVACY, STANDARD,
          "Microsoft suggestions and promotions inside the Settings app.",
          "Off: nothing breaks.",
          _many([(CDM, "SubscribedContent-338393Enabled", 1, 0), (CDM, "SubscribedContent-353694Enabled", 1, 0),
                 (CDM, "SubscribedContent-353696Enabled", 1, 0)])),
        T("start_suggestions", "App suggestions in Start", PRIVACY, STANDARD,
          "Occasional promoted apps in the Start menu.",
          "Off: nothing breaks.",
          _many([(CDM, "SystemPaneSuggestionsEnabled", 1, 0), (CDM, "SubscribedContent-338388Enabled", 1, 0)])),
        T("tips", "Tips and suggestions notifications", PRIVACY, STANDARD,
          "Pop-up tips and “get even more out of Windows” suggestions.",
          "Off: nothing breaks.",
          _many([(CDM, "SubscribedContent-338389Enabled", 1, 0), (CDM, "SoftLandingEnabled", 1, 0)])),
        T("lockscreen_tips", "Fun facts and tips on the lock screen", PRIVACY, STANDARD,
          "Text overlays with tips and facts on the lock screen.",
          "Off: the lock screen picture stays, without the text.",
          _many([(CDM, "RotatingLockScreenOverlayEnabled", 1, 0), (CDM, "SubscribedContent-338387Enabled", 1, 0)])),
        T("silent_apps", "Automatic installs of suggested apps", PRIVACY, STANDARD,
          "Windows can quietly install promoted apps (often games) for new accounts.",
          "Off: apps you already have stay; no new ones get added on their own.",
          _d(CDM, "SilentInstalledAppsEnabled", 1, 0)),

        # ------------------------------------------------------------ Interface
        T("file_ext", "Show file extensions", INTERFACE, STANDARD,
          "Shows the end of file names (.exe, .pdf, .png) in File Explorer.",
          "Useful for safety: a “photo.png.exe” is easy to spot. Refresh Explorer (F5) to see it.",
          _d(ADV, "HideFileExt", 0, 1)),
        T("hidden_files", "Show hidden files", INTERFACE, STANDARD,
          "Shows files and folders Windows normally hides, like AppData.",
          "More clutter in folders. Protected system files stay hidden.",
          _d(ADV, "Hidden", 1, 2)),
        ClassicMenuTweak(),
        T("taskbar_left", "Taskbar icons on the left (Windows 11)", INTERFACE, STANDARD,
          "Moves the Start button and taskbar icons from the center to the left, like Windows 10.",
          "Just a layout change.",
          _d(ADV, "TaskbarAl", 0, 1)),
        T("task_view_btn", "Task View button on the taskbar", INTERFACE, STANDARD,
          "The button for virtual desktops and open windows. Win+Tab still works without it.",
          "Just a layout change.",
          _d(ADV, "ShowTaskViewButton", 1, 0)),
        T("widgets", "Widgets (news and weather panel)", INTERFACE, STANDARD,
          "The Widgets board with news, weather and stocks. Off uses the official "
          "“Allow widgets” policy, so it also removes the taskbar button.",
          "Off: the Widgets board and its background process are gone until you turn it back on.",
          _d(r"HKLM\SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests", 1, 0), admin=True,
          restart="signout"),
        T("dark_mode", "Dark mode for Windows and apps", INTERFACE, STANDARD,
          "Dark taskbar, Start, Settings and apps that follow the system theme.",
          "Same as Settings → Personalization → Colors.",
          _many([(CU + r"\Themes\Personalize", "AppsUseLightTheme", 0, 1),
                 (CU + r"\Themes\Personalize", "SystemUsesLightTheme", 0, 1)])),
        T("end_task", "“End task” in taskbar right-click (Windows 11)", INTERFACE, STANDARD,
          "Right-click a frozen app on the taskbar and close it without opening Task Manager.",
          "Needs Windows 11 23H2 or newer. Ending a task loses unsaved work in that app.",
          _d(ADV + r"\TaskbarDeveloperSettings", "TaskbarEndTask", 1, 0)),
        T("explorer_this_pc", "Open File Explorer to This PC", INTERFACE, STANDARD,
          "File Explorer opens on your drives instead of Home / Quick access.",
          "Just a starting-folder change.",
          _d(ADV, "LaunchTo", 1, 2)),

        # ------------------------------------------------------------ Services
        Service("svc_diagtrack", "DiagTrack", "Telemetry service (Connected User Experiences)",
                "The background service that collects and sends diagnostic data to Microsoft.",
                "Off: Windows can't send diagnostic data; some troubleshooters show less info.", 2),
        Service("svc_sysmain", "SysMain", "SysMain (Superfetch)",
                "Preloads apps you use often into RAM so they open faster.",
                "Off can make apps open slower, especially from a hard drive. On fast SSDs the "
                "difference is small. Some people see less disk activity with it off. Test both ways.", 2),
        Service("svc_wsearch", "WSearch", "Windows Search indexing",
                "Indexes your files so searching in Start and File Explorer is instant.",
                "Off: file searches become much slower and Outlook search may break. App search in "
                "Start still works.", 2),
        Service("svc_spooler", "Spooler", "Print Spooler",
                "Needed for printing and PDF printers.",
                "Off: you can't print at all until you turn it back on. Only turn it off if you never print.", 2),
        Service("svc_fax", "Fax", "Fax service",
                "Sends and receives faxes through a fax modem.",
                "Off: faxing doesn't work. Almost nobody uses it.", 3),
        Service("svc_maps", "MapsBroker", "Downloaded Maps Manager",
                "Keeps offline maps for the Maps app up to date.",
                "Off: offline maps stop updating.", 2),
        Service("svc_wer", "WerSvc", "Windows Error Reporting service",
                "Sends crash reports to Microsoft when an app or Windows fails.",
                "Off: crash reports aren't sent, so Microsoft can't offer fixes for them.", 3),

        # ------------------------------------------------------------ Maintenance
        T("storage_sense", "Storage Sense (automatic cleanup)", MAINTENANCE, STANDARD,
          "Windows automatically clears temporary files and, if you set it up, old Recycle Bin and "
          "Downloads files.",
          "Check its settings (Settings → System → Storage) so it doesn't empty folders you care about.",
          _d(CU + r"\StorageSense\Parameters\StoragePolicy", "01", 1, 0)),
        T("update_restart", "No automatic restart while I'm signed in", MAINTENANCE, STANDARD,
          "Windows Update won't restart the PC on its own while you're signed in, so it can't restart "
          "in the middle of a game. The official “No auto-restart with logged on users” policy.",
          "Updates still install; you restart when it suits you. Don't put it off for weeks.",
          _d(POL + r"\WindowsUpdate\AU", "NoAutoRebootWithLoggedOnUsers", 1, 0), admin=True),
        T("wu_drivers", "Drivers from Windows Update", MAINTENANCE, ADVANCED,
          "Windows Update also installs hardware drivers, which can replace a GPU driver you installed "
          "yourself with an older one.",
          "Off: you update drivers yourself (NVIDIA app / AMD Adrenalin / Intel). Some devices "
          "won't get driver fixes automatically.",
          _d(POL + r"\WindowsUpdate", "ExcludeWUDriversInQualityUpdate", 0, 1), admin=True),
        T("delivery_p2p", "Share updates with PCs on my network", MAINTENANCE, STANDARD,
          "Delivery Optimization: downloads parts of updates from and uploads to other PCs on your "
          "home network. Off makes Windows download updates only from Microsoft.",
          "Off: each PC on your network downloads updates on its own.",
          _d(POL + r"\DeliveryOptimization", "DODownloadMode", 1, 0), admin=True),
    ]


# Categories for the tweaks that already existed before v1.4.3
EXISTING_CATEGORY = {"game_mode": GAMING, "xbox_capture": GAMING, "mouse_accel": GAMING,
                     "windowed_games": GAMING, "hags": GAMING, "transparency": INTERFACE,
                     "sticky_keys_popup": INTERFACE, "fast_startup": MAINTENANCE,
                     "hibernation": MAINTENANCE}
