# Reports Center Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将报告页面重构为可选择、查看详情、打开、下载和同步的报告中心。

**Architecture:** 服务层返回包含完整文件路径的结构化报告数据，并提供安全复制函数。GUI 维护单一 `selected_report` 状态，所有操作都从该状态读取路径，切换标签或刷新后重新校验选择。

**Tech Stack:** Python 3.14、PySide6、pytest、pathlib/shutil

---

### Task 1: 报告文件数据模型与下载

**Files:**
- Modify: `src/daylens/services/reports_service.py`
- Create: `tests/test_reports_service.py`

- [ ] **Step 1: 写入失败测试**

验证列表结果包含 `file_path`、`modified_text` 和 `report_type`，并验证 `download_report()` 将 Markdown 文件复制到目标路径。

- [ ] **Step 2: 运行服务层测试确认失败**

Run: `python -m pytest tests/test_reports_service.py -q`

Expected: FAIL，原因是结构化字段和 `download_report()` 尚不存在。

- [ ] **Step 3: 实现最小服务层功能**

新增结构化字典返回值、文件存在性校验和基于 `shutil.copy2()` 的下载复制。

- [ ] **Step 4: 运行服务层测试确认通过**

Run: `python -m pytest tests/test_reports_service.py -q`

Expected: PASS。

### Task 2: 报告页面选择与详情状态

**Files:**
- Modify: `src/daylens/gui/pages/reports.py`
- Create: `tests/test_reports_page.py`

- [ ] **Step 1: 写入失败测试**

验证初始按钮禁用、选择行后详情更新、切换标签后清空选择。

- [ ] **Step 2: 运行页面测试确认失败**

Run: `python -m pytest tests/test_reports_page.py -q`

Expected: FAIL，原因是详情面板和选中状态尚不存在。

- [ ] **Step 3: 重构页面布局**

实现左侧表格和右侧详情面板，保存 `selected_report`，将完整报告对象存入表格项 `Qt.UserRole`。

- [ ] **Step 4: 运行页面测试确认通过**

Run: `python -m pytest tests/test_reports_page.py -q`

Expected: PASS。

### Task 3: 下载、打开和同步交互

**Files:**
- Modify: `src/daylens/gui/pages/reports.py`
- Modify: `tests/test_reports_page.py`

- [ ] **Step 1: 写入失败测试**

验证下载调用当前选中文件，双击打开当前选中文件，同步操作不再固定使用今日日报。

- [ ] **Step 2: 运行交互测试确认失败**

Run: `python -m pytest tests/test_reports_page.py -q`

Expected: FAIL，原因是操作尚未绑定选中报告。

- [ ] **Step 3: 实现操作**

使用 `QFileDialog.getSaveFileName()` 选择下载路径，调用服务层复制；使用系统默认程序打开；同步当前选中报告。

- [ ] **Step 4: 运行全部相关测试**

Run: `python -m pytest tests/test_reports_service.py tests/test_reports_page.py tests/test_main_architecture.py -q`

Expected: PASS。

### Task 4: 发布验证

**Files:**
- Verify: `src/daylens/gui/pages/reports.py`
- Verify: `release/DayLens.exe`

- [ ] **Step 1: 运行 GUI 冒烟测试**

Run: `python tests/test_gui_smoke.py`

Expected: `GUI smoke test passed`。

- [ ] **Step 2: 重新构建发布版**

先结束当前 `release/DayLens.exe`，再运行 `python tools/build_release.py`。

- [ ] **Step 3: 启动并检查报告页面**

确认页面选中反馈清晰，未选择时按钮禁用，选择后下载按钮可用。
