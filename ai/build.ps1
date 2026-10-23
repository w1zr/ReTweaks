# -Source: build.py passes a temporary copy of GeminiChat.cs with the built-in key filled in (never committed).
param([string]$Source = "$PSScriptRoot\GeminiChat.cs")
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler /nologo /target:winexe /out:"$PSScriptRoot\GeminiChat.exe" /reference:System.Security.dll /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Net.Http.dll /reference:System.Web.Extensions.dll "$Source"
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed' }
