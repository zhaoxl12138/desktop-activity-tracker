# Report List Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow every daily, weekly, and monthly report to be reached through 50-row pages instead of truncating each list at 50 files.

**Architecture:** Add a pure pagination result and reader in `reports_service`, while retaining the old flat-list adapter. `ReportsPage` owns one page number per report type, renders only the selected page, and derives button/tab state from the service result.

**Tech Stack:** Python 3.14, PySide6, pytest, local Markdown report files.

---

### Task 1: Add the report-page service contract

**Files:**
- Modify: `tests/test_reports_service.py`
- Modify: `src/daylens/services/reports_service.py:1-120`

- [x] **Step 1: Write failing pagination tests**

Add a helper that creates 142 nested daily Markdown files and tests asserting:

```python
page_1 = reports_service.list_report_page(str(tmp_path), "daily", page=1, page_size=50)
page_2 = reports_service.list_report_page(str(tmp_path), "daily", page=2, page_size=50)
page_3 = reports_service.list_report_page(str(tmp_path), "daily", page=3, page_size=50)

assert [len(page.rows) for page in (page_1, page_2, page_3)] == [50, 50, 42]
assert page_1.total_count == 142
assert page_1.total_pages == 3
assert page_3.page == 3
assert {row["file_path"] for page in (page_1, page_2, page_3) for row in page.rows} == expected_paths
```

Add boundary tests:

```python
assert reports_service.list_report_page(str(tmp_path), "daily", page=99).page == 3
empty = reports_service.list_report_page(str(tmp_path), "weekly", page=-1)
assert (empty.page, empty.total_pages, empty.total_count, empty.rows) == (1, 1, 0, [])
```

- [x] **Step 2: Run the focused tests and confirm failure**

Run: `python -m pytest tests/test_reports_service.py -q`

Expected: failure because `list_report_page` does not exist.

- [x] **Step 3: Implement the immutable page result and reader**

In `reports_service.py`, add:

```python
@dataclass(frozen=True)
class ReportPage:
    rows: list[dict]
    total_count: int
    page: int
    total_pages: int
    page_size: int


def list_report_page(
    reports_dir: str,
    subdir: str,
    *,
    page: int = 1,
    page_size: int = 50,
) -> ReportPage:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    directory = os.path.join(reports_dir, subdir)
    files = sorted(
        glob.glob(os.path.join(directory, "**", "*.md"), recursive=True),
        reverse=True,
    )
    total_count = len(files)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    current_page = min(max(1, int(page)), total_pages)
    start = (current_page - 1) * page_size
    rows = [_report_row(path, subdir) for path in files[start:start + page_size]]
    return ReportPage(rows, total_count, current_page, total_pages, page_size)
```

Extract the existing row metadata conversion into `_report_row(file_path, subdir)`. Keep `list_report_rows` as a compatibility adapter that returns the first `limit` rows, with its existing default and output type.

- [x] **Step 4: Run service tests**

Run: `python -m pytest tests/test_reports_service.py -q`

Expected: all service tests pass, including 50/50/42 pagination and empty/clamped pages.

### Task 2: Add independent pagination state to the reports page

**Files:**
- Modify: `tests/test_reports_page.py`
- Modify: `src/daylens/gui/pages/reports.py:30-330`

- [x] **Step 1: Write failing GUI pagination tests**

Create 142 daily, 52 weekly, and 2 monthly files. Instantiate `ReportsPage`, then assert:

```python
assert page.tab_daily.rowCount() == 50
assert page.tabs.tabText(0) == "日报  142"
assert page.page_status.text() == "第 1 / 3 页 · 共 142 份"
assert not page.btn_previous_page.isEnabled()
assert page.btn_next_page.isEnabled()

page.btn_next_page.click()
app.processEvents()
assert page.tab_daily.rowCount() == 50
assert page.page_status.text() == "第 2 / 3 页 · 共 142 份"

page.btn_next_page.click()
app.processEvents()
assert page.tab_daily.rowCount() == 42
assert not page.btn_next_page.isEnabled()
```

Add tests that switching to weekly displays its first page, returning to daily restores daily page 3, changing pages clears selected detail state, and deleting enough files clamps an out-of-range page during `refresh()`.

- [x] **Step 2: Run the focused GUI tests and confirm failure**

Run: `python -m pytest tests/test_reports_page.py -q`

Expected: failures because paginator widgets and page state do not exist.

- [x] **Step 3: Build the pagination controls and state**

In `ReportsPage.__init__`, add:

```python
self._page_size = 50
self._report_pages = {"daily": 1, "weekly": 1, "monthly": 1}
self._page_results = {}
```

Below the tab widget, add a horizontal row containing `btn_previous_page`, `page_status`, and `btn_next_page`. Use existing secondary button styling. Replace the tab signal with `_on_tab_changed`, which clears selection, updates pager state, and refreshes the selected type.

Add helpers:

```python
def _current_subdir(self) -> str:
    return ("daily", "weekly", "monthly")[self.tabs.currentIndex()]

def _change_page(self, delta: int) -> None:
    subdir = self._current_subdir()
    self._report_pages[subdir] += delta
    self._clear_selection()
    self.refresh(force_subdir=subdir)

def _update_pager(self) -> None:
    result = self._page_results.get(self._current_subdir())
    if result is None:
        return
    self.page_status.setText(
        f"第 {result.page} / {result.total_pages} 页 · 共 {result.total_count} 份"
    )
    self.btn_previous_page.setEnabled(result.total_count > 0 and result.page > 1)
    self.btn_next_page.setEnabled(
        result.total_count > 0 and result.page < result.total_pages
    )
```

Change `refresh` to request `list_report_page` for all three types using their saved page. Store the normalized page returned by the service, set tab text from `total_count`, render only `result.rows`, and include page/total metadata in the signature. Accept an optional `force_subdir` so clicking a pager button cannot be skipped by an unchanged old signature. After refresh, call `_update_pager()`.

- [x] **Step 4: Run report-page and service regression tests**

Run: `python -m pytest tests/test_reports_page.py tests/test_reports_service.py -q`

Expected: all pagination and existing open/download/selection tests pass.

### Task 3: Verify and publish

**Files:**
- Modify: `docs/superpowers/plans/2026-10-21-report-list-pagination.md`

- [x] **Step 1: Run the report and GUI regression groups**

Run:

```powershell
python -m pytest tests/test_reports_page.py tests/test_reports_service.py tests/test_gui_smoke.py -q
```

Expected: all selected tests pass.

- [x] **Step 2: Run complete verification**

Run:

```powershell
python -m compileall -q src tools
python -m pytest -q
git diff --check
```

Expected: compilation and all tests pass; diff check has no whitespace errors beyond Windows line-ending notices.

- [x] **Step 3: Build and replace the canonical release**

Create an online SQLite backup and verify `PRAGMA quick_check = ok`. Use `python tools/build_release.py` so the existing release exits through maintenance mode. Start `release/DayLens.exe` and verify one responsive process, the canonical executable path, the unchanged `data/usage.db`, and a new session written after startup.

- [x] **Step 4: Perform packaged GUI smoke**

Open Report Center in the packaged application and verify the real 142-report directory shows `日报 142`, pages 1/3 through 3/3, and 42 rows on the last page. Confirm selection, opening, and page switching do not retain hidden selections.

- [x] **Step 5: Mark completed steps and record verification evidence**

## Verification evidence

- Pagination RED tests failed for the expected missing service and controls, then passed after implementation.
- Focused report service/page/GUI group: 24 passed.
- Final full suite: 993 passed in 23.14 seconds.
- Real report directory: 142 daily reports; pages contained 50, 50, and 42 rows.
- Online backup: `data/backups/20261021-report-pagination/usage.db`; `PRAGMA quick_check = ok`.
- Published `release/DayLens.exe` started as the only responsive DayLens process on the canonical database.
- Packaged UI manually verified: `日报 142`, page 1/3, and page 3/3 with 42 reports.

Update this plan's checkboxes only after each command and packaged smoke succeeds. Do not modify or backfill any report contents.

