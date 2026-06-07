---
name: daylens-rebuild
description: Kill DayLens, rebuild with PyInstaller, deploy to release/, update shortcut, launch
---

# DayLens Rebuild & Deploy

## Iron Rule

**必须先停止 DayLens.exe 再清理目录。** 如果目录删除失败（Device or resource busy），再等 2 秒重试。不要换输出目录名 —— 始终输出到 `release/`。

## Step-by-step

```bash
# 1. Kill
taskkill /f /im DayLens.exe 2>/dev/null; sleep 2

# 2. Clean (retry if busy)
rm -rf D:/OfficeSoftware/DayLens/release D:/OfficeSoftware/DayLens/build 2>/dev/null
# If still busy: sleep 2 && retry rm -rf release build

# 3. Build (if release/ is locked, build to _tmp then move)
cd D:/OfficeSoftware/DayLens && python -m PyInstaller --noconfirm --clean --distpath release DayLens.spec
# If COLLECT fails with PermissionError, fallback:
#   python -m PyInstaller --noconfirm --clean --distpath _tmp DayLens.spec
#   mkdir -p release/DayLens && cp -r _tmp/DayLens/* release/DayLens/ && rm -rf _tmp

# 4. Copy config
cp D:/OfficeSoftware/DayLens/config/config.yaml "D:/OfficeSoftware/DayLens/release/DayLens/config.yaml"

# 5. Update shortcut (fixed path, never changes)
powershell -ExecutionPolicy Bypass -File "D:/OfficeSoftware/DayLens/tools/fix_shortcut.ps1"

# 6. Launch
start "" "D:\OfficeSoftware\DayLens\release\DayLens\DayLens.exe"
```

## Notes

- 输出路径固定为 `D:\OfficeSoftware\DayLens\release\DayLens\DayLens.exe`
- 桌面快捷方式始终指向上述路径
- `config.yaml` 源文件在 `config/config.yaml`
- 快捷方式脚本: `tools/fix_shortcut.ps1`
