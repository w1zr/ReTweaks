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
| Not taken from v1.5 | Windows Activation page (embeds massgrave.dev, an unofficial Windows/Office activation tool) | — | **skipped**, owner to decide; also v1.5's empty bundled AI key (owner keeps the shared key) |
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
