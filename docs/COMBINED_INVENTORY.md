# RETWEAKS v2 (combined app) — feature inventory

Owner decision 2026-10-22 (Ryder): combine RETWEAKS v1.6 with a friend's Tkinter app (v1.4), called "the base app" below.
The base app's code is the base (Tkinter + C# helpers), every RETWEAKS feature the base app lacks is added,
and everything is named RETWEAKS with the RETWEAKS chip logo. The base app is GPL-3.0-only, so the
combined app is GPL-3.0 (friend agreed). Local branch `combined` only; not published until the
owner says so. This file is the rewrite-protocol inventory (CLAUDE.md section 4): nothing ships
until every item below works or the owner approves each missing one.

Status legend: **keep** = the base app's version stays · **add** = RETWEAKS feature added to the Tk app ·
**merge** = the base app's version stays and RETWEAKS' extra parts are added to it.

## Pages and tools

Owner request 2026-10-23: Windhawk, next to Browser in Tools, embeds https://windhawk.net/mods
across the page using the shared EmbeddedSite WebView2 helper. Separate browser profile,
visibility/resize/theme support, automatic recovery and clean shutdown match the existing site tabs.

Overlay settings expansion (owner request 2026-10-23): individual FPS, 1%/0.1% lows, rolling
average/min/max, frame time/count, CPU/GPU utilization, RAM percentage and GB, VRAM, temperatures,
clocks, GPU power and names. Adds compact layout, refresh rate, edge margin and precision.
Settings apply live and persist. Overlay holds the shared telemetry sampler while hardware readings
are selected, even off the Dashboard; stale/missing readings remain unavailable. The 0.1% low needs
at least 1,000 frames. No game injection; the existing borderless/windowed-fullscreen limitation stays.

Owner request 2026-10-23: Fortnite-only stretched-resolution controls on Presets and Display.
Edits only existing video keys in the Fortnite settings section, requests Fullscreen, backs up first,
and restores only the previous video settings. It does not call desktop resolution APIs. The separate
whole-display mode controls remain labeled as such. Fortnite/GPU-driver overrides require in-game verification.

Owner additions 2026-10-23: contextual AI help across hardware, monitoring, Health Check, tweaks, games,
drivers, network, storage, startup, cooling, display, benchmarks, apps and recovery (`feature_ai.py`).
Questions are reviewable drafts in the existing assistant; feature observations follow Use hub context.
Drivers adds a combined Install driver action: one consent, fresh official offer, download, publisher
verification, then vendor setup. Existing separate download/run and Windows Update flows remain.
Transparent TB (taskbar) is a new page with a description and Download button that immediately downloads
and installs the official TranslucentTB App Installer package for the current Windows account.

| Area | base app v1.4 | RETWEAKS v1.6 | Decision |
|---|---|---|---|
| Home / dashboard | Home with presets and cards | Live dashboard: per-thread CPU load, CPU clock (live, real), GPU load (all brands, Windows GPU counters), VRAM, disk/network speed, temps via LibreHardwareMonitor, animated banner | merge: Home stays, add **Live monitor** page |
| Hardware info | System info (component_inventory) | Hardware page: DXGI exact GPU + 64-bit VRAM, RAM sticks, disk health, monitors, audio, network; report export | merge: keep System page, add RETWEAKS details + report export |
| Presets | 12 presets (MAX FPS, Esports, Balanced, Streamer, Low-end, Laptop, Privacy, Clean, All safe, CTT ×3) | 10 system profiles with preview of real changes | keep the base app presets; add RETWEAKS profile preview where missing |
| Individual tweaks | 117 tweaks (incl. CTT library); undo = Windows defaults | 53 tweaks; undo = exact original values, Undo everything, restore point | keep all 117; **add** the ~22 RETWEAKS tweaks the base app lacks with exact-original undo |
| Game profiles | 11 games (Fortnite, Valorant, CS2, Apex, Warzone, Minecraft Java, GTA V, Roblox, LoL, Rocket League, OW2) | Game presets: config-file editing with backups, Low/High/Ultra/Ultra Performance, custom presets, import/export, file lock (Fortnite) | merge |
| Benchmark | Browser render benchmark | FPS test (PresentMon, 1%/0.1% lows) + in-game FPS overlay (built-in ETW) | keep; **add** FPS test + overlay |
| Display | (links to Windows settings) | Display & drivers: max refresh check/apply, stretched resolution (global, NVIDIA custom res via NVAPI), GPU driver age | **add** |
| Drivers | Driver links/versions with AI matching | GPU driver version/age (part of Display) | keep the base app; RETWEAKS driver age shown on Display |
| Health Check | — | one scan + Fix buttons | **add** |
| Program rules | — | per-program GPU preference, fullscreen optimizations, CPU priority; auto game mode; background calming | **add** |
| Startup apps | opens Windows Settings | full manager (Run keys, Startup folders, Scheduled Tasks) with restore | **add** |
| Network | DNS presets as tweaks; flush DNS | DNS per adapter (presets/custom/Automatic, restore), DNS speed test, ping test (1.1.1.1) | **add** |
| Storage | Storage Explorer + Disk tools | Storage Explorer, disk analyzer, cleanup with preview | merge: keep the base app explorer, add analyzer + cleanup |
| Audio | Mixer (apps, speakers, mic, preferred devices, pop-out) | Mixer + mic + **volume lock** | merge: add volume lock |
| Auto clicker | interval, button, single/double, cycles, coordinates | CPS/interval, random range, start delay, hotkeys, emergency stop | merge |
| AI | the base app AI (Gemini via C# helpers, shared key) | AI Assistant (own key) | keep the base app's (owner choice) |
| Browser | v1.5: own-process browser (EmbeddedBrowser.exe): tabs, reopen closed tab, reload / hard reload, zoom, print, settings page, shortcuts home page, downloads (Edge download list), popups as tabs, fullscreen | full browser: tabs, private tabs, bookmarks, history, downloads, search engines (5 + custom), download folder / ask, clear site data | **merge (2026-10-22, owner: "the v1.5 browser with RETWEAKS branding")**: v1.5's browser program with RETWEAKS branding + everything RETWEAKS' had (see Browser inventory below) |
| Daily tools, App Starter, PC Value Checker, 3D PC Builder, Bottleneck | yes | — | keep |
| Snapshots | — | before/after snapshots + FPS run compare | **add** |
| Fun tools | — | polling rate, CPS test, reaction test | **add** |
| Crosshair (new, owner request 2026-10-22) | — | — | **new**: click-through crosshair overlay like Crosshair X (`core/crosshair.py`, `rt_pages/crosshair.py`): editor (10 styles incl. PNG image, colour, opacity, length, thickness, gap, outline, centre dot, rotation), 33 built-ins (12 + streamer pack of 21), My crosshairs (`%APPDATA%\RETWEAKS\crosshairs.json`), share codes `RTX1-`, `.rtxhair` files, online gallery (`crosshairs/gallery.json` on GitHub main; shows "Gallery isn't available yet" until published), show/hide hotkey, screen + offset, optional show at start. Settings: crosshair_enabled, crosshair_active, crosshair_hotkey, crosshair_monitor, crosshair_offset |
| Temperatures (base app v1.5) | v1.5: CPU/GPU/drive temperature cards (nvidia-smi, Windows storage sensors, bundled LibreHardwareMonitor sensor host) | needed a separately running LHM | **add** (`rt_pages/cooling.py` TemperaturesPage, °C/°F from `temp_unit`); Dashboard/Hardware now also read the bundled host; PawnIO link |
| Fan control (base app v1.5) | v1.5: live RPM, manual duty per fan / all system / all GPU / both, 30 % minimum, pumps excluded, BIOS control on exit / lost monitoring / ≥85 °C | — | **add** + RETWEAKS fan curves (`fan_curves.py`, `rt_pages/fan_curve_ui.py`): CPU/GPU/hottest source, Silent/Balanced/Performance/Full speed/Custom, 4–6 draggable points, hysteresis + ramp, 8 s missing-temperature failsafe, settings `fan_curves`, `fan_curves_on_start` (off) |
| RGB lighting (base app v1.5) | v1.5: OpenRGB (bundled) Fans / RAM / both, solid presets + custom colour, synced Rainbow with speed, advanced device/zone/mode + LED-count setup | — | **add** + RETWEAKS: Breathing / Color cycle (only when every controller has the mode), brightness, per-device on/off, lighting profiles (`rgb_profiles`), apply a profile at start (`rgb_apply_on_start`, `rgb_start_profile`; off by default) |
| Run (base app v1.5) | v1.5: open an app/folder/command, shortcuts to Task Manager, Resource Monitor, Event Viewer, Services, Disk Management, System Information, Notepad, Calculator, Windows Run | — | **add** (`run_panel.py`) |
| Quick start chart (base app v1.5) | v1.5: GPU utilisation samples (Windows GPU engine counters) + CPU/GPU temperature gauge | — | **add** (`gpu_metrics.py`, hubplus) |
| Other v1.5 fixes | rounded dropdown popup (RSelect), rounded pickers in Audio mixer / PC value, PC value custom country + two-column parts, colour picker field, sidebar slide resizes content, Blackout theme | — | **add** |
| Not taken from v1.5 | startup manager, health check, system tray, Discord presence, updater, settings page, game config/files pages | RETWEAKS has its own | keep RETWEAKS' (owner decision) |
| Windows Activation | Windows Activation page (embeds massgrave.dev, an unofficial Windows/Office activation tool) | — | **added by owner request 2026-10-23** using the shared EmbeddedSite helper (v1.5's empty bundled AI key remains excluded) |
| Activity / logs | Activity log | Logs page | keep the base app's |
| Appearance | themes + animations | 13 themes, custom accent, theme maker + share codes, sidebar header style, banner style | merge |
| Settings / behaviour | first-run desktop shortcut | tray (on by default), start with Windows (+minimized), in-app updater (SHA-256), single instance + reopen animation, Discord status, sensor CSV logging | **add** |
| Welcome tour (new, owner request 2026-10-22) | first-run shortcut prompt (replaced by the tour) | — | **add**: `rt_welcome.py` — shown once to anyone opening v2.0+ (setting `welcome_done_version`), replay in Settings; steps: welcome, how RETWEAKS works, °C/°F (`temp_unit`), language (`language`), automatic updates (`auto_update`, `rt_autoupdate.py`: check, download, SHA-256 verify, ask to restart), tray (`tray_on_close`), desktop shortcut (real .lnk, `first_run.json`), summary. Choices apply on Next only. |
| Branding | feather logo, its own name | chip logo, "ReTweaks" wordmark, chip-scan splash | RETWEAKS everywhere |

## Settings and data to carry over (never reset)
- RETWEAKS `%APPDATA%\RETWEAKS\config.json` keys (fan_curves, fan_curves_on_start, rgb_profiles, rgb_apply_on_start, rgb_start_profile, theme, tray_on_close, start_minimized, header_style, banner_style, custom_themes, custom_accent, discord_status, discord_show_game, ai_model, ai_share_specs, check_updates, calm_enabled, interval, temp_unit, storage_show_hidden, startup_show_windows_tasks, startup_page, last_preset, fun_*_best, audio_lock_output/input, overlay settings, browser_* settings), tweak backups, game backups, program rules, browser.json, startup backups.
- The base app's `%APPDATA%` data folder (`*.json`: appearance, history, benchmarks, …): copied into `%APPDATA%\RETWEAKS` once, old folder kept.

## Rules that change with the merge (owner decisions)
- Toolkit: Tkinter (from the base app) instead of PySide6.
- License: GPL-3.0-only (the base app's license).
- AI: the base app's shared-key Gemini helper (owner choice). The key is hardcoded in `ai/GeminiChat.cs`; publishing it was the owner's decision (2026-10-22).

## Status (2026-10-22, before any Windows testing)

Every row above marked **add** or **merge** is implemented in the Tk app (`rt_pages/`, `audio_panel.py`,
`automation.py`, `appearance.py`, `rt_shell.py`, `rt_sidebar.py`) and covered by a Linux check in `checks/`
(fakes for Windows APIs). Nothing has run on Windows yet.

Owner requests applied: RETWEAKS sidebar with line icons (not the base app's diamonds), RETWEAKS Dashboard as the
home screen, RETWEAKS chip-scan startup without the base app's orbit animation, the base app page contents kept.

### Differences from the PySide6 RETWEAKS (Tk limits) — owner to approve or ask for a fix
- **Light theme** not available: the base app's text colours are fixed light colours, so a light background would be
  unreadable. A saved "Light" choice maps to Graphite.
- **Galaxy theme:** no full-window starfield (the base app's background animations cover that role).
- **Theme maker:** text and status colours are saved in the theme/share code but not applied (fixed in this UI).
- **Startup apps:** no program icons in the list.
- **FPS overlay:** opacity fades the text too (Tk can't make only the background translucent).
- **Browser:** tab drag-reorder (RETWEAKS' old Tk tab strip) isn't in v1.5's browser; tabs open in order.

### Browser inventory (2026-10-22 rebuild: base app v1.5 browser + RETWEAKS)
Before (RETWEAKS Tk page around WebView2 in-process via pythonnet) -> after (ai/EmbeddedBrowser.exe, own process):
- Tabs, new/close/switch (Ctrl+T, Ctrl+W, Ctrl+Tab) -> kept; + reopen closed tab (Ctrl+Shift+T). Tab drag-reorder -> not in v1.5 (listed above).
- Private tabs (Ctrl+Shift+N, never in history) -> kept (WebView2 InPrivate controller; ••• New private tab).
- Address bar: address or search -> kept; engines Google, DuckDuckGo, Brave Search, Bing, Startpage + Custom (https, {q}) sent by RETWEAKS; menu Search engine ›; settings page has the custom field.
- Bookmarks (star / Ctrl+D, rename, delete, start page tiles) -> New tab shortcut tiles + Bookmarks and history page (open, new tab, rename, remove); stored in browser.json (first run merges RETWEAKS bookmarks + the base app shortcuts, else Google/YouTube/Discord/GitHub/Steam).
- History (Ctrl+H, search, clear) -> Bookmarks and history page (search, open, Clear history); visits/titles saved to browser.json; private tabs never.
- Downloads (list, open, show in folder, cancel; folder; ask where to save) -> Edge's download list (↓ button / Ctrl+J) + settings browser_ask_download / browser_download_dir (blank = Downloads).
- Clear site data -> ••• Clear cookies and site data… and Settings > Clear browsing data.
- About engine -> ••• About this browser, Settings > About (WebView2 version).
- Start page with logo + search + bookmarks -> v1.5 "Where to next?" page, RETWEAKS BROWSER label + chip logo, private-tab note.
- Fullscreen video, pop-ups as tabs, reload/stop, back/forward, home -> kept. New from v1.5: zoom, print, reload without cache, browser settings page (site permissions, scripts, autofill, password saving, startup/home URL, appearance options).
- Settings keys kept: browser_search_engine, browser_custom_search, browser_download_dir, browser_ask_download; new browser_v15_merged (first-run merge done).
- Cookies/sign-ins: %LOCALAPPDATA%\RETWEAKS\Browser (same folder as before).
- **Snapshot table** colours follow the theme only after a restart.

### Checks that can only pass on Windows
`check_sidebar_layout.py` (maximized state), `check_navigation_stress.py` (EmbeddedSite.exe),
`check_window_chrome.py` (native frame), `check_first_run.py` (PowerShell).

### Owner-approved removals
- 2026-10-23: **Notifications** page removed from the sidebar and search (owner request). Its data (`history.json`, recent tweak requests) is kept and still used for the AI context; a saved start page of Notifications moves to Dashboard.

Discord presence (2026-10-23): application 1562695957651521627, verified retweaks-logo-1024 asset, Optimizing with RETWEAKS activity and a single Get Now button to https://w1zr.github.io/ReTweaks/. Enabled for new settings; existing explicit opt-outs stay off. Settings can toggle presence; shutdown clears it through local IPC.

File Transfers (2026-10-23): new Tools page, file/folder selection, ZIP preserving folder names and empty folders, encrypted upload to Litterbox (1 GB, 1/12/24/72 hours), copy share code, receive by code to a ZIP, cancellation and honest byte progress. Sender can go offline after upload. AES-256-GCM keys stay in share codes, never settings/logs. Existing pages/settings retained; no existing defaults changed.

File Transfers mixed picker (2026-10-23): Add files & folders selects both types together with Ctrl/Shift. The picker can collect items from multiple directories before Add to transfer. Existing separate file/folder buttons stay. Limits explained on-page: 1 GB total per transfer, up to 10,000 items; no ReTweaks daily counter/reset, no published provider daily quota/reset; each upload expires separately. Directory reads run in a background thread.

Background improvements (2026-10-23): Settings gains visual theme tiles/favorites, larger live animation preview, speed/brightness/detail/FPS/banner-size settings, custom picture banners, Aurora/Starfield/Rain/Pulse. Existing theme/animation names and settings preserved. Hidden accents stop scheduling redraws. New Backgrounds Tools page previews local pictures and six local gradient presets, saves picture/video favorites, applies Windows pictures through IDesktopWallpaper with per-monitor picture+fit backup/restore, and optionally installs/controls Lively via its documented CLI. Lively remains optional; no install/apply happens on opening the page. Current wallpaper API is queried read-only until Apply.

Owner navigation consolidation (2026-10-23): 15 main sidebar pages plus About/Settings. Mapping: docs/NAVIGATION_GROUPS.md and rt_navigation.GROUPS. Existing controls/page objects/tab indices stay; section buttons switch original pages so lifecycle and native embeds remain unchanged. All tweak collections share Tweaks; graphics and FPS benchmarks share Benchmark. Original names remain in search/startup routes. New navigation_sections setting remembers the last section per group without changing old preferences.

Browser fix (2.0.4, 2026-10-23): explicit sys._MEIPASS helper lookup in frozen builds, browser-component validation before packaging, missing-component recovery text distinct from WebView2 installation, and --verify-browser live helper/embedding/local-page check with an isolated profile. Patch version separates this build from old running 2.0.3 copies under the existing single-instance version protocol. Source and packaged live WebView2 initialization passed: helper found, window embedded, built-in New Tab document loaded; packaged startup exit 0. All consolidated navigation and saved browser data remain.

Sidebar refinement (2.0.5): 19 main entries + About/Settings. Drivers, File Transfers, Backgrounds and App Starter restored as direct entries and removed from nested section duplicates. Tweaks and Benchmark remain combined. Short-menu scrollregions are at least viewport height, so scrolling cannot shift the menu into empty space. Legacy Storage & transfers startup alias preserved.

Navigation titles refined by owner request: Hardware & cooling, Benchmark & FPS, Tweaks & presets, Gaming tools, Storage & cleanup, Windows appearance, Windows tools, PC planning, Help & activity. Old group names and remembered section preferences remain compatible through GROUP_ALIASES/preferred_section.

2.0.6: One Dashboard now shows the existing live metric cards and banner plus preset/driver/App Starter shortcuts, Game Mode, game detection and hardware-based preset review. Quick Start route remains compatible but opens Dashboard. Settings has one theme picker and one animation picker/preview; speed, brightness, detail, FPS and height remain behind More animation options with unchanged saved keys. Duplicate theme gallery removed by owner request for simplest controls; stored theme/favorite data is retained. Contextual AI uses page titles without branding, and Discord link text is Get Retweaks.

2.0.7 present-hardware driver matching: scan currently connected PnP devices plus installed signed-driver metadata for all physical component categories; no graphics-only restriction or 32-row truncation. Virtual/disconnected devices and per-thread CPU duplicates excluded. Installer vendor rows hidden until detected, refinements preserve OEM vs silicon vendor distinction and remove stale matches on rescan. Categories come from detected rows only. Existing NVIDIA/AMD/Intel signed installer flow and Windows Update selected-driver installation remain; other components use applicable Windows Update or their official support page, not fabricated direct installers. Four matching tests and full mocked installer flow passed; actual read-only Windows scan yielded 118 present records / 75 distinct components. No driver installation performed during validation.

2.0.7 final UI: setup How RETWEAKS works explains category/section switches; sidebar and wallpaper header say Windows backgrounds, with old Backgrounds route preserved; About Website uses dark default button. Welcome flow (native tray/hotkeys mocked), all-page navigation, visible label and About style checks passed. Final live scan prefers installed-driver model names and strips Bluetooth address-like IDs; 118 present records / 74 distinct rows.

2.0.9: Windows backgrounds has an underscore-named sidebar icon plus compatibility fallback. Browser engine submenu recursively uses app colors, rounded region and readable item/check rendering. Global manual-tweak matches open All tweaks with name filtering; exact names are prioritized before the result cap. Local filters retain widget/selection state and fit short scrollregions. Search results use a transient host over native helpers, close and clear on tab switches, and receive Ctrl+K from browser/site helpers. Tests: 422 passed; expanded search/native focus, filtered selection and sidebar icon checks; native menu/theme/shortcut validation; all-page and browser lifecycle checks. No tweaks applied.
