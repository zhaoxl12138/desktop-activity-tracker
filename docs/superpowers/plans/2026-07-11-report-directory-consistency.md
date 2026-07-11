# Report Directory Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use one database-relative report directory across the main window, report pages, and tray actions while making the derived setting read-only.

**Architecture:** `gui_bootstrap` remains the only place that derives `reports_dir`. It injects the same value into `TrayManager` and `MainWindow`; settings displays the value without pretending it is independently configurable.

**Tech Stack:** Python, PySide6, pytest.

---

### Task 1: Inject the shared report directory into the tray

**Files:**
- Modify: `src/daylens/gui/tray_manager.py`
- Modify: `src/daylens/services/gui_bootstrap.py`
- Create: `tests/test_tray_report_directory.py`
- Modify: `tests/test_main_architecture.py`

- [ ] **Step 1: Write failing tray tests**

Construct `TrayManager` with `reports_dir` while monkeypatching tray availability to false, then assert it stores the path. For action behavior, construct a lightweight instance with `__new__`, set `reports_dir`, patch `generate_daily_report` and `os.startfile`, and assert auto generation, manual generation, and opening use `<reports_dir>/daily` or `<reports_dir>` as appropriate.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest -q tests/test_tray_report_directory.py`

Expected: FAIL because `TrayManager.__init__` does not accept `reports_dir` and action methods derive paths from `get_data_dir()`.

- [ ] **Step 3: Implement constructor injection**

Change the signature to:

```python
def __init__(self, app, db_path, config, reports_dir):
    self.reports_dir = reports_dir
```

Use `os.path.join(self.reports_dir, "daily")` for daily generation and `self.reports_dir` for open-directory behavior. Remove the unused `get_data_dir` import. In bootstrap, construct the tray with `TrayManager(app, db_path, config, reports_dir)`.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest -q tests/test_tray_report_directory.py tests/test_main_architecture.py tests/test_gui_smoke.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/daylens/gui/tray_manager.py src/daylens/services/gui_bootstrap.py tests/test_tray_report_directory.py tests/test_main_architecture.py
git commit -m "fix: share report directory with tray actions"
```

### Task 2: Make the derived report directory read-only

**Files:**
- Modify: `src/daylens/gui/pages/settings.py`
- Modify: `tests/test_settings_page.py`

- [ ] **Step 1: Write failing UI test**

Build the settings page and assert `edit_reports.isReadOnly()` is true. Give browse buttons object names and assert no enabled report-directory browse button exists.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest -q tests/test_settings_page.py -k report_directory`

Expected: FAIL because the field is editable and has a browse button.

- [ ] **Step 3: Implement read-only presentation**

For `edit_reports`, call `setReadOnly(True)`, set explanatory tooltip text, and do not create a browse button. Keep database and Obsidian browse buttons unchanged.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest -q tests/test_settings_page.py tests/test_gui_smoke.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/daylens/gui/pages/settings.py tests/test_settings_page.py
git commit -m "fix: show derived report directory as read only"
```

### Task 3: Verify and publish

- [ ] Run `python -m pytest -q` and `python -m compileall -q src`.
- [ ] Fast-forward the isolated branch into local `main`, rerun tests, remove the owned worktree and branch.
- [ ] Run `python tools/build_release.py` and `powershell -NoProfile -ExecutionPolicy Bypass -File tools/fix_shortcut.ps1`.
- [ ] Start `release/DayLens.exe`; verify exactly one process and both shortcuts target it.
