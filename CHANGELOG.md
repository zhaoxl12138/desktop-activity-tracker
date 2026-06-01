# Changelog

所有值得注意的变更将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## v0.9.0 - 2026-06-01

### Added

- `database.query_date_range_stats()` — 多日聚合统计查询（按日+按分类+按软件）
- `exporter.export_weekly_report()` — ISO 周报 Markdown 生成
- `exporter.export_monthly_report()` — 月报 Markdown 生成
- `exporter._sparkline()` — Unicode 文字趋势图
- `exporter._week_dates()` / `_month_dates()` — 日期范围工具
- Reports 页面新增"本周周报"和"本月月报"按钮
- CLI `weekly` 和 `monthly` 命令（支持 `--year`/`--week`/`--month`）
- 周报包含：每日趋势表 + Sparkline 图 + 周效率评分 + 建议
- 月报包含：每周趋势汇总 + 分类占比 + 日均分析

### Changed

- Reports 页面 UI 重构：生成按钮组合为工具栏，三种报告一键生成

## v0.8.1 - 2026-06-01

### Changed

- 提取 `utils.py` 共享模块：`fmt_seconds()`、`generate_default_config()`
- 消除 `exporter.py` 和 `reporter.py` 中 `_fmt_seconds` 重复定义
- `main.py` 移除 126 行硬编码默认配置，改用 `utils.generate_default_config()`
- GUI 模块统一从 `..utils` 导入 `fmt_seconds`

### Added

- `pyproject.toml` — 支持 `pip install -e .` 和 `desktop-activity-tracker` 命令行入口
- `__main__.py` — 支持 `python -m desktop_activity_tracker`
- `assets/` 目录 — 托盘图标资源路径

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
