# DayLens — 个人数字行为分析系统

> Focus · Analyze · Improve — 看清你的时间流向

DayLens 是一款 Windows 桌面时间追踪工具，通过 1 秒级精度采集前台窗口与用户空闲状态，自动归类使用行为，生成可视化日报/周报/月报。

## 功能特性

- **实时监控** — 1 秒采样频率，精确追踪前台窗口切换与空闲时长
- **智能分类** — 基于进程名 + 窗口标题关键字，自动归类到 AI 工具 / 编程开发 / 阅读学习 / 社交通讯 / 视频娱乐 / 游戏 / 创作工具 / 系统工具 等类别
- **音频检测** — 针对视频/游戏等 "被动可接受" 类别，通过 Windows Core Audio API 检测进程是否在播放音频，避免将暂停/静音的娱乐窗口计为有效时间
- **幻影输入过滤** — 自动识别某些驱动/服务产生的虚假 HID 事件；检测期间冻结空闲计数器，避免误判消耗有效时间
- **会话聚合** — 连续使用同一窗口 (间隔 ≤60s) 自动合并为会话，跨日自动切分
- **时间线聚合** — 今日时间线自动合并相邻同窗口同分类记录，避免碎片化显示
- **专注检测** — 自动识别 >=45 分钟无娱乐中断的连续工作时段
- **深色/浅色主题** — 一键切换，配置持久化不损坏

## 界面一览

| 页面 | 功能 |
|------|------|
| **今日概览** | 5 指标卡片 + 环形时间分布 + 专注时间轴条 + 今日时间线 + 小时趋势图 + Top 5 应用 |
| **实时监控** | 当前窗口信息 (进程/标题/分类/活跃状态) + 最近 50 条记录表 |
| **软件统计** | 按软件维度统计有效时长与占比，支持 CSV/Markdown 导出 |
| **分类统计** | 按类别维度展示时长分布 (进度条 + 百分比) |
| **日报/周报** | 生成 Markdown 日报 (含时间线表格)，可选同步到 Obsidian vault |
| **目标管理** | 管理分类规则: 新增/编辑/删除进程名、标题关键字、计时策略 |
| **设置中心** | 采样间隔、空闲阈值、数据库/报告/Obsidian 路径配置 |

## 系统托盘

- 关闭窗口 -> 最小化到托盘 (不退出)
- 右键菜单: 打开主界面 / 暂停记录 / 生成日报 / 设置 / 退出
- 悬停提示: 今日使用摘要

## 架构

```
src/daylens/
├── main.py                 # QApplication 入口 + CLI 命令
├── __init__.py             # get_app_root() (frozen → sys._MEIPASS)
├── __main__.py             # python -m daylens
├── window_detector.py      # Win32 API 获取前台窗口
├── activity_detector.py    # GetLastInputInfo() 空闲检测
├── audio_detector.py       # IAudioSessionControl2 音频播放检测
├── classifier.py           # 按 process + title 规则分类
├── session_tracker.py      # 会话状态机 (idle/effective 追踪)
├── timeline.py             # 30 分钟块 + 专注块 + 碎片化
├── database.py             # SQLite CRUD (WAL 模式)
├── exporter.py             # Markdown/CSV 日报/周报/月报导出
├── reporter.py             # 控制台文本报告
├── utils.py                # 配置生成、时间格式化
├── gui/
│   ├── main_window.py      # 主窗口 (侧边栏导航 + QStackedWidget)
│   ├── worker.py           # 后台录制线程 (QThread)
│   ├── tray_manager.py     # 系统托盘管理
│   ├── style.py            # 颜色常量 + 主题切换
│   ├── pages/
│   │   ├── today_overview.py   # 今日概览
│   │   ├── live_monitor.py     # 实时监控
│   │   ├── software_stats.py   # 软件统计
│   │   ├── category_stats.py   # 分类统计
│   │   ├── reports.py          # 日报/周报
│   │   ├── rule_config.py      # 目标管理
│   │   └── settings.py         # 设置中心
│   └── widgets/
│       └── dashboard_widgets.py  # 自定义控件 (环形图/时间线/趋势图/FocusBar)
├── assets/
│   ├── icon.ico            # 程序图标
│   └── icons/              # 应用图标缓存 (PNG)
└── tools/
    └── extract_icons.py    # 图标提取工具
```

## 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python 3.11+ |
| GUI | PySide6 (Qt 6) |
| 数据库 | SQLite 3 (WAL mode) |
| 窗口检测 | Win32 API (GetWindowText, GetWindowThreadProcessId) |
| 空闲检测 | Win32 API (GetLastInputInfo) |
| 音频检测 | Windows Core Audio API (pycaw + comtypes) |
| 打包 | PyInstaller onedir (单目录应用, 避免单文件父子双进程) |

## 快速开始

```bash
# 安装依赖
pip install PySide6 pyyaml pycaw comtypes

# 启动 GUI
python -m daylens

# 命令行模式
python -m daylens start       # 后台记录
python -m daylens today       # 今日统计
python -m daylens report --date 2026-06-02
python -m daylens export --format md
python -m daylens weekly
python -m daylens monthly
```

## 配置文件

`config/config.yaml` — 首次运行自动生成:

```yaml
categories:
  coding:
    display_name: 编程开发
    active_rule: interactive_required   # interactive_required | passive_allowed
    match:
      process_names: [Code.exe, Cursor.exe]
      title_keywords: [VS Code, GitHub]

tracker:
  sample_interval_seconds: 1
  idle_threshold_seconds: 60
  flush_interval_seconds: 10
  min_session_seconds: 3
  audio_detection_enabled: true
  audio_check_interval_seconds: 3

db_path: D:\OfficeSoftware\DayLens\data\usage.db   # 必须使用绝对路径
reports_dir: reports
obsidian_output_path: ""               # 可选: Obsidian vault 路径

display_name_mapping:                  # 软件别名映射
  Code.exe: VS Code
  Cursor.exe: Cursor
  DayLens.exe: DayLens
```

## 打包

```bash
pip install pyinstaller
python -m PyInstaller -y DayLens.spec
# 输出: dist/DayLens/DayLens.exe + _internal/ (onedir 模式)
# 部署: cp -r dist/DayLens release/
```

## 版本历史

| 版本 | 日期 | 更新 |
|------|------|------|
| v1.5.2 | 2026-06-02 | **关键修复**: get_app_root() 简化 (修复 frozen 模式路径解析 → 彻底解决数据库丢失)；软件识别优化 (Claude Code/爱奇艺/WindowsTerminal wrapper)；图标系统修复 + DayLens 图标深色主题可辨识；时间分布卡片 UI 重设计 (加粗环形图 + 进度条图例) |
| v1.5.1 | 2026-06-02 | **关键修复**: 空闲检测重写 (连续使用误判为挂机的 P0 bug)；时间线 Session 聚合；趋势图 float 精度 + 24 小时固定点；X 轴标签 QPainter 渲染；窗口几何自适应 |
| v1.5.0 | 2026-06-02 | 项目重命名 DayLens；时间线秒级显示；重复会话去重 + UNIQUE 索引防护；INSERT OR REPLACE；config 持久化修复 |
| v1.4.0 | 2026-05 | 音频检测 (娱乐空转过滤)；幻影 HID 过滤；会话状态机重构 |
| v1.3.0 | 2026-05 | PySide6 GUI；系统托盘；7 功能页面；深色/浅色主题 |
| v1.2.0 | 2026-05 | CLI 完善；日报/周报/月报导出；Obsidian 同步 |
| v1.0.0 | 2026-05 | 初版: 窗口检测 + 空闲检测 + 分类 + SQLite |

## License

MIT
