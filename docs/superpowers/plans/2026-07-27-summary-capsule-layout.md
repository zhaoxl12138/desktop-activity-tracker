# 首页顶部统计卡片布局 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将首页顶部四项统计改为更宽松的垂直卡片布局，避免长时间值挤压相邻列。

**Architecture:** 保留 `MainWindow._build_summary_capsules()` 的四列网格和现有数据绑定，只把单项卡片内部从横向布局改为垂直布局，并通过网格的最小宽度、间距和对齐策略控制视觉密度。紧凑窗口继续使用现有两行两列响应式切换。

**Tech Stack:** Python, PySide6, pytest-qt/offscreen Qt tests.

---

### Task 1: 固定四项卡片的垂直布局契约

**Files:**
- Modify: `tests/test_homepage_redesign.py`（新增卡片布局断言）
- Modify: `src/daylens/gui/main_window.py:370-415`（单项布局）

- [ ] **Step 1: 写失败测试**

在现有首页测试中，创建窗口后断言每个 summary item 的布局为 `QVBoxLayout`，并且图标、标题、数值均水平居中；断言卡片最小宽度至少为 150。

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout

for item in window.summary_capsule_items:
    item_layout = item.layout()
    assert isinstance(item_layout, QVBoxLayout)
    assert item_layout.alignment() & Qt.AlignHCenter
    assert item.minimumWidth() >= 150
```

- [ ] **Step 2: 运行失败测试**

运行：`py -m pytest -q tests/test_homepage_redesign.py -k capsule -vv`

预期：失败，因为当前单项卡片使用 `QHBoxLayout` 且最小宽度为 120。

- [ ] **Step 3: 最小实现**

在 `_build_summary_capsules()` 将 `item.setMinimumWidth(120)` 改为 `item.setMinimumWidth(150)`；在 `_make_capsule()` 使用 `QVBoxLayout`，设置 `setAlignment(Qt.AlignHCenter)`、`setContentsMargins(8, 4, 8, 4)`、`setSpacing(4)`，并对图标、标题、数值分别设置 `Qt.AlignHCenter` 后加入布局。数值标签设置 `setMinimumHeight(30)`，标题和数值保留原有字体。

- [ ] **Step 4: 运行测试确认通过**

运行：`py -m pytest -q tests/test_homepage_redesign.py -k capsule -vv`

预期：新增布局断言通过，其他首页断言保持通过。

- [ ] **Step 5: 提交**

```bash
git add tests/test_homepage_redesign.py src/daylens/gui/main_window.py
git commit -m "fix: loosen homepage summary capsule layout"
```

### Task 2: 调整网格留白并验证响应式宽度

**Files:**
- Modify: `tests/test_homepage_redesign.py`（补充网格间距断言）
- Modify: `src/daylens/gui/main_window.py:355-410`（网格间距和对齐）

- [ ] **Step 1: 写失败测试**

断言 summary grid 的横向间距至少为 24、纵向间距至少为 10，并验证窗口宽度 1366 时四项仍在同一行、宽度低于 1400 的响应式逻辑仍把项目放到两行两列。

```python
assert window._summary_capsule_grid.horizontalSpacing() >= 24
assert window._summary_capsule_grid.verticalSpacing() >= 10
window.resize(1366, 768)
app.processEvents()
assert window._top_bar_compact is True
```

- [ ] **Step 2: 运行失败测试**

运行：`py -m pytest -q tests/test_homepage_redesign.py -k "capsule or responsive" -vv`

预期：失败，因为当前网格间距为 14 和 8。

- [ ] **Step 3: 最小实现**

在 `_build_summary_capsules()` 将 `setHorizontalSpacing(14)` 改为 `setHorizontalSpacing(24)`、`setVerticalSpacing(8)` 改为 `setVerticalSpacing(10)`，保留现有紧凑模式的两列逻辑，不改变导航、数据更新和主题切换。

- [ ] **Step 4: 运行相关测试和全量测试**

运行：`py -m pytest -q tests/test_homepage_redesign.py tests/test_dashboard_refresh_cadence.py`

预期：全部通过。

- [ ] **Step 5: 提交**

```bash
git add tests/test_homepage_redesign.py src/daylens/gui/main_window.py
git commit -m "test: cover summary capsule spacing and responsive layout"
```

### Task 3: 发布前验证

**Files:**
- No source changes.

- [ ] **Step 1: 运行完整测试**

运行：`py -m pytest -q`

预期：全量测试通过。

- [ ] **Step 2: 编译和差异检查**

运行：`py -m compileall -q src tools` 与 `git diff --check`。

预期：无编译错误、无空白错误。

- [ ] **Step 3: 构建并重启发布版**

按现有 `tools/build_release.py` 流程构建，确认 `D:\OfficeSoftware\DayLens\release\DayLens.exe` 与新构建一致，刷新快捷方式后重启 DayLens。

- [ ] **Step 4: 手工验收**

在 1600×900、1366×768 和 1100×700 下检查四项统计的图标、标题、数值均居中且无重叠；切换主题后保持当前页面和布局。
