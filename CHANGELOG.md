# Changelog

所有值得注意的变更将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

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

## v0.1.0 - 2026-06-01

### Added

- 初始化项目结构
- 添加基础文档（README, PRD, ARCHITECTURE, DATABASE, UI, ROADMAP）
- 添加 `.gitignore` 和 `requirements.txt`
- 添加 MIT License
- 添加 `config/config.example.yaml` 示例配置
