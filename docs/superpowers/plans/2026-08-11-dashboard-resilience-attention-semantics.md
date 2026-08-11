# Dashboard Resilience and Attention Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Dashboard refresh resilient to malformed session fields and present engaged-time semantics accurately for new snapshots without breaking legacy snapshots.

**Architecture:** Preserve raw rows for trusted anomaly assessment, sanitize only the copies consumed by Dashboard and Qt, and make timeline distribution reject malformed rows. Carry an explicit primary/trend metric marker in new snapshots so widgets can render “参与” for engaged data and “有效” for legacy effective data.

**Tech Stack:** Python 3, SQLite, PySide6, pytest

---

### Task 1: Strict session parsing

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Modify: `src/daylens/timeline.py`
- Test: `tests/test_dashboard_service.py`
- Test: `tests/test_timeline_logic.py`

- [ ] **Step 1: Write failing malformed-session tests**

Add a real-database Dashboard test containing `effective_seconds='bad'`, non-finite attention values, and an invalid timestamp, plus focused tests for injected rows and timeline construction. Assert that refresh returns, invalid contributions are absent, trust is low, and the insight kind is `data_health`.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_dashboard_service.py -k malformed tests/test_timeline_logic.py -k malformed
```

Expected: conversion or timestamp parsing failures from the existing consumers.

- [ ] **Step 3: Add strict parsing and sanitized consumption**

Implement a finite non-negative integer parser and session sanitizer in the Dashboard service:

```python
def _strict_session_seconds(value) -> int | None:
    if isinstance(value, bool):
        return None
    number = Decimal(str(value).strip())
    if not number.is_finite() or number != number.to_integral_value() or number < 0:
        return None
    return int(number)
```

Use sanitized copies for hourly, best-window, session cards, and Qt payloads while retaining an anomaly flag derived from raw rows. Apply the same finite integer and timestamp checks in `timeline.build_timeline`, skipping malformed rows before distribution. If raw anomalies are not already reflected by aggregate trust, force the affected range to low trust with the timing-anomaly reason.

- [ ] **Step 4: Run tests to verify GREEN**

Run the same focused command and expect every selected test to pass.

### Task 2: Engaged-time snapshot and widget semantics

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Modify: `src/daylens/gui/pages/today_overview.py`
- Modify: `src/daylens/gui/main_window.py`
- Test: `tests/test_dashboard_service.py`
- Test: `tests/test_dashboard_widgets.py`
- Test: `tests/test_homepage_redesign.py`

- [ ] **Step 1: Write failing semantic tests**

Assert that a daily row with differing `effective_seconds` and `engaged_seconds` produces a 30-day engaged point and `thirty_day_metric='engaged'`. Assert that a new snapshot drives the donut center and top capsule from engaged seconds with “参与时长”, while a legacy snapshot uses effective seconds with “有效时长”. Assert the 30-day legend uses “每日参与时间” or “每日有效时间” according to the marker.

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
python -m pytest -q tests/test_dashboard_service.py -k thirty_day tests/test_dashboard_widgets.py -k trend tests/test_homepage_redesign.py -k trusted_snapshots
```

Expected: the existing 30-day point uses effective seconds and the labels still say “活跃”.

- [ ] **Step 3: Implement semantic metadata and rendering**

Build 30-day points from `engaged_seconds`, add `totals.primary_metric='engaged'` and `trend.thirty_day_metric='engaged'`, and extend the donut API with a distinct primary value and label. In `apply_snapshot`, branch on the presence/marker of engaged data:

```python
uses_engaged = totals.get("primary_metric") == "engaged" or "engaged_seconds" in totals
primary_seconds = engaged_seconds if uses_engaged else effective_seconds
primary_label = "参与时长" if uses_engaged else "有效时长"
```

Use engaged/passive/idle ring segments for new snapshots, keep category/effective fallback for legacy snapshots, pass the trend metric marker to the trend card, and update the top capsule dynamically.

- [ ] **Step 4: Run tests to verify GREEN**

Run the same focused command and expect every selected test to pass.

### Task 3: Visible wording consistency and verification

**Files:**
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Modify: `src/daylens/gui/pages/today_overview.py`
- Modify: `src/daylens/gui/main_window.py`
- Modify: `src/daylens/services/shell_service.py`
- Modify: `src/daylens/services/category_stats_service.py`
- Test: relevant existing test files

- [ ] **Step 1: Replace misleading wording**

Use “参与” only for engaged fields and “有效” for existing effective-only surfaces. Preserve real-time state wording such as “活跃中”.

- [ ] **Step 2: Run focused GUI regression**

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_dashboard_service.py tests/test_dashboard_widgets.py tests/test_homepage_redesign.py tests/test_ui_responsive_layout.py tests/test_gui_smoke.py tests/test_timeline_logic.py
```

Expected: all focused tests pass.

- [ ] **Step 3: Run full verification**

```powershell
python -m pytest -q
python -m compileall -q src tests
git diff --check
```

Expected: the full suite passes, compilation exits zero, and diff-check emits no errors.

- [ ] **Step 4: Commit**

```powershell
git add src tests docs/superpowers/plans/2026-08-11-dashboard-resilience-attention-semantics.md
git commit -m "fix: harden dashboard attention metrics"
```
