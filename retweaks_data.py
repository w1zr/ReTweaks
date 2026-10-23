"""RETWEAKS data + engine (tweaks, presets, tips, game settings). Shared by the GUI and the .bat."""
import ctypes, os, sys, subprocess

NOWIN = 0x08000000  # CREATE_NO_WINDOW
# Backups made by the base app before v2.0 (Undo still restores them): hosts copy and registry-backup task.
_OLD_HOSTS_BAK = "." + "perf" + "hub.bak"
_OLD_REG_TASK = "Perf" + "Hub_RegBackup"
APP = "RETWEAKS"

# ----------------------------------------------------------------- helpers
def ensure_admin():
    if os.name != "nt":
        return
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        pass
    frozen = getattr(sys, "frozen", False)
    args = sys.argv[1:] if frozen else [os.path.abspath(sys.argv[0])] + sys.argv[1:]
    params = " ".join(f'"{a}"' for a in args)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    sys.exit()

def win_build():
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0

IS_WIN11 = win_build() >= 22000

def run(kind, cmd):
    try:
        if kind == "ps":
            p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                               capture_output=True, text=True, errors="replace", creationflags=NOWIN)
        else:
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               errors="replace", creationflags=NOWIN)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, str(e)

def reg(key, name, val, typ="REG_DWORD"):
    return ("cmd", f'reg add "{key}" /v "{name}" /t {typ} /d {val} /f')

def regdel(key, name):
    return ("cmd", f'reg delete "{key}" /v "{name}" /f')

def svc_off(name):
    return [("cmd", f"sc stop {name}"), ("cmd", f"sc config {name} start= disabled")]

def svc_on(name, mode="auto"):
    return [("cmd", f"sc config {name} start= {mode}"), ("cmd", f"sc start {name}")]

# ----------------------------------------------------------------- tweaks
TWEAKS = []
def T(id, cat, name, desc, apply, undo=None, risk="Safe", reboot=False, win11=False):
    TWEAKS.append(dict(id=id, cat=cat, name=name, desc=desc, apply=apply, undo=undo,
                       risk=risk, reboot=reboot, win11=win11))

HK_MM = r"HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
HK_EXP = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer"
HK_ADV = HK_EXP + r"\Advanced"
HK_CDM = r"HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"

# ---- Performance
T("ultimate", "Performance", "Ultimate Performance power plan",
  "Unlocks and activates the hidden Ultimate Performance plan (no core parking, max clocks). Uses more power.",
  [("ps", r"$o = powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61; "
          r"if ($o -match '[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}') { powercfg -setactive $matches[0]; 'Activated ' + $matches[0] } else { $o }")],
  [("cmd", "powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e")])
T("prio_sep", "Performance", "Foreground app priority boost",
  "Win32PrioritySeparation = 38: gives the app you're using (your game) more CPU time slices.",
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\PriorityControl", "Win32PrioritySeparation", 38)],
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\PriorityControl", "Win32PrioritySeparation", 2)])
T("power_throttle", "Performance", "Disable power throttling",
  "Stops Windows from throttling background/foreground processes to save power.",
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerThrottling", "PowerThrottlingOff", 1)],
  [regdel(r"HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerThrottling", "PowerThrottlingOff")])
T("usb_suspend", "Performance", "Disable USB selective suspend",
  "Prevents USB devices (mouse/keyboard/headset) from sleeping. Fixes random input lag/disconnects.",
  [("cmd", "powercfg /SETACVALUEINDEX SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 0"),
   ("cmd", "powercfg /SETACTIVE SCHEME_CURRENT")],
  [("cmd", "powercfg /SETACVALUEINDEX SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3 48e6b7a6-50f5-4782-a5d4-53bb8f07e226 1"),
   ("cmd", "powercfg /SETACTIVE SCHEME_CURRENT")])
T("bg_apps", "Performance", "Disable background apps",
  "Stops Store apps from running in the background and eating CPU/RAM/network.",
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled", 1),
   reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsRunInBackground", 2)],
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled", 0),
   regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsRunInBackground")])
T("startup_delay", "Performance", "Remove startup app delay",
  "Startup apps launch immediately after login instead of waiting ~10 seconds.",
  [reg(HK_EXP + r"\Serialize", "StartupDelayInMSec", 0)],
  [regdel(HK_EXP + r"\Serialize", "StartupDelayInMSec")])
T("visual_fx", "Performance", "Reduce visual effects / animations",
  "Sets Windows to 'Adjust for best performance' style animations. Sign out to fully apply.",
  [reg(HK_EXP + r"\VisualEffects", "VisualFXSetting", 2),
   reg(r"HKCU\Control Panel\Desktop\WindowMetrics", "MinAnimate", 0, "REG_SZ"),
   reg(HK_ADV, "TaskbarAnimations", 0),
   reg(r"HKCU\Control Panel\Desktop", "MenuShowDelay", 0, "REG_SZ")],
  [reg(HK_EXP + r"\VisualEffects", "VisualFXSetting", 0),
   reg(r"HKCU\Control Panel\Desktop\WindowMetrics", "MinAnimate", 1, "REG_SZ"),
   reg(HK_ADV, "TaskbarAnimations", 1),
   reg(r"HKCU\Control Panel\Desktop", "MenuShowDelay", 400, "REG_SZ")])
T("transparency", "Performance", "Disable transparency effects",
  "Turns off acrylic/blur. Saves a little GPU and battery.",
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency", 0)],
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency", 1)])
T("faststart", "Performance", "Disable Fast Startup",
  "Makes shutdown a real shutdown. Fixes weird driver/uptime issues. Boot may be a bit slower.",
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HiberbootEnabled", 0)],
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power", "HiberbootEnabled", 1)], reboot=True)
T("hibernate", "Performance", "Disable hibernation (frees disk space)",
  "Deletes hiberfile.sys (several GB). You lose hibernate.",
  [("cmd", "powercfg -h off")], [("cmd", "powercfg -h on")], risk="Medium")

# ---- Gaming
T("gamedvr", "Gaming", "Disable Game DVR / Xbox capture",
  "Turns off background game recording that costs FPS.",
  [reg(r"HKCU\System\GameConfigStore", "GameDVR_Enabled", 0),
   reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 0),
   reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\GameDVR", "AllowGameDVR", 0)],
  [reg(r"HKCU\System\GameConfigStore", "GameDVR_Enabled", 1),
   reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", 1),
   regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\GameDVR", "AllowGameDVR")])
T("gamemode", "Gaming", "Enable Game Mode",
  "Windows prioritizes your game and blocks driver/update interruptions while playing.",
  [reg(r"HKCU\Software\Microsoft\GameBar", "AutoGameModeEnabled", 1),
   reg(r"HKCU\Software\Microsoft\GameBar", "AllowAutoGameMode", 1)],
  [reg(r"HKCU\Software\Microsoft\GameBar", "AutoGameModeEnabled", 0)])
T("hags", "Gaming", "Hardware-accelerated GPU scheduling",
  "Lets the GPU manage its own memory scheduling. Needs a recent GPU + driver (GTX 10+/RX 5000+). Reboot required.",
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", 2)],
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", 1)], reboot=True)
T("mmcss", "Gaming", "Game task priority (MMCSS)",
  "Raises CPU/GPU scheduling priority for the 'Games' multimedia task and sets system responsiveness to 0.",
  [reg(HK_MM, "SystemResponsiveness", 0),
   reg(HK_MM + r"\Tasks\Games", "GPU Priority", 8),
   reg(HK_MM + r"\Tasks\Games", "Priority", 6),
   reg(HK_MM + r"\Tasks\Games", "Scheduling Category", "High", "REG_SZ"),
   reg(HK_MM + r"\Tasks\Games", "SFIO Priority", "High", "REG_SZ")],
  [reg(HK_MM, "SystemResponsiveness", 20),
   reg(HK_MM + r"\Tasks\Games", "GPU Priority", 8),
   reg(HK_MM + r"\Tasks\Games", "Priority", 2),
   reg(HK_MM + r"\Tasks\Games", "Scheduling Category", "Medium", "REG_SZ"),
   reg(HK_MM + r"\Tasks\Games", "SFIO Priority", "Normal", "REG_SZ")])
T("mouse_accel", "Gaming", "Disable mouse acceleration",
  "Raw 1:1 mouse movement ('Enhance pointer precision' off). Sign out to apply.",
  [reg(r"HKCU\Control Panel\Mouse", "MouseSpeed", 0, "REG_SZ"),
   reg(r"HKCU\Control Panel\Mouse", "MouseThreshold1", 0, "REG_SZ"),
   reg(r"HKCU\Control Panel\Mouse", "MouseThreshold2", 0, "REG_SZ")],
  [reg(r"HKCU\Control Panel\Mouse", "MouseSpeed", 1, "REG_SZ"),
   reg(r"HKCU\Control Panel\Mouse", "MouseThreshold1", 6, "REG_SZ"),
   reg(r"HKCU\Control Panel\Mouse", "MouseThreshold2", 10, "REG_SZ")])
T("sticky", "Gaming", "Disable Sticky Keys popup",
  "Stops the Shift x5 popup from minimizing your game.",
  [reg(r"HKCU\Control Panel\Accessibility\StickyKeys", "Flags", 506, "REG_SZ"),
   reg(r"HKCU\Control Panel\Accessibility\Keyboard Response", "Flags", 122, "REG_SZ"),
   reg(r"HKCU\Control Panel\Accessibility\ToggleKeys", "Flags", 58, "REG_SZ")],
  [reg(r"HKCU\Control Panel\Accessibility\StickyKeys", "Flags", 510, "REG_SZ"),
   reg(r"HKCU\Control Panel\Accessibility\Keyboard Response", "Flags", 126, "REG_SZ"),
   reg(r"HKCU\Control Panel\Accessibility\ToggleKeys", "Flags", 62, "REG_SZ")])

# ---- Network
T("net_throttle", "Network", "Disable network throttling",
  "Removes the multimedia network throttle that can cap throughput/raise ping.",
  [reg(HK_MM, "NetworkThrottlingIndex", 4294967295)],
  [reg(HK_MM, "NetworkThrottlingIndex", 10)])
T("nagle", "Network", "Disable Nagle's algorithm (lower latency)",
  "Sets TcpAckFrequency=1 and TCPNoDelay=1 on all network interfaces. Can reduce online-game latency.",
  [("ps", r"Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces' | ForEach-Object { "
          r"New-ItemProperty -Path $_.PSPath -Name TcpAckFrequency -Value 1 -PropertyType DWord -Force | Out-Null; "
          r"New-ItemProperty -Path $_.PSPath -Name TCPNoDelay -Value 1 -PropertyType DWord -Force | Out-Null }")],
  [("ps", r"Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces' | ForEach-Object { "
          r"Remove-ItemProperty -Path $_.PSPath -Name TcpAckFrequency -ErrorAction SilentlyContinue; "
          r"Remove-ItemProperty -Path $_.PSPath -Name TCPNoDelay -ErrorAction SilentlyContinue }")], risk="Medium")
T("dns", "Network", "Set DNS to Cloudflare (1.1.1.1)",
  "Faster, privacy-friendlier DNS on all active adapters. Undo returns to automatic DNS.",
  [("ps", r"Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses ('1.1.1.1','1.0.0.1') }")],
  [("ps", r"Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses }")])
T("flushdns", "Network", "Flush DNS cache",
  "One-shot action. Clears the DNS resolver cache.", [("cmd", "ipconfig /flushdns")], None)
T("delivery", "Network", "Disable Windows Update P2P sharing",
  "Stops your PC from uploading updates to other PCs (saves bandwidth).",
  [reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config", "DODownloadMode", 0)],
  [regdel(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config", "DODownloadMode")])

# ---- Privacy
T("telemetry", "Privacy", "Reduce telemetry & disable tracking services",
  "Sets telemetry to minimum and disables DiagTrack + dmwappushservice.",
  [reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0)]
  + svc_off("DiagTrack") + svc_off("dmwappushservice"),
  [regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry")]
  + svc_on("DiagTrack") + svc_on("dmwappushservice", "demand"))
T("ads", "Privacy", "Disable Start menu ads & suggestions",
  "Turns off suggested apps, lock-screen tips and silent app installs.",
  [reg(HK_CDM, n, 0) for n in ("SubscribedContent-338388Enabled", "SubscribedContent-338389Enabled",
                               "SubscribedContent-353694Enabled", "SubscribedContent-353696Enabled",
                               "SystemPaneSuggestionsEnabled", "SilentInstalledAppsEnabled",
                               "SoftLandingEnabled", "RotatingLockScreenOverlayEnabled")],
  [reg(HK_CDM, n, 1) for n in ("SubscribedContent-338388Enabled", "SubscribedContent-338389Enabled",
                               "SubscribedContent-353694Enabled", "SubscribedContent-353696Enabled",
                               "SystemPaneSuggestionsEnabled", "SilentInstalledAppsEnabled",
                               "SoftLandingEnabled", "RotatingLockScreenOverlayEnabled")])
T("activity", "Privacy", "Disable Activity History / Timeline",
  "Stops Windows from collecting/uploading your activity.",
  [reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System", n, 0)
   for n in ("EnableActivityFeed", "PublishUserActivities", "UploadUserActivities")],
  [regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System", n)
   for n in ("EnableActivityFeed", "PublishUserActivities", "UploadUserActivities")])
T("adid", "Privacy", "Disable advertising ID",
  "Stops apps from using a personal ad ID.",
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0)],
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 1)])
T("bing", "Privacy", "Disable web results in Start search",
  "Start search only searches your PC (no Bing). Faster search.",
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 0),
   reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Search", "CortanaConsent", 0),
   reg(r"HKCU\Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions", 1)],
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 1),
   regdel(r"HKCU\Software\Policies\Microsoft\Windows\Explorer", "DisableSearchBoxSuggestions")])

# ---- Interface
T("fileext", "Interface", "Show file extensions & hidden files",
  "Shows .exe/.txt etc. and hidden files in Explorer (safer against fake files).",
  [reg(HK_ADV, "HideFileExt", 0), reg(HK_ADV, "Hidden", 1)],
  [reg(HK_ADV, "HideFileExt", 1), reg(HK_ADV, "Hidden", 2)])
T("classic_menu", "Interface", "Classic right-click menu (Win 11)",
  "Brings back the full right-click menu without 'Show more options'. Restarts Explorer.",
  [("cmd", r'reg add "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32" /ve /d "" /f'),
   ("cmd", "taskkill /f /im explorer.exe & start explorer.exe")],
  [("cmd", r'reg delete "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}" /f'),
   ("cmd", "taskkill /f /im explorer.exe & start explorer.exe")], win11=True)
T("widgets", "Interface", "Disable Widgets / News & Interests",
  "Removes the widgets panel (Win 11) and News & Interests (Win 10) background load.",
  [reg(r"HKLM\SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests", 0),
   reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Feeds", "EnableFeeds", 0)],
  [regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests"),
   regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Feeds", "EnableFeeds")])

# ---- Services & Debloat
T("sysmain", "Services & Debloat", "Disable SysMain (Superfetch)",
  "Good on SSD systems; keep it ON if you boot from a hard drive.",
  svc_off("SysMain"), svc_on("SysMain"), risk="Medium")
T("wsearch", "Services & Debloat", "Disable Windows Search indexing",
  "Saves disk/CPU but Start/Explorer search becomes slow.",
  svc_off("WSearch"), svc_on("WSearch", "delayed-auto"), risk="Advanced")
T("bloat", "Services & Debloat", "Remove common bloatware apps",
  "Removes News, Weather, Solitaire, Get Help, Feedback Hub, Mixed Reality, Clipchamp, People. Can't be undone (reinstall from Store).",
  [("ps", r"$apps='Microsoft.BingNews','Microsoft.BingWeather','Microsoft.GetHelp','Microsoft.Getstarted',"
          r"'Microsoft.MicrosoftSolitaireCollection','Microsoft.WindowsFeedbackHub','Microsoft.MixedReality.Portal',"
          r"'Clipchamp.Clipchamp','Microsoft.People','Microsoft.3DBuilder'; "
          r"foreach($a in $apps){ Get-AppxPackage -Name $a -AllUsers | Remove-AppxPackage -AllUsers -ErrorAction SilentlyContinue; Write-Output ('checked ' + $a) }")],
  None, risk="Medium")
T("defer_updates", "Services & Debloat", "Delay feature updates by 1 year",
  "Security updates still install. Avoids surprise big version upgrades.",
  [reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate", "DeferFeatureUpdates", 1),
   reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate", "DeferFeatureUpdatesPeriodInDays", 365)],
  [regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate", "DeferFeatureUpdates"),
   regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate", "DeferFeatureUpdatesPeriodInDays")], risk="Medium")

# ---- Maintenance
T("temp", "Maintenance", "Clean temp files",
  "Deletes user + Windows temp files (files in use are skipped).",
  [("cmd", r'del /q /f /s "%TEMP%\*" 2>nul'), ("cmd", r'for /d %i in ("%TEMP%\*") do @rd /s /q "%i" 2>nul'),
   ("cmd", r'del /q /f /s "C:\Windows\Temp\*" 2>nul'), ("cmd", "echo Temp cleanup finished")], None)
T("sfc", "Maintenance", "Repair system files (SFC)",
  "Opens a console running sfc /scannow. Takes a few minutes.",
  [("cmd", 'start "SFC" cmd /k "sfc /scannow"')], None)
T("dism", "Maintenance", "Repair Windows image (DISM)",
  "Opens a console running DISM RestoreHealth. Needs internet; takes a while.",
  [("cmd", 'start "DISM" cmd /k "DISM /Online /Cleanup-Image /RestoreHealth"')], None)

RESTORE_PS_EARLY = (r"Enable-ComputerRestore -Drive ($env:SystemDrive + '\'); "
                    r"Checkpoint-Computer -Description 'RETWEAKS' -RestorePointType MODIFY_SETTINGS")

# ===================================================================== CTT WinUtil items
C_PREF, C_ESS, C_ADV = "CTT Customize", "CTT Essential", "CTT Advanced (caution)"
C_FEAT, C_FIX, C_UPD = "CTT Features", "CTT Fixes", "CTT Updates"
HK_PERS = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
POL_EDGE = r"HKLM\SOFTWARE\Policies\Microsoft\Edge"
POL_BRAVE = r"HKLM\SOFTWARE\Policies\BraveSoftware\Brave"
HK_POL_WU = r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate"
HK_TCP6 = r"HKLM\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters"
HK_POW = r"HKLM\SYSTEM\CurrentControlSet\Control\Power"
EXPLORER_RESTART = ("cmd", "taskkill /f /im explorer.exe & start explorer.exe")

def regs(key, pairs, typ="REG_DWORD"):
    return [reg(key, n, v, typ) for n, v in pairs]

def regsdel(key, names):
    return [regdel(key, n) for n in names]

def feat_on(*names):
    return [("ps", "Enable-WindowsOptionalFeature -Online -FeatureName " + ",".join(names) + " -All -NoRestart | Out-Null")]

def feat_off(*names):
    return [("ps", "Disable-WindowsOptionalFeature -Online -FeatureName " + ",".join(names) + " -NoRestart | Out-Null")]

def winget_install(pid):
    return [("cmd", f"winget install --id {pid} -e --silent --accept-source-agreements --accept-package-agreements")]

# ---------------------------------------------------------------- Customize preferences
T("ctt_dark", C_PREF, "Dark theme for Windows",
  "Dark mode for apps and the system. Undo returns to light mode.",
  regs(HK_PERS, [("AppsUseLightTheme", 0), ("SystemUsesLightTheme", 0)]),
  regs(HK_PERS, [("AppsUseLightTheme", 1), ("SystemUsesLightTheme", 1)]))
T("ctt_numlock", C_PREF, "Num Lock on at startup",
  "Turns Num Lock on at the login screen and after sign-in.",
  [reg(r"HKCU\Control Panel\Keyboard", "InitialKeyboardIndicators", 2, "REG_SZ"),
   reg(r"HKU\.DEFAULT\Control Panel\Keyboard", "InitialKeyboardIndicators", 2, "REG_SZ")],
  [reg(r"HKCU\Control Panel\Keyboard", "InitialKeyboardIndicators", 0, "REG_SZ"),
   reg(r"HKU\.DEFAULT\Control Panel\Keyboard", "InitialKeyboardIndicators", 0, "REG_SZ")])
T("ctt_longpaths", C_PREF, "Enable long file paths",
  "Lets apps use paths longer than 260 characters.",
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\FileSystem", "LongPathsEnabled", 1)],
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\FileSystem", "LongPathsEnabled", 0)])
T("ctt_scrollbars", C_PREF, "Scrollbars always visible",
  "Stops scrollbars from auto-hiding.",
  [reg(r"HKCU\Control Panel\Accessibility", "DynamicScrollbars", 0)],
  [reg(r"HKCU\Control Panel\Accessibility", "DynamicScrollbars", 1)])
T("ctt_snap", C_PREF, "Disable window snapping",
  "Turns off drag-to-edge window snapping. Sign out to apply.",
  [reg(r"HKCU\Control Panel\Desktop", "WindowArrangementActive", 0, "REG_SZ")],
  [reg(r"HKCU\Control Panel\Desktop", "WindowArrangementActive", 1, "REG_SZ")], risk="Medium")
T("ctt_verboselogon", C_PREF, "Verbose logon messages",
  "Shows detailed status text during sign-in and shutdown (useful for troubleshooting).",
  [reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "VerboseStatus", 1)],
  [reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "VerboseStatus", 0)])
T("ctt_bsod", C_PREF, "Verbose blue screen (BSoD) details",
  "Shows technical parameters on the blue screen instead of just the smiley.",
  regs(r"HKLM\SYSTEM\CurrentControlSet\Control\CrashControl", [("DisplayParameters", 1), ("DisableEmoticon", 1)]),
  regs(r"HKLM\SYSTEM\CurrentControlSet\Control\CrashControl", [("DisplayParameters", 0), ("DisableEmoticon", 0)]))
T("ctt_taskbar_left", C_PREF, "Taskbar icons on the left (Win 11)",
  "Left-aligns taskbar icons like Windows 10.",
  [reg(HK_ADV, "TaskbarAl", 0)], [reg(HK_ADV, "TaskbarAl", 1)], win11=True)
T("ctt_search_icon", C_PREF, "Hide taskbar search box",
  "Removes the search box/icon from the taskbar.",
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Search", "SearchboxTaskbarMode", 0)],
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Search", "SearchboxTaskbarMode", 1)])
T("ctt_taskview", C_PREF, "Hide Task View button",
  "Removes the Task View icon from the taskbar.",
  [reg(HK_ADV, "ShowTaskViewButton", 0)], [reg(HK_ADV, "ShowTaskViewButton", 1)])
T("ctt_lockscreen", C_PREF, "Disable the lock screen",
  "Goes straight to the sign-in screen.",
  [reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\Personalization", "NoLockScreen", 1)],
  [regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\Personalization", "NoLockScreen")])
T("ctt_loginblur", C_PREF, "Disable acrylic blur on the sign-in screen",
  "Sharper, slightly faster sign-in screen background.",
  [reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System", "DisableAcrylicBackgroundOnLogon", 1)],
  [regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System", "DisableAcrylicBackgroundOnLogon")])
T("ctt_settingshome", C_PREF, "Hide Settings home page (Win 11)",
  "Opens Settings on System instead of the Home page.",
  [reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer", "SettingsPageVisibility", "hide:home", "REG_SZ")],
  [regdel(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer", "SettingsPageVisibility")], win11=True)
T("ctt_mpo", C_PREF, "Disable Multiplane Overlay (MPO)",
  "Fixes flickering/stutter on some NVIDIA/AMD setups with multiple monitors. Reboot required.",
  [reg(r"HKLM\SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode", 5)],
  [regdel(r"HKLM\SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode")], reboot=True, risk="Medium")
T("ctt_s3", C_PREF, "Use S3 sleep instead of Modern Standby",
  "Only works on PCs whose firmware supports S3. Can fix sleep battery drain. Reboot required.",
  [reg(HK_POW, "PlatformAoAcOverride", 0)], [regdel(HK_POW, "PlatformAoAcOverride")], reboot=True, risk="Advanced")
T("ctt_startrec", C_PREF, "Hide Start menu Recommendations (Win 11)",
  "Hides the Recommended section. Fully effective on Pro/Education editions.",
  [reg(r"HKLM\SOFTWARE\Microsoft\PolicyManager\current\device\Start", "HideRecommendedSection", 1)],
  [regdel(r"HKLM\SOFTWARE\Microsoft\PolicyManager\current\device\Start", "HideRecommendedSection")], win11=True)
T("ctt_newoutlook", C_PREF, "Use classic Outlook (turn off New Outlook)",
  "Stops the New Outlook toggle from being on by default.",
  [reg(r"HKCU\Software\Microsoft\Office\16.0\Outlook\Preferences", "UseNewOutlook", 0)],
  [reg(r"HKCU\Software\Microsoft\Office\16.0\Outlook\Preferences", "UseNewOutlook", 1)])

# ---------------------------------------------------------------- Essential tweaks
T("ctt_restorepoint", C_ESS, "Create a restore point (CTT)",
  "One-shot: makes a System Restore point. (RETWEAKS also does this automatically before presets.)",
  [("ps", RESTORE_PS_EARLY)], None)
T("ctt_consumer", C_ESS, "Consumer Features - disable",
  "Stops Windows from auto-installing promoted apps (Candy Crush, etc.).",
  [reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\CloudContent", "DisableWindowsConsumerFeatures", 1)],
  [regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\CloudContent", "DisableWindowsConsumerFeatures")])

_TELE = [
    (r"HKCU\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0),
    (r"HKCU\Software\Microsoft\Windows\CurrentVersion\Privacy", "TailoredExperiencesWithDiagnosticDataEnabled", 0),
    (r"HKCU\Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy", "HasAccepted", 0),
    (r"HKCU\Software\Microsoft\Input\TIPC", "Enabled", 0),
    (r"HKCU\Software\Microsoft\InputPersonalization", "RestrictImplicitInkCollection", 1),
    (r"HKCU\Software\Microsoft\InputPersonalization", "RestrictImplicitTextCollection", 1),
    (r"HKCU\Software\Microsoft\InputPersonalization\TrainedDataStore", "HarvestContacts", 0),
    (r"HKCU\Software\Microsoft\Personalization\Settings", "AcceptedPrivacyPolicy", 0),
    (r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection", "AllowTelemetry", 0),
    (HK_ADV, "Start_TrackProgs", 0),
    (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System", "PublishUserActivities", 0),
    (r"HKCU\Software\Microsoft\Siuf\Rules", "NumberOfSIUFInPeriod", 0),
]
T("ctt_telemetry", C_ESS, "Telemetry - disable (full CTT set)",
  "Telemetry/ad/input-personalization registry keys, Defender sample submission off, DiagTrack + Error Reporting services off, PowerShell 7 telemetry off.",
  [reg(k, n, v) for k, n, v in _TELE]
  + [("ps", "Set-MpPreference -SubmitSamplesConsent 2"),
     ("ps", "Set-Service -Name diagtrack -StartupType Disabled; Set-Service -Name wermgr -StartupType Disabled"),
     ("ps", "[Environment]::SetEnvironmentVariable('POWERSHELL_TELEMETRY_OPTOUT','1','Machine')"),
     ("cmd", r'reg delete "HKCU\Software\Microsoft\Siuf\Rules" /v PeriodInNanoSeconds /f')],
  [regdel(k, n) for k, n, v in _TELE]
  + [("ps", "Set-MpPreference -SubmitSamplesConsent 1"),
     ("ps", "Set-Service -Name diagtrack -StartupType Automatic; Set-Service -Name wermgr -StartupType Automatic"),
     ("ps", "[Environment]::SetEnvironmentVariable('POWERSHELL_TELEMETRY_OPTOUT','','Machine')")])
T("ctt_location", C_ESS, "Location tracking - disable",
  "Turns off Windows location access and map auto-updates.",
  [reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location", "Value", "Deny", "REG_SZ"),
   reg(r"HKLM\SYSTEM\Maps", "AutoUpdateEnabled", 0)],
  [reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\location", "Value", "Allow", "REG_SZ"),
   reg(r"HKLM\SYSTEM\Maps", "AutoUpdateEnabled", 1)])
T("ctt_wpbt", C_ESS, "Windows Platform Binary Table (WPBT) - disable",
  "Stops firmware from silently injecting software into Windows at boot. Reboot required.",
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager", "DisableWpbtExecution", 1)],
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager", "DisableWpbtExecution", 0)], reboot=True)
T("ctt_devicemeta", C_ESS, "Prevent device companion apps",
  "Stops Windows fetching device metadata/companion apps for new hardware from the internet.",
  [reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Device Metadata", "PreventDeviceMetadataFromNetwork", 1)],
  [regdel(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Device Metadata", "PreventDeviceMetadataFromNetwork")])
T("ctt_services", C_ESS, "Services - set to Manual (CTT list)",
  "CscService/DiagTrack/SharedAccess disabled, MapsBroker/StorSvc manual, and svchost split threshold matched to your RAM (fewer svchost processes). Reboot recommended.",
  [("cmd", "sc config CscService start= disabled"), ("cmd", "sc config DiagTrack start= disabled"),
   ("cmd", "sc config SharedAccess start= disabled"), ("cmd", "sc config MapsBroker start= demand"),
   ("cmd", "sc config StorSvc start= demand"),
   ("ps", r"$m=(Get-CimInstance Win32_PhysicalMemory | Measure-Object Capacity -Sum).Sum/1KB; Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control' -Name SvcHostSplitThresholdInKB -Value ([uint32]$m)")],
  [("cmd", "sc config CscService start= demand"), ("cmd", "sc config DiagTrack start= auto"),
   ("cmd", "sc config SharedAccess start= auto"), ("cmd", "sc config MapsBroker start= delayed-auto"),
   ("cmd", "sc config StorSvc start= auto"),
   reg(r"HKLM\SYSTEM\CurrentControlSet\Control", "SvcHostSplitThresholdInKB", 3670016)],
  risk="Medium", reboot=True)
T("ctt_widget", C_ESS, "Widgets - remove (uninstall package)",
  "Removes the Widgets web experience package and taskbar button. One-shot; reinstall 'Windows Web Experience Pack' from the Store to restore.",
  [("ps", "Get-Process -Name *Widget* -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; "
          "Get-AppxPackage -AllUsers *WebExperience* | Remove-AppxPackage -AllUsers -ErrorAction SilentlyContinue"),
   reg(HK_ADV, "TaskbarDa", 0)], None, risk="Medium")
T("ctt_endtask", C_ESS, "End Task with right-click on taskbar (Win 11)",
  "Adds 'End task' to the taskbar right-click menu.",
  [reg(HK_ADV + r"\TaskbarDeveloperSettings", "TaskbarEndTask", 1)],
  [reg(HK_ADV + r"\TaskbarDeveloperSettings", "TaskbarEndTask", 0)], win11=True)
_BAGS = r"HKCU\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell"
T("ctt_autodiscovery", C_ESS, "File Explorer automatic folder discovery - disable",
  "Stops Explorer from guessing folder types (fixes slow folders). Resets saved folder views. Restarts Explorer.",
  [("cmd", f'reg delete "{_BAGS}\\Bags" /f'), ("cmd", f'reg delete "{_BAGS}\\BagMRU" /f'),
   ("cmd", f'reg add "{_BAGS}\\Bags\\AllFolders\\Shell" /v FolderType /t REG_SZ /d NotSpecified /f'), EXPLORER_RESTART],
  [("cmd", f'reg delete "{_BAGS}\\Bags\\AllFolders\\Shell" /v FolderType /f'), EXPLORER_RESTART])
T("ctt_storesearch", C_ESS, "Microsoft Store recommended search results - disable",
  "Blocks the Store's recommended-results database from being used.",
  [("cmd", r'icacls "%LOCALAPPDATA%\Packages\Microsoft.WindowsStore_8wekyb3d8bbwe\LocalState\store.db" /deny Everyone:F')],
  [("cmd", r'icacls "%LOCALAPPDATA%\Packages\Microsoft.WindowsStore_8wekyb3d8bbwe\LocalState\store.db" /remove:d Everyone')])
T("ctt_diskcleanup", C_ESS, "Disk Cleanup - run (all categories)",
  "One-shot: ticks every Disk Cleanup category and runs it (includes old Windows Update files). Takes a few minutes.",
  [("ps", r"Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VolumeCaches' | ForEach-Object { New-ItemProperty -Path $_.PSPath -Name StateFlags0001 -Value 2 -PropertyType DWord -Force | Out-Null }; Start-Process cleanmgr.exe -ArgumentList '/sagerun:1' -Wait")],
  None)
T("ctt_bitlocker", C_ESS, "BitLocker - DISABLE (decrypts your drives)",
  "WARNING: decrypts every BitLocker drive. Anyone with the PC can then read your files. Only for people who know they want this. Re-enable manually.",
  [("ps", "Get-BitLockerVolume | Where-Object { $_.ProtectionStatus -ne 'Off' } | ForEach-Object { Disable-BitLocker -MountPoint $_.MountPoint }")],
  None, risk="Advanced")

# ---------------------------------------------------------------- Advanced tweaks (caution)
T("ctt_display", C_ADV, "Visual effects - best performance (CTT exact set)",
  "CTT's performance preset: no drag-full-window, faster menus, no Aero Peek/listview shadows, hides Chat/Task View/search on taskbar. Sign out to fully apply.",
  [reg(r"HKCU\Control Panel\Desktop", "DragFullWindows", 0, "REG_SZ"),
   reg(r"HKCU\Control Panel\Desktop", "MenuShowDelay", 200, "REG_SZ"),
   reg(r"HKCU\Control Panel\Desktop\WindowMetrics", "MinAnimate", 0, "REG_SZ"),
   reg(r"HKCU\Control Panel\Keyboard", "KeyboardDelay", 0),
   reg(HK_ADV, "ListviewAlphaSelect", 0), reg(HK_ADV, "ListviewShadow", 0), reg(HK_ADV, "TaskbarAnimations", 0),
   reg(HK_EXP + r"\VisualEffects", "VisualFXSetting", 3),
   reg(r"HKCU\Software\Microsoft\Windows\DWM", "EnableAeroPeek", 0),
   reg(HK_ADV, "TaskbarMn", 0), reg(HK_ADV, "ShowTaskViewButton", 0),
   reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Search", "SearchboxTaskbarMode", 0),
   ("cmd", r'reg add "HKCU\Control Panel\Desktop" /v UserPreferencesMask /t REG_BINARY /d 9012038010000000 /f')],
  [reg(r"HKCU\Control Panel\Desktop", "DragFullWindows", 1, "REG_SZ"),
   reg(r"HKCU\Control Panel\Desktop", "MenuShowDelay", 400, "REG_SZ"),
   reg(r"HKCU\Control Panel\Desktop\WindowMetrics", "MinAnimate", 1, "REG_SZ"),
   reg(r"HKCU\Control Panel\Keyboard", "KeyboardDelay", 1),
   reg(HK_ADV, "ListviewAlphaSelect", 1), reg(HK_ADV, "ListviewShadow", 1), reg(HK_ADV, "TaskbarAnimations", 1),
   reg(HK_EXP + r"\VisualEffects", "VisualFXSetting", 1),
   reg(r"HKCU\Software\Microsoft\Windows\DWM", "EnableAeroPeek", 1),
   reg(HK_ADV, "TaskbarMn", 1), reg(HK_ADV, "ShowTaskViewButton", 1),
   reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Search", "SearchboxTaskbarMode", 1),
   regdel(r"HKCU\Control Panel\Desktop", "UserPreferencesMask")], risk="Medium")

def _dns(id, name, a, b):
    T(id, C_ADV, f"DNS - set to {name}", f"Sets DNS on all active adapters to {a} / {b}. Undo returns to automatic DNS.",
      [("ps", "Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses ('" + a + "','" + b + "') }")],
      [("ps", "Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses }")])
_dns("ctt_dns_google", "Google", "8.8.8.8", "8.8.4.4")
_dns("ctt_dns_quad9", "Quad9", "9.9.9.9", "149.112.112.112")
_dns("ctt_dns_adguard", "AdGuard", "94.140.14.14", "94.140.15.15")
_dns("ctt_dns_opendns", "OpenDNS", "208.67.222.222", "208.67.220.220")

T("ctt_ipv6_off", C_ADV, "IPv6 - disable",
  "Turns off IPv6 on all adapters. Some sites/games/VPNs need it. Reboot required.",
  [reg(HK_TCP6, "DisabledComponents", 255), ("ps", "Disable-NetAdapterBinding -Name '*' -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue")],
  [reg(HK_TCP6, "DisabledComponents", 0), ("ps", "Enable-NetAdapterBinding -Name '*' -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue")],
  reboot=True, risk="Medium")
T("ctt_ipv4_pref", C_ADV, "IPv6 - set IPv4 as preferred",
  "Keeps IPv6 on but prefers IPv4. Reboot required.",
  [reg(HK_TCP6, "DisabledComponents", 32)], [reg(HK_TCP6, "DisabledComponents", 0)], reboot=True, risk="Medium")
T("ctt_teredo", C_ADV, "Teredo - disable",
  "Turns off the Teredo IPv6 tunnel (can reduce odd network behavior; Xbox networking may use it).",
  [("cmd", "netsh interface teredo set state disabled")], [("cmd", "netsh interface teredo set state default")], risk="Medium")
T("ctt_notifications", C_ADV, "Tray notifications & calendar - disable",
  "Turns off the notification center/toasts and calendar flyout.",
  [reg(r"HKCU\Software\Policies\Microsoft\Windows\Explorer", "DisableNotificationCenter", 1),
   reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\PushNotifications", "ToastEnabled", 0)],
  [regdel(r"HKCU\Software\Policies\Microsoft\Windows\Explorer", "DisableNotificationCenter"),
   reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\PushNotifications", "ToastEnabled", 1)], risk="Medium")
_EDGE = [("StartupBoostEnabled", 0), ("BackgroundModeEnabled", 0), ("HubsSidebarEnabled", 0),
         ("EdgeShoppingAssistantEnabled", 0), ("ShowRecommendationsEnabled", 0), ("PersonalizationReportingEnabled", 0),
         ("EdgeFollowEnabled", 0), ("DiagnosticData", 0), ("UserFeedbackAllowed", 0),
         ("MicrosoftEdgeInsiderPromotionEnabled", 0), ("SpotlightExperiencesAndRecommendationsEnabled", 0)]
T("ctt_edge_debloat", C_ADV, "Microsoft Edge - debloat (policies)",
  "Turns off Edge startup boost, background mode, sidebar, shopping assistant, recommendations and diagnostics via policy.",
  regs(POL_EDGE, _EDGE), regsdel(POL_EDGE, [n for n, v in _EDGE]))
_BRAVE = [("BraveRewardsDisabled", 1), ("BraveWalletDisabled", 1), ("BraveVPNDisabled", 1), ("BraveAIChatEnabled", 0),
          ("BraveStatsPingEnabled", 0), ("BraveWebDiscoveryEnabled", 0)]
T("ctt_brave_debloat", C_ADV, "Brave browser - debloat (policies)",
  "Turns off Brave Rewards, Wallet, VPN, Leo AI chat, stats ping and web discovery via policy.",
  regs(POL_BRAVE, _BRAVE), regsdel(POL_BRAVE, [n for n, v in _BRAVE]))
T("ctt_adobe", C_ADV, "Adobe URL block list - enable (hosts file)",
  "Adds a community block list of Adobe activation/telemetry hosts to your hosts file (needs internet; backs up hosts first). Can break Adobe licensing checks.",
  [("ps", "$h=\"$env:SystemRoot\\System32\\drivers\\etc\\hosts\"; Copy-Item $h ($h + '.retweaks.bak') -Force; "
          "$l=(Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/Ruddernation-Designs/Adobe-URL-Block-List/master/hosts').Content; "
          "Add-Content -Path $h -Value $l; ipconfig /flushdns | Out-Null")],
  [("ps", "$h=\"$env:SystemRoot\\System32\\drivers\\etc\\hosts\"; if(Test-Path ($h + '.retweaks.bak')){ Copy-Item ($h + '.retweaks.bak') $h -Force } elseif(Test-Path ($h + '" + _OLD_HOSTS_BAK + "')){ Copy-Item ($h + '" + _OLD_HOSTS_BAK + "') $h -Force }; ipconfig /flushdns | Out-Null")],
  risk="Advanced")
T("ctt_razer", C_ADV, "Razer software auto-install - disable",
  "Stops Windows from auto-installing Razer Synapse when you plug in Razer gear.",
  [("cmd", r'mkdir "%SystemRoot%\Installer\Razer" 2>nul'),
   ("cmd", r'icacls "%SystemRoot%\Installer\Razer" /deny "Everyone:(W)"'),
   reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Device Installer", "DisableCoInstallers", 1)],
  [("cmd", r'icacls "%SystemRoot%\Installer\Razer" /remove:d Everyone'),
   reg(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Device Installer", "DisableCoInstallers", 0)], risk="Medium")
T("ctt_oosu", C_ADV, "O&O ShutUp10++ - download and open",
  "One-shot: downloads O&O ShutUp10++ from O&O Software and opens it so you can pick privacy settings.",
  [("ps", "$p=\"$env:TEMP\\OOSU10.exe\"; Invoke-WebRequest -UseBasicParsing -Uri 'https://dl5.oo-software.com/files/ooshutup10/OOSU10.exe' -OutFile $p; Start-Process $p")],
  None)
T("ctt_edge_remove", C_ADV, "Microsoft Edge - REMOVE",
  "WARNING: uninstalls Edge using its own installer (WebView2 stays). Windows may block or restore it on some builds. Undo reinstalls Edge via winget.",
  [("ps", "$s=Get-ChildItem \"${env:ProgramFiles(x86)}\\Microsoft\\Edge\\Application\\*\\Installer\\setup.exe\" -ErrorAction SilentlyContinue | Select-Object -First 1; "
          "if($s){ Stop-Process -Name msedge -Force -ErrorAction SilentlyContinue; Start-Process $s.FullName -ArgumentList '--uninstall --system-level --verbose-logging --force-uninstall' -Wait } else { 'Edge installer not found (already removed?)' }")],
  winget_install("Microsoft.Edge"), risk="Advanced")
_GAL, _HOME = "{e88865ea-0e1c-4e20-9aa6-edcd0212c87c}", "{f874310e-b6b7-47dc-bc84-b9e6b38f5903}"
T("ctt_homegallery", C_ADV, "File Explorer Home and Gallery - disable (Win 11)",
  "Removes Home and Gallery from the Explorer sidebar and opens Explorer to This PC. Restarts Explorer.",
  [reg(rf"HKCU\Software\Classes\CLSID\{_GAL}", "System.IsPinnedToNameSpaceTree", 0),
   reg(rf"HKCU\Software\Classes\CLSID\{_HOME}", "System.IsPinnedToNameSpaceTree", 0),
   reg(HK_ADV, "LaunchTo", 1), EXPLORER_RESTART],
  [regdel(rf"HKCU\Software\Classes\CLSID\{_GAL}", "System.IsPinnedToNameSpaceTree"),
   regdel(rf"HKCU\Software\Classes\CLSID\{_HOME}", "System.IsPinnedToNameSpaceTree"),
   reg(HK_ADV, "LaunchTo", 2), EXPLORER_RESTART], win11=True)
T("ctt_onedrive", C_ADV, "Microsoft OneDrive - REMOVE",
  "WARNING: turn off OneDrive backup of Desktop/Documents first. Uninstalls OneDrive (local files stay). Undo reinstalls via winget.",
  [("ps", "Stop-Process -Name OneDrive -Force -ErrorAction SilentlyContinue; $a=\"$env:SystemRoot\\SysWOW64\\OneDriveSetup.exe\"; $b=\"$env:SystemRoot\\System32\\OneDriveSetup.exe\"; "
          "if(Test-Path $a){ Start-Process $a -ArgumentList '/uninstall' -Wait } elseif(Test-Path $b){ Start-Process $b -ArgumentList '/uninstall' -Wait } else { 'OneDrive setup not found (already removed?)' }")],
  winget_install("Microsoft.OneDrive"), risk="Advanced")
T("ctt_reservedstorage", C_ADV, "Reserved storage - disable",
  "Frees the ~7 GB Windows keeps for updates. Updates may fail if the drive gets very full.",
  [("cmd", "DISM /Online /Set-ReservedStorageState /State:Disabled")],
  [("cmd", "DISM /Online /Set-ReservedStorageState /State:Enabled")], risk="Medium")
T("ctt_storagesense", C_ADV, "Storage Sense - disable",
  "Stops Windows from auto-deleting temp/recycle bin files.",
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy", "01", 0)],
  [reg(r"HKCU\Software\Microsoft\Windows\CurrentVersion\StorageSense\Parameters\StoragePolicy", "01", 1)], risk="Medium")
T("ctt_utc", C_ADV, "Hardware clock to UTC",
  "Makes Windows treat the hardware clock as UTC (fixes clock drift when dual-booting Linux). Clock may be off by your UTC offset until it resyncs.",
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\TimeZoneInformation", "RealTimeIsUniversal", 1)],
  [regdel(r"HKLM\SYSTEM\CurrentControlSet\Control\TimeZoneInformation", "RealTimeIsUniversal")], risk="Medium")
T("ctt_windowsai", C_ADV, "Windows AI (Copilot / Recall) - disable and remove",
  "Policies that turn off Copilot and Recall data analysis, disables the Recall feature if present, removes Copilot app packages.",
  [reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot", "TurnOffWindowsCopilot", 1),
   reg(r"HKCU\Software\Policies\Microsoft\Windows\WindowsCopilot", "TurnOffWindowsCopilot", 1),
   reg(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI", "DisableAIDataAnalysis", 1),
   reg(HK_ADV, "ShowCopilotButton", 0),
   ("ps", "Disable-WindowsOptionalFeature -Online -FeatureName Recall -NoRestart -ErrorAction SilentlyContinue | Out-Null"),
   ("ps", "Get-AppxPackage -AllUsers *Copilot* | Remove-AppxPackage -AllUsers -ErrorAction SilentlyContinue")],
  [regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot", "TurnOffWindowsCopilot"),
   regdel(r"HKCU\Software\Policies\Microsoft\Windows\WindowsCopilot", "TurnOffWindowsCopilot"),
   regdel(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI", "DisableAIDataAnalysis"),
   reg(HK_ADV, "ShowCopilotButton", 1)], risk="Medium")

# ---------------------------------------------------------------- Features
T("ctt_dotnet", C_FEAT, ".NET Framework 2 / 3 / 4 - enable",
  "Installs the old .NET Framework versions some older apps and games need.",
  feat_on("NetFx4-AdvSrvs", "NetFx3"), feat_off("NetFx4-AdvSrvs", "NetFx3"))
T("ctt_hyperv", C_FEAT, "Hyper-V - enable",
  "Needs Windows Pro. Hyper-V can lower gaming performance slightly. Reboot required.",
  feat_on("Microsoft-Hyper-V-All"), feat_off("Microsoft-Hyper-V-All"), reboot=True, risk="Medium")
T("ctt_legacymedia", C_FEAT, "Legacy media components (WMP, DirectPlay) - enable",
  "Windows Media Player, DirectPlay and legacy components for old games/media.",
  feat_on("WindowsMediaPlayer", "MediaPlayback", "DirectPlay", "LegacyComponents"),
  feat_off("WindowsMediaPlayer", "MediaPlayback", "DirectPlay", "LegacyComponents"))
T("ctt_nfs", C_FEAT, "Network File System (NFS) - enable",
  "NFS client and admin tools.",
  feat_on("ServicesForNFS-ClientOnly", "ClientForNFS-Infrastructure", "NFS-Administration"),
  feat_off("ServicesForNFS-ClientOnly", "ClientForNFS-Infrastructure", "NFS-Administration"))
T("ctt_regbackup", C_FEAT, "Registry backup (daily 12:30 am) - enable",
  "Turns on Windows' periodic registry backups and runs them daily at 12:30 am.",
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Configuration Manager", "EnablePeriodicBackup", 1),
   ("cmd", r'schtasks /Create /TN "RETWEAKS_RegBackup" /TR "schtasks.exe /Run /TN \Microsoft\Windows\Registry\RegIdleBackup" /SC DAILY /ST 00:30 /RU SYSTEM /F')],
  [reg(r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Configuration Manager", "EnablePeriodicBackup", 0),
   ("cmd", 'schtasks /Delete /TN "RETWEAKS_RegBackup" /F & schtasks /Delete /TN "' + _OLD_REG_TASK + '" /F')])
T("ctt_sandbox", C_FEAT, "Windows Sandbox - enable",
  "Disposable throwaway Windows desktop. Needs Pro/Enterprise. Reboot required.",
  feat_on("Containers-DisposableClientVM"), feat_off("Containers-DisposableClientVM"), reboot=True, risk="Medium")
T("ctt_wsl", C_FEAT, "Windows Subsystem for Linux (WSL) - enable",
  "Installs the WSL and Virtual Machine Platform features. Reboot required.",
  feat_on("VirtualMachinePlatform", "Microsoft-Windows-Subsystem-Linux"),
  feat_off("VirtualMachinePlatform", "Microsoft-Windows-Subsystem-Linux"), reboot=True, risk="Medium")
T("ctt_f8", C_FEAT, "Legacy F8 boot recovery menu - enable",
  "Brings back the F8 Advanced Boot Options menu. Undo restores the modern menu.",
  [("cmd", "bcdedit /set {current} bootmenupolicy legacy")], [("cmd", "bcdedit /set {current} bootmenupolicy standard")], risk="Medium")
T("ctt_ssh", C_FEAT, "OpenSSH Server - enable",
  "Installs and starts the SSH server and opens port 22 in the firewall. Only enable if you know you need remote SSH.",
  [("ps", "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null; Set-Service -Name sshd -StartupType Automatic; Start-Service sshd; "
          "if(-not (Get-NetFirewallRule -Name sshd -ErrorAction SilentlyContinue)){ New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null }")],
  [("ps", "Stop-Service sshd -ErrorAction SilentlyContinue; Set-Service -Name sshd -StartupType Disabled -ErrorAction SilentlyContinue; "
          "Remove-NetFirewallRule -Name sshd -ErrorAction SilentlyContinue; Remove-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null")],
  risk="Advanced")

# ---------------------------------------------------------------- Fixes (one-shot actions)
T("ctt_fix_scan", C_FIX, "System corruption scan (chkdsk + SFC + DISM)",
  "Opens a console running chkdsk /scan, SFC, DISM RestoreHealth, then SFC again. Takes a while.",
  [("cmd", 'start "Scan" cmd /k "chkdsk /scan & sfc /scannow & DISM /Online /Cleanup-Image /RestoreHealth & sfc /scannow"')], None)
T("ctt_fix_network", C_FIX, "Network - reset",
  "Releases/renews IP, flushes DNS, resets Winsock and the IP stack. Reboot afterwards.",
  [("cmd", "ipconfig /release"), ("cmd", "ipconfig /renew"), ("cmd", "ipconfig /flushdns"),
   ("cmd", "netsh winsock reset"), ("cmd", "netsh int ip reset"), ("cmd", "netsh int ipv6 reset")],
  None, reboot=True, risk="Medium")
T("ctt_fix_ntp", C_FIX, "NTP time server - enable (pool.ntp.org)",
  "Sets Windows time sync to the NTP pool servers and resyncs now.",
  [("cmd", "sc config w32time start= auto"), ("cmd", "net start w32time"),
   ("cmd", 'w32tm /config /syncfromflags:manual /manualpeerlist:"0.pool.ntp.org 1.pool.ntp.org 2.pool.ntp.org 3.pool.ntp.org" /update'),
   ("cmd", "w32tm /resync")], None)
T("ctt_fix_update", C_FIX, "Windows Update - reset",
  "Stops update services, renames SoftwareDistribution and catroot2 (rebuilt automatically), restarts services. Fixes stuck updates.",
  [("cmd", "net stop wuauserv & net stop bits & net stop cryptsvc & net stop msiserver"),
   ("cmd", 'rd /s /q "%SystemRoot%\\SoftwareDistribution.old" 2>nul & ren "%SystemRoot%\\SoftwareDistribution" SoftwareDistribution.old'),
   ("cmd", 'rd /s /q "%SystemRoot%\\System32\\catroot2.old" 2>nul & ren "%SystemRoot%\\System32\\catroot2" catroot2.old'),
   ("cmd", "net start cryptsvc & net start bits & net start msiserver & net start wuauserv")],
  None, risk="Medium")
T("ctt_fix_winget", C_FIX, "WinGet - reinstall / repair",
  "Repairs the WinGet package manager (needs internet).",
  [("ps", "Install-PackageProvider -Name NuGet -Force | Out-Null; Install-Module Microsoft.WinGet.Client -Force -Repository PSGallery | Out-Null; Repair-WinGetPackageManager -AllUsers")],
  None, risk="Medium")
T("ctt_fix_autologon", C_FIX, "AutoLogon - download and open (Sysinternals)",
  "Downloads Microsoft Sysinternals Autologon and opens it so you can set automatic sign-in.",
  [("ps", "$p=\"$env:TEMP\\Autologon.exe\"; Invoke-WebRequest -UseBasicParsing -Uri 'https://live.sysinternals.com/Autologon.exe' -OutFile $p; Start-Process $p")],
  None, risk="Medium")

# ---------------------------------------------------------------- Updates (CTT "Updates" tab)
T("ctt_upd_security", C_UPD, "Windows Update - security settings",
  "CTT's 'Security' mode: delay feature updates 365 days and quality updates 4 days. Undo = default update behavior.",
  regs(HK_POL_WU, [("DeferFeatureUpdates", 1), ("DeferFeatureUpdatesPeriodInDays", 365),
                   ("DeferQualityUpdates", 1), ("DeferQualityUpdatesPeriodInDays", 4)]),
  regsdel(HK_POL_WU, ["DeferFeatureUpdates", "DeferFeatureUpdatesPeriodInDays",
                      "DeferQualityUpdates", "DeferQualityUpdatesPeriodInDays"]), risk="Medium")
T("ctt_upd_disable", C_UPD, "Windows Update - DISABLE all updates (not recommended)",
  "WARNING: stops ALL updates including security patches. Your PC becomes vulnerable over time. Undo = default update behavior.",
  [reg(HK_POL_WU + r"\AU", "NoAutoUpdate", 1), reg(HK_POL_WU + r"\AU", "AUOptions", 1)]
  + svc_off("wuauserv") + svc_off("UsoSvc"),
  [regdel(HK_POL_WU + r"\AU", "NoAutoUpdate"), regdel(HK_POL_WU + r"\AU", "AUOptions")]
  + svc_on("wuauserv", "demand") + svc_on("UsoSvc", "demand"), risk="Advanced")

# ---------------------------------------------------------------- more CTT WinUtil items
T("ctt_homegroup", C_ESS, "Homegroup - disable",
  "Sets the legacy HomeGroup services to manual (they no longer exist on newer Windows builds; errors are harmless).",
  [("cmd", "sc config HomeGroupListener start= demand"), ("cmd", "sc config HomeGroupProvider start= demand")],
  [("cmd", "sc config HomeGroupListener start= auto"), ("cmd", "sc config HomeGroupProvider start= auto")])
T("ctt_wifisense", C_ESS, "Wi-Fi Sense - disable",
  "Stops Windows from auto-connecting to suggested open hotspots and reporting hotspots.",
  regs(r"HKLM\SOFTWARE\Microsoft\PolicyManager\default\WiFi\AllowWiFiHotSpotReporting", [("Value", 0)])
  + regs(r"HKLM\SOFTWARE\Microsoft\PolicyManager\default\WiFi\AllowAutoConnectToWiFiSenseHotspots", [("Value", 0)]),
  regs(r"HKLM\SOFTWARE\Microsoft\PolicyManager\default\WiFi\AllowWiFiHotSpotReporting", [("Value", 1)])
  + regs(r"HKLM\SOFTWARE\Microsoft\PolicyManager\default\WiFi\AllowAutoConnectToWiFiSenseHotspots", [("Value", 1)]))
T("ctt_ps7tele", C_ESS, "PowerShell 7 telemetry - disable",
  "Sets the POWERSHELL_TELEMETRY_OPTOUT machine environment variable.",
  [("ps", "[Environment]::SetEnvironmentVariable('POWERSHELL_TELEMETRY_OPTOUT','1','Machine')")],
  [("ps", "[Environment]::SetEnvironmentVariable('POWERSHELL_TELEMETRY_OPTOUT','','Machine')")])
T("ctt_removeall_store", C_ADV, "Remove ALL Store apps (not recommended)",
  "WARNING: removes almost every removable Store app for all users (keeps Store, Terminal, Photos, Calculator, Notepad, Paint, codecs, GPU/audio vendor apps and system frameworks). One-shot; reinstall from the Store.",
  [("ps", r"$keep='Store|Installer|Terminal|SecHealth|ShellExperience|StartMenu|Search|CBS|Windows\.Client|Notepad|Calculator|Paint|Photos|NVIDIA|Realtek|AMD|Intel|Dolby|HEVC|VP9|WebP|HEIF|Xaml|VCLibs|NET|AAD|AccountsControl|LockApp|CredDialogHost|Apprep|AsyncTextService|OOBE|PeopleExperienceHost|ContentDeliveryManager|ECApp|FilePicker|PinningConfirmationDialog|Win32WebViewHost|XGpuEjectDialog|CapturePicker|WebExperience'; "
          r"Get-AppxPackage -AllUsers | Where-Object { -not $_.NonRemovable -and -not $_.IsFramework -and $_.Name -notmatch $keep } | ForEach-Object { Write-Output ('removing ' + $_.Name); Remove-AppxPackage -Package $_.PackageFullName -AllUsers -ErrorAction SilentlyContinue }")],
  None, risk="Advanced")
T("ctt_intelmm", C_ADV, "Intel Management Engine (LMS) service - disable",
  "Stops and disables the Intel LMS (vPro) service, which has had security issues. Safe on non-vPro PCs.",
  [("cmd", "sc stop LMS"), ("cmd", "sc config LMS start= disabled")],
  [("cmd", "sc config LMS start= auto"), ("cmd", "sc start LMS")], risk="Medium")
T("ctt_ultimate_remove", C_PREF, "Remove Ultimate Performance power plan",
  "One-shot: switches to Balanced and deletes the Ultimate Performance plan(s).",
  [("ps", r"powercfg -setactive 381b4222-f694-41f0-9685-ff5bb260df2e; "
          r"powercfg -list | Select-String 'Ultimate Performance' | ForEach-Object { if ($_ -match '[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}') { powercfg -delete $matches[0] } }")],
  None)
T("ctt_showext", C_PREF, "Show file extensions",
  "Shows .exe/.txt etc. in Explorer.", [reg(HK_ADV, "HideFileExt", 0)], [reg(HK_ADV, "HideFileExt", 1)])
T("ctt_hidden", C_PREF, "Show hidden files",
  "Shows hidden files and folders in Explorer.", [reg(HK_ADV, "Hidden", 1)], [reg(HK_ADV, "Hidden", 2)])
T("ctt_taskbar_center", C_PREF, "Center taskbar items (Win 11)",
  "Centers taskbar icons (Windows 11 default).", [reg(HK_ADV, "TaskbarAl", 1)], [reg(HK_ADV, "TaskbarAl", 0)], win11=True)
T("ctt_taskbar_widgets", C_PREF, "Hide taskbar Widgets button (Win 11)",
  "Removes the Widgets button from the taskbar.", [reg(HK_ADV, "TaskbarDa", 0)], [reg(HK_ADV, "TaskbarDa", 1)], win11=True)
T("ctt_crossdevice", C_PREF, "Cross-device resume - disable",
  "Turns off Cross-Device Experiences (CDP) sessions and nearby sharing channels.",
  regs(r"HKCU\Software\Microsoft\Windows\CurrentVersion\CDP",
       [("CdpSessionUserAuthzPolicy", 0), ("NearShareChannelUserAuthzPolicy", 0), ("RomeSdkChannelUserAuthzPolicy", 0)]),
  regs(r"HKCU\Software\Microsoft\Windows\CurrentVersion\CDP",
       [("CdpSessionUserAuthzPolicy", 1), ("NearShareChannelUserAuthzPolicy", 1), ("RomeSdkChannelUserAuthzPolicy", 1)]))
T("ctt_snapassist", C_PREF, "Snap Assist / Snap layouts flyout - disable",
  "Turns off the Snap Assist suggestions and the Snap layouts flyout / bar. Sign out to apply.",
  regs(HK_ADV, [("SnapAssist", 0), ("EnableSnapAssistFlyout", 0), ("EnableSnapBar", 0)]),
  regs(HK_ADV, [("SnapAssist", 1), ("EnableSnapAssistFlyout", 1), ("EnableSnapBar", 1)]))
T("ctt_upd_default", C_UPD, "Windows Update - default settings",
  "CTT's 'Default' mode: removes every update policy and restores update services to normal.",
  [("cmd", r'reg delete "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate" /f'),
   ("cmd", "sc config wuauserv start= demand"), ("cmd", "sc config UsoSvc start= demand"),
   ("cmd", "sc start wuauserv")], None)

CTT_CATS = [C_ESS, C_ADV, C_PREF, C_FEAT, C_FIX, C_UPD]

# Older RETWEAKS tweaks that are also in CTT WinUtil -> where they show up in the CTT library
CTT_MAP = {"temp": C_ESS, "gamedvr": C_ESS, "hibernate": C_ESS, "activity": C_ESS, "ultimate": C_PREF,
           "mouse_accel": C_PREF, "sticky": C_PREF, "bing": C_PREF, "visual_fx": C_ADV, "widgets": C_ESS,
           "fileext": C_PREF, "classic_menu": C_PREF, "dns": C_ADV}

def ctt_cat(t):
    """CTT library category of a tweak, or None if it isn't a CTT item."""
    if t["id"].startswith("ctt_"):
        return t["cat"]
    return CTT_MAP.get(t["id"])

CATS = ["Performance", "Gaming", "Network", "Privacy", "Interface", "Services & Debloat", "Maintenance"] + CTT_CATS
BYID = {t["id"]: t for t in TWEAKS}

# ----------------------------------------------------------------- one-click PRESETS (bundles of tweaks)
PRESETS = {
    "maxfps": dict(
        name="MAX FPS",
        desc="Gaming build: Ultimate power plan, game CPU/GPU priority, Game DVR off, mouse + network latency tweaks, lighter visuals, tracking off.",
        ids=["ultimate", "prio_sep", "power_throttle", "usb_suspend", "bg_apps", "gamedvr", "gamemode", "hags", "mmcss",
             "mouse_accel", "sticky", "net_throttle", "nagle", "visual_fx", "transparency", "telemetry", "ads",
             "widgets", "startup_delay", "delivery", "temp"]),
    "esports": dict(
        name="ESPORTS EXTREME",
        desc="Everything in MAX FPS plus Cloudflare DNS, Fast Startup off, ad ID/activity tracking off, bloatware removal and DNS flush.",
        ids=["ultimate", "prio_sep", "power_throttle", "usb_suspend", "bg_apps", "gamedvr", "gamemode", "hags", "mmcss",
             "mouse_accel", "sticky", "net_throttle", "nagle", "dns", "flushdns", "visual_fx", "transparency",
             "faststart", "telemetry", "ads", "adid", "activity", "widgets", "startup_delay", "delivery", "bloat", "temp"]),
    "balanced": dict(
        name="BALANCED (safe for everyone)",
        desc="Only low-risk tweaks: tracking and ads off, background apps off, faster startup, Game Mode on, file extensions shown.",
        ids=["gamedvr", "gamemode", "bg_apps", "startup_delay", "telemetry", "ads", "adid", "activity", "bing",
             "delivery", "fileext", "temp"]),
    "streamer": dict(
        name="STREAMER / CREATOR",
        desc="Smooth games while capturing: Ultimate power plan, GPU scheduling, game priority, no background load, network tuning.",
        ids=["ultimate", "usb_suspend", "bg_apps", "gamedvr", "gamemode", "hags", "mmcss", "net_throttle", "delivery",
             "telemetry", "startup_delay", "temp"]),
    "lowend": dict(
        name="LOW-END / OLD PC BOOST",
        desc="Makes weak or old PCs feel faster: animations and transparency off, background junk off, bloatware removed, widgets off.",
        ids=["visual_fx", "transparency", "power_throttle", "bg_apps", "telemetry", "ads", "adid", "activity",
             "startup_delay", "widgets", "delivery", "bloat", "temp"]),
    "laptop": dict(
        name="LAPTOP / BATTERY FRIENDLY",
        desc="Cleans Windows without forcing max-power plans, so battery life and heat stay reasonable.",
        ids=["telemetry", "ads", "adid", "activity", "bing", "bg_apps", "startup_delay", "transparency",
             "widgets", "delivery", "gamedvr", "temp"]),
    "privacy": dict(
        name="PRIVACY LOCKDOWN",
        desc="Turns off telemetry, tracking services, ad ID, activity history, web search in Start and update sharing.",
        ids=["telemetry", "ads", "adid", "activity", "bing", "delivery", "widgets"]),
    "clean": dict(
        name="CLEAN & REPAIR",
        desc="Deletes temp files, flushes DNS, then opens SFC and DISM repair windows to fix corrupted system files.",
        ids=["temp", "flushdns", "sfc", "dism"]),
}
PRESETS["allsafe"] = dict(
    name="ALL SAFE TWEAKS",
    desc="Every tweak marked Safe that can be undone. The 'do a lot at once' option.",
    ids=[t["id"] for t in TWEAKS if t["risk"] == "Safe" and t["undo"] is not None])
# ---- CTT WinUtil presets (built only from CTT items)
PRESETS["ctt_standard"] = dict(
    name="CTT STANDARD",
    desc="Chris Titus WinUtil 'Standard' style: restore point, temp cleanup, consumer features/telemetry/activity/location/Wi-Fi Sense off, "
         "GameDVR off, Homegroup off, services to manual, hibernation off, End Task, PowerShell 7 telemetry off.",
    ids=["ctt_restorepoint", "temp", "ctt_consumer", "ctt_telemetry", "activity", "ctt_location", "ctt_wifisense",
         "gamedvr", "ctt_homegroup", "ctt_services", "hibernate", "ctt_endtask", "ctt_ps7tele", "ctt_wpbt",
         "ctt_autodiscovery"])
PRESETS["ctt_minimal"] = dict(
    name="CTT MINIMAL",
    desc="Chris Titus WinUtil 'Minimal' style: only the lightest changes - restore point, consumer features off, WPBT off, "
         "End Task, Explorer folder discovery off, no device companion apps.",
    ids=["ctt_restorepoint", "ctt_consumer", "ctt_wpbt", "ctt_endtask", "ctt_autodiscovery", "ctt_devicemeta"])
PRESETS["ctt_allsafe"] = dict(
    name="CTT - ALL SAFE ITEMS",
    desc="Every CTT-library tweak marked Safe that can be undone. Open it to review the long list and untick what you don't want.",
    ids=[t["id"] for t in TWEAKS if ctt_cat(t) and t["risk"] == "Safe" and t["undo"] is not None])
PRESET_ORDER = ["maxfps", "esports", "balanced", "streamer", "lowend", "laptop", "privacy", "clean", "allsafe",
                "ctt_standard", "ctt_minimal", "ctt_allsafe"]
PROFILES = {PRESETS[k]["name"]: PRESETS[k]["ids"] for k in PRESET_ORDER}

# ---- user-edited bundles (saved to %APPDATA%\RETWEAKS\custom_presets.json)
import json
CUSTOM_FILE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "RETWEAKS", "tweak_custom_presets.json")

def load_custom():
    try:
        with open(CUSTOM_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: [i for i in v if i in BYID] for k, v in data.items() if k in PRESETS and isinstance(v, list)}
    except Exception:
        return {}

CUSTOM = load_custom()

def save_custom():
    try:
        os.makedirs(os.path.dirname(CUSTOM_FILE), exist_ok=True)
        with open(CUSTOM_FILE, "w", encoding="utf-8") as f:
            json.dump(CUSTOM, f, indent=1)
        return True
    except Exception:
        return False

def is_customized(key):
    return key in CUSTOM

def set_custom(key, ids):
    """Save an edited bundle (or drop the override if it equals the default)."""
    if list(ids) == list(PRESETS[key]["ids"]):
        CUSTOM.pop(key, None)
    else:
        CUSTOM[key] = list(ids)
    return save_custom()

def reset_custom(key):
    CUSTOM.pop(key, None)
    return save_custom()

def preset_ids(key):
    """Preset tweak ids (your saved edits if any), minus Windows-11-only tweaks on Windows 10."""
    base = CUSTOM.get(key, PRESETS[key]["ids"])
    return [i for i in base if not (BYID[i]["win11"] and not IS_WIN11)]

# ----------------------------------------------------------------- game presets
def S(label, low, med, high):
    return (label, low, med, high)

GAMES = {
    "Fortnite": dict(
        exe="FortniteClient-Win64-Shipping.exe",
        settings=[
            S("Display mode", "Fullscreen", "Fullscreen", "Fullscreen"),
            S("Rendering mode", "Performance", "Performance", "DirectX 11 (or DX12 w/ high-end GPU)"),
            S("3D resolution", "75-85%", "100%", "100%"),
            S("Frame rate limit", "Monitor refresh", "Monitor refresh (or 240)", "Unlimited / monitor refresh"),
            S("View distance", "Medium", "Far", "Epic"),
            S("Shadows", "Off", "Off", "Off (competitive) / Medium"),
            S("Global illumination", "Off", "Off", "Off / Low"),
            S("Reflections", "Off", "Off", "Off"),
            S("Anti-aliasing", "Off", "Low / Off", "Medium (TSR)"),
            S("Textures", "Low", "Medium", "High"),
            S("Effects", "Low", "Low", "Medium"),
            S("Post processing", "Low", "Low", "Medium"),
            S("Nanite virtual geometry", "Off", "Off", "Off (more FPS)"),
            S("Hardware ray tracing", "Off", "Off", "Off"),
            S("VSync / Motion blur", "Off / Off", "Off / Off", "Off / Off"),
            S("NVIDIA Reflex", "On", "On", "On + Boost"),
        ],
        tips=["Performance mode is the biggest FPS jump (older GPUs/CPUs especially).",
              "Clear the Fortnite shader cache if you get stutter after a driver update.",
              "Use Windowed Fullscreen only if you alt-tab a lot."]),
    "Valorant": dict(
        exe="VALORANT-Win64-Shipping.exe",
        settings=[
            S("Display mode", "Fullscreen", "Fullscreen", "Fullscreen"),
            S("Multithreaded rendering", "On", "On", "On"),
            S("Material / Texture quality", "Low", "Low", "Medium"),
            S("Detail / UI quality", "Low", "Low", "Medium"),
            S("Vignette", "Off", "Off", "Off"),
            S("VSync", "Off", "Off", "Off"),
            S("Anti-aliasing", "None", "MSAA 2x", "MSAA 4x"),
            S("Anisotropic filtering", "1x", "2x", "4x"),
            S("Improve clarity", "Off", "Off", "Off"),
            S("Bloom / Distortion", "Off / Off", "Off / Off", "Off / Off"),
            S("Cast shadows", "Off", "Off", "Off"),
            S("NVIDIA Reflex Low Latency", "On", "On", "On + Boost"),
        ],
        tips=["Valorant is CPU-bound; close browsers/Discord overlays for steadier FPS.",
              "Cap FPS slightly under your monitor limit only if you see stutter."]),
    "Counter-Strike 2": dict(
        exe="cs2.exe",
        launch="-novid -console",
        settings=[
            S("Display mode", "Fullscreen", "Fullscreen", "Fullscreen"),
            S("Global shadow quality", "Low", "Medium", "High"),
            S("Model / texture detail", "Low", "Medium", "High"),
            S("Shader detail", "Low", "Low", "High"),
            S("Particle detail", "Low", "Low", "Medium"),
            S("Ambient occlusion", "Disabled", "Disabled", "Medium"),
            S("High dynamic range", "Performance", "Performance", "Quality"),
            S("FidelityFX Super Resolution", "Performance", "Disabled", "Disabled"),
            S("Multisampling AA", "None / CMAA2", "2x MSAA", "4x or 8x MSAA"),
            S("Boost player contrast", "Enabled", "Enabled", "Enabled"),
            S("VSync", "Disabled", "Disabled", "Disabled"),
            S("NVIDIA Reflex", "Enabled", "Enabled", "Enabled + Boost"),
        ],
        tips=["Add the launch options in Steam > CS2 > Properties.",
              "Stretched res (4:3) is personal preference, not required for FPS."]),
    "Apex Legends": dict(
        exe="r5apex.exe",
        launch="+fps_max unlimited -novid",
        settings=[
            S("Display mode", "Fullscreen", "Fullscreen", "Fullscreen"),
            S("Field of view", "100", "104", "110"),
            S("Model detail", "Low", "Medium", "High"),
            S("Effects detail", "Low", "Low", "Medium"),
            S("Impact marks", "Low", "Low", "Medium"),
            S("Ragdolls", "Low", "Medium", "High"),
            S("Texture streaming budget", "Low/None (match VRAM)", "Medium (4-6GB)", "High (8GB+)"),
            S("Anti-aliasing", "None", "TSAA", "TSAA"),
            S("Ambient occlusion", "Disabled", "Disabled", "Medium"),
            S("Sun shadow coverage / detail", "Low / Low", "Low / Low", "High / Low"),
            S("Spot shadow detail / dynamic", "Disabled", "Disabled", "Low"),
            S("Volumetric lighting", "Disabled", "Disabled", "Enabled"),
            S("VSync", "Disabled", "Disabled", "Disabled"),
        ],
        tips=["Set texture streaming to match your VRAM or you'll get hitching.",
              "Launch options go in Steam/EA App > Apex > Game properties."]),
    "Call of Duty: Warzone": dict(
        exe="cod.exe",
        settings=[
            S("Display mode", "Fullscreen exclusive", "Fullscreen exclusive", "Fullscreen exclusive"),
            S("Render resolution", "70-80%", "100%", "100%"),
            S("Upscaling", "FSR 1 / DLSS Perf", "DLSS Balanced / FSR", "DLSS Quality / Native"),
            S("Texture resolution", "Low", "Normal", "High"),
            S("Texture filter anisotropic", "Normal", "Normal", "High"),
            S("Shadow map resolution", "Low", "Normal", "High"),
            S("Particle quality", "Low", "Low", "Normal"),
            S("Ambient occlusion", "Off", "Off", "GTAO normal"),
            S("Screen space reflections", "Off", "Off", "Off"),
            S("Weather grid volumes", "Off", "Off", "Off"),
            S("Depth of field / Motion blur / Film grain", "Off / Off / 0", "Off / Off / 0", "Off / Off / 0"),
            S("Field of view", "100-110", "110", "110-120"),
            S("NVIDIA Reflex", "On", "On", "On + Boost"),
        ],
        tips=["Let shaders finish compiling after each update before judging FPS.",
              "Cap FPS at monitor refresh if frametimes are uneven."]),
    "Minecraft (Java)": dict(
        exe="javaw.exe",
        settings=[
            S("Render distance", "8", "12", "16-24"),
            S("Simulation distance", "5", "8", "12"),
            S("Graphics", "Fast", "Fancy", "Fancy"),
            S("Smooth lighting", "Minimum", "Maximum", "Maximum"),
            S("Clouds", "Off", "Fast", "Fancy"),
            S("Particles", "Minimal", "Decreased", "All"),
            S("Entity shadows", "Off", "On", "On"),
            S("Biome blend", "1x1", "3x3", "5x5"),
            S("VSync / Max FPS", "Off / Unlimited", "Off / Unlimited", "Off / Unlimited"),
        ],
        tips=["Install Fabric + Sodium + Lithium for 2-4x FPS.",
              "Give Java 4-6 GB RAM, not more - too much causes GC lag."]),
    "GTA V": dict(
        exe="GTA5.exe",
        settings=[
            S("DirectX version", "DX11", "DX11", "DX11"),
            S("Texture quality", "Normal", "High", "Very High"),
            S("Shader quality", "Normal", "High", "Very High"),
            S("Shadow quality", "Normal", "High", "Very High"),
            S("Reflection quality", "Normal", "High", "Ultra"),
            S("MSAA", "Off", "2x", "4x"),
            S("FXAA", "On", "Off", "Off"),
            S("Grass quality", "Normal", "High", "Very High"),
            S("Post FX", "Normal", "High", "Very High"),
            S("Tessellation", "Off", "Normal", "High"),
            S("Population density / variety", "50% / 50%", "75% / 75%", "100% / 100%"),
        ],
        tips=["Stay on DX11 - DX10/10.1 are for ancient PCs only.",
              "Keep the VRAM bar in the menu under the limit."]),
    "Roblox": dict(
        exe="RobloxPlayerBeta.exe",
        settings=[
            S("Graphics mode", "Manual", "Manual", "Manual"),
            S("Graphics quality", "1-3", "5", "8-10"),
            S("Fullscreen", "On (F11)", "On (F11)", "On"),
            S("FPS cap", "Unlock (60+)", "Unlock", "Unlock"),
        ],
        tips=["Use the in-game Settings > Graphics Quality slider; individual games can override it.",
              "Disable Game DVR + Game Mode tweaks help here too."]),
    "League of Legends": dict(
        exe="League of Legends.exe",
        settings=[
            S("Resolution", "Native", "Native", "Native"),
            S("Character quality", "Low", "Medium", "High"),
            S("Environment quality", "Low", "Medium", "High"),
            S("Effects quality", "Low", "Medium", "High"),
            S("Shadows", "Off", "Low", "Medium"),
            S("Frame rate cap", "144", "240", "Uncapped"),
            S("VSync / Anti-aliasing", "Off / Off", "Off / On", "Off / On"),
        ],
        tips=["Set the client to close during games to save RAM (Settings > General)."]),
    "Rocket League": dict(
        exe="RocketLeague.exe",
        settings=[
            S("Render quality", "High Performance", "High Performance", "High Quality"),
            S("Render detail", "Performance", "Quality", "High Quality"),
            S("Texture detail", "Performance", "Quality", "High Quality"),
            S("World / Particle detail", "Performance", "Performance", "Quality"),
            S("Anti-aliasing", "Off", "FXAA", "MSAA 4x"),
            S("Ambient occlusion / Depth of field / Bloom", "Off", "Off", "Off"),
            S("Light shafts / Lens flares / Dynamic shadows", "Off", "Off", "Off"),
            S("Motion blur / Weather effects", "Off", "Off", "Off"),
            S("Transparent goalposts", "On", "On", "On"),
            S("VSync / FPS cap", "Off / 240", "Off / 240", "Off / 240"),
        ],
        tips=["Keep FPS at 120+ for smooth physics feel; 240 if your monitor supports it."]),
    "Overwatch 2": dict(
        exe="Overwatch.exe",
        settings=[
            S("Display mode", "Fullscreen", "Fullscreen", "Fullscreen"),
            S("Render scale", "75-100%", "100%", "100%"),
            S("Texture quality / filtering", "Low / 1x", "Medium / 4x", "High / 8x"),
            S("Local fog detail", "Low", "Low", "Medium"),
            S("Dynamic reflections", "Off", "Off", "Off"),
            S("Shadow detail", "Off", "Low", "Medium"),
            S("Model detail", "Low", "Medium", "High"),
            S("Effects / Lighting quality", "Low / Low", "Low / Low", "Medium / Medium"),
            S("Anti-alias quality", "Off", "SMAA Low / FXAA", "SMAA Medium"),
            S("Refraction / Ambient occlusion", "Low / Off", "Low / Off", "Medium / Off"),
            S("Reduce buffering", "On", "On", "On"),
            S("NVIDIA Reflex", "On", "On", "On + Boost"),
        ],
        tips=["Cap FPS ~3 below monitor refresh with VSync off for the most stable frametimes."]),
}

GENERIC_GPU_TIPS = (
    "NVIDIA Control Panel: Power management mode = Prefer maximum performance, Low latency mode = On/Ultra, "
    "Texture filtering quality = High performance.\n"
    "AMD Adrenalin: Anti-Lag on, Radeon Boost off for competitive, Image Sharpening 40-60%.\n"
    "Always update GPU drivers and keep game on an SSD.")

PRESET_INFO = {
    "Low": "Low = max FPS. Older / budget hardware (GTX 1050-1650, integrated graphics) or competitive play.",
    "Medium": "Medium = balanced. Mid-range hardware (GTX 1660 / RTX 3050-4060 class).",
    "High": "High = best visuals while staying smooth. RTX 3060 Ti / RX 6700 and above.",
}


# ----------------------------------------------------------------- tips & recommendations
TIPS = {
    "Biggest FPS wins (free)": [
        "Set your monitor to its real refresh rate: Settings > System > Display > Advanced display. Many PCs sit at 60 Hz on a 144/240 Hz screen.",
        "Enable XMP / EXPO in the BIOS so your RAM runs at its rated speed instead of a slow default.",
        "Use two RAM sticks (dual channel). It can give a big FPS jump, especially with integrated graphics.",
        "Update your GPU driver. For stutter/crashes after updates, do a clean install (DDU in Safe Mode).",
        "Install games on an SSD or NVMe drive, and keep 15-20% of the drive free.",
        "Cap FPS a few below your refresh rate (VSync off) for steadier frametimes and less input lag.",
        "Enable Resizable BAR / Smart Access Memory in the BIOS if your CPU, GPU and board support it.",
    ],
    "In-game": [
        "Turn off shadows, reflections, motion blur and ambient occlusion first. They cost the most FPS for the least visual loss.",
        "Keep textures as high as your VRAM allows. Textures are cheap on FPS but use VRAM.",
        "Use NVIDIA Reflex / AMD Anti-Lag where the game offers it to cut input latency.",
        "Use DLSS / FSR 'Quality' or 'Balanced' for free FPS in newer games. Avoid 'Ultra Performance'.",
        "Close overlays you don't need: Discord, Steam, GeForce, Xbox Game Bar, browsers with video playing.",
    ],
    "Windows habits": [
        "Task Manager > Startup apps: disable everything you don't need at boot.",
        "Restart your PC every few days. Fast Startup can keep old driver state alive for weeks.",
        "Use Ethernet instead of Wi-Fi for games. On Wi-Fi use 5 GHz or 6 GHz, not 2.4 GHz.",
        "Keep Windows and your chipset/BIOS reasonably up to date for stability.",
        "Mouse: 800-1600 DPI with 1000 Hz polling is plenty; turn off 'Enhance pointer precision'.",
    ],
    "Laptops": [
        "Plug in while gaming and set Settings > System > Power > Power mode to 'Best performance'.",
        "Make sure the game uses the dedicated GPU: Settings > Display > Graphics > pick the game > High performance.",
        "Use a cooling pad or raise the back for airflow; heat causes throttling more than any setting.",
        "Run MAX FPS only while plugged in. The LAPTOP preset is better for daily use on battery.",
    ],
    "Temperatures & hardware": [
        "Watch CPU/GPU temps with HWiNFO or HWMonitor. Over about 90 C under load means throttling.",
        "Blow out dust every 6-12 months. Repaste older CPUs/GPUs that run hot.",
        "Hard drive (HDD) as your main drive? An SSD is the single biggest upgrade for how fast a PC feels.",
        "8 GB of RAM is tight for modern games; 16 GB is the sweet spot.",
    ],
    "Things NOT to do": [
        "Don't use 'registry cleaners', 'RAM boosters' or 'driver updater' tools. They add risk and no speed.",
        "Don't permanently disable Windows Defender, Windows Update or the page file.",
        "Don't run extreme presets on a PC you can't afford to troubleshoot. Keep the restore point.",
        "Turning off Memory Integrity (Core Isolation) can add a few FPS in some games but lowers security. RETWEAKS leaves it on.",
        "Don't overclock without monitoring temperatures and testing stability.",
    ],
}

INFO_PS = ("$cs=Get-CimInstance Win32_ComputerSystem; $cpu=Get-CimInstance Win32_Processor|Select-Object -First 1; "
           "$gpu=(Get-CimInstance Win32_VideoController|ForEach-Object{$_.Name}) -join ', '; "
           "$disk='Unknown'; try{ $disk=(Get-Partition -DriveLetter C | Get-Disk | Get-PhysicalDisk).MediaType }catch{}; "
           "'os=' + (Get-CimInstance Win32_OperatingSystem).Caption; 'cpu=' + $cpu.Name; "
           "'cores=' + $cpu.NumberOfCores; 'threads=' + $cpu.NumberOfLogicalProcessors; 'gpu=' + $gpu; "
           "'ram=' + [math]::Round($cs.TotalPhysicalMemory/1GB); "
           "'laptop=' + [bool](Get-CimInstance Win32_Battery); 'disk=' + $disk")

# Full hardware scan: one PowerShell run that prints a single JSON object (single quotes only, sent base64-encoded).
INFO_FULL_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
function S($v) { if ($null -eq $v) { '' } else { ([string]$v).Trim() } }
$r = [ordered]@{}
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$cpus = @(Get-CimInstance Win32_Processor)
$bios = Get-CimInstance Win32_BIOS
$bb = Get-CimInstance Win32_BaseBoard
$cv = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$r.os = S $os.Caption
$r.os_version = S $cv.DisplayVersion
$r.os_build = (S $os.BuildNumber) + '.' + (S $cv.UBR)
$r.os_arch = S $os.OSArchitecture
if ($os.InstallDate) { $r.install = $os.InstallDate.ToString('yyyy-MM-dd') }
if ($os.LastBootUpTime) { $u = (Get-Date) - $os.LastBootUpTime; $r.uptime = ('{0}d {1}h {2}m' -f $u.Days, $u.Hours, $u.Minutes) }
$r.host = S $env:COMPUTERNAME
$r.user = S $env:USERNAME
$r.maker = S $cs.Manufacturer
$r.model = S $cs.Model
$r.laptop = [string][bool](Get-CimInstance Win32_Battery)
if ($cpus.Count -gt 0) {
  $c = $cpus[0]
  $r.cpu = S $c.Name
  $r.cores = [string](($cpus | Measure-Object NumberOfCores -Sum).Sum)
  $r.threads = [string](($cpus | Measure-Object NumberOfLogicalProcessors -Sum).Sum)
  $r.cpu_mhz = S $c.MaxClockSpeed
  $r.cpu_l2 = S $c.L2CacheSize
  $r.cpu_l3 = S $c.L3CacheSize
  $r.cpu_socket = S $c.SocketDesignation
  $r.cpu_virt = S $c.VirtualizationFirmwareEnabled
}
$vram = @{}
Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11cd-80c1-00805f77eb77}' | ForEach-Object {
  $p = Get-ItemProperty $_.PSPath
  $m = $p.'HardwareInformation.qwMemorySize'
  if ($p.DriverDesc -and $m) { try { $vram[[string]$p.DriverDesc] = [double]$m } catch {} }
}
$gp = @(Get-CimInstance Win32_VideoController)
$r.gpu = (($gp | ForEach-Object { $_.Name }) -join ', ')
$r.gpus = @($gp | ForEach-Object {
  $v = $vram[[string]$_.Name]
  if (-not $v) { $v = $_.AdapterRAM }
  $res = ''
  if ($_.CurrentHorizontalResolution) { $res = ('{0} x {1}' -f $_.CurrentHorizontalResolution, $_.CurrentVerticalResolution) }
  $dd = ''
  if ($_.DriverDate) { $dd = $_.DriverDate.ToString('yyyy-MM-dd') }
  $vg = 0
  if ($v) { $vg = [math]::Round([double]$v / 1GB, 1) }
  [ordered]@{ name = S $_.Name; pnp = $(if ($_.PNPDeviceID -like 'PCI\*') {'PCI\'} else {'OTHER'}); vram = $vg; driver = S $_.DriverVersion; date = $dd; res = $res; hz = S $_.CurrentRefreshRate }
})
$r.monitors = @(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorID | ForEach-Object {
  $n = -join ($_.UserFriendlyName | Where-Object { $_ -ne 0 } | ForEach-Object { [char]$_ })
  if (-not $n) { $n = 'Generic monitor' }
  $n
})
$mods = @(Get-CimInstance Win32_PhysicalMemory)
$tmap = @{ 20 = 'DDR'; 21 = 'DDR2'; 24 = 'DDR3'; 26 = 'DDR4'; 30 = 'LPDDR4'; 34 = 'DDR5'; 35 = 'LPDDR5' }
$r.ram = [string][math]::Round($cs.TotalPhysicalMemory / 1GB)
$r.ram_free = [string][math]::Round($os.FreePhysicalMemory / 1MB, 1)
$r.ram_slots = S ((Get-CimInstance Win32_PhysicalMemoryArray | Measure-Object MemoryDevices -Sum).Sum)
$r.ram_modules = @($mods | ForEach-Object {
  $t = $tmap[[int]$_.SMBIOSMemoryType]
  [ordered]@{ gb = [math]::Round($_.Capacity / 1GB); speed = S $_.ConfiguredClockSpeed; rated = S $_.Speed; type = S $t; maker = S $_.Manufacturer; part = S $_.PartNumber; slot = S $_.DeviceLocator }
})
$r.disks = @(Get-PhysicalDisk | ForEach-Object {
  $kind = S $_.MediaType
  if ((S $_.BusType) -eq 'NVMe') { $kind = 'NVMe SSD' }
  [ordered]@{ name = S $_.FriendlyName; kind = $kind; gb = [math]::Round($_.Size / 1GB); health = S $_.HealthStatus }
})
$r.volumes = @(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
  [ordered]@{ letter = S $_.DeviceID; label = S $_.VolumeName; fs = S $_.FileSystem; gb = [math]::Round($_.Size / 1GB); free = [math]::Round($_.FreeSpace / 1GB) }
})
$dm = 'Unknown'
try { $dm = (Get-Partition -DriveLetter C | Get-Disk | Get-PhysicalDisk).MediaType } catch {}
$r.disk = S $dm
$r.board = ((S $bb.Manufacturer) + ' ' + (S $bb.Product)).Trim()
$r.bios = ((S $bios.Manufacturer) + ' ' + (S $bios.SMBIOSBIOSVersion)).Trim()
if ($bios.ReleaseDate) { $r.bios_date = $bios.ReleaseDate.ToString('yyyy-MM-dd') }
try { $sb = Confirm-SecureBootUEFI -ErrorAction Stop; $r.boot = 'UEFI'; if ($sb) { $r.secureboot = 'On' } else { $r.secureboot = 'Off' } } catch { $r.boot = 'Legacy BIOS'; $r.secureboot = 'Not available' }
try { $t = Get-Tpm -ErrorAction Stop; if ($t.TpmPresent) { $r.tpm = 'Present' } else { $r.tpm = 'Not found' } } catch { $r.tpm = 'Unknown' }
$r.net = @(Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' } | ForEach-Object {
  $kind = 'Ethernet'
  if ($_.InterfaceDescription -match 'Wi-?Fi|Wireless|802\.11') { $kind = 'Wi-Fi' }
  [ordered]@{ name = S $_.InterfaceDescription; kind = $kind; speed = S $_.LinkSpeed }
})
$b = Get-CimInstance Win32_Battery | Select-Object -First 1
if ($b) { $r.battery = (S $b.EstimatedChargeRemaining); $r.battery_status = (S $b.BatteryStatus) }
$pp = (powercfg /getactivescheme) -join ' '
if ($pp -match '\((.+)\)') { $r.power_plan = $Matches[1] }
$r | ConvertTo-Json -Depth 5 -Compress
"""

def sysinfo():
    """Hardware/OS details. Flat string keys (os, cpu, cores, threads, gpu, ram, laptop, disk) feed recommend();
    info['raw'] holds the full structured scan for the System Info page."""
    info = dict(os="?", cpu="?", cores="?", threads="?", gpu="?", ram="0", laptop="False", disk="Unknown")
    if os.name != "nt":
        return info
    raw = None
    try:
        import base64
        enc = base64.b64encode(INFO_FULL_PS.encode("utf-16-le")).decode()
        p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=NOWIN, timeout=120)
        out = p.stdout or ""
        a, b = out.find("{"), out.rfind("}")
        if a >= 0 and b > a:
            raw = json.loads(out[a:b + 1])
    except Exception:
        raw = None
    if isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, (str, int, float)) and not isinstance(v, bool):
                info[k] = str(v)
        info["raw"] = raw
        return info
    rc, out = run("ps", INFO_PS)  # fallback: the small scan
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    return info

def _lst(x):
    if x is None or x == "":
        return []
    return x if isinstance(x, list) else [x]

def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

def _gb(x):
    x = _num(x)
    return f"{x:.0f} GB" if x >= 10 or x == int(x) else f"{x:.1f} GB"

def info_headline(info):
    """(title, subtitle) for the System Info header card."""
    r = info.get("raw") or {}
    maker, model = r.get("maker", ""), r.get("model", "")
    title = (model if model and model.lower() not in ("system product name", "to be filled by o.e.m.")
             else (r.get("board") or "Your PC")).strip() or "Your PC"
    if maker and maker.lower() not in title.lower() and maker.lower() not in ("system manufacturer", "to be filled by o.e.m."):
        title = f"{maker} {title}"
    bits = [info.get("cpu", ""), info.get("gpu", "").split(", ")[0] if info.get("gpu") else "",
            (info.get("ram", "0") + " GB RAM") if info.get("ram", "0") not in ("0", "") else ""]
    return title, "  |  ".join(b for b in bits if b and b != "?")

def info_sections(info):
    """[(title, [(label, value) or (label, value, fraction)])] for the System Info page."""
    r = info.get("raw")
    S = []
    if not r:  # non-Windows / fallback scan: just the basics
        rows = [("OS", info.get("os", "?")), ("CPU", info.get("cpu", "?")),
                ("Cores / threads", f"{info.get('cores', '?')} / {info.get('threads', '?')}"),
                ("GPU", info.get("gpu", "?")), ("RAM", f"{info.get('ram', '0')} GB"),
                ("C: drive type", info.get("disk", "?")), ("Laptop", info.get("laptop", "?"))]
        return [("System", rows)]
    laptop = str(r.get("laptop", "")).lower() == "true"
    sysrows = [("Computer name", r.get("host", "")), ("User", r.get("user", "")),
               ("Manufacturer", r.get("maker", "")), ("Model", r.get("model", "")),
               ("Form factor", "Laptop" if laptop else "Desktop / other"),
               ("Motherboard", r.get("board", "")),
               ("BIOS", (r.get("bios", "") + (f"  ({r['bios_date']})" if r.get("bios_date") else "")).strip()),
               ("Boot mode", r.get("boot", "")), ("Secure Boot", r.get("secureboot", "")), ("TPM", r.get("tpm", ""))]
    junk = ("system product name", "to be filled by o.e.m.", "system manufacturer", "default string", "not applicable")
    S.append(("System", [x for x in sysrows if x[1] and x[1].lower() not in junk]))
    ver = r.get("os_version", "")
    osrows = [("Edition", r.get("os", "")), ("Version", (ver + "  " if ver else "") + f"build {r.get('os_build', '')}".strip()),
              ("Architecture", r.get("os_arch", "")), ("Installed", r.get("install", "")),
              ("Uptime", r.get("uptime", "")), ("Power plan", r.get("power_plan", ""))]
    S.append(("Operating system", [x for x in osrows if x[1]]))
    cpu = [("Name", r.get("cpu", "")), ("Cores / threads", f"{r.get('cores', '?')} cores / {r.get('threads', '?')} threads")]
    if _num(r.get("cpu_mhz")):
        cpu.append(("Max clock", f"{_num(r.get('cpu_mhz')) / 1000:.2f} GHz"))
    cache = []
    if _num(r.get("cpu_l2")):
        cache.append(f"L2 {_num(r.get('cpu_l2')) / 1024:.1f} MB")
    if _num(r.get("cpu_l3")):
        cache.append(f"L3 {_num(r.get('cpu_l3')) / 1024:.0f} MB")
    if cache:
        cpu.append(("Cache", "  |  ".join(cache)))
    cpu.append(("Socket", r.get("cpu_socket", "")))
    virt = str(r.get("cpu_virt", "")).lower()
    if virt in ("true", "false"):
        cpu.append(("Virtualization", "Enabled" if virt == "true" else "Disabled in BIOS"))
    S.append(("Processor", [x for x in cpu if x[1]]))
    gpus = _lst(r.get("gpus"))
    grows = []
    for i, g in enumerate(gpus, 1):
        tag = f"GPU {i}" if len(gpus) > 1 else "GPU"
        grows.append((tag, g.get("name", "")))
        if _num(g.get("vram")):
            grows.append(("  VRAM", _gb(g.get("vram"))))
        if g.get("driver"):
            grows.append(("  Driver", g["driver"] + (f"  ({g['date']})" if g.get("date") else "")))
        if g.get("res"):
            grows.append(("  Resolution", g["res"] + (f" @ {g['hz']} Hz" if g.get("hz") else "")))
    for i, m in enumerate(_lst(r.get("monitors")), 1):
        grows.append((f"Monitor {i}", m))
    S.append(("Graphics & display", grows or [("GPU", info.get("gpu", "?"))]))
    total, free = _num(r.get("ram")), _num(r.get("ram_free"))
    mem = []
    mods = _lst(r.get("ram_modules"))
    if total:
        mem.append(("Installed", f"{total:.0f} GB"))
        if free:
            used = max(0.0, total - free)
            mem.append(("In use now", f"{used:.1f} GB of {total:.0f} GB  ({used / total * 100:.0f}%)", used / total))
    if mods:
        speeds = [m.get("speed") or m.get("rated") for m in mods if (m.get("speed") or m.get("rated"))]
        types = [m.get("type") for m in mods if m.get("type")]
        if types or speeds:
            mem.append(("Type / speed", f"{types[0] if types else 'RAM'}" + (f" @ {speeds[0]} MHz" if speeds else "")))
        if r.get("ram_slots"):
            mem.append(("Slots", f"{len(mods)} of {r['ram_slots']} used"))
        for i, m in enumerate(mods, 1):
            mem.append((f"Module {i}", f"{m.get('gb', '?')} GB  {m.get('maker', '')}  {m.get('part', '')}".replace("  ", " ").strip()
                        + (f"  [{m['slot']}]" if m.get("slot") else "")))
    S.append(("Memory", mem))
    st = []
    for d in _lst(r.get("disks")):
        st.append((d.get("kind") or "Disk", f"{d.get('name', '')}  {_num(d.get('gb')):.0f} GB  {d.get('health', '')}".replace("  ", " ").strip()))
    for v in _lst(r.get("volumes")):
        size, fr = _num(v.get("gb")), _num(v.get("free"))
        if size:
            used = size - fr
            nm = v.get("letter", "") + (f" {v['label']}" if v.get("label") else "")
            st.append((nm, f"{fr:.0f} GB free of {size:.0f} GB  ({v.get('fs', '')})", used / size))
    S.append(("Storage", st))
    net = [(n.get("kind", "Adapter"), f"{n.get('name', '')}  {n.get('speed', '')}".strip()) for n in _lst(r.get("net"))]
    if net:
        S.append(("Network", net))
    if r.get("battery"):
        status = {"1": "On battery", "2": "Plugged in", "3": "Fully charged", "4": "Low", "5": "Critical",
                  "6": "Charging", "7": "Charging (high)", "8": "Charging (low)", "9": "Charging (critical)"}.get(
            str(r.get("battery_status", "")), "")
        pct = _num(r.get("battery"))
        S.append(("Battery", [("Charge", f"{pct:.0f}%  {status}".strip(), pct / 100.0)]))
    return [(t, rows) for t, rows in S if rows]

def recommend(info):
    """Returns (preset_key, reason, [tailored tips])."""
    try:
        ram = int(float(info.get("ram", "0")))
    except ValueError:
        ram = 0
    laptop = info.get("laptop", "").lower() == "true"
    gpu = info.get("gpu", "")
    disk = info.get("disk", "")
    discrete = any(x in gpu for x in ("NVIDIA", "GeForce", "RTX", "GTX", "Radeon RX", "Radeon Pro", "Arc A"))
    tips = []
    if laptop:
        key, why = "laptop", "Laptop detected - this keeps battery and heat sane (use MAX FPS only while plugged in)"
        tips.append("Laptop: plug in and set Power mode to 'Best performance' when gaming.")
    elif ram and ram <= 8 or not discrete:
        key, why = "lowend", "Limited RAM or no dedicated GPU - the Low-end boost frees the most resources"
    else:
        key, why = "maxfps", "Desktop with a dedicated GPU - MAX FPS gives you the most"
    if disk.upper() == "HDD":
        tips.append("Your C: drive is a hard drive (HDD). An SSD is the biggest upgrade; also keep SysMain ON.")
    if ram and ram <= 8:
        tips.append(f"You have {ram} GB RAM. Close browsers while gaming; 16 GB is the best next upgrade.")
    if ram and ram >= 32:
        tips.append(f"{ram} GB RAM is plenty - RAM is not your bottleneck.")
    if "NVIDIA" in gpu or "GeForce" in gpu:
        tips.append("NVIDIA: set Power management = Prefer maximum performance and Low latency = On in NVIDIA Control Panel.")
    elif "Radeon" in gpu and "Graphics" not in gpu:
        tips.append("AMD: turn on Anti-Lag in Adrenalin and use FSR in supported games.")
    elif gpu and not discrete:
        tips.append("Integrated graphics: use dual-channel RAM and lower resolution scale / FSR for the biggest gains.")
    if IS_WIN11:
        tips.append("Windows 11: Settings > Gaming > Game Mode should be ON. RETWEAKS's presets handle this.")
    return key, why, tips

# ----------------------------------------------------------------- engine
RESTORE_PS = (r"Enable-ComputerRestore -Drive ($env:SystemDrive + '\'); "
              r"Checkpoint-Computer -Description 'RETWEAKS' -RestorePointType MODIFY_SETTINGS")

def apply_ids(ids, mode, log, restore=True):
    """Run tweak ids in 'apply' or 'undo' mode. Returns True if a reboot is advisable."""
    if mode == "apply" and restore:
        log("== Creating restore point ==")
        rc, out = run("ps", RESTORE_PS)
        log(out or ("OK" if rc == 0 else "skipped (Windows allows 1 restore point per 24h by default)"))
    need_reboot = False
    total = len(ids)
    for n, tid in enumerate(ids, 1):
        t = BYID[tid]
        cmds = t["apply"] if mode == "apply" else t["undo"]
        if not cmds:
            continue
        log(f"\n[{n}/{total}] {'APPLY' if mode == 'apply' else 'UNDO'}: {t['name']}")
        for kind, cmd in cmds:
            rc, out = run(kind, cmd)
            log(("   [ok] " if rc == 0 else "   [!!] ") + (out.replace("\n", " | ")[:200] if out else cmd[:80]))
        need_reboot |= t["reboot"]
    log("\n== Done ==")
    return need_reboot
