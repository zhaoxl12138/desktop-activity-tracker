# Retire Local Behavior Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the local behavior-profile foreground feature and report appendices while preserving compatibility and independent trust validation.

**Architecture:** Delete the UI and report call chain at its actual consumers, keep the legacy settings key as inert compatible state, then remove the now-unreferenced profile and experiment modules. Regression tests verify visible behavior and generated artifacts rather than retaining tests for retired internals.

**Tech Stack:** Python 3.10+、PySide6、SQLite、pytest、PyInstaller。

---

### Task 1: Add retirement regression tests

**Files:**
- Create: `tests/test_behavior_profile_retirement.py`
- Modify: `tests/test_task_intelligence_settings.py`
- Delete: `tests/test_behavior_v18.py`

- [ ] Add a report-center test asserting no behavior-profile button or handler exists.
- [ ] Add a settings test asserting the checkbox is absent and a legacy true value survives saving unrelated settings.
- [ ] Add daily, weekly and monthly report tests for both normal generation and data-insufficient paths, asserting no behavior-profile diagnostic text is appended.
- [ ] Run the new tests and verify they fail against the current implementation.

### Task 2: Remove foreground and report integrations

**Files:**
- Modify: `src/daylens/gui/pages/reports.py`
- Modify: `src/daylens/gui/widgets/intelligence_settings.py`
- Modify: `src/daylens/exporter.py`
- Delete: `src/daylens/gui/widgets/behavior_dialog.py`

- [ ] Remove the report-center button, callback and dialog import.
- [ ] Remove the settings checkbox and preserve the loaded legacy value when saving.
- [ ] Remove all five report append calls, including weekly/monthly insufficient-data branches.
- [ ] Run the retirement tests and verify the public behavior is green.

### Task 3: Delete dead implementation and documentation claims

**Files:**
- Delete: `src/daylens/services/behavior_profile_service.py`
- Delete: `src/daylens/services/behavior_experiment_service.py`
- Modify: `README.md`

- [ ] Confirm no runtime imports remain with `rg`.
- [ ] Delete the unreferenced services and replace the README feature section with no current behavior-profile claim.
- [ ] Run targeted settings, report, exporter, trusted-metrics and retirement tests.

### Task 4: Full verification and release

**Files:**
- Create: `docs/reviews/2026-10-29-behavior-profile-retirement-result.md`

- [ ] Run full pytest, compileall and GUI smoke.
- [ ] Run `python tools/build_release.py --stage-only`.
- [ ] Record actual results and changed files.
- [ ] Commit, fast-forward main, publish through maintenance exit, restart one canonical process and verify its visible responsive window.
