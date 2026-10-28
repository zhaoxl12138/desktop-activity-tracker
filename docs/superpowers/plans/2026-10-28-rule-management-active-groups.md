# Rule Management Active Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group the category list and show only recently used or learned application rules without deleting the built-in recognition catalog.

**Architecture:** Add a focused read-only usage service that derives 30-day process metrics and visibility from `activity_sessions`, factory categories, and loaded categories. The Qt page consumes this immutable snapshot to render grouped category headers and filtered application rows while retaining the full rule payload in the existing advanced editor.

**Tech Stack:** Python 3, SQLite, PySide6, pytest

---

### Task 1: Rule usage snapshot

**Files:**
- Create: `src/daylens/services/rule_usage_service.py`
- Create: `tests/test_rule_usage_service.py`

- [ ] Write failing tests for recent matches, case-insensitive deduplication, learned rules, hidden factory candidates, empty history fallback, and query failure degradation.
- [ ] Run `python -m pytest tests/test_rule_usage_service.py -q` and confirm the missing service failure.
- [ ] Implement `load_rule_usage_snapshot(db_path, categories, factory_categories, days=30)` returning per-category visible processes, hidden factory count, hit count, effective seconds, last-seen date, and a `has_history` flag.
- [ ] Run the focused tests and commit the green implementation.

### Task 2: Grouped classification list

**Files:**
- Modify: `src/daylens/gui/pages/rule_config.py`
- Modify: `tests/test_rule_config_page.py`

- [ ] Write failing GUI tests that require stable group headers, non-selectable headers, original category keys, and first valid category selection.
- [ ] Run the focused tests and confirm failure against the flat list.
- [ ] Add the fixed group mapping and render group header rows plus child category rows without changing the editor model.
- [ ] Make selection helpers ignore header rows and preserve dirty-editor behavior.
- [ ] Run focused rule-page tests and commit.

### Task 3: Active application rows

**Files:**
- Modify: `src/daylens/gui/pages/rule_config.py`
- Modify: `tests/test_rule_config_page.py`
- Modify: `tests/test_local_rules_simple.py`

- [ ] Write failing tests that recent and learned processes remain visible, unused factory processes are hidden, metadata appears in tooltips, and the full advanced process list remains intact.
- [ ] Run the focused tests and confirm the old page exposes every process.
- [ ] Load one snapshot per page refresh, filter `_refresh_applications`, update category summaries, and preserve full rule editing and removal semantics.
- [ ] Run all rule-management tests and commit.

### Task 4: Verification and release

**Files:**
- Create: `docs/reviews/2026-10-28-rule-management-active-groups-result.md`

- [ ] Run `python -m pytest -q`, `python -m compileall -q src tests`, `python tests/test_gui_smoke.py`, and `git diff --check`.
- [ ] Build with `python tools/build_release.py --stage-only`.
- [ ] Record real rule counts, tests, release hashes, backup/recovery path, and visible GUI checks.
- [ ] Safely stop DayLens, publish staging while retaining `release_previous`, refresh the shortcut, restart once, and verify a visible responsive window.
- [ ] Commit the verification record.

