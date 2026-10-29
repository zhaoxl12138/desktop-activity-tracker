# 数据统计范围与实时监控快捷行优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除实时监控页的重复快捷纠错行，并将分类统计范围控件改成宽松、日期完整可读的工具卡。

**Architecture:** 保留实时监控纠错控件对象但不加入可见布局，以兼容现有状态更新和主窗口信号接线。分类统计页保留现有 `period_combo`、`start_edit`、`end_edit` 数据接口，在其外增加范围卡、预设摘要和仅自定义时显示的日期编辑区，不改变刷新控制器或查询服务。

**Tech Stack:** Python 3、PySide6、pytest、现有 DashboardRefreshController。

---

### Task 1: 移除实时监控快捷纠错行

**Files:**
- Modify: `src/daylens/gui/pages/live_monitor.py:75-98`
- Test: `tests/test_classification_correction.py`

- [ ] **Step 1: Write the failing test**

在 `tests/test_classification_correction.py` 中增加：

```python
def test_live_monitor_hides_redundant_correction_shortcut_row(qtbot):
    page = LiveMonitorPage()
    qtbot.addWidget(page)
    page.show()

    assert not page.correct_button.isVisible()
    assert not page.manage_patterns_button.isVisible()
    assert not page.correction_status.isVisible()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_classification_correction.py::test_live_monitor_hides_redundant_correction_shortcut_row`

Expected: FAIL because the three widgets are currently added to the visible `correction_actions` layout.

- [ ] **Step 3: Write minimal implementation**

在 `LiveMonitorPage.__init__` 中继续创建并连接三个兼容控件，但不创建 `correction_actions`，不把控件加入页面布局，并显式调用：

```python
self.correct_button.hide()
self.manage_patterns_button.hide()
self.correction_status.hide()
```

保留隐藏的 `apply_retry_button`，确保现有纠错保存、规则管理导航和重试信号代码不需要改写。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_classification_correction.py tests/test_review_confirmation_finance.py tests/test_stage_a_reliability.py`

Expected: PASS；既有测试仍可通过隐藏 `correction_status` 检查状态文本。

- [ ] **Step 5: Commit**

```powershell
git add src/daylens/gui/pages/live_monitor.py tests/test_classification_correction.py
git commit -m "ui: remove live monitor correction shortcut row"
```

### Task 2: 重构分类统计范围工具条

**Files:**
- Modify: `src/daylens/gui/pages/category_stats.py:230-360`
- Test: `tests/test_category_range.py`

- [ ] **Step 1: Write the failing tests**

在 `tests/test_category_range.py` 中增加两个测试：

```python
def test_range_toolbar_shows_full_preset_summary_and_hides_custom_editors(page, qtbot):
    page.show()
    qtbot.wait(1)
    assert page.period_combo.minimumWidth() >= 140
    assert page.range_summary.text() == (
        f"{page.start_edit.date().toString('yyyy-MM-dd')} 至 "
        f"{page.end_edit.date().toString('yyyy-MM-dd')} · 共 7 天"
    )
    assert not page.custom_range_widget.isVisible()


def test_custom_range_uses_wide_editors_and_calendar(page, qtbot):
    page.show()
    page.period_combo.setCurrentIndex(page.period_combo.findData("custom"))
    qtbot.wait(1)
    assert page.custom_range_widget.isVisible()
    assert page.start_edit.minimumWidth() >= 150
    assert page.end_edit.minimumWidth() >= 150
    assert page.start_edit.calendarWidget().minimumWidth() >= 340
    assert page.start_edit.calendarWidget().minimumHeight() >= 260
```

测试可适配该文件现有 fixture 名称，但断言语义保持不变。

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -q tests/test_category_range.py -k "range_toolbar or custom_range_uses_wide"`

Expected: FAIL because `range_summary` and `custom_range_widget` do not yet exist and控件没有最小宽度。

- [ ] **Step 3: Implement the range card**

在 `CategoryStatsPage.__init__` 中：

```python
self.range_card = QFrame()
self.range_card.setObjectName("categoryRangeCard")
range_layout = QVBoxLayout(self.range_card)
range_layout.setContentsMargins(18, 14, 18, 14)
range_layout.setSpacing(10)

top_row = QHBoxLayout()
top_row.setSpacing(12)
title = QLabel("统计范围")
self.period_combo.setMinimumWidth(140)
self.period_combo.setMinimumHeight(36)
self.range_summary = QLabel()
self.range_summary.setWordWrap(False)
top_row.addWidget(title)
top_row.addWidget(self.period_combo)
top_row.addWidget(self.range_summary, 1)
range_layout.addLayout(top_row)

self.custom_range_widget = QWidget()
custom_row = QHBoxLayout(self.custom_range_widget)
custom_row.setContentsMargins(0, 0, 0, 0)
custom_row.setSpacing(10)
custom_row.addWidget(QLabel("开始日期"))
custom_row.addWidget(self.start_edit)
custom_row.addWidget(QLabel("结束日期"))
custom_row.addWidget(self.end_edit)
custom_row.addStretch(1)
range_layout.addWidget(self.custom_range_widget)
```

两个 `QDateEdit` 设置 `minimumWidth=150`、`minimumHeight=36`；各自 `calendarWidget()` 设置最小尺寸 `340 × 260`。范围卡使用现有深色面板颜色和圆角，不引入新主题变量。

- [ ] **Step 4: Update period visibility and summary**

在 `_on_period_changed()` 末尾调用 `_update_range_controls()`；新增：

```python
def _update_range_controls(self) -> None:
    custom = self.period_combo.currentData() == "custom"
    self.custom_range_widget.setVisible(custom)
    start = self.start_edit.date()
    end = self.end_edit.date()
    days = start.daysTo(end) + 1
    self.range_summary.setText(
        f"{start.toString('yyyy-MM-dd')} 至 {end.toString('yyyy-MM-dd')} · 共 {days} 天"
    )
```

构造结束时调用一次，保证默认近 7 天立即显示完整摘要。自定义日期变化继续走原有 `_on_period_changed()`，不增加数据库请求。

- [ ] **Step 5: Run focused tests**

Run: `pytest -q tests/test_category_range.py`

Expected: PASS，原范围边界和新增布局断言全部通过。

- [ ] **Step 6: Commit**

```powershell
git add src/daylens/gui/pages/category_stats.py tests/test_category_range.py
git commit -m "ui: expand category statistics range controls"
```

### Task 3: 全量验证、发布与重启

**Files:**
- Modify: `docs/reviews/` 中本次验证记录（如项目现有发布脚本要求）

- [ ] **Step 1: Run full automated verification**

Run:

```powershell
pytest -q
python -m compileall -q src tests
```

Expected: 全量测试通过，`compileall` 退出码为 0。

- [ ] **Step 2: Run GUI smoke**

使用仓库现有 GUI smoke 命令检查 1280×720 默认范围、切换自定义范围、实时监控顶部布局和日历弹窗；确认无重叠、截断或日期省略号。

- [ ] **Step 3: Inspect diff and repository state**

Run:

```powershell
git diff --check
git status --short
```

Expected: 无空白错误；只保留用户原有未跟踪文件和本次预期改动。

- [ ] **Step 4: Publish with existing safe release workflow**

使用仓库现有构建、维护退出、备份和替换脚本发布，禁止覆盖用户数据库或设置。

- [ ] **Step 5: Restart and verify DayLens**

启动 `release/DayLens.exe`，确认只存在一个 DayLens 实例、进程可响应且主窗口正常显示；检查统计范围与实时监控页面。

