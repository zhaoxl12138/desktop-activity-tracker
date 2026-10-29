# DayLens Stability and Layout Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复代码审查确认的逻辑、兼容性和高 DPI 布局问题，并完成偏爱应用名称清理。

**Architecture:** 保持现有数据模型和计时逻辑不变，在各自边界做最小修复：展示名称在指标构建层清理；后台结果携带请求上下文；报告指纹读取显式分类语义；主窗口尺寸由屏幕可用逻辑尺寸约束。更新隔离布局工具以覆盖现行顶栏。

**Tech Stack:** Python 3.10+、PySide6、SQLite、pytest、PyInstaller。

---

### Task 1: 偏爱应用展示名称

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Test: `tests/test_history_cards_presentation.py`

- [ ] 写入 `display_name` 带 `.exe` 的失败测试，并确认当前输出仍带后缀。
- [ ] 在 `_favorite_app` 最终候选名称上统一调用 `_strip_executable_suffix`。
- [ ] 运行 `python -m pytest -q tests/test_history_cards_presentation.py`。

### Task 2: 设置页数据修复回退路径

**Files:**
- Modify: `src/daylens/gui/pages/settings.py`
- Test: `tests/test_settings_page.py`

- [ ] 构造无后台队列的数据修复测试，确认未定义 `db_path` 失败。
- [ ] 将闭包中的数据库路径改为 `self.db_path`。
- [ ] 运行设置页定向测试。

### Task 3: 智能复盘请求上下文与证据指纹

**Files:**
- Modify: `src/daylens/gui/widgets/intelligence_review_bar.py`
- Modify: `src/daylens/services/report_evidence_service.py`
- Modify: `src/daylens/exporter.py`
- Test: `tests/test_intelligence_review_bar.py`
- Test: `tests/test_report_evidence_fingerprint.py`

- [ ] 写测试证明切换下拉框后，返回结果仍更新原请求周期。
- [ ] 队列消息携带 `kind`，按周期维护 stale 状态。
- [ ] 写测试证明显式 `classification_policy_version/source` 变化会改变指纹。
- [ ] 指纹查询使用显式字段，并对旧库列缺失兼容降级。
- [ ] 写测试证明 SQLite 指纹读取失败不阻断报告状态渲染。
- [ ] 运行智能复盘和报告定向测试。

### Task 4: Python 3.10 语法兼容

**Files:**
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Test: `tests/test_python_compatibility.py`

- [ ] 添加 Python 3.10 不允许同引号嵌套 f-string 的静态回归检查。
- [ ] 将颜色值提取到局部变量后格式化。
- [ ] 运行兼容性测试与 `compileall`。

### Task 5: 主窗口高 DPI 尺寸与导航布局验收

**Files:**
- Modify: `src/daylens/gui/main_window.py`
- Modify: `tools/check_navigation_layout.py`
- Test: `tests/test_ui_responsive_layout.py`

- [ ] 写测试模拟可用逻辑高度小于旧最小高度，确认窗口不越界。
- [ ] 调整窗口最小尺寸与初始几何计算，使其不超过可用屏幕。
- [ ] 更新导航布局脚本，移除已删除的 `btn_report` 断言并检查现行单按钮顶栏。
- [ ] 运行 1280×720、1920×1080，100%/125%/150% 布局检查。

### Task 6: 完整验证和发布

**Files:**
- Modify: `docs/reviews/2026-10-29-stability-layout-fixes-result.md`

- [ ] 运行定向测试和 `python -m pytest -q`。
- [ ] 运行 `python -m compileall -q src tests tools` 与 GUI smoke。
- [ ] 运行所有受影响布局脚本。
- [ ] 运行 `python tools/build_release.py --stage-only`。
- [ ] 记录真实测试结果，提交修改，合并后按安全发布流程重启 DayLens。
