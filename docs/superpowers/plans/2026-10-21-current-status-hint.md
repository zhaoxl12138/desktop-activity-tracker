# Current Status Hint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the poetry UI and settings, replacing its Today header line with a real-time recording status hint.

**Architecture:** A pure status presenter maps the latest sample and worker health into text, semantic color, and tooltip. MainWindow updates one existing ElidedLabel on sample, health, navigation, and pause changes. Settings persistence discards the retired flag while the SQLite poetry table and data stay intact.

**Tech Stack:** Python, PySide6, SQLite, pytest.

---

### Task 1: Pure status presenter

**Files:** Create `src/daylens/services/current_status_hint.py`; create `tests/test_current_status_hint.py`.

- [ ] Write failing parameterized tests for fatal, paused, delayed, idle, passive, engaged, missing sample, missing category, and sensitive sample fields.
- [ ] Run `python -m pytest tests/test_current_status_hint.py -q` and confirm the missing presenter causes failure.
- [ ] Implement `build_current_status_hint(sample, health)` returning a frozen `StatusHint(text, kind, tooltip)`; use only `category_name`, `engaged_seconds`, `persistent_idle`, and `attention_state` from samples.
- [ ] Re-run the focused test and confirm it passes.

### Task 2: MainWindow updates and display

**Files:** Modify `src/daylens/gui/main_window.py`; modify `tests/test_main_window_recording_health.py`; modify `tests/test_ui_responsive_layout.py`.

- [ ] Add a failing Qt test showing the Today hint updates on sample/health changes, hides on other pages, and remains plain text.
- [ ] Run focused tests and confirm failure at the missing behavior.
- [ ] Replace poetry refresh calls with `_update_current_status_hint()`, applying semantic colors and tooltip. Invoke it on navigation, sample, health, pause, and config/theme refresh.
- [ ] Re-run focused Qt tests.

### Task 3: Retire poetry settings and runtime code

**Files:** Modify `src/daylens/gui/pages/settings.py`, `src/daylens/services/settings_service.py`, `src/daylens/repositories/settings_repository.py`, `src/daylens/services/shell_service.py`, `src/daylens/database.py`, `tests/test_stage_c_shell.py`, `tests/test_database_architecture.py`; delete `src/daylens/repositories/poetry_repository.py`, `tests/test_poetry_hint.py`, `tools/fetch_poetry.py`, `tools/migrate_poetry.py`.

- [ ] Change the settings test to require no poetry key after save, including when old config/DB settings contain it; add a UI assertion that the checkbox is absent.
- [ ] Run focused settings tests and confirm the old behavior fails them.
- [ ] Remove poetry UI, service/repository routes, and import scripts. Delete the retired settings key from the settings table on save, and from the in-memory config. Keep `poetry_lines` schema/data untouched.
- [ ] Re-run focused tests and check `rg` shows no active poetry references outside schema and historical docs.

### Task 4: Integration and release validation

**Files:** No new product files expected.

- [ ] Run focused tests, then `python -m pytest -q`, `python -m compileall -q src`, and `git diff --check`.
- [ ] Run GUI smoke at 1280×720 and verify label visibility, no clipping, and database poetry row count unchanged.
- [ ] Build the release executable with the existing build script; launch the canonical release path and verify one responsive process.
- [ ] Inspect final diff and report test/build evidence and any remaining limitation.
