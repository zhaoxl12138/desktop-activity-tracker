# Remove Homepage Action Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the redundant “今日行动” goal/task summaries from the homepage while preserving the complete task-chain and goal workspaces.

**Architecture:** `TodayOverviewPage` will own only the five dashboard cards that remain visible. `MainWindow` will keep constructing and refreshing task/goal pages, but will no longer connect or forward their models to a homepage action card.

**Tech Stack:** Python 3, PySide6, pytest, PyInstaller staging build.

---

### Task 1: Lock the new homepage contract

**Files:**
- Modify: `tests/test_today_action_card.py`
- Modify: `tests/test_stage_c_shell.py`
- Modify: `tests/test_gui_smoke.py`

- [ ] Replace homepage assertions with checks that `TodayOverviewPage` has no `action_card`, the wide grid ends at row 2, and the single-column grid contains exactly five cards.
- [ ] Keep assertions that the statistics page has four tabs and still contains the task and goal pages.
- [ ] Run `python -m pytest -q tests/test_today_action_card.py tests/test_stage_c_shell.py tests/test_gui_smoke.py` and verify the new assertions fail because `action_card` still exists.

### Task 2: Remove homepage rendering and wiring

**Files:**
- Modify: `src/daylens/gui/pages/today_overview.py`
- Modify: `src/daylens/gui/main_window.py`

- [ ] Remove `TodayActionCard` construction, responsive layout participation, and task/goal model forwarding methods from `TodayOverviewPage`.
- [ ] Remove only the two homepage button signal connections and homepage model-forwarding calls from `MainWindow`; keep task/goal page refresh and model updates intact.
- [ ] Run the focused tests and verify they pass.

### Task 3: Verify and deploy locally

**Files:**
- Modify only if a failing test exposes a regression in files already in scope.

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m compileall -q src/daylens`.
- [ ] Run the offscreen GUI smoke at scale factors 1 and 1.5.
- [ ] Run `git diff --check`.
- [ ] Stop the running release safely, rebuild with `python tools/build_release.py --stage-only`, launch `release_staging/DayLens.exe`, and verify one running instance whose homepage omits the removed area.
