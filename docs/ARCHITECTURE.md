# 架构设计

## 总体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Windows API                          │
│         (GetForegroundWindow, GetLastInputInfo)         │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │   Window Detector    │  进程名 / 窗口标题 / 路径
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Activity Detector   │  空闲秒数 / 用户是否活跃
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │    Classifier        │  分类 key / 计时规则
              │  (YAML 配置驱动)      │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │   SQLite Database    │  activity_logs 表
              └──────────┬───────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ┌───────────┐  ┌───────────┐  ┌───────────┐
   │ Reporter  │  │ Exporter  │  │   GUI     │
   │ 统计查询   │  │ MD / CSV  │  │ 可视化     │
   └───────────┘  └─────┬─────┘  └───────────┘
                        │
                        ▼
              ┌──────────────────────┐
              │  Obsidian Vault      │  (可选)
              └──────────────────────┘
```

## 数据流

```
每 5 秒循环:
  1. get_idle_seconds()           → 用户空闲秒数
  2. get_foreground_window_info() → {进程名, 标题, 路径}
  3. classify(进程名, 标题)        → {分类key, 名称, 计时规则}
  4. is_effective(规则, 空闲秒数)   → True/False
  5. INSERT INTO activity_logs    → 写入采样记录
  6. emit sample_updated(sample)  → GUI 刷新 (异步)
```

## 模块职责

| 模块 | 职责 | 依赖 |
|------|------|------|
| `window_detector` | 获取前台窗口信息 | pywin32 |
| `activity_detector` | 获取用户空闲秒数 | ctypes |
| `classifier` | 软件分类 + 有效判定 | YAML 配置 |
| `database` | SQLite CRUD + 统计查询 | sqlite3 |
| `reporter` | 终端格式统计输出 | database |
| `exporter` | Markdown/CSV 导出 | database |
| `gui/worker` | 后台录制线程 (QThread) | 以上全部 |
| `gui/main_window` | 主窗口 | PySide6 |
| `gui/tray_manager` | 系统托盘 | PySide6 |
| `gui/pages/*` | 7 个功能页面 | database, exporter |

## 配置驱动

所有分类规则存储在 `config/config.yaml`，结构如下：

```yaml
categories:
  coding:
    display_name: "编程开发"
    active_rule: "interactive_required"
    match:
      process_names: ["Code.exe", "WindowsTerminal.exe"]
      title_keywords: ["VS Code", "GitHub"]
```

用户可通过 GUI 规则配置页编辑，无需修改代码。

## 打包部署

```
main.py
  → PyInstaller --onefile -w
    → LifeOSTracker.exe (单文件, ~50MB)
      ├── Python 3.14 运行时
      ├── PySide6 + Qt 库
      ├── pywin32 / psutil
      └── tracker + gui 源码
```
