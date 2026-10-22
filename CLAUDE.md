# RyTweaks: instructions for AI assistants

RyTweaks is an open source Windows PC performance and optimization app (Python + PySide6),
built into a single `RYTWEAKS.exe` with PyInstaller. Owner: Ryder (GitHub: w1zr).
It's used by people with all kinds of PCs (NVIDIA, AMD and Intel GPUs, desktops and laptops,
any Windows language), not just the developer's own machine.

## Golden rules

1. **Never show fake or guessed data.** If Windows doesn't report a value, show
   "Not available" (`None` in code). No placeholder values, no estimates presented as real
   (the old code once showed "CPU load × 0.4" as GPU load, and a hardcoded "Healthy" for disks).
2. **No per-model hacks.** Never write `if "4060" in name: vram = 8`. Fix the data source so
   it's right for every PC.
3. **Never delete user data.** Tweaks and profiles must not touch documents, downloads, game
   files or the Recycle Bin. Temp cleanup only touches %TEMP% and Windows\Temp.
4. **Report real results.** Every action returns `(ok, message)` from what Windows actually did,
   and is logged with `ctx.log_action(...)`. Never say "Success" unless it succeeded.
5. **Privacy.** Hardware reports get posted in public GitHub issues: never collect serial
   numbers, MAC/IP addresses, user names or computer names.
6. **Keep the UI responsive.** Anything that calls PowerShell, WMI or the registry runs in a
   worker thread (`ui/workers.py`), never directly in a button handler on the UI thread.
7. **No console windows.** Run commands through `core/winutil.run()` / `run_powershell()`,
   which hide the console. Don't use `subprocess` with `shell=True`.
8. **Ask before big changes.** Show Ryder a plan before restructuring the UI or adding
   dependencies. All changes go on a branch with a pull request; never push to `main`.

## Project layout

```
main.py                 entry point (splash, then MainWindow)
build.py                builds dist/RYTWEAKS.exe (PyInstaller --onefile --windowed --uac-admin)
core/version.py         __version__: the ONLY place the version number lives
core/winutil.py         run commands/PowerShell without a console window, is_admin()
core/hardware.py        static hardware scan (one PowerShell call) + parse_static()
core/gpu_dxgi.py        GPU list via DirectX: any vendor, correct 64-bit VRAM, LUIDs
core/telemetry.py       live data: Windows performance counters (GPU/CPU), NVML (NVIDIA), psutil
core/sensors_lhm.py     optional temps/fans from LibreHardwareMonitor's WMI namespace
core/optimizer.py       tweaks: each get_* reads real state, each set_* returns (ok, msg)
core/profiles.py        profiles = named lists of optimizer steps
core/startup_manager.py startup apps (with backups so they can be re-enabled)
core/storage_manager.py drives, file browsing, temp cleanup
core/report.py          hardware report export (no personal identifiers)
core/themes.py          color tokens + Qt stylesheet (all colors come from here)
ui/main_window.py       shell: sidebar NAV, page stack, workers, settings, log
ui/workers.py           QThreads: static scan, telemetry loop, one-off tasks
ui/widgets/             Card, Notice, KeyValueGrid, Page base class, Sparkline, MetricCard
ui/pages/               one file per page
tests/                  pytest tests for parsing logic (run on any OS)
```

To add a page: subclass `Page` in `ui/pages/`, then add it to `NAV` in `ui/main_window.py`.
Pages get data through hooks: `on_static(data)`, `on_telemetry(sample)`, `on_shown()`,
`on_theme(theme)`, and optional `on_sources(src)`.

## Where live data comes from (and why)

- GPU load and VRAM used: Windows "GPU Engine" / "GPU Adapter Memory" performance counters,
  the same ones Task Manager uses, so they work on every GPU brand. Counters are added with
  `AddEnglishCounter` so they work on non-English Windows.
- VRAM size: DXGI `DedicatedVideoMemory` (64-bit). Don't use WMI `AdapterRAM` (capped at 4 GB).
- CPU clock: `Processor Frequency × % Processor Performance`. Don't use `psutil.cpu_freq()` on
  Windows; it only returns the base clock.
- NVIDIA temperature, clocks, power, fan: NVML (`nvidia-ml-py`, imported as `pynvml`).
- CPU temperature, fans, motherboard sensors: Windows has no API for these without a kernel
  driver. RyTweaks doesn't ship a driver; it reads LibreHardwareMonitor's WMI namespace when the
  user runs it. Don't add a bundled driver without asking.

## Testing

- `python -m pytest tests` runs the parsing tests (any OS). Add a test with real sample
  output whenever a user reports wrong hardware data.
- The UI can't be fully tested off Windows. Before a release, Ryder runs `python main.py`
  on his PC and checks every page.

## Release process

1. Bump `__version__` in `core/version.py`.
2. Branch → pull request → Ryder reviews and merges.
3. Ryder builds on Windows: `python build.py` (makes `dist/RYTWEAKS.exe`).
4. Publish a GitHub release with tag `vX.Y`, release notes and `RYTWEAKS.exe` attached.
