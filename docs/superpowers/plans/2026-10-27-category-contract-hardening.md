# DayLens Category Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every DayLens statistics consumer derive category grouping from the central category registry without changing stored sessions or timing semantics.

**Architecture:** Keep `category_registry.py` as the vocabulary owner and expose immutable group sets through `utils.py`. Existing services retain their public constants where compatibility is useful, but those constants become aliases of the shared sets rather than independent literals.

**Tech Stack:** Python 3, PySide6, SQLite, pytest

---

### Task 1: Lock the shared category contract

**Files:**
- Modify: `tests/test_category_labels.py`
- Modify: `tests/test_dashboard_service.py`

- [ ] Add a failing test asserting the aggregate `work` category is included in `WORK_CATEGORY_KEYS` and is counted as work by `category_seconds`.
- [ ] Add a failing test asserting dashboard compatibility constants equal the shared registry-derived sets.
- [ ] Run `python -m pytest tests/test_category_labels.py tests/test_dashboard_service.py -q` and confirm the new assertion fails because dashboard constants are hand-written.

### Task 2: Replace duplicated dashboard category sets

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Modify: `src/daylens/services/behavior_profile_service.py`
- Modify: `src/daylens/services/task_grouping_service.py`

- [ ] Import the shared immutable category sets from `daylens.utils`.
- [ ] Keep `WORK_KEYS` and `ENTERTAINMENT_KEYS` as compatibility aliases so callers do not break.
- [ ] Run the Task 1 tests and confirm they pass.

### Task 3: Remove remaining work-group literals from statistics consumers

**Files:**
- Modify: `src/daylens/repositories/stats_repository.py`
- Modify: `src/daylens/timeline.py`
- Modify: `src/daylens/services/daily_goal_service.py`
- Modify: `src/daylens/gui/pages/today_overview.py`
- Modify: `src/daylens/exporter.py`
- Test: `tests/test_category_labels.py`
- Test: `tests/test_office_work_category.py`

- [ ] Add contract tests covering the repository, timeline, goals and exporter-facing shared work set.
- [ ] Run those tests and confirm at least one duplicated literal is detected.
- [ ] Replace duplicated work literals with shared constants, without changing public behavior for concrete categories.
- [ ] Run the contract tests and confirm they pass.

### Task 4: Make category detail expansion registry-driven

**Files:**
- Modify: `src/daylens/services/category_stats_service.py`
- Test: `tests/test_category_range.py`

- [ ] Add a failing test showing aggregate category detail expansion includes registry aliases and aggregate keys.
- [ ] Add one helper that resolves a requested bucket to its registry-derived source keys.
- [ ] Verify single-day and date-range category details use the same bucket contract.

### Task 5: Baseline and regression verification

**Files:**
- Modify: `.gitignore`
- Create: `docs/reviews/2026-10-27-category-contract-hardening-result.md`

- [ ] Add ignore rules for known release-backup, runtime-log, temporary and local-intelligence directories without deleting existing files.
- [ ] Compare current database total effective seconds before and after the code change; require exact equality.
- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m compileall -q src`.
- [ ] Run `python tools/gui_smoke_test.py` or the repository's current GUI smoke entry point.
- [ ] Record exact commands and results in the review document.
- [ ] Restart DayLens once after all checks complete, following the established safe restart path.
