# Runtime Settings and Report Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make database-path changes restart DayLens safely, keep current weekly/monthly reports fresh, and allow an empty Obsidian path to remove stale persistent overrides.

**Architecture:** Keep persistence rules in `settings_service`, isolate restart command construction and scheduling in a new `restart_service`, and let `SettingsPage` emit a restart request that `MainWindow` handles. Current-period report generation becomes an idempotent five-minute refresh using the existing fixed filenames and exporter functions.

**Tech Stack:** Python 3.11+, PySide6, pytest, YAML, Windows PowerShell, PyInstaller.

---

### Task 1: Clear stale user configuration overrides

**Files:**
- Modify: `src/daylens/utils.py:299-315`
- Modify: `src/daylens/services/settings_service.py:60-66`
- Modify: `tests/test_project_metadata.py`

- [ ] **Step 1: Write the failing persistence test**

Add a test that redirects `daylens.get_data_dir` to `tmp_path`, writes an existing `user_config.yaml`, calls `save_user_config({}, remove_keys={"obsidian_output_path"})`, and asserts that the Obsidian key is absent while `db_path` remains.

```python
def test_save_user_config_can_remove_stale_override(tmp_path, monkeypatch):
    monkeypatch.setattr(daylens, "get_data_dir", lambda: str(tmp_path))
    user_path = tmp_path / "user_config.yaml"
    user_path.write_text(
        "obsidian_output_path: E:/old/month\ndb_path: D:/data/usage.db\n",
        encoding="utf-8",
    )

    save_user_config({}, remove_keys={"obsidian_output_path"})

    saved = yaml.safe_load(user_path.read_text(encoding="utf-8"))
    assert "obsidian_output_path" not in saved
    assert saved["db_path"] == "D:/data/usage.db"
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest -q tests/test_project_metadata.py::test_save_user_config_can_remove_stale_override`

Expected: FAIL because `save_user_config` does not accept `remove_keys`.

- [ ] **Step 3: Implement explicit key removal**

Change the persistence helper to remove requested keys before merging overrides.

```python
def save_user_config(overrides: dict, remove_keys: set[str] | None = None) -> None:
    # existing load logic
    for key in remove_keys or set():
        existing.pop(key, None)
    existing.update(overrides)
    # existing write logic
```

In `save_page_config`, persist nonempty values and request deletion when the Obsidian path is empty.

```python
persisted = {
    key: updated[key]
    for key in ("obsidian_output_path", "theme", "db_path")
    if key in updated and updated[key]
}
remove_keys = {"obsidian_output_path"} if not obsidian_output_path else set()
save_user_config(persisted, remove_keys=remove_keys)
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest -q tests/test_project_metadata.py tests/test_category_labels.py`

Expected: PASS.

- [ ] **Step 5: Commit the persistence fix**

```powershell
git add src/daylens/utils.py src/daylens/services/settings_service.py tests/test_project_metadata.py
git commit -m "fix: clear stale user configuration overrides"
```

### Task 2: Refresh current weekly and monthly reports

**Files:**
- Modify: `src/daylens/services/reports_service.py:175-205`
- Modify: `src/daylens/gui/main_window.py:619-648`
- Modify: `tests/test_reports_service.py`

- [ ] **Step 1: Write the failing refresh test**

Use real files for the existing report markers and monkeypatch only the expensive exporter boundary.

```python
def test_auto_generate_refreshes_existing_current_reports(tmp_path, monkeypatch):
    weekly = Path(reports_service.weekly_report_path(str(tmp_path)))
    monthly = Path(reports_service.monthly_report_path(str(tmp_path)))
    weekly.parent.mkdir(parents=True, exist_ok=True)
    monthly.parent.mkdir(parents=True, exist_ok=True)
    weekly.write_text("stale weekly", encoding="utf-8")
    monthly.write_text("stale monthly", encoding="utf-8")
    calls = []
    monkeypatch.setattr(reports_service, "generate_weekly_report", lambda *_: calls.append("weekly") or str(weekly))
    monkeypatch.setattr(reports_service, "generate_monthly_report", lambda *_: calls.append("monthly") or str(monthly))

    generated = reports_service.auto_generate_current_reports("usage.db", str(tmp_path))

    assert calls == ["weekly", "monthly"]
    assert generated == [str(weekly), str(monthly)]
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest -q tests/test_reports_service.py::test_auto_generate_refreshes_existing_current_reports`

Expected: FAIL because existing files suppress both generators outside the closing schedule window.

- [ ] **Step 3: Make current-period generation idempotently refresh both files**

Remove the file-existence gates in `auto_generate_current_reports`; call each generator once and retain the existing per-generator exception handling. In `MainWindow._check_report_schedule`, retain the 290-second debounce but remove the early return based on `weekly_report_exists` and `monthly_report_exists`, then always call `auto_generate_current_reports` after the debounce.

```python
if now - last < 290:
    return
self._last_report_gen = now
generated = auto_generate_current_reports(self.db_path, self.reports_dir)
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest -q tests/test_reports_service.py tests/test_reports_page.py tests/test_main_architecture.py`

Expected: PASS.

- [ ] **Step 5: Commit the report refresh fix**

```powershell
git add src/daylens/services/reports_service.py src/daylens/gui/main_window.py tests/test_reports_service.py
git commit -m "fix: refresh current period reports"
```

### Task 3: Restart safely after database path changes

**Files:**
- Create: `src/daylens/services/restart_service.py`
- Create: `tests/test_restart_service.py`
- Modify: `src/daylens/gui/pages/settings.py:50-230`
- Modify: `src/daylens/gui/main_window.py:84-140,654-665`
- Modify: `tests/test_gui_smoke.py`

- [ ] **Step 1: Write failing tests for path comparison and restart scheduling**

```python
def test_database_path_changed_ignores_equivalent_windows_paths():
    assert database_path_changed(r"D:\\Data\\usage.db", r"d:/data/usage.db") is False
    assert database_path_changed(r"D:\\Data\\usage.db", r"D:\\Other\\usage.db") is True


def test_schedule_restart_starts_hidden_waiter(monkeypatch):
    captured = {}
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kwargs: captured.update(args=args, kwargs=kwargs) or object())

    schedule_restart([r"D:\\OfficeSoftware\\DayLens\\release\\DayLens.exe"], current_pid=123)

    assert captured["args"][:4] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle"]
    assert captured["kwargs"]["creationflags"] == subprocess.CREATE_NO_WINDOW
```

- [ ] **Step 2: Run the restart-service tests and verify RED**

Run: `python -m pytest -q tests/test_restart_service.py`

Expected: collection FAIL because `daylens.services.restart_service` does not exist.

- [ ] **Step 3: Implement the restart service**

Provide three focused functions:

```python
def database_path_changed(current: str, requested: str) -> bool:
    return os.path.normcase(os.path.abspath(current)) != os.path.normcase(os.path.abspath(requested))


def current_launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, os.path.abspath(sys.argv[0]), *sys.argv[1:]]


def schedule_restart(command: list[str], current_pid: int | None = None) -> None:
    env = os.environ.copy()
    env["DAYLENS_RESTART_COMMAND"] = json.dumps(command, ensure_ascii=False)
    script = (
        "$cmd = ConvertFrom-Json $env:DAYLENS_RESTART_COMMAND; "
        f"Wait-Process -Id {current_pid or os.getpid()} -ErrorAction SilentlyContinue; "
        "Start-Process -FilePath $cmd[0] -ArgumentList @($cmd | Select-Object -Skip 1)"
    )
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
```

- [ ] **Step 4: Run restart-service tests and verify GREEN**

Run: `python -m pytest -q tests/test_restart_service.py`

Expected: PASS.

- [ ] **Step 5: Write the failing SettingsPage signal test**

Extend the GUI test worker with counters. Build a `SettingsPage`, change only `edit_db`, accept message boxes, and assert `restart_requested` emits once while `worker.update_settings` is not called. A second case leaves the database path unchanged and asserts hot update occurs without restart.

```python
emissions = []
page.restart_requested.connect(lambda: emissions.append(True))
page.edit_db.setText(str(tmp_path / "new.db"))
page._save_all()
QApplication.processEvents()
assert emissions == [True]
assert worker.settings_updated is False
```

- [ ] **Step 6: Run the GUI signal test and verify RED**

Run: `python -m pytest -q tests/test_gui_smoke.py -k database_path`

Expected: FAIL because `SettingsPage.restart_requested` does not exist.

- [ ] **Step 7: Wire SettingsPage to MainWindow restart handling**

Add `restart_requested = Signal()` to `SettingsPage`. In `_save_all`, compare the previous effective path with the requested path before saving; on change, show a restart notice, emit the signal, and skip worker hot reload. Otherwise retain the existing hot update.

Connect the signal after page construction in `MainWindow` and implement `_restart_app`:

```python
def _restart_app(self) -> None:
    try:
        schedule_restart(current_launch_command())
    except Exception as exc:
        QMessageBox.warning(self, "重启失败", str(exc))
        return
    if self.worker:
        self.worker.stop()
        self.worker.wait(5000)
    QApplication.instance().quit()
```

The waiter is scheduled before stopping the worker; if scheduling fails, the current worker remains active. The waiter starts the replacement only after the old PID exits, so the single-instance mutex is no longer held.

- [ ] **Step 8: Run focused GUI and restart tests**

Run: `python -m pytest -q tests/test_restart_service.py tests/test_gui_smoke.py tests/test_release_runtime.py`

Expected: PASS.

- [ ] **Step 9: Commit the restart behavior**

```powershell
git add src/daylens/services/restart_service.py src/daylens/gui/pages/settings.py src/daylens/gui/main_window.py tests/test_restart_service.py tests/test_gui_smoke.py
git commit -m "fix: restart safely after database path changes"
```

### Task 4: Restore the live Obsidian root and verify the release

**Files:**
- Modify but do not commit: `config/config.yaml`
- Modify but do not commit: `data/user_config.yaml` (ignored runtime state)

- [ ] **Step 1: Restore both live configuration sources**

Set `obsidian_output_path` in both files to:

```yaml
obsidian_output_path: E:\obsidian_github\Daylog\时间追踪\桌面活动日报
```

Keep this machine-specific config out of the code commit.

- [ ] **Step 2: Run the full automated verification**

Run: `python -m pytest -q`

Expected: `104 passed` or more, with zero failures.

Run: `python -m compileall -q src`

Expected: exit code 0 with no output.

- [ ] **Step 3: Build the release and refresh shortcuts**

Run: `python tools/build_release.py`

Expected: PyInstaller exits 0, `release/DayLens.exe` exists, and the desktop shortcut is refreshed.

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tools/fix_shortcut.ps1`

Expected: `Shortcuts updated (desktop + startup)`.

- [ ] **Step 4: Start and verify the new release**

Run: `Start-Process -FilePath 'D:\OfficeSoftware\DayLens\release\DayLens.exe'`

Verify with PowerShell that the running process executable path resolves to `D:\OfficeSoftware\DayLens\release\DayLens.exe` and that only one DayLens process is running.

- [ ] **Step 5: Review final repository state**

Run: `git status --short --branch` and `git log -5 --oneline`.

Expected: implementation files committed; only the known machine-specific `config/config.yaml` change and pre-existing untracked user artifacts remain.
