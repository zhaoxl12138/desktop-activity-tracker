param(
    [string]$InstallDir = (Join-Path $PSScriptRoot "..\release")
)

$exe = Join-Path (Resolve-Path $InstallDir) "DayLens.exe"
$ws = New-Object -ComObject WScript.Shell

# Desktop shortcut
$desktop = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "DayLens.lnk"))
$desktop.TargetPath = $exe
$desktop.WorkingDirectory = Split-Path $exe
$desktop.IconLocation = "$exe,0"
$desktop.Save()

# Startup folder shortcut (auto-start on boot)
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$startup = $ws.CreateShortcut((Join-Path $startupDir "DayLens.lnk"))
$startup.TargetPath = $exe
$startup.WorkingDirectory = Split-Path $exe
$startup.IconLocation = "$exe,0"
$startup.Save()

Write-Output "Shortcuts updated (desktop + startup)"
