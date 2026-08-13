# 通用视频状态检测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 扫描视频前台进程及其子进程的音频峰值，恢复跨播放器的连续播放计时。

**Architecture:** 在现有 `AudioDetector` 内增加安全的递归进程树 PID 收集；按目标树、全局兜底、异常保守播放的顺序查询，不改变 `SessionTracker` 的视频/空闲口径。

**Tech Stack:** Python 3.11, psutil, pycaw/Core Audio, pytest, PyInstaller。

---

### Task 1: 进程树音频检测

**Files:**
- Modify: `src/daylens/audio_detector.py`
- Test: `tests/test_audio_detector.py`

- [ ] 写失败测试覆盖目标主进程静音但递归子进程有峰值、目标无会话但子进程有峰值，以及进程树查询异常仍走全局兜底。
- [ ] 实现 `_process_tree_pids` 与按 PID 集合匹配音频会话。
- [ ] 运行定向音频测试并确认通过。

### Task 2: 回归与发布验证

**Files:**
- No production files beyond Task 1.

- [ ] 运行音频、tracker 策略和 GUI smoke 测试。
- [ ] 运行全量测试、compileall、git diff --check。
- [ ] 构建 `release/DayLens.exe`，确认唯一进程、唯一数据库路径。
- [ ] 启动发布版，等待用户播放视频进行人工验证。
