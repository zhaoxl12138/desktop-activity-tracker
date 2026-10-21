# Remove AI Exclusions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the two AI exclusion settings and their behavior without weakening built-in redaction.

**Architecture:** The settings widget will expose only supported toggles, budget and credentials. The settings service will normalize legacy JSON by ignoring exclusion keys. The privacy layer retains title redaction and uses a stable revision compatible with the old empty-exclusion default.

**Tech Stack:** Python, PySide6, pytest, PyInstaller.

---

### Task 1: Characterize the desired behavior

**Files:** `tests/test_intelligence_scheduler.py`, `tests/test_settings_page.py`, `tests/test_stage_a_reliability.py`

- [ ] Add tests that legacy exclusion keys do not block `title_context`, disappear from `load_settings` and `save_settings`, and do not alter `privacy_revision`.
- [ ] Add a GUI assertion that `IntelligenceSettings` has no exclusion editors.
- [ ] Run targeted tests and verify failures specifically identify the old behavior.

### Task 2: Remove exclusion implementation

**Files:** `src/daylens/gui/widgets/intelligence_settings.py`, `src/daylens/services/intelligence_state.py`, `src/daylens/services/intelligence_privacy.py`

- [ ] Remove the two editors, their style loop entries and save payload values.
- [ ] Remove exclusion defaults, loading, validation and title checks; keep all regex redaction and title limits.
- [ ] Make `privacy_revision` return the old empty-exclusion revision for cached-data compatibility.
- [ ] Update obsolete exclusion tests to assert preserved redaction and correct downgraded behavior.

### Task 3: Verify and release

**Files:** `tests/test_scheduled_intelligence_reports.py` only if its fixture requires normalization.

- [ ] Run targeted pytest, full pytest, `compileall`, `git diff --check`, packaged GUI smoke and database-path check.
- [ ] Rebuild release, gracefully stop the old process, publish with a recoverable previous-version directory and restart one instance.
