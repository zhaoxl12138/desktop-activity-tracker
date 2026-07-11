# Settings State and Path Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make settings changes propagate to all live consumers, validate database file selection safely, and persist the actual startup-shortcut state.

**Architecture:** `SettingsPage` remains the coordinator for UI actions and emits a full saved-config signal. `settings_service` owns database-path normalization and safe persistence; `MainWindow` distributes successful settings to report and tray consumers without dynamically changing database connections.

**Tech Stack:** Python 3.14, PySide6 signals and file dialogs, YAML, SQLite, pytest.

---

### Task 1: Validate and normalize database paths before persistence

**Files:**
- Modify: `src/daylens/services/settings_service.py`
- Modify: `tests/test_settings_service.py`

- [ ] **Step 1: Add failing tests**

```python
def test_normalize_database_path_resolves_relative_path(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_service, "get_app_root", lambda: str(tmp_path))
    assert settings_service.normalize_database_path("data/new.db") == str(tmp_path / "data" / "new.db")


def test_empty_database_path_does_not_overwrite_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("db_path: original.db\n", encoding="utf-8")
    monkeypatch.setattr(settings_service, "save_user_config", lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="不能为空"):
        settings_service.save_page_config(
            config_path=str(config_path),
            db_path=str(tmp_path / "current.db"),
            config={"db_path": "original.db", "tracker": {}},
            sample_interval=1,
            idle_threshold=60,
            startup_enabled=False,
            new_db_path="",
            obsidian_output_path="",
        )
    assert config_path.read_text(encoding="utf-8") == "db_path: original.db\n"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest -q tests/test_settings_service.py -k "normalize_database_path or empty_database_path"`

Expected: normalization test fails because the helper does not exist; empty-path preservation remains green.

- [ ] **Step 3: Implement normalization and use it before mutation**

```python
def normalize_database_path(path: str) -> str:
    expanded = os.path.expandvars(os.path.expanduser(path.strip()))
    if not expanded:
        raise ValueError("数据库路径不能为空")
    if not os.path.isabs(expanded):
        expanded = os.path.join(get_app_root(), expanded)
    return os.path.abspath(expanded)
```

Call the helper before constructing `updated`, store the normalized value, initialize its schema, then write YAML and DB settings.

- [ ] **Step 4: Verify focused tests**

Run: `python -m pytest -q tests/test_settings_service.py tests/test_release_runtime.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/daylens/services/settings_service.py tests/test_settings_service.py
git commit -m "fix: validate database paths before saving settings"
```

### Task 2: Correct file browsing and startup-state persistence

**Files:**
- Modify: `src/daylens/gui/pages/settings.py`
- Modify: `tests/test_settings_page.py`

- [ ] **Step 1: Add failing database-browser test**

```python
def test_database_browser_selects_a_db_file(tmp_path, monkeypatch):
    _app, page, _worker, _old_db = _build_page(tmp_path, monkeypatch)
    selected = str(tmp_path / "selected.db")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (selected, "SQLite (*.db)"))
    page._browse_database()
    assert page.edit_db.text() == selected
```

- [ ] **Step 2: Add failing startup-result test**

Have `_toggle_startup(True)` return `False`, capture `startup_enabled` passed to `save_page_config`, save, and assert the captured value and checkbox are both false.

```python
assert captured["startup_enabled"] is False
assert page.chk_startup.isChecked() is False
```

- [ ] **Step 3: Run tests and verify RED**

Run: `python -m pytest -q tests/test_settings_page.py -k "browser or startup"`

Expected: FAIL because `_browse_database` does not exist and `_save_all` ignores the actual shortcut result.

- [ ] **Step 4: Implement separate file and directory browsing**

Connect the database row button to `_browse_database`; keep report and Obsidian buttons connected to `_browse_dir`.

```python
def _browse_database(self) -> None:
    selected, _ = QFileDialog.getSaveFileName(
        self, "选择数据库文件", self.edit_db.text().strip(), "SQLite 数据库 (*.db);;所有文件 (*)"
    )
    if selected:
        if not os.path.splitext(selected)[1]:
            selected += ".db"
        self.edit_db.setText(selected)
```

- [ ] **Step 5: Return and persist actual startup state**

Change `_toggle_startup` to return `True` only after shortcut creation succeeds and `False` after disable or failure. In `_save_all`, assign the return value, update the checkbox, and pass that value to `save_page_config`. Wrap the save flow in `try/except`; on failure show `QMessageBox.warning` and return before signals or success messages.

- [ ] **Step 6: Verify focused tests**

Run: `python -m pytest -q tests/test_settings_page.py tests/test_settings_service.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/daylens/gui/pages/settings.py tests/test_settings_page.py
git commit -m "fix: validate settings paths and startup state"
```

### Task 3: Propagate saved configuration to live GUI consumers

**Files:**
- Modify: `src/daylens/gui/pages/settings.py`
- Modify: `src/daylens/gui/main_window.py`
- Modify: `src/daylens/gui/worker.py`
- Modify: `tests/test_settings_page.py`
- Modify: `tests/test_main_architecture.py`

- [ ] **Step 1: Add failing saved-config signal test**

Connect to `page.config_saved`, save without changing DB path, and assert one emitted dict contains the new Obsidian path.

```python
saved = []
page.config_saved.connect(saved.append)
page.edit_obsidian.setText("E:/vault/reports")
page._save_all()
assert saved[0]["obsidian_output_path"] == "E:/vault/reports"
```

- [ ] **Step 2: Add failing MainWindow propagation test**

Invoke `MainWindow._apply_saved_config` as an unbound method on a small object containing a report page and tray double.

```python
MainWindow._apply_saved_config(holder, config)
assert holder.config is config
assert holder.pages["reports"].obsidian_path == "E:/vault/reports"
assert holder.tray.config is config
```

- [ ] **Step 3: Run tests and verify RED**

Run: `python -m pytest -q tests/test_settings_page.py tests/test_main_architecture.py -k "saved_config or propagate"`

Expected: FAIL because the signal and handler do not exist.

- [ ] **Step 4: Implement signal and distribution handler**

Add `config_saved = Signal(dict)` and emit it after successful persistence, before an optional restart request. Connect it beside `restart_requested` whenever pages are constructed.

```python
def _apply_saved_config(self, config: dict) -> None:
    self.config = config
    obsidian_path = config.get("obsidian_output_path", "").strip()
    reports_page = self.pages.get("reports")
    if reports_page is not None:
        reports_page.obsidian_path = obsidian_path
    tray = getattr(self, "tray", None)
    if tray is not None:
        tray.config = config
```

Set `self.config = config` in `RecordingWorker.update_settings` so all runtime owners reference the latest configuration.

- [ ] **Step 5: Verify focused tests**

Run: `python -m pytest -q tests/test_settings_page.py tests/test_main_architecture.py tests/test_reports_page.py tests/test_dashboard_refresh_cadence.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/daylens/gui/pages/settings.py src/daylens/gui/main_window.py src/daylens/gui/worker.py tests/test_settings_page.py tests/test_main_architecture.py
git commit -m "fix: propagate saved settings to live components"
```

### Task 4: Full verification and release

**Files:**
- No tracked source changes expected.

- [ ] **Step 1: Run full tests and compile**

Run: `python -m pytest -q`

Expected: at least 109 tests, zero failures.

Run: `python -m compileall -q src`

Expected: exit code 0.

- [ ] **Step 2: Integrate the isolated branch into local `main`**

Use a fast-forward merge, rerun the full tests on `main`, then remove the owned worktree and branch.

- [ ] **Step 3: Build and refresh shortcuts**

Run: `python tools/build_release.py`

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tools/fix_shortcut.ps1`

Expected: both commands exit 0.

- [ ] **Step 4: Restart and verify**

Start `D:\OfficeSoftware\DayLens\release\DayLens.exe`; verify exactly one DayLens process and confirm both desktop and startup shortcuts target that executable.
