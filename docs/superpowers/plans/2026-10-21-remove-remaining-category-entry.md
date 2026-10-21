# Remove Remaining Category Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining-category button and dialog from the Today distribution card.

**Architecture:** Keep the existing dashboard snapshot and donut fallback segment. Change only the Today page widget tree and delete its now-unused dialog handler.

**Tech Stack:** Python, PySide6, pytest, PyInstaller.

---

### Task 1: UI behavior

**Files:** `tests/test_homepage_redesign.py`, `src/daylens/gui/pages/today_overview.py`

- [x] Add a test with a hidden-category snapshot. Assert the card has no `remaining_categories_button`, has no button text, and the donut retains the gray residual segment.
- [x] Run `python -m pytest tests/test_homepage_redesign.py -q` and observe the test fail on the current button.
- [x] Remove button creation, visibility/text updates, `_hidden_categories` UI state, dialog method and unused `QMessageBox` import. Retain the computed `hidden_seconds` donut segment.
- [x] Re-run targeted tests, then full pytest, compileall and diff check.

### Task 2: Publish

**Files:** `tools/build_release.py` (use existing script without editing it).

- [x] Build and run packaged smoke; safely stop the current process, keep a rollback release, publish and restart exactly one `release/DayLens.exe`.
- [x] Confirm the canonical `data/usage.db` path and SQLite quick check.
