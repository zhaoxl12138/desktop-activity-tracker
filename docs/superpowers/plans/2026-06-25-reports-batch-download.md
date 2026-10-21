# Reports Batch Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为报告中心增加多选与批量下载到目录功能。

**Architecture:** 表格切换为扩展多选，页面维护 `selected_reports` 列表并根据数量调整详情和按钮。服务层负责复制、重名避让和逐文件结果汇总。

**Tech Stack:** Python 3.14、PySide6、pytest、shutil

---

### Task 1: 批量复制服务

**Files:**
- Modify: `src/daylens/services/reports_service.py`
- Modify: `tests/test_reports_service.py`

- [ ] 写失败测试：多个源文件复制到目标目录，同名自动追加序号，缺失文件记录失败。
- [ ] 运行 `python -m pytest tests/test_reports_service.py -q` 确认失败。
- [ ] 实现 `download_reports(source_paths, destination_dir)`。
- [ ] 运行服务层测试确认通过。

### Task 2: 多选状态与详情

**Files:**
- Modify: `src/daylens/gui/pages/reports.py`
- Modify: `tests/test_reports_page.py`

- [ ] 写失败测试：表格支持扩展多选，选择两行后显示数量并禁用打开和同步。
- [ ] 运行页面测试确认失败。
- [ ] 实现 `selected_reports`、多选详情和动态按钮文案。
- [ ] 运行页面测试确认通过。

### Task 3: 批量下载交互

**Files:**
- Modify: `src/daylens/gui/pages/reports.py`
- Modify: `tests/test_reports_page.py`

- [ ] 写失败测试：多选时调用目录选择器和 `download_reports()`。
- [ ] 运行测试确认失败。
- [ ] 实现批量下载结果提示，保留单选另存为流程。
- [ ] 运行相关测试和 GUI 冒烟测试。

### Task 4: 发布验证

- [ ] 结束旧发布进程并运行 `python tools/build_release.py`。
- [ ] 启动新版，确认单选与多选操作状态。
