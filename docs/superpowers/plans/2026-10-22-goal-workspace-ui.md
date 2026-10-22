# Goal Workspace UI Stage A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the full-height goals table and bottom action strip with a compact daily goal workspace.

**Architecture:** Keep `GoalStore`, daily evaluation, IDs and write methods unchanged. Build presentation-only goal/empty widgets and connect card-scoped actions to the existing page operations by stable goal ID. Keep the goals tab inside Statistics; align the outer header text when that tab is active.

**Tech Stack:** Python, PySide6, pytest.

## Task 1: Empty and header

- [ ] Add GUI assertions in `tests/test_daily_goal_gui.py` that empty state has no `QTableWidget`, exposes new-time/new-outcome buttons, includes summary 0/3 and keeps its natural height. Run the test and see it fail.
- [ ] Update `src/daylens/gui/pages/daily_goals.py`: page header, primary create menu, date previous/next/today/calendar, three metrics, bounded empty state. Preserve existing add methods. Run focused test green.

## Task 2: Goal cards and operations

- [ ] Add failing tests for one/time and one/outcome goal, two/three responsive cards, card menu edit/delete and outcome confirm by ID, loading/unavailable display, daily limit, date isolation.
- [ ] Add `src/daylens/gui/widgets/goal_workspace_widgets.py`: reusable goal card and empty state. Replace table rendering in `daily_goals.py` with one-to-three cards, stable ID-scoped signals, non-stretch content and a scroll area. Keep storage calls and optimistic revision semantics unchanged. Run focused tests green.

## Task 3: Navigation and acceptance

- [ ] Add failing GUI assertion that the Statistics goals tab updates the global title/subtitle without adding a navigation item; then implement in `main_window.py`/`statistics.py`.
- [ ] Run `python -m pytest -q tests/test_daily_goal_gui.py tests/test_gui_smoke.py`; `python -m pytest -q`; `python -m compileall -q src/daylens`.
- [ ] Render isolated goal states at 1280×720 and 1920×1080 with 100/125/150% scales in dark/light themes; assert card/button bounds and no overlap. Do not modify real data.
- [ ] Save observed results and remaining limits in `docs/reviews/2026-10-22-goal-workspace-ui-result.md`. Do not replace the formal release or push unless asked.
