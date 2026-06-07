$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("C:\Users\Administrator\Desktop\DayLens.lnk")
$sc.TargetPath = "D:\OfficeSoftware\DayLens\release\DayLens\DayLens.exe"
$sc.WorkingDirectory = "D:\OfficeSoftware\DayLens\release\DayLens"
$sc.Save()
Write-Output "Shortcut updated"
