# Dashboard Card Responsibilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor four homepage cards so work episodes, confidence, application usage, and time composition each have one distinct responsibility.

**Architecture:** Add pure dashboard-service builders for work episodes and stable application rows, then render their stable snapshot payloads in focused Qt widgets. Preserve existing snapshot and widget aliases as compatibility adapters while removing only redundant visual consumption.

**Tech Stack:** Python 3.11, PySide6, SQLite aggregate payloads, pytest, PyInstaller release script.

---

### Task 1: Work episode presentation model

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Test: `tests/test_dashboard_service.py`

- [ ] Add failing tests proving work sessions separated by at most 30 seconds merge across Codex/Chrome, non-work and long gaps split, counters are conserved, and malformed rows are skipped.
- [ ] Run `python -m pytest tests/test_dashboard_service.py -k "work_episode" -q` and confirm the new assertions fail because the builder and snapshot field are absent.
- [ ] Implement `build_work_episode_rows`, representative-title selection, stable application collection, and `work_episode_rows` snapshot wiring.
- [ ] Re-run the focused tests and require zero failures.

### Task 2: Work episode widget and low-confidence insight compression

**Files:**
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Modify: `src/daylens/gui/pages/today_overview.py`
- Test: `tests/test_dashboard_widgets.py`
- Test: `tests/test_homepage_redesign.py`
- Test: `tests/test_ui_responsive_layout.py`

- [ ] Add failing widget tests for the “关键工作片段” rows, five-row limit, old-snapshot fallback, low-confidence height, hidden action, and high-confidence full layout.
- [ ] Run the focused widget and homepage cases and confirm they fail for the missing presentation behavior.
- [ ] Add `WorkEpisodeListWidget`, retain `SessionTop3Widget` compatibility, wire `work_episode_rows`, and make `TrustedInsightCard` switch between compact and full modes.
- [ ] Re-run the focused tests and require zero failures at 1280×720.

### Task 3: Stable application identity and usage details

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Modify: `src/daylens/gui/pages/today_overview.py`
- Test: `tests/test_dashboard_service.py`
- Test: `tests/test_dashboard_widgets.py`

- [ ] Add failing tests showing process aliases merge case-insensitively, different browser executables remain separate even when labels are similar, and rows carry foreground, engaged, passive, and top-purpose fields.
- [ ] Run the focused top-app tests and confirm the new contract fails.
- [ ] Implement stable identity grouping and compact two-line rows with explicit foreground and attention breakdown.
- [ ] Re-run the focused tests and require zero failures.

### Task 4: Pure time-distribution card

**Files:**
- Modify: `src/daylens/gui/pages/today_overview.py`
- Test: `tests/test_homepage_redesign.py`

- [ ] Replace the existing comparison-row assertions with failing assertions that the card has no “较昨日” labels while status and category composition remain.
- [ ] Run the focused homepage tests and confirm failure against the current redundant row.
- [ ] Remove the comparison row and its snapshot update path while keeping `day_comparison` payload compatibility.
- [ ] Re-run the focused tests and require zero failures.

### Task 5: Verification and release

**Files:**
- Verify: `tests/`
- Verify: `scripts/build_release.ps1`

- [ ] Run focused dashboard service, widget, homepage, responsive-layout, and GUI smoke tests.
- [ ] Run the complete pytest suite and require zero failures.
- [ ] Run `python -m compileall -q src tests` and `git diff --check`.
- [ ] Rebuild the release with the repository release script.
- [ ] Verify the release configuration and runtime resolve only `D:\\OfficeSoftware\\DayLens\\data\\usage.db`, then launch one release process and inspect the homepage layout.

