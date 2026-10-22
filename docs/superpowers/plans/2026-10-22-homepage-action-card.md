# Homepage Action Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace two full-width Today cards with one compact “今日行动” card while retaining separate goal and task destinations.

**Architecture:** A presentation-only `TodayActionCard` receives the existing goal and task snapshot dictionaries. `TodayOverviewPage` lays it out as one grid row and forwards snapshots; `MainWindow` routes its two signals to existing Statistics tabs. No service, data model, query, or metric change.

**Tech Stack:** Python 3.14, PySide6, pytest, existing PyInstaller stage-only release script.

---

## File responsibilities

- Create `src/daylens/gui/widgets/today_action_card.py`: compact two-section view, state formatting, routing signals, responsive internal layout.
- Modify `src/daylens/gui/pages/today_overview.py`: replace two homepage cards with one grid item; retain snapshot forwarding.
- Modify `src/daylens/gui/main_window.py`: connect both section signals to existing Statistics tabs.
- Create `tests/test_today_action_card.py`: widget state, one-line text/tooltip, responsive behavior and grid position.
- Modify `tests/test_gui_smoke.py` and `tests/test_stage_c_shell.py`: integrated layout and routing assertions.
- Create `docs/reviews/2026-10-22-homepage-action-card-result.md`: real verification outputs and rollback note.

The existing `TaskInsightCard` and `DailyGoalCard` classes remain for tests and compatibility but are not instantiated on Today. Do not edit V1.6/V1.7 services, original sessions, or reports.

### Task 1: Compact view behavior

- [ ] **Step 1: Write failing tests** in `tests/test_today_action_card.py` for: title “今日行动”; only one goal/task summary each; goal and task signals emitted separately; disabled, empty, unavailable statuses; long title remains one visual line with a full-text tooltip.

```python
card = TodayActionCard()
card.set_goal_model({"status": "ready", "goals": [{"title": "相机课程", "type": "time_commitment", "target_minutes": 60, "actual_seconds": 1200, "difference_seconds": 2400, "evidence_status": "ready"}]})
assert "相机课程" in card.goal_summary.text()
assert card.goal_summary.toolTip() == "相机课程"
```

- [ ] **Step 2: Verify red** with `python -m pytest -q tests/test_today_action_card.py`; expect missing `TodayActionCard` import.
- [ ] **Step 3: Implement** `TodayActionCard` with `goals_requested` and `tasks_requested` signals, existing `fmt_seconds`, two `QToolButton`-like sections or equivalent accessible buttons, one line of model-derived text each, and concise status for no data/disabled/unavailable. Keep output plain text and never infer completion from time.
- [ ] **Step 4: Verify green** with the same command; expect all new widget tests passing.

### Task 2: Responsive layout and routing

- [ ] **Step 1: Add failing integration tests** to `tests/test_today_action_card.py`, `tests/test_stage_c_shell.py`, and `tests/test_gui_smoke.py`. Assert `TodayOverviewPage.action_card` occupies exactly one bottom grid row in wide/compact modes, no old cards are present, narrow mode stacks its sections, and each section routes to the correct Statistics tab.

```python
page = TodayOverviewPage(str(tmp_path / "usage.db"))
page.set_content_width(1200)
assert page._card_grid.itemAtPosition(3, 0).widget() is page.action_card
assert page._card_grid.itemAtPosition(4, 0) is None
page.set_content_width(800)
assert page._card_grid.itemAtPosition(5, 0).widget() is page.action_card
```

- [ ] **Step 2: Verify red** with `python -m pytest -q tests/test_today_action_card.py tests/test_stage_c_shell.py` and `python tests/test_gui_smoke.py`; expect layout or missing-card assertions to fail.
- [ ] **Step 3: Replace homepage wiring** in `today_overview.py` and `main_window.py`: instantiate one `TodayActionCard`, keep its single grid row, forward existing `set_goal_model`/`set_task_model`, route `goals_requested` to `navigate_to("stats", tab="goals")` and `tasks_requested` to `navigate_to("stats", tab="tasks")`.
- [ ] **Step 4: Verify green** with the same focused commands. If grid row numbering differs in single mode because of five existing cards, use the actual six-item order and fix the test, not behavior.

### Task 3: Verification and handoff

- [ ] **Step 1: Run** `python -m pytest -q`; record pass/fail count.
- [ ] **Step 2: Run** `python -m compileall -q src/daylens` and `python tests/test_gui_smoke.py` serially at normal, `QT_SCALE_FACTOR=1.25`, and `1.5`. Do not parallelize GUI smoke: it can contend on the same theme-config backup file.
- [ ] **Step 3: Run** `python tools/build_release.py --stage-only`; validate `release_staging` without terminating or replacing the running app. Check `git diff --check`.
- [ ] **Step 4: Save observed commands/results** in `docs/reviews/2026-10-22-homepage-action-card-result.md`. State explicitly that code remains in the current dirty `main` checkout and no formal release replacement or push occurred.

## Constraints

The user previously requested one main branch, and V1.6/V1.7 edits overlap the current dirty checkout. Reuse that checkout; do not create a worktree or commit overlapping files implicitly. Preserve all unrelated untracked backup/runtime files. Use `apply_patch` for edits, test-first for each behavior, and no real database modifications during tests.
