# Rhythm History Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show every recorded work-rhythm value from 2026-08-13 onward without treating legacy values as comparable engaged data.

**Architecture:** Extend the existing rhythm presentation model with a cutoff-aware display-value helper and per-point display kinds. Keep trusted comparison helpers unchanged, then teach the existing canvas to render legacy or partial points in gray.

**Tech Stack:** Python 3.14, PySide6, SQLite, pytest

---

### Task 1: Reproduce the empty mixed-history chart

**Files:**
- Test: `tests/test_dashboard_service.py`

- [ ] Add a test with attention rows from 2026-08-13, a legacy day, and a mixed current day.
- [ ] Assert that all recorded dates remain visible, values before the cutoff are absent, and comparison remains disabled.
- [ ] Run the focused test and confirm it fails because the current exact-version filtering returns only `None` values.

### Task 2: Build cutoff-aware rhythm values

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Test: `tests/test_dashboard_service.py`

- [ ] Add a fixed display-start constant and a helper returning `(seconds, kind, trusted)` for a daily row.
- [ ] Use the helper in 7-day and 30-day builders while retaining `_trusted_work_seconds` for comparisons.
- [ ] Clip the 30-day date range to the display start and emit incomplete-week values as `partial`.
- [ ] Run focused service tests and confirm they pass.

### Task 3: Render legacy and partial values distinctly

**Files:**
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Test: `tests/test_dashboard_widgets.py`

- [ ] Add a canvas test for `value_kinds` state.
- [ ] Render current values in blue and legacy/partial values in gray without adding a category legend.
- [ ] Run focused widget tests and confirm they pass.

### Task 4: Verify and publish

**Files:**
- No additional source files.

- [ ] Run dashboard, widget, mixed-history, and range-query tests.
- [ ] Run the full test suite, `compileall`, and `git diff --check`.
- [ ] Commit the implementation, rebuild `D:\OfficeSoftware\DayLens\release`, and restart the single canonical executable.

