$exe = "D:\OfficeSoftware\DayLens\release\DayLens.exe"
$ws = New-Object -ComObject WScript.Shell

# Desktop shortcut
$desktop = $ws.CreateShortcut("C:\Users\Administrator\Desktop\DayLens.lnk")
$desktop.TargetPath = $exe
$desktop.WorkingDirectory = "D:\OfficeSoftware\DayLens\release"
$desktop.IconLocation = "$exe,0"
$desktop.Save()

# Startup folder shortcut (auto-start on boot)
$startup = $ws.CreateShortcut("C:\Users\Administrator\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\DayLens.lnk")
$startup.TargetPath = $exe
$startup.WorkingDirectory = "D:\OfficeSoftware\DayLens\release"
$startup.IconLocation = "$exe,0"
$startup.Save()

Write-Output "Shortcuts updated (desktop + startup)"
