# DayLens Data Repair and Report Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely repair known legacy entertainment-idle data errors, show a manual repair preview, preserve per-title software categories, and backfill missing daily reports without blocking the GUI.

**Architecture:** Put database inspection, backup, and repair in `data_quality_service` with transaction boundaries and a one-time metadata marker. Keep report backfill in `reports_service` and run it through a small dedicated `QThread`. Extend statistics rows so category identity travels with every title instead of being inferred later.

**Tech Stack:** Python 3.14, SQLite WAL/backup API, PySide6/QThread, pytest.

---

### Task 1: Safe legacy Session repair service

**Files:**
- Modify: `src/daylens/services/data_quality_service.py`
- Modify: `src/daylens/services/bootstrap_runtime_service.py`
- Test: `tests/test_data_quality_service.py`

- [ ] **Step 1: Add failing preview and repair tests**

Add helpers to create one repairable legacy row and one unrelated mismatch. Test that only the legacy row is repairable:

```python
def test_preview_repairable_sessions_only_selects_legacy_entertainment_idle(tmp_path):
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO activity_sessions
           (session_id,start_time,end_time,date,process_name,category_key,
            category_name,duration_seconds,effective_seconds,idle_seconds,switch_reason)
           VALUES ('legacy','2026-07-01 10:00:00','2026-07-01 10:10:00',
                   '2026-07-01','QyClient.exe','video','娱乐休闲',600,600,301,
                   'entertainment_idle')"""
    )
    conn.execute(
        """INSERT INTO activity_sessions
           (session_id,start_time,end_time,date,process_name,category_key,
            category_name,duration_seconds,effective_seconds,idle_seconds,switch_reason)
           VALUES ('other','2026-07-01 11:00:00','2026-07-01 11:10:00',
                   '2026-07-01','Code.exe','coding','编程开发',10,8,5,
                   'app_change')"""
    )
    conn.commit()
    conn.close()

    preview = preview_repairable_sessions(str(db_path))

    assert preview["repairable_count"] == 1
    assert preview["dates"] == ["2026-07-01"]
    assert preview["duplicate_idle_seconds"] == 301
```

Test backup failure leaves the row untouched:

```python
def test_repair_does_not_modify_database_when_backup_fails(tmp_path, monkeypatch):
    db_path = _create_repairable_database(tmp_path)
    monkeypatch.setattr(
        data_quality_service,
        "create_database_backup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("backup failed")),
    )

    with pytest.raises(OSError, match="backup failed"):
        repair_legacy_session_data(str(db_path))

    conn = sqlite3.connect(db_path)
    idle = conn.execute(
        "SELECT idle_seconds FROM activity_sessions WHERE session_id='legacy'"
    ).fetchone()[0]
    conn.close()
    assert idle == 301
```

Test a successful repair creates a backup and clears only the duplicated idle value:

```python
def test_repair_creates_backup_and_repairs_matching_rows(tmp_path):
    db_path = _create_repairable_database(tmp_path)

    result = repair_legacy_session_data(str(db_path), reason="manual-test")

    assert result["repaired_count"] == 1
    assert Path(result["backup_path"]).is_file()
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT duration_seconds,effective_seconds,idle_seconds "
        "FROM activity_sessions WHERE session_id='legacy'"
    ).fetchone()
    conn.close()
    assert row == (600, 600, 0)
```

Test automatic repair writes a marker and does not create another backup on the second call:

```python
def test_auto_repair_runs_once(tmp_path):
    db_path = _create_repairable_database(tmp_path)

    first = auto_repair_legacy_sessions(str(db_path))
    second = auto_repair_legacy_sessions(str(db_path))

    assert first["status"] == "repaired"
    assert second["status"] == "already_completed"
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1
```

- [ ] **Step 2: Run the repair tests and verify they fail**

Run:

```powershell
py -m pytest tests/test_data_quality_service.py -q
```

Expected: failures because the preview, backup, repair, and auto-repair functions do not exist.

- [ ] **Step 3: Implement preview, backup, transaction repair, and one-time marker**

Add these public functions to `data_quality_service.py`:

```python
REPAIR_META_KEY = "legacy_entertainment_idle_repair_v1"


def preview_repairable_sessions(db_path: str) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """SELECT date,idle_seconds
               FROM activity_sessions
               WHERE switch_reason='entertainment_idle'
                 AND idle_seconds > 0
                 AND effective_seconds + idle_seconds > duration_seconds + 1"""
        ).fetchall()
        dates = sorted({str(row[0]) for row in rows})
        return {
            "repairable_count": len(rows),
            "dates": dates,
            "duplicate_idle_seconds": sum(int(row[1] or 0) for row in rows),
        }
    finally:
        conn.close()
```

Implement `create_database_backup(db_path, reason)` using `sqlite3.Connection.backup()`. Store backups under `<db directory>/backups` using a microsecond timestamp. Copy existing `-wal` and `-shm` files beside the backup using suffixes `.wal` and `.shm`.

Implement `repair_legacy_session_data(db_path, reason="manual")`:

1. Call `preview_repairable_sessions`.
2. Return a zero-change result without a backup if no rows match.
3. Create the backup before opening the write transaction.
4. Execute `BEGIN IMMEDIATE`.
5. Update only the predicate above with `idle_seconds=0`.
6. Verify the predicate returns zero rows.
7. Commit or roll back.
8. Return preview counts and `backup_path`.

Implement `auto_repair_legacy_sessions(db_path)`:

1. Read `schema_meta[REPAIR_META_KEY]`.
2. Return `already_completed` if present.
3. Run the preview.
4. If rows exist, call `repair_legacy_session_data(..., reason="startup")`.
5. Write the marker only after successful repair, or immediately when no rows exist.

- [ ] **Step 4: Close the bootstrap initialization connection and run auto repair**

Change `prepare_runtime_config()` to close the connection returned by `database.init_db()` and invoke auto repair before initializing the shared read connection:

```python
connection = database.init_db(db_path)
database.close_db(connection)
try:
    auto_repair_legacy_sessions(db_path)
except Exception as exc:
    import sys
    print(f"[DataRepair] Startup repair failed: {exc}", file=sys.stderr)
database.init_shared_read_conn(db_path)
```

Startup repair failure must not prevent DayLens from recording.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
py -m pytest tests/test_data_quality_service.py tests/test_release_runtime.py -q
```

Expected: all focused tests pass.

### Task 2: Manual preview-and-repair UI

**Files:**
- Modify: `src/daylens/gui/pages/settings.py:190-345`
- Test: `tests/test_settings_page.py`

- [ ] **Step 1: Add a failing UI test**

Create a temporary database with one legacy repairable row, construct `SettingsPage`, find the data-quality button, and verify its label communicates repair:

```python
def test_settings_data_quality_action_offers_preview_and_repair(tmp_path):
    page = _build_settings_page_with_database(tmp_path)
    labels = [button.text() for button in page.findChildren(QPushButton)]
    assert "预览并修复数据" in labels
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
py -m pytest tests/test_settings_page.py -q
```

Expected: FAIL because the button is still labeled `检查数据质量`.

- [ ] **Step 3: Implement the two-stage interaction**

Import:

```python
from ...services.data_quality_service import (
    inspect_data_quality,
    preview_repairable_sessions,
    repair_legacy_session_data,
)
```

Rename the button to `预览并修复数据`.

In `_check_data_quality()`:

1. Run both inspection functions.
2. If `repairable_count == 0`, show the existing information/warning result and return.
3. Show a `QMessageBox.question` containing repairable count, affected dates, duplicate idle duration, and the number of other issues.
4. If the user confirms, call `repair_legacy_session_data`.
5. Re-run `inspect_data_quality`.
6. Show repaired count, remaining issue count, and backup path.
7. On exception, show a warning without changing the current page.

- [ ] **Step 4: Run settings tests**

Run:

```powershell
py -m pytest tests/test_settings_page.py tests/test_data_quality_service.py -q
```

Expected: all focused tests pass.

### Task 3: Preserve category identity for every software title

**Files:**
- Modify: `src/daylens/repositories/stats_repository.py:75-132`
- Modify: `src/daylens/repositories/stats_repository.py:1-65`
- Modify: `src/daylens/services/software_stats_service.py:10-49`
- Create: `tests/test_software_stats_categories.py`

- [ ] **Step 1: Write a failing integration test**

Insert two current-date Chrome sessions with different titles and categories. Assert the service returns each title with its own category:

```python
def test_browser_titles_keep_their_own_categories(tmp_path):
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """INSERT INTO activity_sessions
           (session_id,start_time,end_time,date,process_name,normalized_title,
            category_key,category_name,duration_seconds,effective_seconds,idle_seconds)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [
            ("video", f"{today} 10:00:00", f"{today} 10:10:00", today,
             "chrome.exe", "YouTube", "video", "娱乐休闲", 600, 600, 0),
            ("code", f"{today} 11:00:00", f"{today} 11:10:00", today,
             "chrome.exe", "GitHub", "coding", "编程开发", 600, 600, 0),
        ],
    )
    conn.commit()
    conn.close()

    rows = software_stats_service.load_software_rows(
        str(db_path),
        {"chrome.exe": "Chrome"},
    )
    categories = {row["title"]: row["category_key"] for row in rows}

    assert categories["YouTube"] == "entertainment"
    assert categories["GitHub"] == "work"
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
py -m pytest tests/test_software_stats_categories.py -q
```

Expected: FAIL because both rows inherit the first category found for `chrome.exe`.

- [ ] **Step 3: Include category fields in title-detail queries**

For Session-backed data, select `category_key` and `category_name`, then group by:

```sql
GROUP BY process_name, normalized_title, category_key, category_name
```

For legacy log-backed data, select the same category fields and group by:

```sql
GROUP BY process_name, window_title, category_key, category_name
```

- [ ] **Step 4: Remove process-level category inference**

In `load_software_rows()`, stop iterating over `by_app`. Read the category from each detail row:

```python
raw_category_name = str(app.get("category_name", "") or "")
raw_category_key = str(app.get("category_key", "") or "")
category_name = normalize_category_display_name(
    raw_category_key,
    raw_category_name,
)
category_key = normalize_category_bucket_key(
    raw_category_key,
    raw_category_name,
)
```

- [ ] **Step 5: Run focused statistics tests**

Run:

```powershell
py -m pytest tests/test_software_stats_categories.py tests/test_software_stats_export.py tests/test_mixed_history_queries.py -q
```

Expected: all focused tests pass.

### Task 4: Missing daily report backfill service and worker

**Files:**
- Modify: `src/daylens/services/reports_service.py`
- Create: `src/daylens/gui/report_backfill_worker.py`
- Modify: `src/daylens/gui/main_window.py:1-135`
- Modify: `tests/test_reports_service.py`

- [ ] **Step 1: Write failing report backfill tests**

Test that existing reports and today are skipped while missing historical dates are generated:

```python
def test_backfill_generates_only_missing_historical_reports(tmp_path, monkeypatch):
    db_path = _create_database_with_dates(
        tmp_path,
        ["2026-07-20", "2026-07-21", "2026-07-24"],
    )
    reports_dir = tmp_path / "reports"
    existing = Path(
        exporter.daily_report_path(str(reports_dir / "daily"), "2026-07-20")
    )
    existing.parent.mkdir(parents=True)
    existing.write_text("existing", encoding="utf-8")
    generated_dates = []

    def fake_export(_db, date_str, output_dir):
        generated_dates.append(date_str)
        path = Path(exporter.daily_report_path(output_dir, date_str))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(date_str, encoding="utf-8")
        return str(path)

    monkeypatch.setattr(reports_service.exporter, "export_markdown", fake_export)

    result = reports_service.backfill_missing_daily_reports(
        str(db_path),
        str(reports_dir),
        today_str="2026-07-24",
    )

    assert generated_dates == ["2026-07-21"]
    assert result["generated_count"] == 1
    assert result["skipped_count"] == 2
```

Test one failed date does not stop the next missing date:

```python
def test_backfill_continues_after_one_report_failure(tmp_path, monkeypatch):
    db_path = _create_database_with_dates(
        tmp_path,
        ["2026-07-20", "2026-07-21", "2026-07-22"],
    )

    def fake_export(_db, date_str, output_dir):
        if date_str == "2026-07-20":
            raise RuntimeError("broken day")
        path = Path(exporter.daily_report_path(output_dir, date_str))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(date_str, encoding="utf-8")
        return str(path)

    monkeypatch.setattr(reports_service.exporter, "export_markdown", fake_export)

    result = reports_service.backfill_missing_daily_reports(
        str(db_path),
        str(tmp_path / "reports"),
        today_str="2026-07-23",
    )

    assert result["generated_count"] == 2
    assert result["failure_count"] == 1
    assert result["failures"][0]["date"] == "2026-07-20"
```

- [ ] **Step 2: Run report tests and verify they fail**

Run:

```powershell
py -m pytest tests/test_reports_service.py -q
```

Expected: failures because `backfill_missing_daily_reports` does not exist.

- [ ] **Step 3: Implement backfill service**

Add `list_recorded_dates(db_path)` using one SQLite query:

```sql
SELECT date FROM activity_sessions WHERE date != ''
UNION
SELECT date FROM activity_logs WHERE date != ''
ORDER BY date
```

Implement:

```python
def backfill_missing_daily_reports(
    db_path: str,
    reports_dir: str,
    obsidian_path: str = "",
    today_str: str | None = None,
) -> dict[str, object]:
```

For each recorded date:

- Skip `date_str >= today_str`.
- Calculate `exporter.daily_report_path(os.path.join(reports_dir, "daily"), date_str)`.
- Skip existing files.
- Generate missing Markdown reports.
- Sync only newly generated files when `obsidian_path` is configured.
- Catch exceptions per date and append `{"date": date_str, "error": str(exc)}`.
- Return generated, skipped, and failure counts plus paths/failures.

- [ ] **Step 4: Add a dedicated QThread**

Create `ReportBackfillWorker(QThread)` with:

```python
completed = Signal(dict)
failed = Signal(str)
```

Its `run()` method calls `backfill_missing_daily_reports`. It emits `failed` only for a service-level exception; per-date failures remain in the result.

- [ ] **Step 5: Wire the worker into MainWindow**

Import `ReportBackfillWorker`. In `MainWindow.__init__`, set:

```python
self._report_backfill_worker = None
QTimer.singleShot(15000, self._start_report_backfill)
```

Implement `_start_report_backfill()`:

- Return if a worker already exists or is running.
- Construct it with database path, reports directory, and live Obsidian path.
- Connect `completed` and `failed` to logging methods.
- Connect `finished` to a cleanup method that calls `deleteLater()` and clears the reference.
- Start the worker.

- [ ] **Step 6: Run focused report and GUI tests**

Run:

```powershell
py -m pytest tests/test_reports_service.py tests/test_gui_smoke.py tests/test_main_architecture.py -q
```

Expected: all focused tests pass.

### Task 5: Full verification, live repair, release, and restart

**Files:**
- Verify all modified production and test files.

- [ ] **Step 1: Run the complete test suite**

Run:

```powershell
py -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run syntax and diff checks**

Run:

```powershell
py -m compileall -q src tests
git diff --check
```

Expected: both commands exit successfully.

- [ ] **Step 3: Commit implementation**

Stage only the files in this plan and commit:

```powershell
git commit -m "fix: repair legacy data and backfill reports"
```

- [ ] **Step 4: Build the release**

Run:

```powershell
py tools/build_release.py
```

Expected: the build succeeds and refreshes `C:\Users\Administrator\Desktop\DayLens.lnk`.

- [ ] **Step 5: Restart DayLens**

Run:

```powershell
Start-Process -FilePath "D:\OfficeSoftware\DayLens\release\DayLens.exe" -WindowStyle Hidden
Start-Sleep -Seconds 5
```

Verify exactly one process runs from the release path.

- [ ] **Step 6: Verify live database repair and backup**

Confirm:

- `schema_meta` contains `legacy_entertainment_idle_repair_v1`.
- No Session matches the repair predicate.
- A timestamped startup backup exists under `data/backups`.
- `PRAGMA integrity_check` returns `ok`.
- General data-quality inspection has fewer issues than before.

- [ ] **Step 7: Verify report coverage**

Compare recorded historical dates to report files. Confirm every date before today with recorded data has a Markdown daily report, and today remains managed by the hourly refresh.

