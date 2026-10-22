# DayLens V1.7 Daily Goals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user-authored daily commitments and evidence-separated weekly review without changing existing timing or classification.

**Architecture:** Keep versioned goals as a locked, atomic derived JSON under `AppPaths.intelligence_dir`. A pure evaluator consumes one read-only session query plus confirmed V1.6 assignments. GUI and weekly reports consume its stable output; no AI call or SQLite write is involved.

**Tech Stack:** Python 3.14, PySide6, SQLite read-only repository, pytest, PyInstaller stage-only smoke.

---

### Task 1: Durable daily goal state

**Files:** Create `src/daylens/services/daily_goal_service.py`; create `tests/test_daily_goal_service.py`.

- [ ] Write tests for a 3-goal day, duplicate IDs, invalid type/target, revision conflict, atomic recovery and manual outcome confirmation/undo.
- [ ] Run `python -m pytest -q tests/test_daily_goal_service.py`; confirm failures come from the missing API.
- [ ] Implement `GoalStore(directory).load()`, `save_day(day, goals, expected_revision=...)`, `confirm_outcome(day, goal_id, confirmed, expected_revision=...)` with versioned JSON, file lock and recovery journal. Validate 1–3 goals and date/length/target constraints before writing.
- [ ] Rerun the focused tests, then the full suite.

### Task 2: Trusted goal evaluation

**Files:** Extend `src/daylens/services/daily_goal_service.py`; extend `tests/test_daily_goal_service.py`.

- [ ] Write tests showing trusted `attention-v1` engaged seconds for a work category and an explicitly confirmed task, duplicate/anomalous/legacy exclusion, 0 versus missing data, and negative/positive difference.
- [ ] Run the tests and verify the new assertions fail.
- [ ] Implement `evaluate_day(day, goals, rows, assignments)` as a pure function. Reuse `session_row_is_anomalous` and category keys; never infer a completed outcome from time.
- [ ] Rerun focused/full tests.

### Task 3: Today card and goal editor

**Files:** Create `src/daylens/gui/widgets/daily_goal_widgets.py`, `src/daylens/gui/pages/daily_goals.py`; modify `src/daylens/gui/pages/today_overview.py`, `src/daylens/gui/pages/statistics.py`, `src/daylens/gui/main_window.py`; create `tests/test_daily_goal_gui.py`.

- [ ] Write GUI tests for default empty state, adding up to three goals, selecting past dates, showing evidence insufficiency, manual outcome confirmation and card-to-tab navigation.
- [ ] Verify focused GUI tests fail before adding widgets.
- [ ] Add a compact summary card and one Statistics tab (no new left navigation). Load evaluation in existing background queue; route all writes through `GoalStore` with revisions and refresh after mutation.
- [ ] Run GUI-focused/full tests and `python tests/test_gui_smoke.py` at 1280×720.

### Task 4: Existing weekly report extension

**Files:** Modify `src/daylens/exporter.py`; extend `tests/test_exporter.py` or create `tests/test_weekly_goals_report.py`.

- [ ] Write tests for ISO week boundaries, plan/input/manual-outcome separation, no-goal state and invalid evidence text; verify red.
- [ ] In `export_weekly_report`, append a deterministic section from `daily_goal_service.build_weekly_review(...)`; query seven dates in one read and keep previous report sections intact.
- [ ] Run focused/full tests. Never rewrite past report files except when the user explicitly regenerates that report.

### Task 5: Documentation and release verification

**Files:** Modify `README.md`; create `docs/reviews/2026-10-22-daily-goals-v17-result.md`.

- [ ] Document the evidence labels, local-only scope, limitations and rollback.
- [ ] Run `python -m pytest -q`, `python -m compileall -q src/daylens`, `python tests/test_gui_smoke.py`, `python tools/build_release.py --stage-only`, and `git diff --check`.
- [ ] Record actual command outputs and failures; do not stop or replace the running DayLens, alter the live database, or push without a separate request.
