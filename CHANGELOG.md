# Changelog

所有值得注意的变更将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## v0.8.0 - 2026-06-01

### Added

- `gui/worker.py` — QThread 后台录制线程，带暂停/恢复
- `gui/tray_manager.py` — 系统托盘图标 + 右键菜单 + Tooltip 摘要
- `gui/main_window.py` — 主窗口框架（侧边栏导航 + 7 页 QStackedWidget）
- `gui/pages/today_overview.py` — 今日概览（4 数据卡片 + 效率评分 + 建议）
- `gui/pages/live_monitor.py` — 实时监控（当前窗口信息 + 最近 20 条记录）
- `gui/pages/software_stats.py` — 软件统计（表格 + CSV/MD 导出按钮）
- `gui/pages/category_stats.py` — 分类统计（彩色进度条可视化）
- `gui/pages/reports.py` — 报告管理（日报/周报/月报 tab + Obsidian 同步）
- `gui/pages/rule_config.py` — 规则配置（分类列表 + 编辑器 + 写入 config.yaml）
- `gui/pages/settings.py` — 设置页（基础参数 + 路径 + 数据管理）
- `main.py` 支持 `gui` 命令，无参数默认启动 GUI
- 托盘关闭窗口 → 最小化不退出；托盘退出 → 完整关闭

## v0.6.0 - 2026-06-01

### Added

- 移植核心 tracker 模块到 `src/desktop_activity_tracker/`
- `window_detector.py` — GetForegroundWindow + 窗口标题 + 进程名检测
- `activity_detector.py` — GetLastInputInfo 用户空闲检测
- `classifier.py` — 三级匹配（进程+标题 / 浏览器标题优先 / 进程匹配）+ 双规则
- `database.py` — SQLite WAL 模式 + activity_logs 表 + 统计查询
- `reporter.py` — 终端格式统计输出
- `exporter.py` — Markdown 日报（含效率评分、优化建议）+ CSV 导出 + Obsidian 同步
- `main.py` — CLI 入口 (start / today / report / export)
- 修复 `get_app_root()` 适配 `src/` 三层目录结构

## v0.1.0 - 2026-06-01

### Added

- 初始化项目结构
- 添加基础文档（README, PRD, ARCHITECTURE, DATABASE, UI, ROADMAP）
- 添加 `.gitignore` 和 `requirements.txt`
- 添加 MIT License
- 添加 `config/config.example.yaml` 示例配置
