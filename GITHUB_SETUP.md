# GitHub Setup - ReTweaks

Use this folder as the repository root: `.github`, `ai`, `assets`, `core`, `rt_pages`, `retweaks.py`, `build.py` and `RETWEAKS.spec` belong directly at the root. It contains only the current source snapshot, with no old build folders or previous release-note files.

## Upload

Copy this folder's contents into your existing Git checkout, review the changes and commit/push them. Include the hidden `.github` folder and `.gitignore`. Existing repository files not present in this snapshot need to be reviewed for removal separately; copying files does not remove old files already tracked on GitHub. Nothing has been published by preparing this folder.

Generated application EXEs belong in GitHub Releases, not the source tree. The newest local EXE is `dist/RETWEAKS.exe` in this folder. It and compiled AI helpers are intentionally ignored by Git. Your two existing keys are preserved in the **ignored local** `ai/gemini_key.txt` file. Push this folder with Git so that file stays local; never drag/upload it through the GitHub browser.

## AI Build Secret

In the GitHub repository, set **Settings > Secrets and variables > Actions > New repository secret** named `GEMINI_API_KEY`. If the existing repository already has it, keep it. To retain both configured keys on GitHub, store both lines from your private local key file in this one repository secret. The Windows workflow passes that secret as `RETWEAKS_GEMINI_KEY` to the build without putting it in source. Local builds may use that environment variable or the ignored `ai/gemini_key.txt`; never upload the key file or a generated `GeminiChat.build.cs`.

A build without a configured shared key cannot provide AI responses. There is no user-key setup screen. Release builds check for the secret before building.

## Build and Check

On Windows with Python 3.13 and the .NET Framework C# compiler:

```powershell
python -m pip install -r requirements.txt
python -m pytest tests -q
python build.py
```

`build.py` compiles the app's C# helpers and writes `dist/RETWEAKS.exe`. Bundled WebView2 SDK files, OpenRGB and LibreHardwareMonitor are included with their licenses and source notices. Microsoft WebView2 Runtime is still needed on the user's PC. Build output is ignored by Git.

The GitHub workflow can create a preview build without publishing. Release publishing requires an explicit tag/manual release request. Release notes should be maintained separately for each release.

## Automatic Setup

Run the following command in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-ReTweaks.ps1 -Build
```

This installs Python if needed through WinGet, installs requirements and builds all required helpers. The app automatically installs missing feature runtimes on demand. App Installer/WinGet itself must be available to install Python and optional Lively. Installer failures are shown, and restart requests are preserved. No runtime dependency installer is executed merely by running the test suite.
