# Desktop Activity Tracker

<p align="center">
  <b>Windows 桌面软件使用时长记录器 / 个人数字行为分析系统</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.9.0-blue" alt="version">
  <img src="https://img.shields.io/badge/python-3.10+-green" alt="python">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey" alt="platform">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="license">
</p>

---

## 项目介绍

Desktop Activity Tracker 是一款 Windows 桌面时间追踪工具，通过监控前台窗口自动记录软件使用时长，对不同类型的软件应用差异化的有效时间计算规则，最终生成可视化的日报/周报/月报。

### 功能目标

- **自动记录**：后台静默运行，实时检测当前活动窗口的进程名和标题
- **智能分类**：基于进程名 + 窗口标题关键词，将软件自动归类（AI工具、编程开发、阅读学习、视频娱乐等）
- **有效时长**：区分主动使用和挂机，对学习/工作类软件要求鼠标键盘活跃才算有效时间，视频类允许被动观看
- **数据存储**：SQLite 本地存储，数据完全由用户掌控
- **日报生成**：每日生成 Markdown 日报，包含效率评分和优化建议
- **Obsidian 集成**：支持一键同步日报到 Obsidian 知识库
- **系统托盘**：最小化到系统托盘后台运行，不干扰正常使用
- **GUI 界面**：PySide6 桌面界面，可视化查看今日概览、实时监控、软件/分类统计
- **独立 EXE**：PyInstaller 打包为单文件 `.exe`，无需安装 Python 环境

### 核心设计

对**学习/工作类**软件要求 60 秒内有鼠标/键盘活动才计入有效时间；对**视频娱乐类**允许被动观看（无操作也计时）。有效时间占比构成每日"效率评分"，引导用户反思时间分配。

## 技术栈

| 层面 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| GUI | PySide6 (Qt for Python) |
| 窗口检测 | Windows API (pywin32) |
| 活跃检测 | GetLastInputInfo (ctypes) |
| 数据存储 | SQLite |
| 配置 | YAML |
| 打包 | PyInstaller |

## 当前开发状态

> **v0.9.0** — 周报/月报已完成，支持趋势分析和 Sparkline 可视化。

详见 [ROADMAP.md](docs/ROADMAP.md) 和 [CHANGELOG.md](CHANGELOG.md)。

## 快速开始

```bash
# 克隆项目
git clone https://github.com/zhaoxl12138/desktop-activity-tracker.git
cd desktop-activity-tracker

# 安装（开发模式）
pip install -e .

# 启动 GUI
python -m desktop_activity_tracker

# 或使用 CLI
python -m desktop_activity_tracker start   # 命令行记录
python -m desktop_activity_tracker today   # 今日统计
python -m desktop_activity_tracker report  # 统计报告
python -m desktop_activity_tracker export  # 导出日报
```

> Windows 打包版本 (`.exe`) 将在 v1.0 发布，请关注 [Releases](https://github.com/zhaoxl12138/desktop-activity-tracker/releases)。

## 项目结构

```
desktop-activity-tracker/
├── src/desktop_activity_tracker/   # 核心源码
│   ├── main.py                     # CLI + GUI 入口
│   ├── __main__.py                 # python -m 支持
│   ├── utils.py                    # 共享工具函数
│   ├── window_detector.py          # 前台窗口检测
│   ├── activity_detector.py        # 用户活跃检测
│   ├── classifier.py               # 软件分类器
│   ├── database.py                 # SQLite 操作
│   ├── reporter.py                 # 统计报告
│   ├── exporter.py                 # Markdown/CSV 导出
│   └── gui/                        # PySide6 GUI
│       ├── style.py                # 颜色 + 样式
│       ├── worker.py               # 后台录制线程
│       ├── main_window.py          # 主窗口
│       ├── tray_manager.py         # 系统托盘
│       └── pages/                  # 7 个功能页面
├── config/                         # 配置文件
├── docs/                           # 文档
├── assets/                         # 图标资源
├── reports/                        # 生成的日报
├── data/                           # 数据库文件
├── logs/                           # 运行日志
├── tests/                          # 测试
└── pyproject.toml                  # 工程配置
```

## 隐私说明

- **所有数据存储在本地**，不会上传到任何服务器
- 数据库文件位于 `data/usage.db`，用户可随时查看和删除
- 程序仅检测前台窗口的进程名和标题，不记录键盘输入内容
- 无需网络连接即可运行

## License

MIT © [zhaoxl12138](https://github.com/zhaoxl12138)
