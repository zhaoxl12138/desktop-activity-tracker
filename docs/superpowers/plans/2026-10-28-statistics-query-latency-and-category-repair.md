# Statistics Query Latency and Category Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make statistics navigation and category expansion feel immediate, then safely correct deterministic category mistakes from 2026-09-29 through 2026-10-28 without changing any recorded time.

**Architecture:** Reuse the range aggregation already performed by the statistics repository and expose a bounded per-category detail snapshot, so clicks are pure UI operations. Add freshness-aware single-flight refresh behavior for tab reuse, limit report listing to the visible report type, and perform historical correction through a separately tested preview/apply service with backup and audit output.

**Tech Stack:** Python 3.11, PySide6, SQLite, pytest, existing `DashboardRefreshController`, repository/service/page layers.

---

## File map

- Modify `src/daylens/gui/pages/statistics.py`: stable tab ordering.
- Modify `src/daylens/repositories/stats_repository.py`: bounded detail data in the existing range snapshot.
- Modify `src/daylens/services/category_stats_service.py`: normalize and merge detail rows into large-category buckets.
- Modify `src/daylens/gui/pages/category_stats.py`: expand from the in-memory snapshot and remove the second query controller.
- Modify `src/daylens/gui/dashboard_refresh_controller.py`: freshness-aware foreground activation without duplicate reads.
- Modify `src/daylens/gui/pages/software_stats.py`: reuse a fresh snapshot when switching back.
- Modify `src/daylens/gui/pages/reports.py`: load only the visible report list and lightweight counts for hidden tabs.
- Create `src/daylens/services/historical_category_repair_service.py`: deterministic preview, backup, transactional apply, rule update and audit.
- Create `scripts/repair_recent_categories.py`: explicit preview/apply entry point for the one-time repair.
- Modify/add focused tests in `tests/test_category_range.py`, `tests/test_dashboard_refresh_controller.py`, `tests/test_reports_page.py`, `tests/test_stage_c_shell.py`.
- Create `tests/test_historical_category_repair.py`.
- Record verification in `docs/reviews/2026-10-28-statistics-query-latency-and-category-repair.md`.

### Task 1: Put realtime monitoring first without index coupling

**Files:**
- Modify: `src/daylens/gui/pages/statistics.py`
- Modify: `tests/test_category_range.py`

- [ ] **Step 1: Write the failing tab-order test**

```python
def test_statistics_places_live_monitor_before_software():
    pages = [QWidget() for _ in range(4)]
    page = StatisticsPage(pages[0], pages[1], pages[2], live_page=pages[3])
    assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == [
        "实时监控", "软件", "分类", "目标与成果",
    ]
    assert page.tabs.currentWidget() is pages[3]
    page.select_tab("category")
    assert page.tabs.currentWidget() is pages[1]
```

- [ ] **Step 2: Run the test and verify it fails on the old order**

Run: `pytest -q tests/test_category_range.py -k "statistics_places_live_monitor_before_software"`

Expected: FAIL because the first tab is `软件`.

- [ ] **Step 3: Add tabs in the new order**

```python
if live_page is not None:
    self.tabs.addTab(live_page, "实时监控")
self.tabs.addTab(software_page, "软件")
self.tabs.addTab(category_page, "分类")
if goal_page is not None:
    self.tabs.addTab(goal_page, "目标与成果")
if live_page is not None:
    self.tabs.setCurrentWidget(live_page)
```

- [ ] **Step 4: Run focused tests**

Run: `pytest -q tests/test_category_range.py -k "statistics"`

Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/daylens/gui/pages/statistics.py tests/test_category_range.py
git commit -m "ui: place realtime monitoring first"
```

### Task 2: Produce bounded category details in the existing aggregation

**Files:**
- Modify: `src/daylens/repositories/stats_repository.py`
- Modify: `src/daylens/services/category_stats_service.py`
- Modify: `tests/test_category_range.py`

- [ ] **Step 1: Write failing service tests for grouped details**

```python
def test_category_summary_contains_bounded_bucket_details(monkeypatch):
    monkeypatch.setattr(category_stats_service.database, "query_date_range_stats", lambda *_: {
        "by_category": [{"category_key": "gaming", "category_name": "游戏娱乐", "effective_seconds": 30}],
        "category_details": {
            "gaming": [
                {"process_name": f"game{i}.exe", "window_title": str(i),
                 "category_key": "gaming", "category_name": "游戏娱乐",
                 "effective_seconds": 10 - i}
                for i in range(8)
            ]
        },
    })
    result = category_stats_service.load_category_summary("usage.db", "2026-10-01", "2026-10-02")
    assert len(result["category_details"]["entertainment"]) == 5
```

- [ ] **Step 2: Verify the test fails because no detail snapshot exists**

Run: `pytest -q tests/test_category_range.py -k "bounded_bucket_details"`

Expected: FAIL with missing `category_details`.

- [ ] **Step 3: Preserve only five rows per source category in repository output**

Before removing `by_app_detail`, derive a bounded mapping:

```python
details: dict[str, list[dict]] = {}
for row in payload.get("by_app_detail", []):
    bucket = details.setdefault(str(row.get("category_key") or "other"), [])
    if len(bucket) < 5:
        bucket.append(dict(row))
payload["category_details"] = details
payload.pop("by_app_detail", None)
```

- [ ] **Step 4: Normalize source-category details into display buckets**

Add `_merge_category_details` in `category_stats_service.py`. It must normalize with `normalize_category_bucket_key`, merge rows with identical `(process_name, window_title)`, sort by effective seconds, and keep five rows per bucket.

- [ ] **Step 5: Run repository/service tests**

Run: `pytest -q tests/test_category_range.py tests/test_mixed_history_aggregation.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/daylens/repositories/stats_repository.py src/daylens/services/category_stats_service.py tests/test_category_range.py
git commit -m "perf: include bounded category details in snapshots"
```

### Task 3: Make category expansion query-free

**Files:**
- Modify: `src/daylens/gui/pages/category_stats.py`
- Modify: `tests/test_category_range.py`

- [ ] **Step 1: Replace old detail-query expectations with failing no-query tests**

```python
def test_category_click_uses_summary_snapshot_without_query(tmp_path, monkeypatch):
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary({
        "today": "2026-10-28", "range_start": "2026-09-29", "range_end": "2026-10-28",
        "categories": [{"category_key": "other", "category_name": "其他", "effective_seconds": 60}],
        "category_details": {"other": [{"process_name": "app.exe", "window_title": "A", "effective_seconds": 60}]},
        "total_effective_seconds": 60, "total_label": "范围总计",
    })
    monkeypatch.setattr(category_stats_service, "load_category_range_detail",
                        lambda *_: (_ for _ in ()).throw(AssertionError("unexpected DB read")))
    page._on_card_clicked("other")
    page._on_card_clicked("other")
    page._on_card_clicked("other")
    assert page._cards["other"]._expanded is True
```

- [ ] **Step 2: Verify the test fails through the old detail controller**

Run: `pytest -q tests/test_category_range.py -k "click_uses_summary_snapshot_without_query"`

Expected: FAIL because expansion schedules `load_category_range_detail`.

- [ ] **Step 3: Store and render snapshot details**

Add `self._category_details = {}`. `_apply_summary` atomically replaces it only after payload validation. `_expand_card` renders `self._category_details.get(cat_key, [])`. Remove `_detail_refresh_controller`, `_detail_query`, and detail refresh methods.

- [ ] **Step 4: Keep the old snapshot on refresh failure**

Add a test that expands a category, invokes `_show_refresh_error`, and asserts the same detail table remains visible.

- [ ] **Step 5: Run category-page tests**

Run: `pytest -q tests/test_category_range.py tests/test_category_card_labels.py`

Expected: PASS and no detail-query calls.

- [ ] **Step 6: Commit**

```powershell
git add src/daylens/gui/pages/category_stats.py tests/test_category_range.py
git commit -m "perf: expand category cards from memory"
```

### Task 4: Reuse fresh page snapshots and avoid hidden report scans

**Files:**
- Modify: `src/daylens/gui/dashboard_refresh_controller.py`
- Modify: `src/daylens/gui/pages/software_stats.py`
- Modify: `src/daylens/gui/pages/reports.py`
- Modify: `src/daylens/services/reports_service.py`
- Modify: `tests/test_dashboard_refresh_controller.py`
- Modify: `tests/test_reports_page.py`
- Modify: `tests/test_reports_service.py`

- [ ] **Step 1: Write failing freshness tests**

Test that foreground activation within `max_age_ms=30_000` does not start a second loader, while activation after the injected clock advances past 30 seconds does.

- [ ] **Step 2: Verify freshness tests fail**

Run: `pytest -q tests/test_dashboard_refresh_controller.py -k "fresh"`

Expected: FAIL because `set_foreground(True)` always requests a refresh.

- [ ] **Step 3: Add monotonic freshness tracking**

Extend `DashboardRefreshController` with `max_age_ms` and an injectable monotonic clock. Record the last successful completion time. Foreground activation calls `request_refresh()` only when there is no successful snapshot or it is stale. `invalidate_context()` always bypasses freshness.

- [ ] **Step 4: Configure software and category pages for 30-second reuse**

Pass `max_age_ms=30_000` to their controllers. Explicit refresh continues to bypass freshness via `invalidate_context()`.

- [ ] **Step 5: Write failing report-list tests**

Patch `list_report_page` and assert initial activation loads only the visible `daily` page plus lightweight counts; switching to `weekly` loads weekly once and does not reload daily/monthly rows.

- [ ] **Step 6: Add a lightweight report count helper and visible-tab refresh**

Add `count_reports(reports_dir, subdir)` and update `ReportsPage.refresh` to populate only `_current_subdir()`. Hidden tab labels use counts and cached `ReportPage` objects. Manual changes invalidate only their affected subdir.

- [ ] **Step 7: Run focused performance behavior tests**

Run: `pytest -q tests/test_dashboard_refresh_controller.py tests/test_reports_page.py tests/test_reports_service.py tests/test_software_stats.py`

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/daylens/gui/dashboard_refresh_controller.py src/daylens/gui/pages/software_stats.py src/daylens/gui/pages/reports.py src/daylens/services/reports_service.py tests/test_dashboard_refresh_controller.py tests/test_reports_page.py tests/test_reports_service.py tests/test_software_stats.py
git commit -m "perf: reuse fresh page snapshots"
```

### Task 5: Implement deterministic historical category repair

**Files:**
- Create: `src/daylens/services/historical_category_repair_service.py`
- Create: `scripts/repair_recent_categories.py`
- Create: `tests/test_historical_category_repair.py`

- [ ] **Step 1: Write failing preview/apply tests on a temporary database**

Cover the exact date range, case-insensitive process matching, `category_key='other'` guard, idempotency, time-column conservation, backup-before-write, local-rule updates and audit output without titles.

- [ ] **Step 2: Verify tests fail because the service does not exist**

Run: `pytest -q tests/test_historical_category_repair.py`

Expected: collection/import FAIL.

- [ ] **Step 3: Implement immutable repair mappings and read-only preview**

```python
REPAIR_GROUPS = {
    "gaming": ("游戏娱乐", "interactive_required",
               ("lostcastle2.exe", "lost_castle.exe", "brotato.exe")),
    "finance": ("投资理财", "interactive_required",
                ("hexin.exe", "股票盯盘.exe", "xiadan.exe", "hexinhelper.exe")),
}
```

`preview_repair` returns affected row count and conserved duration/effective/engaged/passive/idle totals without opening a write connection.

- [ ] **Step 4: Implement backup, transactional update, rule merge and audit**

Use SQLite backup API to `data/backups/usage-before-category-repair-<timestamp>.db`. Begin an immediate transaction, update only matching `other` rows in the exact range, merge process names into `custom_rules`, validate the same time totals, commit, then write an atomic JSON audit file under `data/logs`.

- [ ] **Step 5: Add an explicit preview/apply CLI**

The script defaults to preview. `--apply` requires exact start/end arguments and prints the backup/audit paths and changed counts.

- [ ] **Step 6: Run repair tests**

Run: `pytest -q tests/test_historical_category_repair.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/daylens/services/historical_category_repair_service.py scripts/repair_recent_categories.py tests/test_historical_category_repair.py
git commit -m "feat: add audited historical category repair"
```

### Task 6: Verify, apply to real data, publish and restart

**Files:**
- Create: `docs/reviews/2026-10-28-statistics-query-latency-and-category-repair.md`

- [ ] **Step 1: Run focused and full verification**

```powershell
pytest -q tests/test_category_range.py tests/test_dashboard_refresh_controller.py tests/test_reports_page.py tests/test_historical_category_repair.py
pytest -q
python -m compileall -q src tests
```

Expected: all tests PASS and compileall exits 0.

- [ ] **Step 2: Run GUI smoke at required sizes and scaling**

Use the repository's existing GUI smoke command at 1280×720 and 1920×1080 with 100%, 125%, and 150% scaling. Confirm realtime is first and category cards open immediately.

- [ ] **Step 3: Stop DayLens through the existing maintenance path**

Confirm the session-recovery file is clear and no `DayLens.exe` process remains before database work.

- [ ] **Step 4: Preview and apply the exact repair**

```powershell
python scripts/repair_recent_categories.py --db data/usage.db --start 2026-09-29 --end 2026-10-28
python scripts/repair_recent_categories.py --db data/usage.db --start 2026-09-29 --end 2026-10-28 --apply
```

Expected: preview/apply counts match, backup and audit paths exist, and time-conservation validation passes.

- [ ] **Step 5: Build and publish with the existing safe-release workflow**

Archive the current release to a uniquely named recoverable folder, atomically replace the executable, launch once visibly, and verify one running process.

- [ ] **Step 6: Verify live behavior after at least one sampling interval**

Confirm heartbeat and sample time advance, newly observed game/finance processes use their corrected categories, and category card clicks do not produce database reads.

- [ ] **Step 7: Record evidence and commit**

Write exact commands, pass counts, executable hashes, backup path, audit path, changed counts, and remaining limitations to the review document.

```powershell
git add docs/reviews/2026-10-28-statistics-query-latency-and-category-repair.md
git commit -m "docs: record statistics latency repair verification"
```

