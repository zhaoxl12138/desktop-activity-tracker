# DayLens Statistics, Settings, Idle and UI Polish Implementation Plan

> **For agentic workers:** Execute task-by-task in the current checkout, use test-first verification, and preserve pre-existing changes. The user explicitly requested one main branch; do not create a worktree or commit/push automatically.

**Goal:** Deliver all seven approved UI, statistics, rule, and desktop-idle changes without rewriting history.

**Architecture:** Extend the current Qt pages and existing repository aggregations. Keep desktop-idle recognition at the foreground/session boundary; all other changes are presentation or read-only aggregation.

**Tech Stack:** Python 3, PySide6, SQLite, pytest, QPainter; existing release builder.

---

### Task 1: Statistics default and range totals

**Files:** `src/daylens/gui/pages/statistics.py`, `src/daylens/gui/pages/category_stats.py`, `src/daylens/services/category_stats_service.py`, `src/daylens/repositories/stats_repository.py` (only if range detail is not already available), `tests/test_category_labels.py`, `tests/test_category_card_labels.py`, `tests/test_stage_c_shell.py`.

- [x] Write failing Qt tests: a new StatisticsPage opens `live_page` by default while `select_tab('software')` and `select_tab('category')` still work; category page starts at 7 days and user can choose today, 30 days, and valid inclusive custom dates.
- [x] Write failing service tests with synthetic sessions on range boundaries: `load_category_summary(db_path, start_day, end_day)` returns `by_category` effective totals and matching range label; missing dates stay missing; invalid or >366-day selections are rejected; range detail belongs only to selected category.
- [x] Run targeted tests and record expected failures. Reuse `database.query_date_range_stats(db_path, dates)` for summary, then add a bounded category-detail query only if existing range payload cannot provide complete top-five per category.
- [x] Add compact period controls above category cards; issue work only when active and invalidate old refresh results on selection changes; preserve empty/error states.
- [x] Run targeted tests and verify all new tests pass. Full integration baseline after task: 1278 passed.

### Task 2: Rule names and usable save

**Files:** `config/config.yaml`, `config/config.example.yaml`, `src/daylens/gui/pages/rule_config.py`, `tests/test_rule_config_page.py`, `tests/test_local_rules_simple.py`.

- [x] Add failing tests that `gaming` and `video` remain distinct with `interactive_required` and `passive_allowed`, the action bar is visible at 1280×720, and clicking save with no changes explains the no-op; actual edits still persist once.
- [x] Reproduce the disabled/offscreen button with Qt geometry and button-click tests, then put actions in a visible top toolbar; remove unconditional disabled state and preserve dirty-editor prompts.
- [x] Set distinct factory names “游戏娱乐” and “视频娱乐”. For the user's two current, identical custom labels, prepare a targeted, backed-up rename during publication only; never touch other rules or historical sessions.
- [x] Run rule, classifier, timing, and GUI tests. Task 2 full integration checkpoint: 1294 passed, compileall passed; publication-time real-data rename remains under Task 7.

### Task 3: Desktop/Taskbar idle semantics

**Files:** `src/daylens/window_detector.py`, `src/daylens/session_tracker.py`, `tests/test_session_tracker_policies.py`, new `tests/test_desktop_idle.py`.

- [x] Add failing tests for foreground Win32 desktop/taskbar window classes vs normal Explorer folder windows, no foreground window, active mouse on desktop, and no change to previous persisted sessions.
- [x] Expose a small pure function that recognizes shell desktop/taskbar windows from observed class/title and attach the classification to the foreground observation. Ensure the session tracker credits `idle_seconds` rather than engaged/passive/effective seconds for this case.
- [x] Check video pause, ordinary Explorer interaction, system gaps, and cross-domain session splitting with focused tests. Task 3 full integration checkpoint: 1307 passed; independent focused review: 109 passed.

### Task 4: Daily rhythm, settings layout, AI usage footer

**Files:** `src/daylens/gui/widgets/dashboard_widgets.py`, `src/daylens/gui/pages/settings.py`, `src/daylens/gui/widgets/intelligence_settings.py`, `tests/test_rhythm_chart_layout.py`, `tests/test_settings_page.py`, `tests/test_intelligence_settings.py`.

- [x] Add failing geometry tests: Y-axis labels have at least 12 px gap from the plot; hover uses same chart rectangle. Settings headings and content do not intersect at 100%/125%/150% DPI at 1280×720 and 1920×1080.
- [x] Use a shared chart inset for draw/hit-test. Make settings group margins respond to font/DPI and replace fixed-width crowded rows with adaptive layout.
- [x] Reuse `IntelligenceBudget.snapshot()` for one page-bottom monthly estimate/budget label; ensure unavailable budget data is not shown as zero and AI card stays behaviorally unchanged.
- [x] Run targeted tests and inspect rendered captures. Task 4 full integration checkpoint: 1312 passed; captures inspected under `tmp/settings-rhythm-layout/`.

### Task 5: Day activity table and category filters

**Files:** `src/daylens/gui/widgets/day_activity_dialog.py`, `src/daylens/gui/widgets/day_activity_category_timeline.py`, `src/daylens/gui/widgets/day_activity_event_model.py` (only if display hooks needed), `tests/test_day_activity_gui.py`, `tests/test_day_activity_category_timeline.py`.

- [x] Add failing tests for responsive event-column widths, preserved full-title tooltip, category filter affecting both timeline and rows, intersection with >5-minute toggle, and reset to all when day changes.
- [x] Replace title-column unlimited stretch with bounded proportional widths and minimum widths for time, category, effective time, and notes. Add checkable category chips and a single selected-category state in the dialog; filter derived visible data only.
- [x] Verify click-row/timeblock linkage and full-day totals remain unchanged. Task 5 checkpoint: 1316 full tests passed; 52 focused tests independently rerun; filtered 150% layout capture inspected.

### Task 6: Home controls and font

**Files:** `src/daylens/gui/main_window.py`, `tests/test_stage_c_shell.py`, `tests/test_gui_smoke.py`.

- [x] Add failing tests that the home top bar has no “生成日报” button, report-center and scheduled generation remain available, and top/side “记录中” typography stays readable without the previous oversized weight.
- [x] Remove only the top-button widget and adapt its optional busy-state updates safely; normalize recording-label font size/weight and verify pause/restart states. New focused tests: 3 passed after 3 expected red failures.

### Task 7: End-to-end verification and visible restart

**Files:** `docs/reviews/2026-10-26-statistics-settings-idle-polish-result.md`, README if behavior changes need explaining.

- [x] Run focused tests for each task, then `python -m pytest -q`, `python -m compileall -q src/daylens`, GUI smoke, and layout captures at 1280×720/1920×1080 × 100%/125%/150% light/dark. Final: 1318 passed, manual GUI smoke passed.
- [x] Verify before/after synthetic raw effective/idle totals; no historical-session rewrite, no new AI call from these views, category range totals reconcile with original range query.
- [x] Check the exact running process and release paths; stage-build, gracefully stop, back up the prior binary, publish using existing safe script. Launch the interactive exe with normal/default window style, then verify an actually visible main window and live recording health. Roll back if any gate fails. New sole PID 56824 is visible/responding/running; no rollback needed.
- [x] Record commands, pass/fail counts, screenshots, release hash, any remaining issues in `docs/reviews/2026-10-27-statistics-settings-idle-polish-result.md`. No commit or push.
