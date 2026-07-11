# Responsive UI No-Overlap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the DayLens UI resilient to resizing and DPI scaling without changing its visual information architecture.

**Architecture:** MainWindow owns a resizable shell with a scrollable page host. Each page keeps its own layout but removes the fixed dimensions that force clipping; tests exercise geometry at three window sizes.

**Tech Stack:** PySide6, Qt layouts/QScrollArea, pytest.

---

### Task 1: Add geometry regression tests

**Files:**
- Create: `tests/test_ui_responsive_layout.py`

- [ ] Build a MainWindow with the existing dummy worker and temporary database at 1600×900, 1200×750, and 1100×700.
- [ ] Assert the window is resizable, the page host fits inside the central widget, and the visible page's direct children stay within its rect after `app.processEvents()`.
- [ ] Assert the sidebar navigation has a scrollbar policy that permits scrolling.
- [ ] Run `python -m pytest -q tests/test_ui_responsive_layout.py` and verify RED because the window is fixed and the sidebar scrollbar is disabled.

### Task 2: Make the shell resizable and scroll-aware

**Files:**
- Modify: `src/daylens/gui/main_window.py`
- Test: `tests/test_ui_responsive_layout.py`

- [ ] Replace `setFixedSize` with `resize` plus minimum size 1100×700 and a resizable window flag.
- [ ] Keep the sidebar width at 254 but set its navigation vertical scrollbar to `ScrollBarAsNeeded` and allow the list to consume available height.
- [ ] Wrap the page stack in a scroll area or equivalent page host that preserves page width while allowing vertical overflow.
- [ ] Run the responsive tests and verify GREEN.

### Task 3: Remove high-risk fixed card dimensions

**Files:**
- Modify: `src/daylens/gui/pages/today_overview.py`
- Modify: `src/daylens/gui/pages/reports.py`
- Modify: `src/daylens/gui/pages/rule_config.py`
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Test: `tests/test_ui_responsive_layout.py`

- [ ] Replace fixed heights for the focus card and top-level bar with minimum heights and stretch factors.
- [ ] Replace the report detail fixed width with a minimum width and a responsive layout policy.
- [ ] Keep editor minimum heights in rule configuration but let the enclosing scroll host handle overflow.
- [ ] Add word wrapping/elision to long labels that can grow from live data.
- [ ] Run the responsive tests and existing GUI tests.

### Task 4: Verify and publish

- [ ] Run full pytest and `python -m compileall -q src`.
- [ ] Merge the isolated branch into local main, rerun tests, and remove the owned worktree.
- [ ] Run `python tools/build_release.py`, refresh both shortcuts, start `release/DayLens.exe`, and verify exactly one process.
