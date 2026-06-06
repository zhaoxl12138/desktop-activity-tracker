# DayLens 首页重排实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the oversized `今日洞察` card and restore a balanced two-column dashboard so `时间趋势` and `软件使用 TOP5` regain normal width and alignment.

**Architecture:** Keep the existing dashboard data pipeline and reuse `load_today_snapshot()` outputs. Remove the insight card from the page layer, shrink the grid back to a clean 8:4 two-column layout, and keep the left-side distribution + session content intact. The right column should be visually independent again, with no leftover insight calculations or empty space.

**Tech Stack:** Python 3.14, PySide6, existing dashboard service/widgets, pytest

---

### Task 1: Remove the insight card from the dashboard page

**Files:**
- Modify: `src/daylens/gui/pages/today_overview.py:1-650`
- Test: `tests/test_homepage_redesign.py`
- Test: `tests/test_gui_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
def test_homepage_has_no_insight_card(window):
    today = window.pages["today"]
    assert getattr(today, "insight_card", None) is None
    assert getattr(today, "insight_grid_widget", None) is None
    assert getattr(today, "insight_empty_label", None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_homepage_redesign.py::test_homepage_has_no_insight_card -v`
Expected: FAIL because the current page still builds the insight card.

- [ ] **Step 3: Write minimal implementation**

Remove the `self.insight_card = self._build_insight_card()` branch from `TodayOverviewPage.__init__`, delete `_build_insight_card()` and `_update_insights()`, and stop reading `snapshot["insights"]` in `refresh()`. Keep `distribution_cmp_labels` and `focus_hint` intact.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_homepage_redesign.py::test_homepage_has_no_insight_card -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daylens/gui/pages/today_overview.py tests/test_homepage_redesign.py
git commit -m "refactor: remove homepage insight card"
```

### Task 2: Rebalance the dashboard grid so the right column gets full width

**Files:**
- Modify: `src/daylens/gui/pages/today_overview.py:1-140`
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py:520-980`
- Test: `tests/test_dashboard_widgets.py`
- Test: `tests/test_homepage_redesign.py`

- [ ] **Step 1: Write the failing test**

```python
def test_homepage_grid_uses_two_column_layout(window):
    today = window.pages["today"]
    layout = today.layout().itemAt(0).layout()
    assert layout.columnStretch(0) == 1
    assert layout.columnStretch(7) == 1
    assert layout.columnStretch(8) == 1
    assert layout.columnStretch(11) == 1
    assert today.trend_card.minimumHeight() >= 280
    assert today.top_app_card.minimumHeight() >= 230
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_homepage_redesign.py::test_homepage_grid_uses_two_column_layout -v`
Expected: FAIL because the current layout still reflects the old three-zone balance.

- [ ] **Step 3: Write minimal implementation**

Change the grid to a clean 8:4 split on both rows, ensure `trend_card` and `top_app_card` are no longer visually compressed by middle-column content, and keep the existing card classes but give them enough minimum height to fill the right column naturally.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_homepage_redesign.py::test_homepage_grid_uses_two_column_layout -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daylens/gui/pages/today_overview.py src/daylens/gui/widgets/dashboard_widgets.py tests/test_homepage_redesign.py
git commit -m "refactor: rebalance homepage right column"
```

### Task 3: Remove stale insight projection from the dashboard service

**Files:**
- Modify: `src/daylens/services/dashboard_service.py:1-420`
- Test: `tests/test_dashboard_service.py`
- Test: `tests/test_homepage_redesign.py`

- [ ] **Step 1: Write the failing test**

```python
def test_today_snapshot_no_longer_includes_insights(db_path):
    snapshot = load_today_snapshot(db_path)
    assert "insights" not in snapshot
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_service.py::test_today_snapshot_no_longer_includes_insights -v`
Expected: FAIL because `load_today_snapshot()` still builds and returns `insights`.

- [ ] **Step 3: Write minimal implementation**

Delete `build_today_insights()` and the `insights` entry from `load_today_snapshot()`. Keep the rest of the snapshot contract unchanged so the page still has `distribution_sections`, `day_comparison`, `sessions`, `trend`, `focus_summary`, `consecutive_days`, and `top_app_rows`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_service.py::test_today_snapshot_no_longer_includes_insights -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daylens/services/dashboard_service.py tests/test_dashboard_service.py
git commit -m "refactor: drop dashboard insight projection"
```

### Task 4: Update smoke coverage and release docs

**Files:**
- Modify: `tests/test_gui_smoke.py`
- Modify: `README.md` if the homepage description mentions insights
- Modify: `CHANGELOG.md`
- Modify: `TODO.md`

- [ ] **Step 1: Write the failing test**

```python
def test_homepage_smoke_uses_right_column_layout(window):
    today = window.pages["today"]
    assert today.time_stats_card is None
    assert getattr(today, "insight_card", None) is None
    assert today.trend_card.minimumHeight() >= 280
    assert today.top_app_card.minimumHeight() >= 230
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gui_smoke.py::test_homepage_smoke_uses_right_column_layout -v`
Expected: FAIL before implementation, PASS after Tasks 1-3.

- [ ] **Step 3: Write minimal implementation**

Update smoke assertions to match the new homepage shape. Add a short changelog entry describing that the homepage now uses a balanced two-column layout without the insight panel.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gui_smoke.py::test_homepage_smoke_uses_right_column_layout -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_gui_smoke.py README.md CHANGELOG.md TODO.md
git commit -m "docs: record homepage layout simplification"
```

### Task 5: Rebuild, verify, and update the desktop launcher

**Files:**
- Use: `tools/build_release.py`
- Use: `C:\Users\Administrator\Desktop\DayLens 最新启动方式.lnk`

- [ ] **Step 1: Run the full targeted test set**

Run: `pytest tests/test_dashboard_service.py tests/test_homepage_redesign.py tests/test_dashboard_widgets.py tests/test_gui_smoke.py -q`
Expected: all tests pass.

- [ ] **Step 2: Rebuild the release**

Run: `python tools/build_release.py`
Expected: `Release prepared at: D:\OfficeSoftware\DayLens\release`

- [ ] **Step 3: Refresh the desktop shortcut target**

Ensure the desktop shortcut points at `D:\OfficeSoftware\DayLens\release\DayLens.exe`.

- [ ] **Step 4: Final verification**

Run `git status --short` and confirm only intentional source/doc/test changes remain.

- [ ] **Step 5: Commit any remaining changes**

```bash
git add .
git commit -m "feat: rebalance dashboard layout"
```

## Coverage Check
- Task 1 removes the insight card and its rendering hooks.
- Task 2 restores the right-column width and removes the squeeze on `时间趋势` and `软件使用 TOP5`.
- Task 3 drops the unused `insights` projection from the data pipeline.
- Task 4 keeps the test suite aligned with the new homepage shape and documents the change.
- Task 5 rebuilds and verifies the release path used by the desktop shortcut.

## Notes
- Do not touch the unrelated untracked poetry migration files.
- Keep the `时间分布 + 较昨日` and `今日专注 Session` sections intact.
- Do not alter the historical report format or session heuristics in this pass.
