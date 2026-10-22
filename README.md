<p align="center">
  <img src="assets/brand/banner.png" alt="RETWEAKS" width="720">
</p>

<p align="center">
  <b>Free Windows PC diagnostics and optimization.</b><br>
  Real hardware readings, reversible tweaks, and honest results. No fake numbers.
</p>

<p align="center">
  <a href="https://github.com/w1zr/retweaks/releases/latest"><b>Download the latest release</b></a>
</p>

---

## What it does

**Monitor**
- **Dashboard and Hardware:** CPU, GPU (exact model and real VRAM), motherboard and BIOS, RAM, drives and disk health, monitors, audio and network, plus live CPU and GPU load and clocks. Temperatures and fans work when LibreHardwareMonitor is running.
- **Health Check:** one scan of startup apps, temp files, power plan, disk health, free space, pending restarts, Windows Update, Game Mode, refresh rate and RAM. Each check has a **Fix** button where RETWEAKS can help.
- **FPS test:** real average FPS, 1% lows and 0.1% lows measured with Intel PresentMon, with saved runs you can compare.
- **In-game FPS overlay:** live FPS, 1% low and frame time over games in borderless or windowed fullscreen. Nothing is injected into the game.
- **Display and drivers:** checks whether each monitor runs at its highest refresh rate, and shows your GPU driver version and age.

**Optimize**
- **Tweaks:** individual, explained tweaks, each with **Undo** and an "undo everything" option, plus a restore point.
- **Profiles, Game presets and Program rules:**
  - Game presets: Low, High, Ultra and Ultra Performance for Fortnite, Minecraft (Java and Bedrock), Apex Legends and Rocket League, or your own file. Backups are made first.
  - Program rules: per-program GPU choice and CPU priority.
  - Auto game mode and background calming.
- **Startup apps:** registry entries, Startup folders and scheduled tasks, which you can disable and re-enable at any time.
- **Network:** pick your own DNS, or go back to automatic; DNS speed test; ping test to 1.1.1.1.

**Tools**
- **Storage and cleanup:** disk space analyzer, file explorer, and temp cleanup that always shows a preview first.
- **Browser:** RETWEAKS's own browser on Microsoft's Edge engine, with tabs, private tabs, bookmarks, history, downloads and your choice of search engine (Google, DuckDuckGo, Brave Search, Bing, Startpage or your own).
- **Audio mixer** (speakers, microphone and per-app volume), **auto clicker and Fun tools:** mouse polling rate test, clicks-per-second test and reaction time test.
- **AI Assistant:** ask Google Gemini about your PC with your own free API key. The key is stored in Windows Credential Manager and never in a file. You must be 18+ under Google's terms.
- **Snapshots and Logs:** sensor logging to CSV, and a log of every change RETWEAKS made.

RETWEAKS never promises FPS gains. Use the FPS test to measure your own before and after.

## Install

1. Download `RETWEAKS.exe`, or `RETWEAKS.zip` if you prefer a zip, from the [latest release](https://github.com/w1zr/retweaks/releases/latest).
2. Run it. It asks for administrator rights, because many tweaks change system settings.
3. Updates install from inside the app. When a new version is out, a bar appears at the top of every page.

**Requirements:** Windows 10 or 11, 64-bit.

> RETWEAKS isn't code-signed, so Windows SmartScreen or your antivirus may show a warning. All the source code is here on GitHub. Always download from the official releases page.

## Build from source

```powershell
git clone https://github.com/w1zr/retweaks.git
cd retweaks
python -m pip install -r requirements.txt
python -m pytest tests     # run the tests
python main.py             # run from source
python build.py            # build dist\RETWEAKS.exe (Windows only)
```

Built with Python and PySide6 (Qt). Every release is built on GitHub Actions on a Windows runner.

## Reporting a problem

Open an [issue](https://github.com/w1zr/retweaks/issues). In the app, **Settings → Report a problem** copies a hardware report (no personal info) for you to paste.
