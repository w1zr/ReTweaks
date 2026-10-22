# RYTWEAKS — CLAUDE.md (Master Project Context)

This is the single source of truth for RYTWEAKS. Read the whole file before making any change. The rules in it are hard constraints. If a request conflicts with this file, explain the conflict and ask before doing anything destructive.

---

## 1. Project overview

- **Name:** RYTWEAKS (always written in all caps). Never show the old name "Galaxy Optimizer".
- **What it is:** A Windows PC diagnostics and optimization app, shipped as a single-file Windows `.exe`. It shows real hardware information and live readings, applies practical PC and game tweaks, and includes game profiles, storage tools, an audio mixer, an auto clicker and related utilities.
- **Core goal:** Real functionality only. Every control must perform a real Windows action and report the true result. No mockups, stubs, placeholder data, fake math (for example, never `cpu_pct * 0.4` for GPU load) or hardcoded device hacks.
- **Owner:** Ryder. GitHub user `w1zr`.
- **Repo:** `w1zr/rytweaks`, public. All source files stay viewable on GitHub.
- **License:** None. Do not add a license file unless the owner asks for one.
- **Local folder:** `C:\pc_optimizer` on Ryder's Windows PC, a Git clone of the repo. Ryder updates it from PowerShell with `git fetch origin`, `git reset --hard origin/main` (or a branch), `python build.py`.
- **This file's location:** `C:\pc_optimizer\CLAUDE.md` and the root of the GitHub repo. Both copies must stay identical. When one changes, update the other in the same session.
- **Language policy:** RYTWEAKS stays mainly Python for now. Changing languages, mixing in other languages, or rewriting modules is allowed in the future, but only under the rewrite protocol in section 4.

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

- `main.py` — Entry point. Sets the Windows AppUserModelID (`rytweaks.pcoptimizer.suite.v1`) so the taskbar shows the RYTWEAKS icon. Loads `assets/icon.ico` and shows the splash screen, then the main window. Calls `freeze_support()` for PyInstaller.
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
- `core/updater.py` — Update check and in-app updates (SHA-256 verified, keeps RYTWEAKS.old.exe); since v1.4 an update bar at the top of every page offers **Update now** (owner request 2026-10-21).
- `core/nettest.py` — DNS speed test and ping test (1.1.1.1 / 1.0.0.1).
- `core/autostart.py` — Start with Windows via a Task Scheduler task (no UAC prompt at sign-in).
- `core/profiles.py` — System profiles. v1.4.3 `PRESETS` = data {tweak id: On/Off} + power plan: Esports, Max FPS, Balanced, Low-end PC, High quality, Ultra quality, Streamer, Privacy; plus the original Max Performance and Windows Default. `preview()` reads current state so only real changes are shown before applying (`ui/widgets/preset_apply.py`, used by the Profiles page). On the Tweaks page a preset only ticks its tweaks (`preset_selection`, `SELECTABLE_PRESETS`); the user unticks/adds, Clear selection, then Apply selected (`selection_preview`, `apply_selection`). Setting `last_preset` remembers the last one applied.
- `core/startup_manager.py`, `core/storage_manager.py`, `core/themes.py`, `core/report.py` — Startup apps (including scheduled tasks), Storage Explorer, disk space analyzer and cleanup, theme tokens, hardware report export.
- v1.4 modules: `core/healthcheck.py` (Health Check), `core/fps.py` (PresentMon FPS runs), `core/sensorlog.py` (sensor CSV logging), `core/display.py` (refresh rate + GPU driver info), `core/audio.py` (audio mixer), `core/autoclicker.py`, `core/funtools.py` (polling-rate / CPS / reaction tests), `core/ai_assistant.py` (Gemini AI Assistant), `core/overlay_fps.py` + `ui/overlay.py` (in-game FPS overlay: a separate click-through topmost window; never inject into a game process). v1.4.3: `core/etw_frames.py` is the built-in frame source (default, setting `overlay_source` = `builtin` / `presentmon`): its own real-time ETW session `RYTWEAKS_frames` with DXGI Present_Start 42/55, D3D9 Present_Start 1, DxgKrnl Present_Info 184 (IDs from PresentMon's PresentData/ETW headers); measures time between presents (MsBetweenPresents), not display time. Background calming lives in `core/app_rules.py`.
- v1.5 modules: `core/browser_data.py` (search engines, address-bar parsing, bookmarks/history in `%APPDATA%\RYTWEAKS\browser.json`, never in config.json), `core/browser_engine.py` (loads Microsoft's Edge engine, WebView2, through pythonnet + .NET Framework 4.8; SDK DLLs from the pywebview package, bundled by `build.py` into `webview2/`), `ui/widgets/edge_view.py` (one tab = a native QWidget hosting a WebView2 controller; .NET Tasks polled with QTimer; every .NET callback wrapped), `ui/pages/browser.py` (Browser page: tabs, private tabs via IsInPrivateModeEnabled, bookmarks, history, downloads). Engine profile (cookies/cache): `%LOCALAPPDATA%\RYTWEAKS\Browser`. The engine starts only when the Browser page is opened. Settings: `browser_search_engine`, `browser_custom_search`, `browser_download_dir`, `browser_ask_download`. `tools/browser_smoke.py` checks the engine on GitHub's Windows runner in every build. Audio mixer (v1.5) also controls the default microphone (`AudioBackend.input_*`, `set_default_input`). Start page: `core/browser_newtab.py` writes themed index.html/private.html to `%LOCALAPPDATA%\RYTWEAKS\Browser\newtab`, served as https://rytweaks.newtab/ (WebView2 virtual host); websites' preferred color scheme follows the theme. Volume lock (v1.5): `core/audio_lock.py` logic, enforced by a 0.5 s timer in MainWindow (`set_volume_lock`, settings `audio_lock_output` / `audio_lock_input`, None = off), follows the default device, never touches mute. Stretched resolution (v1.5, global since owner request 2026-10-22; the Fortnite-file version was removed because Windowed Fullscreen ignores the file): Display & drivers page, per monitor. `display.stretch_choices()` (narrower widths at native height + 4:3), `display.set_resolution()` (ChangeDisplaySettingsExW with DEVMODE dmDisplayFixedOutput = DMDFO_STRETCH; trial without saving → 15 s KeepSettingsDialog → save to registry, else `restore_saved_mode()`). Fortnite stays `lockable` so a previously locked GameUserSettings.ini can be unlocked. `core/nvidia_display.py` (ctypes NVAPI via nvapi64.dll nvapi_QueryInterface; IDs/structs from NVIDIA's MIT NVAPI SDK, sizes verified by compiling nvapi.h: NV_CUSTOM_DISPLAY 144, NV_TIMING 96, NV_TIMING_INPUT 32) adds a missing mode: source WxH with the monitor's native timing (GetTiming AUTO) so the GPU stretches; TryCustomDisplay → 15 s Keep → SaveCustomDisplay + `restore_saved_mode()` or RevertCustomDisplayTrial. Single instance (v1.5): `winutil.single_instance()` mutex; a second launch asks the running copy over a QLocalServer (`main._listen_for_show`, name `RYTWEAKS_show_<user>`) to show its window and waits for its "ok"; no answer → `winutil.other_instances()` / `close_other_instances()` offer "Close it and start"; `main._exit` ends the process after 6 s if shutdown hangs. Tray (v1.5): setting `tray_on_close` (default ON, owner decision 2026-10-22), tray icon = `assets/icon.ico` (owner's pick 2026-10-22); closeEvent hides to tray; `--minimized` start goes to the tray when it's on.
- `ui/main_window.py` — App shell: sidebar navigation, page stack, background workers, settings, change log.
- `ui/pages/` — One file per page (Dashboard, Hardware, Health Check, FPS test, Display & drivers, Tweaks, Profiles, Game presets, Program rules, Startup apps, Network, Storage & cleanup, Audio mixer, Auto clicker, AI Assistant, Snapshots, Fun tools, Logs, About, Settings).
- `ui/widgets/brand.py` — The chip logo drawn with QPainter, `ChipLoader` (mini scanning loader, only during real work), `EmptyState`, and the thin-line sidebar icons. `ui/widgets/chip_pins.py` — Health Check chip.
- `ui/widgets/` — Shared widgets (cards, live graphs) and the `Page` base class.
- `ui/workers.py` — Background threads. `ui/splash.py` — The splash screen (`RytweaksSplash`).
- `tests/` — pytest tests (parsing, tweaks undo, game presets, program rules, updater, network tests); run on any OS with `python -m pytest tests`.
- `release-notes/vX.Y.md` — The text of each GitHub release.
- `create_logo.py` — Builds `assets/icon.ico` (the chip) at 16–256 px, each size drawn separately. `build.py` — PyInstaller single-file build. Output: `dist\RYTWEAKS.exe`.
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
- The sidebar header shows the small chip logo next to the RYTWEAKS wordmark by default (owner choice 2026-10-21). Settings → Appearance → Sidebar header can switch to "Wordmark only" (setting `header_style`: `chip` / `wordmark`).
- Pop-ups and dialogs match the app's style, with clear confirm and cancel options and real outcomes.
- No fake progress bars or artificial waits.
- Accessibility: readable contrast, keyboard navigation where practical, visible focus states and a layout that scales.
- A targeted UI request gets a targeted change, not a redesign.

### Themes
- Built-in themes: Midnight black/grey (the default) plus accent themes Pink, Blue, Purple, Red, Green and Cyan. Full-UI themes (v1.4.1, owner choice): Super Black (pure black/OLED), Galaxy (with a static starfield backdrop), Ocean, Ember, Forest and Light. The logo uses the theme's `logo` token: grey/white on dark themes, dark on Light.
- Dashboard banner (v1.4.1): setting `banner_style` = `cores` (default, live per-thread load), `wave` (live CPU load), `circuit`, `galaxy` or `off`. It animates only while visible and not minimized.
- Custom accent color through a validated HEX input.
- Theme maker (v1.4.3): users build themes from 10 editable colors (`core/themes.py` EDITABLE); the rest are derived. Saved in settings `custom_themes` {name: colors}; built-in names can't be reused. Share codes `RYT1-` + base64 JSON, validated on import (hex colors only).
- Discord status (v1.4.3): `core/discord_rpc.py`, local Discord IPC only, off by default (`discord_status`, `discord_show_game`). Public Application ID 1562695957651521627; large image asset name `rytweaks`.
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
- Reopening while RYTWEAKS is already running hidden in the tray (or minimized) plays the same animation and fades into the window (owner choice 2026-10-22, `main._reopen`). A window already on screen is just brought to the front.
- Must close properly if startup fails, and must never stay stuck on top of the main window.
- The RYTWEAKS `.ico` must be embedded in the `.exe` and used for the window, the taskbar and shortcuts. The taskbar previously showed a random blue icon, which is a known bug to keep fixed.

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
- **CPU temperature, fans, motherboard sensors:** Windows has no API for these without a kernel driver, and RYTWEAKS does not ship one. Read them from LibreHardwareMonitor when the user runs it: its Remote Web Server (`http://localhost:8085/data.json`, needed for LHM 0.9.5 and newer, which removed WMI), or WMI `root\LibreHardwareMonitor` for 0.9.4 and older.
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
- **Services (v1.4.3):** only the `Start` value under `HKLM\SYSTEM\CurrentControlSet\Services\<name>` (4 = Disabled), applied after a restart; RYTWEAKS never force-stops a service. Undo restores the exact original start type. Always Advanced.
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
- Stay in sync with changes made outside RYTWEAKS. React when devices or sessions change.
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
- Bring your own key. No key in the code or the repo. The key is stored only in Windows Credential Manager (`RYTWEAKS/GeminiAPIKey`), never in config.json or logs.
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
- Build a single-file `.exe` with `build.py` (PyInstaller `--onefile --windowed`, with the icon embedded and bundled). Output: `dist\RYTWEAKS.exe`.
- The `.exe` must be built on Windows. Never claim an `.exe` was built or tested unless that actually happened.
- **Admin rights (owner decision):** `build.py` keeps `--uac-admin`, so the app always runs as administrator. Several tweaks need admin access. Still tell the user in the UI which tweaks change system-wide settings, and handle a declined UAC prompt gracefully.
- Test clean startup, shutdown and relaunch. Make sure paths and config work when the app runs from any folder.

### Git
- Every commit message is exactly: **`RYTWEAKS`**
- Never commit `build/`, `dist/` or the `.exe` itself. The `.exe` goes in GitHub Releases.

### Releases
- Only publish a release when the owner says to.
- Attach the **current single-file `RYTWEAKS.exe`** built from the latest committed code. Each release has three files: `RYTWEAKS.exe`, `RYTWEAKS.zip` (the same .exe zipped, for people who prefer a .zip) and `RYTWEAKS.exe.sha256` (used by the in-app updater). Owner decision 2026-10-21.
- **Default build: GitHub Actions** on a Windows runner, which runs `build.py` and attaches `dist\RYTWEAKS.exe` to the release.
  - How to release (set up 2026-10-21): add `release-notes/vX.Y.md`, merge to `main`, then either push tag `vX.Y`, or run **Actions → Build RYTWEAKS → Run workflow** with `release_tag` = `vX.Y`. Both build the `.exe` on Windows and publish the release as Latest. Claude can start the manual run after the owner says to release. Running it again for a tag that already has a release deletes that release and tag first, then publishes the new build (owner re-released v1.5 on 2026-10-22).
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
- The FPS test needs the user to download Intel PresentMon (2.x console app); RYTWEAKS doesn't bundle it. The overlay doesn't (built-in ETW reader since v1.4.3), but its numbers must be compared against PresentMon on a real PC before release; the ETW code was written and unit-tested (struct layouts, frame math) on Linux.
- Browser (v1.5): a proxy option was requested and postponed by the owner. Brave can't be the page engine (no embeddable runtime); it's offered as Brave Search. Video fullscreen fills the Browser page area, not the whole screen.
- Audio output switching uses pycaw's SetDefaultDevice (the undocumented IPolicyConfig interface), so it's labelled as such and falls back to Windows Sound settings.

## 18a. Feature backlog (approved by the owner, not built yet)

### v1.4 (owner decisions 2026-10-21; everything below is built on the v1.4 branch except RYTWEAKS Pro)
- **New logo and startup animation (owner choice 2026-10-21): logo C "Chip" and splash C "Chip scan".** Source: `assets/brand/logo-chip.svg` and the design canvas "RYTWEAKS logo & startup animation". Splash: the chip outline draws, the pins light up in sequence, a scan line sweeps, the R traces in, then the RYTWEAKS wordmark and an honest status line ("Scanning hardware…") appear, then it fades into the main window. It plays while the app really loads (no added waiting, no version number, section 6). The chip becomes the app icon (`assets/icon.ico`: window, taskbar, .exe). The main window header keeps the wordmark only, with no logo beside it (section 5), unless the owner approves the header comparison on the design canvas.
- **Chip design across the app (owner choices 2026-10-21):** the chip as the app icon at every Windows size (16–256 px); a matching monochrome thin-line icon set for the sidebar pages; a mini chip "scanning" loader shown only while real work runs; Health Check results shown as chip pins lighting up per real check result (✔ / amber / ✖); an About / "What's new" screen with the chip and version; a 150 ms fade between pages and a sliding accent bar in the sidebar; empty states with a faint chip outline and one helpful line.
- **Splash timing (owner update 2026-10-21, after testing):** the reveal always plays at normal speed (about 1.4 s; the earlier ~1 s sped-up version looked rushed). If loading takes longer, the scan line keeps sweeping until loading really finishes. Then a 0.3 s pause on the finished logo and a ~0.55 s cross-fade: the main window opens centered behind the splash and fades in while the splash fades out. No other waiting.
- **Logo color (owner choice):** grey/white on every theme. The chip doesn't follow the accent color.
- **Health Check:** one scan of startup apps, temp file size, power plan, disk health, pending updates, etc., each with a "Fix" that uses the existing undoable tweaks.
- **Background calming:** while a game runs, temporarily lower the CPU priority of **only the apps the user picks**, then restore them.
- **Real FPS and 1% / 0.1% lows** with Intel PresentMon, plus before/after run comparison in Snapshots.
- **Sensor logging to CSV** (temps, loads, clocks) during a session.
- **Audio mixer** (section 11) and **auto clicker** (section 10).
- **Disk space analyzer**, Storage Explorer upgrade (section 12), Scheduled Tasks in Startup apps, smooth animations (section 5).
- **RYTWEAKS Pro: ON HOLD (owner decision 2026-10-22).** v1.5 and later stay free and open source until the owner says otherwise; build nothing paid. Original plan kept for reference: **RYTWEAKS Pro, $8 one-time.** Core stays free (monitoring, tweaks, game presets). Pro: extras such as auto game mode, FPS compare, Health Check fixes and sensor logging (final list to be confirmed with the owner). Payment and license accounts go through the account owner (adult). Decide how Pro features stay protected while the repo is public (for example open core: Pro code in a private repo).

### Later
- DNS speed test, if it isn't finished in v1.3 (section 8).
- Other new tools are welcome. Each one must follow every rule in this file: real function, honest results and no lost features. Confirm the scope with the owner before building.

---

## 19. Workflow for every task

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
- [ ] The taskbar and window use the RYTWEAKS icon.
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
