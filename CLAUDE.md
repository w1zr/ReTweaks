# RETWEAKS — CLAUDE.md (Master Project Context)

This is the single source of truth for RETWEAKS. Read the whole file before making any change. The rules in it are hard constraints. If a request conflicts with this file, explain the conflict and ask before doing anything destructive.

---

## 0. Combined app (RETWEAKS v2.0 and later)

Owner decision 2026-10-22: RETWEAKS is combined with a friend's Tkinter app (v1.4), called **the base app** in this file.
The base app's code is the base; every RETWEAKS feature the base app lacks was added; everything is named RETWEAKS with
the RETWEAKS chip logo, the ReTweaks wordmark, the RETWEAKS sidebar (line icons) and the RETWEAKS chip-scan
startup (no orbit animation). The RETWEAKS Dashboard is the home screen; the base app's pages keep their contents.
- **License:** GPL-3.0-only (the base app's license; the friend agreed). `LICENSE` is at the repo root (keep it). This
  replaces "License: None" in section 1. **Owner rule (2026-10-22): never mention the base app's name or the app's
  previous name ("RY"+"TWEAKS") anywhere — UI, docs, comments, release notes.** Only hidden technical identifiers needed
  for data migration and Undo keep them, built from pieces in `core/rename_migration.py`, `retweaks_data.py`,
  `core/app_rules.py` and `core/game_presets.py`.
- **UI toolkit:** Tkinter (the base app) + small C# helpers in `ai/` (GeminiChat, EmbeddedAI, DriverAI, ValueAI,
  EmbeddedSite). The PySide6 UI in `ui/` and `main.py` is legacy, kept for reference and for
  `tools/make_branding.py` (renders the chip/startup/sidebar-icon PNGs with the original drawing code); it is
  excluded from the build.
- **Entry point:** `retweaks.py` (the base app's main, renamed). `retweaks_data.py` = the base app's 117 tweaks, 12 presets,
  11 game profiles. `hubplus.py` = the base app's extra pages + hooks for RETWEAKS pages.
- **RETWEAKS pages:** `rt_pages/` (registry in `rt_pages/__init__.py`, one class per page taking `(hub, tab, g)`,
  using the unchanged `core/` modules). Sidebar: `rt_sidebar.py`. App shell (single instance over the same named
  pipe protocol as v1.5.1, tray via pystray, reopen animation, update bar, Discord, auto game mode services,
  6 s exit watchdog): `rt_shell.py`. Settings stay in `%APPDATA%\RETWEAKS\config.json` (`rt_pages/settings_store.py`).
- **Data carried over once:** the base app's `%APPDATA%`/`%LOCALAPPDATA%` folders -> `\RETWEAKS` (its `custom_presets.json`
  becomes `tweak_custom_presets.json` because RETWEAKS already uses that name), plus the previous-name migration (v1.6).
  Undo for changes the base app made still works (its hosts backup and registry-backup task; `retweaks_data.py`
  `_OLD_HOSTS_BAK`, `_OLD_REG_TASK`).
- **AI (owner choice 2026-10-22, updated v2.0.1):** the base app's shared-key Gemini helper. The first shared key was
  published in the code with v2.0 (owner decision) and Google disabled it minutes later. Since v2.0.1 **no key is in the
  repo**: `ai/GeminiChat.cs` has the placeholder `@@RETWEAKS_GEMINI_KEY@@`; `build.py` fills it from the env var
  `RETWEAKS_GEMINI_KEY` (GitHub Actions secret `GEMINI_API_KEY`) or the untracked `ai/gemini_key.txt` into a temporary
  copy it deletes after compiling; `ai/GeminiChat.exe` is no longer tracked. Never commit a key again. Several keys are
  allowed (one per line, joined with `|`); `GeminiChat.Request` switches to the next key only when Google says a key is
  dead (401, or 400/403 about the key), never on 429 limits (owner choice 2026-10-23); the working key's index is kept in
  `%LOCALAPPDATA%\GeminiChat\active-key.txt` (a number, never the key). The Notifications page was removed from the
  sidebar (owner request 2026-10-23); its page object stays so later page indexes don't shift. There is no
  own-key option (owner request 2026-10-23, after the built-in keys were confirmed working); the helper ignores any old
  saved key file. `rt_pages/ai_key.py` holds the model picker (setting `ai_model`, "" = newest non-preview Flash-Lite).
- **Base app v1.5 merge (owner decisions 2026-10-22):** added the base app's v1.5 Temperatures, Fan control, RGB lighting
  and Run pages (`rt_pages/cooling.py` wrapping `cooling_panel.py`, `thermal_dashboard.py`, `run_panel.py`;
  sensors `temperatures.py`, `gpu_metrics.py`; RGB `rgb_service.py`, `rgb_sync.py`) plus its fixes (rounded
  dropdown popup, audio/PC-value pickers, sidebar slide, Blackout theme). **Bundled** (owner choice):
  `ai/sensors` = LibreHardwareMonitor 0.9.6 + `SensorHost.exe` (temperatures, fans, fan control) and `ai/openrgb` =
  OpenRGB 1.1 portable (RGB), licenses and SOURCE.txt alongside. This changes section 7 for this branch: CPU temps and
  fans no longer need a separately running LHM (`core/sensors_lhm.set_bundled_provider`); RETWEAKS still installs no
  driver — CPU/motherboard sensors and most fan control need **PawnIO**, which the user installs from its official page
  (button on the pages). Fan safety: manual duty 30–100 % within the controller's range, pumps excluded, hardware
  (BIOS) control returns on Quit, crash (sensor host stdin closes), 45 s without heartbeat and CPU/GPU >= 85 °C.
  RETWEAKS additions: fan curves (`fan_curves.py`, `rt_pages/fan_curve_ui.py`; settings `fan_curves`,
  `fan_curves_on_start` default off; 8 s missing-temperature failsafe) and RGB Breathing/Color cycle (only when every
  controller has the mode), brightness, per-device on/off, profiles (`rgb_profiles`), `rgb_apply_on_start` (default
  off). Nothing writes to fans or lighting at launch unless the user ticked those options. Not taken from v1.5:
  its own browser, startup manager, health check, tray, Discord, updater and settings (RETWEAKS keeps its versions),
  its empty-AI-key change (owner keeps the shared key), and initially the "Windows Activation" page. Owner request 2026-10-23 adds it using the shared EmbeddedSite helper (massgrave.dev), beside Windows tweaks.
- **v2.0 additions (owner requests 2026-10-22):** browser = the base app's v1.5 own-process `ai/EmbeddedBrowser.exe`
  (`embedded_browser.py`, `rt_pages/browser.py`; RETWEAKS branding, data still in `browser.json` and
  `%LOCALAPPDATA%\RETWEAKS\Browser`; the in-process pythonnet/WebView2 browser and `tools/browser_smoke.py` were
  removed because a native fault there crashed the whole app). Global search in the top bar (`rt_search.py`, Ctrl+K;
  results are a frame inside the main window). Themed rounded tray menu (`rt_traymenu.py`). Quit ends the process right
  after cleanup (`os._exit`). Startup = the real v1.6 Qt splash in its own process (`rt_splash_qt.py` /
  `rt_splash_client.py`, 1.7x slower), PySide6 bundled only for that. One °C/°F setting for every page
  (`rt_pages/settings_store.set_temp_unit`). Crosshair overlay (`core/crosshair.py`, `rt_pages/crosshair.py`, share
  codes `RTX1-`, gallery `crosshairs/gallery.json`). Welcome tour (`rt_welcome.py`, once from v2.0, setting
  `welcome_done_version`) and automatic updates (`rt_autoupdate.py`, setting `auto_update`). Translations
  (`rt_i18n.py`, `i18n/*.json`: es, fr, de, pt-BR; setting `language`; machine-made). Discord button "Get Now" ->
  https://w1zr.github.io/ReTweaks/. Super Black is the default theme. v2.0 was released by owner request on 2026-10-22.
- **Inventory (rewrite protocol, section 4):** `docs/COMBINED_INVENTORY.md`. Nothing is released until every item
  works or the owner approves each missing one.
- **Testing on Linux:** `xvfb-run -a python3.12 tools/linux_shim.py <check script>` (inert fakes for Windows APIs);
  `tools/tk_screens.py` saves screenshots of any page; page checks live in `checks/`, the base app's in `check_*.py`.
- **Build:** `python build.py` compiles the C# helpers with the .NET Framework `csc.exe`, then PyInstaller
  `RETWEAKS.spec` (single file, `uac_admin=True`, chip icon). Output `dist\RETWEAKS.exe`.

---

## 1. Project overview

- **Name:** RETWEAKS (written in all caps in text). The wordmark next to the chip logo (sidebar, splash, dashboard banner, browser, README banner `assets/brand/banner.png`) reads **ReTweaks** (`core/version.py` `BRAND`, owner choice 2026-10-22). Renamed from its previous name in v1.6 (owner decision 2026-10-22; `core/rename_migration.py` copies the old `%APPDATA%`/`%LOCALAPPDATA%` folders to `\RETWEAKS`, moves the Gemini credential and the Start-with-Windows task, and offers to close a running old-name .exe; old theme codes `RYT1-` and old preset files still import). The old name never appears in text; only that migration code builds it. Never show the even older name "Galaxy Optimizer".
- **What it is:** A Windows PC diagnostics and optimization app, shipped as a single-file Windows `.exe`. It shows real hardware information and live readings, applies practical PC and game tweaks, and includes game profiles, storage tools, an audio mixer, an auto clicker and related utilities.
- **Core goal:** Real functionality only. Every control must perform a real Windows action and report the true result. No mockups, stubs, placeholder data, fake math (for example, never `cpu_pct * 0.4` for GPU load) or hardcoded device hacks.
- **Owner:** Ryder. GitHub user `w1zr`.
- **Repo:** `w1zr/ReTweaks`, public (the old `w1zr/retweaks` and `w1zr/rytweaks` URLs redirect; `core/updater.py` `REPO` uses `w1zr/ReTweaks`). All source files stay viewable on GitHub.
- **License:** GPL-3.0-only since v2.0 (section 0). `LICENSE` stays at the repo root.
- **Local folder:** `C:\pc_optimizer` on Ryder's Windows PC, a Git clone of the repo. Ryder updates it from PowerShell with `git fetch origin`, `git reset --hard origin/main` (or a branch), `python build.py`.
- **This file's location:** `C:\pc_optimizer\CLAUDE.md` and the root of the GitHub repo. Both copies must stay identical. When one changes, update the other in the same session.
- **Language policy:** RETWEAKS stays mainly Python for now. Changing languages, mixing in other languages, or rewriting modules is allowed in the future, but only under the rewrite protocol in section 4.

---

## 2. Tech stack (verified from the code)

- Python. The last build used Python 3.15 (64-bit).
- GUI: **PySide6** (Qt). Not PyQt, and not customtkinter.
- Windows integration (v1.2): `winreg`, PowerShell/CIM (run through `core/winutil.py`, no console window), `ctypes` (DXGI GPU list), `psutil`, `pywin32` (`win32pdh` performance counters, `win32com` for WMI), and `nvidia-ml-py` (imported as `pynvml`) for NVIDIA telemetry.
- Removed in v1.2 because nothing imported them: `wmi`, `py-cpuinfo`, `customtkinter`. `pycaw` + `comtypes` came back in v1.4 for the audio mixer.
- AI Assistant (v1.4): Gemini REST API through `urllib` (no SDK); the user's key is kept in Windows Credential Manager via advapi32 `CredWriteW`/`CredReadW` (ctypes; pywin32's win32cred blob handling failed on a real PC).
- Packaging: PyInstaller, run through `build.py`.

---

## 3. Architecture and folder layout

The real layout is the one in the GitHub repo. Inspect the repo before assuming a path. Layout as of v1.2:

- `main.py` — Entry point. Sets the Windows AppUserModelID (`retweaks.pcoptimizer.suite.v1`) so the taskbar shows the RETWEAKS icon. Loads `assets/icon.ico` and shows the splash screen, then the main window. Calls `freeze_support()` for PyInstaller.
- `core/version.py` — `__version__`, the only place the version number lives.
- `core/winutil.py` — Runs commands and PowerShell without a console window; `is_admin()`.
- `core/hardware.py` — Static hardware scan (one PowerShell call): OS, CPU, motherboard/BIOS, RAM sticks, disk health, monitors, audio, network.
- `core/gpu_dxgi.py` — GPU list via DirectX (DXGI): exact names, 64-bit VRAM, every vendor.
- `core/telemetry.py` — Live readings: GPU load/VRAM used (Windows GPU counters), live CPU clock, NVML extras, disk/network speed.
- `core/sensors_lhm.py` — Optional temperatures and fans from LibreHardwareMonitor.
- `core/optimizer.py` — Windows tweaks: each `get_*` reads the real state, each `set_*` returns `(ok, message)`. Saves previous power plan and DNS so they can be restored.
- `core/tweaks.py` — Individual tweaks (Standard/Advanced): real state, original values saved before the first change, Undo and Undo everything, restore point. v1.4.3: `core/tweaks_catalog.py` adds 44 more (53 total; search keywords in `KEYWORDS`) in categories Gaming, Privacy, Interface, Services, Maintenance (`CATEGORY_ORDER`); `core/quick_actions.py` holds the Essentials actions (flush DNS, Windows Update cache with preview, SFC).
- `core/game_presets.py` — Game settings presets: parsers for ini / key:value / Valve KeyValues files, backups, only changes keys that already exist, refuses while the game runs.
- `core/app_rules.py` — Per-program rules (GPU preference, fullscreen optimizations, CPU priority) and auto game mode.
- `core/updater.py` — Update check and in-app updates (SHA-256 verified; since 2.0.7 no RETWEAKS.old.exe is kept, see the 2.0.7 note at the end); since v1.4 an update bar at the top of every page offers **Update now** (owner request 2026-10-21).
- `core/nettest.py` — DNS speed test and ping test (1.1.1.1 / 1.0.0.1).
- `core/autostart.py` — Start with Windows via a Task Scheduler task (no UAC prompt at sign-in).
- `core/profiles.py` — System profiles. v1.4.3 `PRESETS` = data {tweak id: On/Off} + power plan: Esports, Max FPS, Balanced, Low-end PC, High quality, Ultra quality, Streamer, Privacy; plus the original Max Performance and Windows Default. `preview()` reads current state so only real changes are shown before applying (`ui/widgets/preset_apply.py`, used by the Profiles page). On the Tweaks page a preset only ticks its tweaks (`preset_selection`, `SELECTABLE_PRESETS`); the user unticks/adds, Clear selection, then Apply selected (`selection_preview`, `apply_selection`). Setting `last_preset` remembers the last one applied.
- `core/startup_manager.py`, `core/storage_manager.py`, `core/themes.py`, `core/report.py` — Startup apps (including scheduled tasks), Storage Explorer, disk space analyzer and cleanup, theme tokens, hardware report export.
- v1.4 modules: `core/healthcheck.py` (Health Check), `core/fps.py` (PresentMon FPS runs), `core/sensorlog.py` (sensor CSV logging), `core/display.py` (refresh rate + GPU driver info), `core/audio.py` (audio mixer), `core/autoclicker.py`, `core/funtools.py` (polling-rate / CPS / reaction tests), `core/ai_assistant.py` (Gemini AI Assistant), `core/overlay_fps.py` + `ui/overlay.py` (in-game FPS overlay: a separate click-through topmost window; never inject into a game process). v1.4.3: `core/etw_frames.py` is the built-in frame source (default, setting `overlay_source` = `builtin` / `presentmon`): its own real-time ETW session `RETWEAKS_frames` with DXGI Present_Start 42/55, D3D9 Present_Start 1, DxgKrnl Present_Info 184 (IDs from PresentMon's PresentData/ETW headers); measures time between presents (MsBetweenPresents), not display time. Background calming lives in `core/app_rules.py`.
- v1.5 modules: `core/browser_data.py` (search engines, address-bar parsing, bookmarks/history in `%APPDATA%\RETWEAKS\browser.json`, never in config.json), `core/browser_engine.py` (loads Microsoft's Edge engine, WebView2, through pythonnet + .NET Framework 4.8; SDK DLLs from the pywebview package, bundled by `build.py` into `webview2/`), `ui/widgets/edge_view.py` (one tab = a native QWidget hosting a WebView2 controller; .NET Tasks polled with QTimer; every .NET callback wrapped), `ui/pages/browser.py` (Browser page: tabs, private tabs via IsInPrivateModeEnabled, bookmarks, history, downloads). Engine profile (cookies/cache): `%LOCALAPPDATA%\RETWEAKS\Browser`. The engine starts only when the Browser page is opened. Settings: `browser_search_engine`, `browser_custom_search`, `browser_download_dir`, `browser_ask_download`. `tools/browser_smoke.py` checks the engine on GitHub's Windows runner in every build. Audio mixer (v1.5) also controls the default microphone (`AudioBackend.input_*`, `set_default_input`). Start page: `core/browser_newtab.py` writes themed index.html/private.html to `%LOCALAPPDATA%\RETWEAKS\Browser\newtab`, served as https://retweaks.newtab/ (WebView2 virtual host); websites' preferred color scheme follows the theme. Volume lock (v1.5): `core/audio_lock.py` logic, enforced by a 0.5 s timer in MainWindow (`set_volume_lock`, settings `audio_lock_output` / `audio_lock_input`, None = off), follows the default device, never touches mute. Stretched resolution (v1.5, global since owner request 2026-10-22; the Fortnite-file version was removed because Windowed Fullscreen ignores the file): Display & drivers page, per monitor. `display.stretch_choices()` (narrower widths at native height + 4:3), `display.set_resolution()` (ChangeDisplaySettingsExW with DEVMODE dmDisplayFixedOutput = DMDFO_STRETCH; trial without saving → 15 s KeepSettingsDialog → save to registry, else `restore_saved_mode()`). Fortnite stays `lockable` so a previously locked GameUserSettings.ini can be unlocked. `core/nvidia_display.py` (ctypes NVAPI via nvapi64.dll nvapi_QueryInterface; IDs/structs from NVIDIA's MIT NVAPI SDK, sizes verified by compiling nvapi.h: NV_CUSTOM_DISPLAY 144, NV_TIMING 96, NV_TIMING_INPUT 32) adds a missing mode: source WxH with the monitor's native timing (GetTiming AUTO) so the GPU stretches; TryCustomDisplay → 15 s Keep → SaveCustomDisplay + `restore_saved_mode()` or RevertCustomDisplayTrial. Single instance (v1.5): `winutil.single_instance()` mutex; a second launch talks to the running copy over a QLocalServer (`main._listen_for_show`, name `RETWEAKS_show_<user>`; commands `ver` → "ver X", `show` → "ok", `quit` → "bye", v1.5.1+): same version → show its window; different version → ask, then `quit` (normal cleanup) and start; no answer (pre-1.5.1 or stuck) → `winutil.other_instances()` / `close_other_instances()` offer "Close it and start"; `main._exit` ends the process after 6 s if shutdown hangs. `MainWindow.closeEvent` calls `QApplication.quit()` because Qt doesn't quit when a hidden (tray) window closes (bug fixed in v1.5.1). Tray (v1.5): setting `tray_on_close` (default ON, owner decision 2026-10-22), tray icon = `assets/icon.ico` (owner's pick 2026-10-22); closeEvent hides to tray; `--minimized` start goes to the tray when it's on.
- `ui/main_window.py` — App shell: sidebar navigation, page stack, background workers, settings, change log.
- `ui/pages/` — One file per page (Dashboard, Hardware, Health Check, FPS test, Display & drivers, Tweaks, Profiles, Game presets, Program rules, Startup apps, Network, Storage & cleanup, Audio mixer, Auto clicker, AI Assistant, Snapshots, Fun tools, Logs, About, Settings).
- `ui/widgets/brand.py` — The chip logo drawn with QPainter, `ChipLoader` (mini scanning loader, only during real work), `EmptyState`, and the thin-line sidebar icons. `ui/widgets/chip_pins.py` — Health Check chip.
- `ui/widgets/` — Shared widgets (cards, live graphs) and the `Page` base class.
- `ui/workers.py` — Background threads. `ui/splash.py` — The splash screen (`RetweaksSplash`).
- `tests/` — pytest tests (parsing, tweaks undo, game presets, program rules, updater, network tests); run on any OS with `python -m pytest tests`.
- `release-notes/vX.Y.md` — The text of each GitHub release.
- `create_logo.py` — Builds `assets/icon.ico` (the chip) at 16–256 px, each size drawn separately. `build.py` — PyInstaller single-file build. Output: `dist\RETWEAKS.exe`.
- `.github/workflows/` — GitHub Actions build and release.
- `assets/icon.ico` — The .exe / Explorer / shortcut icon (small sizes drawn on the pixel grid). `assets/taskbar.ico` — The window and taskbar icon, kept as the v1.4 drawing by owner preference (2026-10-21). Both come from `create_logo.py`.
- `.gitignore` — Excludes `build/`, `dist/`, `__pycache__/`, `*.spec`, `.vscode/` and `.pytest_cache/`.

---

## 4. Highest-priority rule: never lose existing features or settings

A previous update deleted many settings. Preventing that from happening again comes before convenience or refactoring.

Before every meaningful update:
1. Inspect the repo: source files, settings models, persistence, screens, feature modules and the build configuration.
2. Write a complete inventory of the existing screens, controls, settings, tweaks, profiles and features.
3. Check Git history, branches or backups when you need to understand an earlier regression.
4. Make the smallest focused change that does the job. Do not rewrite unrelated modules.
5. Keep setting keys, IDs, defaults, behavior and user data. Never silently reset, rename, delete or simplify them.
6. If a data-model change cannot be avoided, write a backward-compatible, repeat-safe migration. Back up the old config before migrating.
7. Never remove a feature because it is inconvenient. Explain why and ask first.
8. After editing, compare against the inventory and confirm nothing unrelated disappeared.
9. Test that settings, profiles and preferences persist across restart and upgrade.
10. If you find an existing regression, restore the real function. Do not hide it behind a placeholder.

### Rewrite protocol (a language change or a large rewrite)
Rewrites are allowed, but they are the most likely way to lose features. Follow these steps every time:
1. The owner approves the rewrite and the target language before any work starts.
2. Write a complete written inventory of every screen, control, setting key, default, tweak, profile and feature. Save it to the repo.
3. Build the new version against that inventory.
4. Migrate existing user settings and profiles. Never discard them.
5. Do not release the new version until every inventoried item works, or until the owner approves each missing item in writing.

---

## 5. Design and branding

- Clean, professional and modern. Mostly black and grey.
- Moderately rounded corners, consistent spacing, clear hierarchy, restrained borders and shadows. Nothing square or boxy, and no overdone redesign.
- Smooth, short transitions for navigation, buttons, loading states and dialogs. They must not make the app feel slow.
- Navigation gets a subtle click or selection animation. Buttons respond to hover and press.
- Use monochrome icons. No picture emojis (the colorful phone-style ones) anywhere in the app UI. Plain text symbols such as ✔ ✖ → • are fine (owner clarification 2026-10-21).
- The sidebar header shows the small chip logo next to the RETWEAKS wordmark by default (owner choice 2026-10-21). Settings → Appearance → Sidebar header can switch to "Wordmark only" (setting `header_style`: `chip` / `wordmark`).
- Pop-ups and dialogs match the app's style, with clear confirm and cancel options and real outcomes.
- No fake progress bars or artificial waits.
- Accessibility: readable contrast, keyboard navigation where practical, visible focus states and a layout that scales.
- A targeted UI request gets a targeted change, not a redesign.

### Themes
- Built-in themes: Midnight black/grey (the default) plus accent themes Pink, Blue, Purple, Red, Green and Cyan. Full-UI themes (v1.4.1, owner choice): Super Black (pure black/OLED), Galaxy (with a static starfield backdrop), Ocean, Ember, Forest and Light. The logo uses the theme's `logo` token: grey/white on dark themes, dark on Light.
- Dashboard banner (v1.4.1): setting `banner_style` = `cores` (default, live per-thread load), `wave` (live CPU load), `circuit`, `galaxy` or `off`. It animates only while visible and not minimized.
- Custom accent color through a validated HEX input.
- Theme maker (v1.4.3): users build themes from 10 editable colors (`core/themes.py` EDITABLE); the rest are derived. Saved in settings `custom_themes` {name: colors}; built-in names can't be reused. Share codes `RET1-` + base64 JSON (codes from before the rename, `RYT1-`, still import), validated on import (hex colors only).
- Discord status (v1.4.3): `core/discord_rpc.py`, local Discord IPC only, enabled for new settings (`discord_status`, `discord_show_game`); existing opt-outs are preserved. Public Application ID 1562695957651521627; verified logo asset `retweaks-logo-1024`. Activity says Optimizing with RETWEAKS, with one Get Now button to https://w1zr.github.io/ReTweaks/.
- Use centralized theme tokens. Never hardcode colors across the UI.
- Apply the theme consistently to buttons, active navigation, switches, sliders, highlights and focus states.
- Keep the dark foundation unless the user picks a supported light mode.
- Status, warning and error colors must stay readable under every theme.
- Save the theme choice and restore it on launch. Adding theme settings must not reset any existing setting.

---

## 6. Splash screen and app icon

- About 600 × 360 px as a starting point, adjusted for DPI scaling.
- Centered on the active monitor's usable work area, not at fixed coordinates.
- Black and grey branding with a clean logo reveal.
- **No version number on the splash screen.**
- Fades smoothly into the main window. No artificial delay. Show honest status only when it helps.
- Reopening while RETWEAKS is already running hidden in the tray (or minimized) plays the same animation and fades into the window (owner choice 2026-10-22, `main._reopen`). A window already on screen is just brought to the front.
- Must close properly if startup fails, and must never stay stuck on top of the main window.
- The RETWEAKS `.ico` must be embedded in the `.exe` and used for the window, the taskbar and shortcuts. The taskbar previously showed a random blue icon, which is a known bug to keep fixed.

---

## 7. Hardware detection and live data

- Show CPU, GPU, motherboard and BIOS, RAM, storage, OS, monitors, audio devices and any other reliable system information.
- Show the **exact** GPU name reported by the driver (for example "NVIDIA GeForce RTX 4060"), never a generic label. Detect multiple GPUs.
- **VRAM detection (64-bit fix, owner-approved change 2026-10-21):** WMI `Win32_VideoController.AdapterRAM` is a 32-bit value and caps at about 4 GB. Use:
  1. DirectX (DXGI) `DedicatedVideoMemory`, a 64-bit value that works for every GPU brand. DXGI also gives each GPU's LUID, which links it to the Windows GPU performance counters.
  2. NVIDIA NVML (`pynvml`) for NVIDIA-only extras: temperature, clocks, power, fan, VRAM in use.
  3. If DXGI fails: the GPU names from WMI/CIM, with VRAM shown as "Unavailable" (never the capped WMI number).
- **Live GPU load (every brand):** the Windows "GPU Engine" performance counters, the same source Task Manager uses. Add counters with English names (`AddEnglishCounter`) so non-English Windows works.
- **Live CPU clock:** `Processor Frequency x % Processor Performance`. `psutil.cpu_freq()` only returns the base clock on Windows.
- **CPU temperature, fans, motherboard sensors:** Windows has no API for these without a kernel driver, and RETWEAKS does not ship one. Read them from LibreHardwareMonitor when the user runs it: its Remote Web Server (`http://localhost:8085/data.json`, needed for LHM 0.9.5 and newer, which removed WMI), or WMI `root\LibreHardwareMonitor` for 0.9.4 and older.
- Motherboard and BIOS: CIM `Win32_BaseBoard` and `Win32_BIOS`.
- Disk health: `Get-PhysicalDisk` status. Show SMART or health data only when the hardware or driver actually exposes it.
- Monitors: real names from `WmiMonitorID`, plus resolution and refresh rate from Qt. Audio: `Win32_SoundDevice`.
- PSU: show it only if the system reliably reports it. Otherwise show "Unavailable".
- Any metric that isn't supported or available shows **"Unavailable"**. Never show a fake value or a hardcoded zero.
- Label readings as live, cached, stale or unavailable.
- Poll hardware in the background, never on the UI thread, and clean up timers and resources.
- Never hardcode the reference PC's specs (section 17) into the app.

---

## 8. Windows tweaks

Every tweak must:
- Explain what it does in plain language, including the trade-off or downside.
- Say whether it needs administrator rights.
- Detect and show its current state when possible.
- Use an explicit Apply action and report the real result only after the Windows operation finishes.
- Record the previous state first and offer undo or restore when practical.
- Use documented Windows mechanisms. Never invent registry keys or present "FPS boost" folklore as fact.
- Never claim an FPS or ping gain that wasn't actually measured.
- Keep safe, reversible tweaks separate from advanced or disruptive ones.
- Never be applied silently, and never on launch.

Users must be able to apply tweaks **individually**, not only as one bundle. Categories: gaming and responsiveness, startup apps, background apps, power, network, Windows gaming features, visual effects, storage and cleanup.

Known mechanisms:
- **Game Mode:** `HKCU\Software\Microsoft\GameBar` → `AutoGameModeEnabled` (the value Windows 10/11 Settings uses). v1.2 also writes the older `AllowAutoGameMode`. This is a reversible on/off toggle and must never be forced on, because it can lower FPS on some systems.
- **Ultimate Performance power plan:** duplicate and activate the hidden scheme GUID `e9a42b02-d5df-448d-aa00-03f14749eb61`. Keep the user's previous plan so it can be restored.
- **HAGS:** the graphics driver scheduling key `HwSchMode`. A restart is needed for it to take effect.
- **Services (v1.4.3):** only the `Start` value under `HKLM\SYSTEM\CurrentControlSet\Services\<name>` (4 = Disabled), applied after a restart; RETWEAKS never force-stops a service. Undo restores the exact original start type. Always Advanced.
- **Privacy and Interface tweaks (v1.4.3):** only values the Settings app or official Group Policy write. "On" always means what the tweak's name says.
- **Temp cleanup:** clean `%TEMP%` and `%SystemRoot%\Temp`, handle errors, and show a preview before deleting anything.

### Startup apps
- Enumerate entries from HKCU Run, HKLM Run, Startup folders and Scheduled Tasks. Show the name, path, source, scope and publisher.
- Disabling and re-enabling must really work. Keep the original command and state so the entry can be restored, and never delete unrelated data.
- Not every entry is safe to disable, so say so. Handle per-user versus machine-wide entries and their permissions.
- Refresh and verify the state after every action.

### DNS (user's choice)
- Let the user **choose their own DNS**. Offer presets plus a custom entry with validated IPv4 and IPv6 input.
- Let the user pick **which network adapter** to change (Wi-Fi or Ethernet). Default to the adapter currently in use.
- Include an **"Automatic (from router)"** option that returns the adapter to DHCP-provided DNS.
- Apply with `Set-DnsClientServerAddress`, then flush the cache with `ipconfig /flushdns`. This needs admin rights.
- Save the previous DNS settings so they can be restored with one click.
- Never claim one DNS is faster unless it was measured on this PC.

### DNS speed test (requested feature)
- Measure real DNS lookup times against the presets, the user's custom servers and the current or automatic DNS.
- Use several lookups per server, and show the average, the best, the worst and any failures. State the method and the number of lookups.
- Test uncached lookups so the results aren't skewed by caching, and say how this was done.
- Results are for this PC, on this network, at this moment. Say so in the UI.
- Never change DNS automatically from the results. The user picks, then applies through the DNS tweak.

### Network and ping tests
- Ping and latency tests must use **1.1.1.1 or 1.0.0.1** as the target.
- Keep DNS lookup time, packet latency, packet loss and in-game latency separate.
- Show real results and errors. Never fabricate values or claim an improvement without before-and-after measurements.

---

## 9. Game profiles

- The user picks a target game. Each game gets its own profiles with **Low, High, Ultra and Ultra Performance** presets where they make sense for that game, plus a Custom option.
- Profiles can be created, renamed, duplicated, edited, deleted, exported and imported. Each game's settings save independently and persist across restarts.
- Preview the changes before applying. Back up the game's config files first and support rollback.
- Validate game paths and config formats. Never overwrite unrelated files.
- Handle games that aren't installed, configs synced to the cloud, and different config locations. Report honestly when a setting can't be detected or applied.
- Never modify anti-cheat-protected files or try to bypass anti-cheat.
- **Fortnite** is the key target: competitive 1080p FPS and responsiveness, no promised FPS numbers, reversible changes only.
- **Minecraft** is also a target. Only edit settings that can be safely identified for the installed edition and version.
- New games must be easy to add. Don't build the system around Fortnite and Minecraft only.

### Performance measurement
Measure real FPS and 1% lows where supported. State the method, duration and limits. Compare under comparable conditions. Never invent benchmark numbers or credit a tweak for an inconclusive result.

---

## 10. Auto clicker

- Settings: left, right or middle button; single or double click; speed in CPS or as an interval (with units and limits); optional click count or run time; optional random interval range; optional start delay.
- Start and stop controls, configurable hotkeys, and an emergency stop that always works.
- Show basic session stats and the true running state. Save preferences across launches.
- Use a proper Windows input API. Run the click loop off the UI thread. Stop cleanly on stop, emergency stop, app close or error. No runaway threads, stuck buttons, or clicking after the app closes.
- Validate every number so bad values can't freeze the app.
- No stealth, evasion or anti-cheat bypass features. State in the UI that users are responsible for following the rules of each game or service.

---

## 11. Audio mixer

- Master volume and mute. List output devices and let the user switch between them. Per-app volume and mute where Windows supports it.
- Stay in sync with changes made outside RETWEAKS. React when devices or sessions change.
- Use Windows Core Audio (`IAudioEndpointVolume`, `IAudioSessionManager2`, `ISimpleAudioVolume`) through `pycaw`.
- No slider that isn't connected to a real device or session. Handle disconnects, default-device changes and COM cleanup. Report unsupported controls honestly.

---

## 12. Storage Explorer

- Browse, breadcrumbs, search, sort, show or hide hidden items, copy path, and open files with the normal Windows app.
- Folder and file sizes are calculated in the background. Include a disk usage breakdown.
- Cleanup always shows a preview first. Never delete anything automatically or without an explicit user action.
- Handle access-denied paths, symlinks and reparse points, disconnected drives and long paths. Never freeze the UI on large folders.

---

## 13. AI Assistant (Gemini)

Gemini was removed in v1.2 and brought back in v1.4 as the **AI Assistant** tab, approved on 2026-10-21 by Chris, the adult account owner, who confirmed that only he uses the API key.
- Google's Gemini API terms require users to be 18+ and forbid apps "likely to be accessed by individuals under the age of 18" (ai.google.dev/terms). The setup card makes the key owner confirm 18+ and accept Google's terms.
- Superseded by section 0 (v2.0.1 and later): built-in keys are filled in at build time from the `GEMINI_API_KEY` Actions secret or the untracked `ai/gemini_key.txt`; there is no own-key option. Still: no key in the code or the repo, and never in config.json or logs. (Original v1.4 rule: bring your own key, stored in Windows Credential Manager `RETWEAKS/GeminiAPIKey`.)
- Only whitelisted PC specs are sent (never serials, names, addresses or paths), and only when "Include my PC specs" is on. "See what's shared" shows the exact text.
- The assistant gives advice only. It never runs commands or changes settings.
- Default model: `gemini-3.8-flash` (stable and free tier per Google's docs, checked 2026-10-21). It's a setting, so it can change without a code change.

## 14. UI behavior

- Loading indicators only appear for real work.
- Long tasks run asynchronously and can be cancelled where feasible.
- Success or error messages appear only after the real result is known.
- No dead buttons, fake controls, placeholder data, or settings that look functional but aren't.

---

## 15. Settings, migration and persistence

- Settings persist between launches. Keep existing formats and keys.
- New settings get safe defaults. Old settings are never reset.
- Validate imported settings and profiles, and handle bad data without wiping good data.
- Keep app settings separate from game profiles and backups.
- Reset-to-default must be explicit and limited to the intended settings. Never do a silent global reset.
- Never store credentials in plain text. **The repo is public, so never commit secrets, API keys, tokens or personal data.**

---

## 16. Packaging, Git and releases

### Build
- Build a single-file `.exe` with `build.py` (PyInstaller `--onefile --windowed`, with the icon embedded and bundled). Output: `dist\RETWEAKS.exe`.
- The `.exe` must be built on Windows. Never claim an `.exe` was built or tested unless that actually happened.
- **Admin rights (owner decision):** `build.py` keeps `--uac-admin`, so the app always runs as administrator. Several tweaks need admin access. Still tell the user in the UI which tweaks change system-wide settings, and handle a declined UAC prompt gracefully.
- Test clean startup, shutdown and relaunch. Make sure paths and config work when the app runs from any folder.

### Git
- Every commit message is exactly: **`RETWEAKS`**
- Never commit `build/`, `dist/` or the `.exe` itself. The `.exe` goes in GitHub Releases.

### Releases
- Only publish a release when the owner says to.
- Attach the **current single-file `RETWEAKS.exe`** built from the latest committed code. Each release has three files: `RETWEAKS.exe`, `RETWEAKS.zip` (the same .exe zipped, for people who prefer a .zip) and `RETWEAKS.exe.sha256` (used by the in-app updater). Owner decision 2026-10-21.
- **Default build: GitHub Actions** on a Windows runner, which runs `build.py` and attaches `dist\RETWEAKS.exe` to the release.
  - How to release (set up 2026-10-21): add `release-notes/vX.Y.md`, merge to `main`, then either push tag `vX.Y`, or run **Actions → Build RETWEAKS → Run workflow** with `release_tag` = `vX.Y`. Both build the `.exe` on Windows and publish the release as Latest. Claude can start the manual run after the owner says to release. Running it again for a tag that already has a release deletes that release and tag first, then publishes the new build (owner re-released v1.5 on 2026-10-22).
- **Alternative:** the owner builds on his PC in `C:\pc_optimizer` and the `.exe` is uploaded from there.
- Before releasing, confirm the `.exe` was built from the current code and that it launches.
- The `.exe` is not code-signed, so Windows SmartScreen or antivirus may warn people who download it. Never claim it is signed.

---

## 17. Reference PC (for testing only; never hardcode)

- iBUYPOWER Trace Mesh TMI7N4601, Windows 11 Home
- Intel Core i7-14700F, Intel B760 Wi-Fi motherboard (the exact vendor and model must be detected)
- NVIDIA GeForce RTX 4060 8 GB
- 32 GB DDR5-5600 RAM, 2 TB NVMe SSD
- Main use: 1080p gaming focused on Fortnite FPS. Minecraft is also played.

---

## 18. Known issues (updated 2026-10-21, v1.4)

- Game presets cover Fortnite, Minecraft Java, Minecraft Bedrock, Apex Legends and Rocket League. CS2 has no built-in preset because its settings file contents couldn't be confirmed from sources; CS2 players use "Choose your own file".
- Some preset keys could not be confirmed for every game version (for example the Fortnite rendering-mode key, Bedrock graphics mode). The engine only changes keys already present in the user's file, so wrong names are skipped, never added.
- Startup-app "Impact" was a guess based on where the entry came from, so v1.2 removed that column.
- v1.4 was written and unit-tested on Linux. Everything that touches Windows (audio, clicks, display mode changes, PresentMon, Credential Manager, scheduled tasks, priorities, raw mouse input) still needs testing on a real Windows PC before release.
- The FPS overlay only shows over borderless/windowed-fullscreen games; exclusive fullscreen draws over it. It must never be changed to inject into game processes (anti-cheat).
- The FPS test needs the user to download Intel PresentMon (2.x console app); RETWEAKS doesn't bundle it. The overlay doesn't (built-in ETW reader since v1.4.3), but its numbers must be compared against PresentMon on a real PC before release; the ETW code was written and unit-tested (struct layouts, frame math) on Linux.
- Browser (v1.5): a proxy option was requested and postponed by the owner. Brave can't be the page engine (no embeddable runtime); it's offered as Brave Search. Video fullscreen fills the Browser page area, not the whole screen.
- Audio output switching uses pycaw's SetDefaultDevice (the undocumented IPolicyConfig interface), so it's labelled as such and falls back to Windows Sound settings.

## 18a. Feature backlog (approved by the owner, not built yet)

### v1.4 (owner decisions 2026-10-21; everything below is built on the v1.4 branch except RETWEAKS Pro)
- **New logo and startup animation (owner choice 2026-10-21): logo C "Chip" and splash C "Chip scan".** Source: `assets/brand/logo-chip.svg` and the design canvas "RETWEAKS logo & startup animation". Splash: the chip outline draws, the pins light up in sequence, a scan line sweeps, the R traces in, then the RETWEAKS wordmark and an honest status line ("Scanning hardware…") appear, then it fades into the main window. It plays while the app really loads (no added waiting, no version number, section 6). The chip becomes the app icon (`assets/icon.ico`: window, taskbar, .exe). The main window header keeps the wordmark only, with no logo beside it (section 5), unless the owner approves the header comparison on the design canvas.
- **Chip design across the app (owner choices 2026-10-21):** the chip as the app icon at every Windows size (16–256 px); a matching monochrome thin-line icon set for the sidebar pages; a mini chip "scanning" loader shown only while real work runs; Health Check results shown as chip pins lighting up per real check result (✔ / amber / ✖); an About / "What's new" screen with the chip and version; a 150 ms fade between pages and a sliding accent bar in the sidebar; empty states with a faint chip outline and one helpful line.
- **Splash timing (owner update 2026-10-21, after testing):** the reveal always plays at normal speed (about 1.4 s; the earlier ~1 s sped-up version looked rushed). If loading takes longer, the scan line keeps sweeping until loading really finishes. Then a 0.3 s pause on the finished logo and a ~0.55 s cross-fade: the main window opens centered behind the splash and fades in while the splash fades out. No other waiting.
- **Logo color (owner choice):** grey/white on every theme. The chip doesn't follow the accent color.
- **Health Check:** one scan of startup apps, temp file size, power plan, disk health, pending updates, etc., each with a "Fix" that uses the existing undoable tweaks.
- **Background calming:** while a game runs, temporarily lower the CPU priority of **only the apps the user picks**, then restore them.
- **Real FPS and 1% / 0.1% lows** with Intel PresentMon, plus before/after run comparison in Snapshots.
- **Sensor logging to CSV** (temps, loads, clocks) during a session.
- **Audio mixer** (section 11) and **auto clicker** (section 10).
- **Disk space analyzer**, Storage Explorer upgrade (section 12), Scheduled Tasks in Startup apps, smooth animations (section 5).
- **RETWEAKS Pro: ON HOLD (owner decision 2026-10-22).** v1.5 and later stay free and open source until the owner says otherwise; build nothing paid. Original plan kept for reference: **RETWEAKS Pro, $8 one-time.** Core stays free (monitoring, tweaks, game presets). Pro: extras such as auto game mode, FPS compare, Health Check fixes and sensor logging (final list to be confirmed with the owner). Payment and license accounts go through the account owner (adult). Decide how Pro features stay protected while the repo is public (for example open core: Pro code in a private repo).

### Later
- **Possible merge (owner note 2026-10-22):** Ryder may later combine his friends' software with this one to form RETWEAKS. Nothing to build yet; when it happens, follow section 4 (inventory, no lost features, migration).
- DNS speed test, if it isn't finished in v1.3 (section 8).
- Other new tools are welcome. Each one must follow every rule in this file: real function, honest results and no lost features. Confirm the scope with the owner before building.

---

## 19. Workflow for every task

Owner request 2026-10-23: Windhawk page (base tab 29), next to Browser in Tools, full-page
https://windhawk.net/mods via EmbeddedSite's windhawk option. Own WindhawkBrowser profile,
same lifecycle/theme/recovery as the other site tabs. Browsing the page does not install Windhawk.

Owner request 2026-10-23: FPS overlay has individual metric switches (FPS/1%/0.1% lows,
rolling avg/min/max, frame time/count, CPU/GPU utilization, RAM/VRAM, temperatures, clocks,
GPU power and names), compact layout, refresh interval, margins and precision. Hardware readings
use the shared telemetry service while selected; it remains acquired when leaving the Dashboard.
Missing/stale values show –; 0.1% lows require 1,000 frames; temperature units follow Settings.

Owner request 2026-10-23: `feature_ai.py` adds contextual help across the app, using the existing
Gemini assistant and its Use hub context control. No AI action applies changes automatically.
`driver_download_ui.py` also offers Install driver (fresh offer, one consent, verified download,
then vendor setup; existing separate controls stay). `rt_pages/taskbar.py` / `core/taskbar_download.py`
adds Transparent TB (taskbar): Download immediately downloads the official TranslucentTB App Installer
and installs it for the current account through Add-AppxPackage; nothing installs on page open.
Fortnite-only resolution (owner request 2026-10-23): `core/fortnite_resolution.py` and
`fortnite_resolution_ui.py`, on Presets and Display. Only existing keys inside Fortnite's video
settings section are edited (Fullscreen and resolution), with backup and resolution-only restore.
Desktop display APIs are not called. The original whole-display controls remain clearly labeled.
Fullscreen/game/driver overrides mean the result must be checked in Fortnite after launching it.

**Before you start:**
1. Read this file.
2. Inspect the current repo.
3. Give a short plan that names the files you'll change.
4. List the risks to existing settings and features.
5. Make a focused, backward-compatible change.

**After you finish:**
1. Run the available tests, linting and build.
2. Manually verify what can be tested in your environment.
3. Check for controls that aren't connected to real code.
4. Check that settings persist.
5. Compare against the original inventory.
6. Report exactly what changed, what was tested, what passed or failed, and what is still unverified.
7. Never claim a test passed if you didn't run it. If a Windows-only feature can't be tested in your environment, say so and give the next validation step.

---

## 20. Acceptance checklist

A change is not done until each applicable item is verified:

- [ ] All existing screens, settings, tweaks, profiles and features are still there.
- [ ] Nothing unrelated was reset, renamed, deleted or simplified.
- [ ] Existing preferences and profiles still load, and new settings persist.
- [ ] Any migration is backward-compatible and preserves old data.
- [ ] The UI fits the black/grey rounded design, with no picture emojis and no "Galaxy Optimizer".
- [ ] The sidebar header follows the `header_style` setting (chip + wordmark by default).
- [ ] The splash is centered and sized correctly, animates smoothly, and shows no version number.
- [ ] The taskbar and window use the RETWEAKS icon.
- [ ] Hardware data, including the exact GPU name, comes from real detection. Unsupported metrics show "Unavailable".
- [ ] Tweaks make real, reversible changes and report actual results.
- [ ] Startup-app controls work and can be restored.
- [ ] DNS lets the user choose a preset, a custom server or Automatic, per adapter, and can be restored.
- [ ] Ping tests use 1.1.1.1 or 1.0.0.1 and promise nothing unmeasured. The DNS speed test shows only real measurements.
- [ ] Any rewrite or language change followed the rewrite protocol (section 4).
- [ ] Game profiles offer Low, High, Ultra and Ultra Performance where they apply, with backups.
- [ ] The auto clicker starts and stops reliably, including emergency stop and app close.
- [ ] The theme persists and updates the whole interface.
- [ ] The audio mixer and Storage Explorer still work.
- [ ] The AI Assistant follows section 13 (own key in Credential Manager, whitelisted specs, advice only).
- [ ] No secrets or personal data are in the commit.
- [ ] The build and tests actually ran, or the untested parts are clearly disclosed.

Owner request 2026-10-23: File Transfers in Tools. `core/file_transfers.py` / `rt_pages/file_transfers.py`: encrypted temporary transfers through Litterbox, up to 1 GB including ZIP/encryption overhead, expiry 1/12/24/72 hours. Files/folders become a ZIP; receiver saves a ZIP without auto-extract/execute. Share code contains the encryption key and is not persisted/logged. Sender can close after upload; no server/account configuration needed. Runtime dependency cryptography.

File Transfers mixed picker (2026-10-23): Add files & folders selects both types together with Ctrl/Shift. The picker can collect items from multiple directories before Add to transfer. Existing separate file/folder buttons stay. Limits explained on-page: 1 GB total per transfer, up to 10,000 items; no ReTweaks daily counter/reset, no published provider daily quota/reset; each upload expires separately. Directory reads run in a background thread.

Background improvements (2026-10-23): Settings gains visual theme tiles/favorites, larger live animation preview, speed/brightness/detail/FPS/banner-size settings, custom picture banners, Aurora/Starfield/Rain/Pulse. Existing theme/animation names and settings preserved. Hidden accents stop scheduling redraws. New Backgrounds Tools page previews local pictures and six local gradient presets, saves picture/video favorites, applies Windows pictures through IDesktopWallpaper with per-monitor picture+fit backup/restore, and optionally installs/controls Lively via its documented CLI. Lively remains optional; no install/apply happens on opening the page. Current wallpaper API is queried read-only until Apply.

Owner navigation consolidation (2026-10-23): 15 main sidebar pages plus About/Settings. Mapping: docs/NAVIGATION_GROUPS.md and rt_navigation.GROUPS. Existing controls/page objects/tab indices stay; section buttons switch original pages so lifecycle and native embeds remain unchanged. All tweak collections share Tweaks; graphics and FPS benchmarks share Benchmark. Original names remain in search/startup routes. New navigation_sections setting remembers the last section per group without changing old preferences.

Browser fix (2.0.4, 2026-10-23): explicit sys._MEIPASS helper lookup in frozen builds, browser-component validation before packaging, missing-component recovery text distinct from WebView2 installation, and --verify-browser live helper/embedding/local-page check with an isolated profile. Patch version separates this build from old running 2.0.3 copies under the existing single-instance version protocol. Source and packaged live WebView2 initialization passed: helper found, window embedded, built-in New Tab document loaded; packaged startup exit 0. All consolidated navigation and saved browser data remain.

Sidebar refinement (2.0.5): 19 main entries + About/Settings. Drivers, File Transfers, Backgrounds and App Starter restored as direct entries and removed from nested section duplicates. Tweaks and Benchmark remain combined. Short-menu scrollregions are at least viewport height, so scrolling cannot shift the menu into empty space. Legacy Storage & transfers startup alias preserved.

Navigation titles refined by owner request: Hardware & cooling, Benchmark & FPS, Tweaks & presets, Gaming tools, Storage & cleanup, Windows appearance, Windows tools, PC planning, Help & activity. Old group names and remembered section preferences remain compatible through GROUP_ALIASES/preferred_section.

2.0.6 owner refinements: Dashboard merges Quick Start actions, Game Mode/detection and recommendation with the live metric overview. Legacy tab 0 routes to Dashboard; single-destination groups have no section chips. Settings has one theme selector and one background animation selector/preview; additional animation controls are collapsed, existing setting keys preserved. Contextual AI matches the actual page title only, never RETWEAKS branding. Discord website button now reads exactly Get Retweaks.

2.0.7: Drivers joins Get-PnpDevice -PresentOnly with installed signed-driver metadata across physical buses, excludes disconnected/software/virtual devices and per-thread processor duplicates, and retains all detected component categories. A category filter limits visible results. Vendor installer rows start hidden and only appear for detected matching devices; actual silicon vendor stays distinct from OEM support URL. Windows Update offers in-app applicable driver installation for other hardware; BIOS/firmware remain exact-model support links. Settings and prior driver installation confirmations/signature checks are unchanged.

2.0.7 additional owner refinements: welcome tour explains category/section switches at the top of some pages; Windows backgrounds is the visible sidebar/page title (legacy Backgrounds routes retained); About Website button uses the same dark default style as its neighboring links.

2.0.8 owner request: clean GitHub-ready snapshot with current source only, private keys in ignored ai/gemini_key.txt and GEMINI_API_KEY Actions secret, automatic missing feature dependency installation. core/dependencies.py pins verified PawnIO and PresentMon releases; WebView2 uses Microsoft Authenticode verification. rt_dependencies.py serializes per-component asynchronous setup, reports failures/restarts and avoids loops. Lively remains on-demand for animated actions. Settings automatic_dependencies defaults on; source app entry and frozen runtime enable setup, checks do not. Setup-ReTweaks.ps1 installs build prerequisites, build.py compiles helpers. Do not publish local keys or compiled GeminiChat.exe.

2.0.9 user fixes: Windows backgrounds icon uses underscore slug and legacy icon fallback. Native browser menus recursively apply readable theme colors, rounded submenu regions and custom check/text rendering. Ctrl+K forwards from browser/site helpers. All tweaks gains a persistent-widget name/description/category filter; global tweak results open the filtered list without applying changes. Global search clears on navigation and uses a transient popup above native helper windows while preserving the existing in-window popup on Tk pages. Browser self-check verifies native menu theme/rounding and Ctrl+K events.

Release publication: all current changes since 2.0.3 are released together as 2.0.4 at the user's request. core/version.py is the authoritative published version. Discord website button is Get Retweaks.

2.0.5 (owner report 2026-10-24): Dashboard banner `Banner._watch_window` re-checks every 0.5 s while it should animate but the window is hidden/minimized (first launch behind the splash, tray, minimize) and starts by itself; check `checks/check_rt_banner_start.py`. Browser menu `KeepInsideApp` opens the Search engine submenu to the left when it would pass the RETWEAKS window or screen edge (it opened on a second monitor).
2.0.5 translations (owner report 2026-10-24): ~420 strings added in 2.0.4 translated for es/fr/de/pt-BR (coverage 99.9%; the 3 untranslated are the Windows Activation page texts, which Claude does not work on). Units/product names/search keywords added to keep_en.json. Sidebar labels must fit the 245 px sidebar: de "Zustand & Reparatur", fr "Matériel et ventilation", pt-BR "Fundos do Windows", es "Disco y limpieza". checks/check_rt_i18n.py and check_rt_monitor.py updated for the 2.0.4 sidebar groups and Dashboard.
2.0.6 (owner request 2026-10-24): updates always come from the GitHub release (`core/updater.install_update`). Packaged exe: swap as before. From source: the verified release exe goes to `%LOCALAPPDATA%\RETWEAKS\app\RETWEAKS.exe` (`install_release_copy`) and starts after this process exits; the source folder is never touched. `REPO` is the canonical `w1zr/ReTweaks`. Banner colour: settings `banner_color` (original default / mono / accent / custom) + `banner_custom_color` (HEX), `rt_pages/monitor.banner_palette`; Settings → Appearance → Banner color; check `checks/check_rt_banner_color.py`.
2.0.7 (owner request 2026-10-24): no RETWEAKS.old.exe is kept. The swap moves the old exe aside only for rollback, deletes it after the new one is in place; `updater.remove_old_exe()` (run in the background by `rt_shell.Shell._remove_old_exe` at start) deletes one left by 2.0.6 and earlier beside the exe or in `%LOCALAPPDATA%\RETWEAKS\app`, logged as "Delete previous version".
2.0.7 Fortnite resolution (owner request 2026-10-24, it didn't stick): `fortnite_resolution.apply(..., lock=True)` makes GameUserSettings.ini read-only after saving (setting `fortnite_resolution_lock`, default on); state file records the previous read-only flag and `restore` puts it back (older state files: unlocked). Also writes DesiredScreenWidth/Height + LastUserConfirmedDesiredScreen* when present. `mode_check` reads the primary display's mode list only (no display change); the confirm dialog says whether the card offers the size and how to add a custom resolution / Full-screen scaling.
2.0.7 Fortnite file detection (owner request 2026-10-24): `fortnite_resolution.find_files()` = %LOCALAPPDATA% candidate + every profile under the Users folder (`RELATIVE` path), newest first; the panel detects in the background on open and shows the path (read-only). A saved custom path and Choose file still win.
2.0.7 (re-released) Dashboard summary (owner report 2026-10-24): `monitor.pc_label` drops a PC model that repeats the CPU name (iBUYPOWER reports the CPU as the model) or is an OEM placeholder, and the summary skips duplicate parts. Hardware page and report still show the raw maker/model Windows reports.
2.0.8 (owner request 2026-10-26: error on first launch, antivirus): retweaks.py wraps optional startup steps (`_optional`, logged as STARTUP STEP FAILED) and, if the window/shell fails, logs STARTUP FAILED and restarts once via `rt_shell.restart_after_exit` (`--restarted`), then shows the crash.log path. `rt_shell.still_starting`: a second launch within 90 s of another copy exits quietly. Antivirus: spec `upx=False`, Windows version resource from `build.write_version_info` (`build_version_info.txt`, ignored), CI compiles the PyInstaller bootloader from source (continue-on-error). Not code-signed (owner: free fixes only).
README/website version (owner request 2026-10-26): README shows a shields.io latest-release badge instead of a typed version; docs/index.html already loads the newest release from the GitHub API, its fallback text is "latest version". Never type a version number into README or the website.
2.0.9 (owner report 2026-10-27: language switch on Windows left the sidebar without icons and text unchanged): `rt_i18n.set_language` relabels viewable widgets first, then hidden ones in batches of 250 via after() (`busy()`, generation counter cancels an older switch; `sync=True` does all at once); the sidebar gets `Sidebar.relabel` (redraw only, icons kept) instead of `refresh`; `retweaks.text_w` caches widths per (font, text). Check `checks/check_rt_language_switch.py`.

## 21. Handoff from earlier sessions (2026-10-27)

Development moved mostly to Claude Code on 2026-10-27. The full handoff, `docs/COWORK_NOTES.md`, stays on the owner's PC only (excluded from git); never commit it.

### Owner rules
- **Isolation:** keep this project's work inside this project. GitHub is the only approved connector; don't use other connectors, memory or files on the machine. RETWEAKS must never run on a work laptop.
- **CLAUDE.md source:** only this file (`C:\pc_optimizer` or the repo root). Ignore older copies in backup folders.
- **Windows Activation page** (added by the friend in 2.0.4): Claude doesn't work on it, translate it, or mention it in release notes.
- **Release notes (owner change 2026-10-27):** from 2.1 on, each release's notes describe the whole app: "What's new in X" first, then "Everything in ReTweaks X" and "Good to know", kept up to date with every change since. Don't link to an older release for the feature list. (`release-notes/v2.0.6`–`v2.0.9` linked to 2.0.5; `v2.1.md` is the current full description.)
- **Re-releasing a version is allowed** (2.0.7 was re-published 2026-10-24). The updater compares version numbers, so people already on it don't get the rebuild.
- **"Unlimited AI" / Freebuff tab: on hold** (2026-10-24). Freebuff has no public chat API; the unofficial `freebuff2api` proxy was refused (imitates the official client, rotates accounts). If built later: an official API only, and not called "Unlimited".
- **Code signing:** free fixes only (2026-10-26). No certificate.

### Open work and known bugs
- **First-launch error on a friend's PC (2026-10-26):** cause unknown; 2.0.8 only added a restart-once guard. Needs that PC's `%APPDATA%\RETWEAKS\crash.log` (`STARTUP FAILED` / `STARTUP STEP FAILED`).
- **2.0.9 language switch:** `checks/check_rt_language_switch.py` passed on Windows 11 from source on 2026-10-27 (screen switched in 0.11 s, icons kept). Still worth one manual check in the built .exe.
- **Fixed 2026-10-27:** the welcome tour's "Step {n} of {total}" is translated (strings + template "Step {0} of {1}" in each `i18n/*.json`); the language-switch check now asserts it found its hidden-page labels ("Ready to check") instead of passing when none exist.
- **Fixed 2026-10-27 (smoothness, from perf.log: ~1,700 freezes of ~130 ms):** the volume lock (`audio_panel.AudioPanel.lock_tick`) reads/writes Core Audio on its own thread (`_lock_worker`, COM via `core.audio.com_scope`); the UI tick only starts it and passes its log lines to `log_action`. An injected `lock_io` (checks) still runs inline. UI cost per tick went from ~130 ms to 0.4 ms.
- **Fixed 2026-10-27 (crash):** opening Fun tools a second time crashed the whole process (0xC000041D): `RawMouseListener` re-registered its window class under the same name, Windows kept the first run's freed WNDPROC. The class is now unregistered when the listener stops and every WNDPROC is kept alive (`_procs`).
- `run_bg` renames its polling callback after `done`, so perf.log names the slow page callback instead of `common.run_bg.check`.
- **Page switching (2.1):** `hubplus` `show_tab` runs the switch inside `rt_perf.paint_once(self.content)` (WM_SETREDRAW off, layout, one RedrawWindow), so a page appears in one paint instead of black boxes. Measured on Windows 2026-10-27 over 47 pages: median 88 → 48 ms (first visit) / 41 ms (later); every page under 100 ms after its first visit. Base-app tabs 1, 2 and 23 still take ~300–400 ms on their first visit (first layout); laying them out ahead of time cost the same and didn't help, so it isn't done.
- **Known failing check:** `check_sidebar_layout.py` stops at `hub.nav[19].command()` (`'_NoNav' object has no attribute 'command'`); it already failed before 2.1 (the sidebar no longer uses the base app's nav buttons).
- **2.1 (owner request 2026-10-27):** version after the smoothness fixes is 2.1 (`core/version.py`, `release-notes/v2.1.md`); `parse_version("2.1")` = (2, 1, 0).
- **Testing from source:** taskbar buttons of python.exe test windows can show a stale cached icon; `RETWEAKS.exe` shows the chip. Not a bug in the app.
- **v2.0.5 release page:** the full description (commit `05d2a9c`) was pushed after publishing; unconfirmed whether the release page shows it.
- **README badge:** confirm on GitHub that the shields.io badge shows the right version.
- **Antivirus/SmartScreen:** not re-checked since 2.0.8.
- **Never tested on real Windows:** updating from source (`%LOCALAPPDATA%\RETWEAKS\app`), `updater.remove_old_exe`, the Fortnite read-only lock and multi-profile file search, `rt_shell.restart_after_exit` / `still_starting`.

### Lessons learned
- `python build.py` recompiles the tracked `ai/*.exe` helpers, so they show as modified after every local build; don't commit them unless their C# source changed.
- Tests run as root on Linux ignore read-only files: use `lock=False` in Fortnite tests (a root-only pass failed on Windows CI in 2.0.7).
- Keep each file's encoding and line endings (BOM/CRLF), or diffs cover the whole file.
- In `ai/GeminiChat.cs`, a method named `Keys()` shadowed the WinForms `Keys` enum; it is `AllKeys()`.
- `RETWEAKS.exe` can't be tested under Wine ("Failed to start embedded python interpreter!").
