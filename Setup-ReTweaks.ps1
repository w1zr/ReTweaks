param([switch]$Build)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = $null
foreach ($candidate in @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'), (Join-Path $env:ProgramFiles 'Python313\python.exe'))) {
    if (Test-Path -LiteralPath $candidate) { $python = $candidate; break }
}
if (-not $python) {
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) { & $command.Source -c 'import sys; assert sys.version_info >= (3, 10)' 2>$null; if ($LASTEXITCODE -eq 0) { $python=$command.Source } }
}
if (-not $python) {
    $winget=Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { throw 'Install Microsoft App Installer from Microsoft Store, then rerun setup so it can install Python.' }
    & $winget.Source install --id Python.Python.3.13 --exact --source winget --silent --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
    foreach ($candidate in @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'), (Join-Path $env:ProgramFiles 'Python313\python.exe'))) {
        if (Test-Path -LiteralPath $candidate) { $python=$candidate; break }
    }
    if (-not $python) { throw 'Python installed but its executable was not found. Open a new terminal and rerun setup.' }
}
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
if ($Build) { & $python build.py; if ($LASTEXITCODE -ne 0) { throw 'Build failed.' } }
else { Write-Output 'Source dependencies installed. Run Setup-ReTweaks.ps1 -Build to compile the required helpers and package the app.' }
