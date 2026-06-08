$exe = "D:\OfficeSoftware\DayLens\release\DayLens.exe"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("C:\Users\Administrator\Desktop\DayLens.lnk")
$sc.TargetPath = $exe
$sc.WorkingDirectory = "D:\OfficeSoftware\DayLens\release"
$sc.IconLocation = "$exe,0"
$sc.Save()
Write-Output "Shortcut updated"
