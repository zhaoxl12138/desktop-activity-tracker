# Daily Goals and Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a trusted daily work target and configurable entertainment boundary beneath a five-row software ranking.

**Architecture:** Build a pure `goals` presentation model from the dashboard's existing 30-day aggregate payload and today's totals, persist two optional boundary settings through the existing settings table, and render a compact Qt card below the Top 5 list. No new query or schema is introduced.

**Tech Stack:** Python, PySide6, SQLite settings table, pytest, PyInstaller.

---

### Task 1: Trusted goals model

**Files:** `src/daylens/services/dashboard_service.py`, `tests/test_dashboard_service.py`

- [ ] Add failing tests for weekday/weekend selection, seven-sample median, 15-minute rounding, three-day minimum, metric/classification breaks, entertainment totals, and advice states.
- [ ] Run `python -m pytest tests/test_dashboard_service.py -k "daily_goals" -q` and confirm failures are caused by the absent model.
- [ ] Implement `build_daily_goals` and add `goals` to the existing snapshot without adding queries.
- [ ] Re-run the focused tests and require zero failures.

### Task 2: Settings persistence

**Files:** `src/daylens/repositories/settings_repository.py`, `src/daylens/services/settings_service.py`, `src/daylens/gui/pages/settings.py`, `tests/test_settings_service.py`, `tests/test_settings_page.py`

- [ ] Add failing tests that weekday/weekend entertainment boundary minutes round-trip through existing settings and that zero disables the boundary.
- [ ] Run the focused settings tests and confirm the new fields are absent.
- [ ] Whitelist, validate, display, save, and hot-reload both settings using existing APIs.
- [ ] Re-run focused settings tests and require zero failures.

### Task 3: Compact card and Top 5 layout

**Files:** `src/daylens/gui/widgets/dashboard_widgets.py`, `src/daylens/gui/pages/today_overview.py`, `tests/test_dashboard_widgets.py`, `tests/test_homepage_redesign.py`, `tests/test_ui_responsive_layout.py`

- [ ] Add failing tests for Top 5, goals card modes, pure-text labels, progress caps, old snapshots, and 1280×720 non-overlap.
- [ ] Run focused GUI tests and confirm failure against the current Top 9-only layout.
- [ ] Add `DailyGoalsCard`, wire `goals`, set `TopAppListWidget.MAX_ROWS = 5`, and split the old ranking stretch between the two cards.
- [ ] Re-run focused GUI tests and require zero failures.

### Task 4: Verification and release

**Files:** `tests/`, `tools/build_release.py`

- [ ] Run focused dashboard/settings/GUI tests, then the full suite.
- [ ] Run `python -m compileall -q src tests` and `git diff --check`.
- [ ] Build with `python tools/build_release.py`, launch exactly one release process, and verify the canonical database remains `D:\\OfficeSoftware\\DayLens\\data\\usage.db`.

