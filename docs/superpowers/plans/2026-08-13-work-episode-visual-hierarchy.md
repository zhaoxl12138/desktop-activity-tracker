# Work Episode Visual Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提升首页“关键工作片段”的字体层级和颜色对比，同时保持现有布局与数据行为。

**Architecture:** 只修改 `TodayOverviewPage` 的区块标题样式和 `WorkEpisodeListWidget` 的四类行内标签样式。通过稳定对象名进行真实 Qt 控件样式回归，不引入新的展示组件或数据字段。

**Tech Stack:** Python 3、PySide6、pytest、Qt offscreen。

---

### Task 1: 锁定并实现视觉层级

**Files:**
- Modify: `src/daylens/gui/pages/today_overview.py`
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Test: `tests/test_dashboard_widgets.py`
- Test: `tests/test_homepage_redesign.py`

- [ ] **Step 1: 写失败测试**

在真实 `WorkEpisodeListWidget` 行中按对象名定位主题、应用、时间和参与时长标签，断言目标字号、字重与主题色；在首页卡片中定位区块标题并断言 15px、高权重与亮蓝色。

- [ ] **Step 2: 验证测试因缺少新视觉层级而失败**

Run: `py -3 -m pytest -q tests/test_dashboard_widgets.py::test_work_episode_widget_renders_topic_apps_and_participation tests/test_homepage_redesign.py::test_homepage_shell_matches_reference_structure`

Expected: FAIL，现有控件没有稳定对象名且仍使用旧字号与颜色。

- [ ] **Step 3: 写最小实现**

为五类标签设置稳定对象名，并应用以下样式：

```python
section_title.setStyleSheet("font-size: 15px; font-weight: 800; color: primary_hover")
topic.setStyleSheet("font-size: 13px; font-weight: 800; color: text")
app_label.setStyleSheet("font-size: 11px; color: text_secondary")
time_label.setStyleSheet("font-size: 11px; font-weight: 700; color: primary_hover")
duration_label.setStyleSheet("font-size: 12px; font-weight: 800; color: primary")
```

- [ ] **Step 4: 验证定向测试转绿**

Run: `py -3 -m pytest -q tests/test_dashboard_widgets.py tests/test_homepage_redesign.py tests/test_ui_responsive_layout.py tests/test_gui_smoke.py`

Expected: PASS，且现有响应式布局与纯文本断言继续通过。

- [ ] **Step 5: 完整验证并提交**

Run: `py -3 -m pytest -q`

Run: `py -3 -m compileall -q src tests`

Run: `git diff --check`

只暂存本计划列出的实现和测试文件，提交信息为 `fix: improve work episode hierarchy`，然后重建并启动发布版。
