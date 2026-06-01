# Desktop Activity Tracker

<p align="center">
  <b>Windows 桌面时间追踪 · 个人数字行为分析系统</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.2.0-blue" alt="version">
  <img src="https://img.shields.io/badge/python-3.10+-green" alt="python">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey" alt="platform">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="license">
</p>

---

## 功能

- **自动记录** — 后台静默运行，1 秒采样检测前台窗口进程名和标题
- **Session 聚合** — 连续使用同一窗口合并为 session，数据库写入减少 95%
- **智能分类** — 进程名 + 标题关键词自动归类（AI 工具 / 编程 / 阅读 / 视频 / 游戏等 9 类）
- **有效时长** — 学习类要求鼠键活跃才算有效时间，视频类允许被动观看
- **GUI 界面** — PySide6 桌面应用，7 个功能页面 + 系统托盘常驻
- **日报/周报/月报** — Markdown 导出，含效率评分和优化建议
- **Obsidian 集成** — 一键同步报告到 Obsidian vault
- **单文件 EXE** — PyInstaller 打包，无需安装 Python，双击即用

## 快速开始

### 直接使用 (Windows)

从 [Releases](https://github.com/zhaoxl12138/desktop-activity-tracker/releases) 下载 `desktop-activity-tracker.exe`，双击运行。托盘图标出现在右下角通知区域。

### 开发模式

```bash
git clone https://github.com/zhaoxl12138/desktop-activity-tracker.git
cd desktop-activity-tracker
pip install -e .

# 启动 GUI
python -m desktop_activity_tracker.main

# 命令行
python -m desktop_activity_tracker.main start     # 后台记录
python -m desktop_activity_tracker.main today     # 今日统计
python -m desktop_activity_tracker.main export    # 导出日报
python -m desktop_activity_tracker.main weekly    # 周报
python -m desktop_activity_tracker.main monthly   # 月报
```

### 托盘操作

| 操作 | 行为 |
|------|------|
| 左键点击 | 打开主界面 |
| 右键点击 | 弹出菜单（打开 / 暂停 / 退出） |
| 双击桌面图标 | 已在运行时提示"程序已在运行中" |

## 项目结构

```
desktop-activity-tracker/
├── src/desktop_activity_tracker/   # 核心源码
│   ├── main.py                     # CLI + GUI 入口
│   ├── __main__.py                 # python -m 支持
│   ├── session_tracker.py          # Session 状态机
│   ├── window_detector.py          # 前台窗口检测
│   ├── activity_detector.py        # 用户活跃检测 (idle)
│   ├── classifier.py               # 软件分类器
│   ├── database.py                 # SQLite 读写
│   ├── reporter.py                 # 统计查询
│   ├── exporter.py                 # Markdown/CSV 导出
│   ├── utils.py                    # 工具函数
│   └── gui/                        # PySide6 界面
│       ├── style.py                # 颜色 + 样式
│       ├── worker.py               # 后台录制 QThread
│       ├── main_window.py          # 主窗口
│       ├── tray_manager.py         # 系统托盘
│       └── pages/                  # 7 个页面
├── config/config.yaml              # 配置文件（首次运行自动生成）
├── assets/icon.ico                 # 应用图标
├── tests/                          # 测试
├── AI_READING_RULES.md             # AI 读取报告的规则说明
└── pyproject.toml                  # 工程配置
```

运行时生成的文件（不纳入 Git）：
- `usage.db` — SQLite 数据库
- `reports/` — 导出的日报/周报/月报
- `desktop-activity-tracker.exe` — PyInstaller 构建产物

## 隐私

- 所有数据存储在本地 SQLite (`usage.db`)，不上传任何服务器
- 仅检测前台窗口的进程名和标题，**不记录键盘输入内容**
- 无需网络连接

## License

MIT © [zhaoxl12138](https://github.com/zhaoxl12138)
