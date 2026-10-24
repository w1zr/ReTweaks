# Current snapshot: ReTweaks 2.0.4

- Current source, assets, tests, build workflow and bundled third-party tools/licenses are included.
- The newest executable is `dist/RETWEAKS.exe`. It is a local build/release artifact and is ignored by Git.
- Two configured AI keys are preserved in ignored `ai/gemini_key.txt`. Push with Git; never upload this private file through a browser. GitHub Actions uses the private repository secret `GEMINI_API_KEY` (both keys, one per line).
- Current release notes are in `release-notes/v2.0.4.md`. Older build/output folders and logs are excluded.
- Build setup: `powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-ReTweaks.ps1 -Build`.
- Missing WebView2, PawnIO and PresentMon are set up when their features open. Lively is set up when animated wallpaper actions need it. Existing installations are retained; Settings can disable automatic setup. Windows can require elevation or a restart. Network/install errors are reported.

Validation: all 422 tests and all-page UI checks passed. Automatic installer error, checksum, restart and duplicate-request handling were tested with mocked installers; the tests did not install third-party programs on this computer. The source rebuilt its C# helpers with both configured keys and produced the current single-file EXE. Git ignore/secret/file-size audit passed.

See GITHUB_SETUP.md before uploading. The 2.0.4 release is prepared for w1zr/ReTweaks.
