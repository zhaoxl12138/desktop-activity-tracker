# Transactional Classification Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make manual classification correction immediately update today's exact matching sessions and add ordinary desktop processes to local rules while keeping shared browsers title-scoped.

**Architecture:** Add one focused correction service that validates the category, rewrites only exact same-day session classifications, updates process ownership in `custom_rules` for non-browser apps, verifies all time columns are conserved, saves the existing manual title decision, and emits a title-free audit. The live-monitor page calls this service and the main window invalidates statistics snapshots and hot-reloads intelligence/classifier state.

**Tech Stack:** Python 3.14, SQLite, PySide6, existing classification state transactions, pytest.

---

## File map

- Create `src/daylens/services/classification_correction_service.py`: browser boundary, exact historical selection, local-rule ownership, compensation, conservation and audit.
- Modify `src/daylens/gui/pages/live_monitor.py`: invoke the service and expose the structured result to the shell.
- Modify `src/daylens/gui/main_window.py`: invalidate cached statistics and reload the classifier when a process rule changes.
- Create `tests/test_classification_correction_service.py`: service-level correctness, safety and rollback tests.
- Modify `tests/test_classification_correction.py`: GUI status and signal behavior.
- Modify `tests/test_stage_c_shell.py`: main-window cache invalidation and worker reload behavior.
- Create `docs/reviews/2026-10-28-classification-correction-transaction-result.md`: actual verification, backup, changed counts and release evidence.

### Task 1: Implement exact same-day correction and browser-safe local rules

**Files:**
- Create: `tests/test_classification_correction_service.py`
- Create: `src/daylens/services/classification_correction_service.py`

- [ ] **Step 1: Write failing tests for ordinary desktop applications**

Create a temporary database with `connection_repository.init_db`, insert same-day sessions for `Probably Stolen.exe` with both matching and different normalized titles, plus a prior-day matching session. Call the wished-for API:

```python
result = apply_classification_correction(
    db_path=str(db), intelligence_dir=tmp_path / "intelligence",
    process_name="Probably Stolen.exe", window_title="Probably Stolen",
    normalized_title="Probably Stolen", category_key="gaming",
    categories={}, day=date(2026, 10, 28), scope="similar",
)
assert result.updated_sessions == 2
assert result.rule_changed is True
assert result.shared_browser is False
```

Assert that only the two exact same-day rows move to `gaming / 游戏娱乐 / interactive_required / manual-correction-v1`, all five time columns retain their exact values, and `Probably Stolen.exe` exists only in the gaming custom rule.

- [ ] **Step 2: Run the ordinary-app test and verify RED**

Run: `pytest -q tests/test_classification_correction_service.py -k ordinary`

Expected: collection fails because `classification_correction_service` does not exist.

- [ ] **Step 3: Write failing tests for shared browsers and idempotency**

Parametrize `chrome.exe`, `360ChromeX.exe`, `msedge.exe`, and `firefox.exe`. Assert same-day exact-title sessions change category, but no custom process rule is created. Repeating the same correction must return zero newly changed sessions/rules while preserving the manual decision.

- [ ] **Step 4: Implement the minimal service**

Define:

```python
@dataclass(frozen=True)
class CorrectionResult:
    updated_sessions: int
    rule_changed: bool
    shared_browser: bool
    time_conserved: bool
    audit_path: str

def apply_classification_correction(*, db_path, intelligence_dir,
                                    process_name, window_title,
                                    normalized_title, category_key,
                                    categories, day=None,
                                    scope="similar") -> CorrectionResult:
    """Apply one user-confirmed category to exact same-day evidence."""
```

Use the classifier's canonical default browser-process set as the single browser boundary. Select candidates by exact date and case-insensitive process name, then compare `normalized_title` after whitespace normalization; only fall back to `normalize_window_title(process, window_title)` when the stored normalized title is empty.

Within `BEGIN IMMEDIATE`, snapshot matching row classification fields and affected custom-rule rows, update only `category_key`, `category_name`, `active_rule`, and `classification_version`, and move a non-browser process out of every other custom rule into the target rule. Preserve all keyword/pattern/mode columns and use `process_names_mode='inherit'` when creating a missing target row.

Verify these sums before commit and after update:

```python
TIME_FIELDS = ("duration_seconds", "effective_seconds", "engaged_seconds",
               "passive_seconds", "idle_seconds")
```

Commit SQLite, then call the existing `save_override`. If that call fails, restore only the touched session IDs and affected custom-rule keys from the snapshot in a compensating transaction, then re-raise. Write a title-free atomic audit JSON only after both stores succeed.

- [ ] **Step 5: Verify GREEN and rollback behavior**

Run: `pytest -q tests/test_classification_correction_service.py`

Expected: ordinary app, browser exception, idempotency, exact-boundary, conservation and injected state-write failure tests all pass.

- [ ] **Step 6: Commit the service**

```powershell
git add src/daylens/services/classification_correction_service.py tests/test_classification_correction_service.py
git commit -m "feat: make manual classification correction immediate"
```

### Task 2: Integrate correction results with the live UI and caches

**Files:**
- Modify: `tests/test_classification_correction.py`
- Modify: `tests/test_stage_c_shell.py`
- Modify: `src/daylens/gui/pages/live_monitor.py`
- Modify: `src/daylens/gui/main_window.py`

- [ ] **Step 1: Write failing live-page tests**

Construct `LiveMonitorPage(paths=AppPaths.from_database(str(db)))`, select a synthetic ordinary-app sample, accept `gaming`, and patch the service to return `CorrectionResult(updated_sessions=6, rule_changed=True, shared_browser=False, time_conserved=True, audit_path=str(tmp_path / "audit.json"))`. Assert:

```python
assert "已修正今天6条记录，并加入本地规则" in page.correction_status.text()
assert emitted_result["updated_sessions"] == 6
```

Add a browser result test expecting `已修正今天2条记录，并保存标题规则`.

- [ ] **Step 2: Run live-page tests and verify RED**

Run: `pytest -q tests/test_classification_correction.py -k "immediate or browser"`

Expected: failures because the page still calls `save_override` directly and exposes no result signal.

- [ ] **Step 3: Add the structured signal and service call**

Add `classification_history_changed = Signal(object)`. `_correct_current` must require `self.paths.database` for the immediate path, pass both raw and normalized titles to the service, display the result-specific message, then call `_decision_saved(message)` and emit a plain dictionary containing `updated_sessions`, `rule_changed`, and `shared_browser`.

For synthetic/legacy pages without `paths`, retain the existing title-only `save_override` path so packaged reliability smoke and isolated legacy tests remain valid.

- [ ] **Step 4: Write failing shell tests**

Emit `classification_history_changed` with `rule_changed=True`. Assert the worker receives both `reload_intelligence()` and `reload_classifier()`, `dashboard_refresh.invalidate_context()` runs, and software/category refresh controllers are invalidated without forcing hidden pages to query.

- [ ] **Step 5: Implement main-window invalidation**

Connect the signal to `_on_classification_history_changed`. The handler reloads the classifier only when `rule_changed`, invalidates the dashboard controller, and invalidates software/category page controllers. Existing `classification_corrected` continues to reload intelligence and update the applied revision status.

- [ ] **Step 6: Run GUI integration tests**

Run: `pytest -q tests/test_classification_correction.py tests/test_stage_c_shell.py tests/test_dashboard_refresh_controller.py`

Expected: all selected tests pass.

- [ ] **Step 7: Commit GUI integration**

```powershell
git add src/daylens/gui/pages/live_monitor.py src/daylens/gui/main_window.py tests/test_classification_correction.py tests/test_stage_c_shell.py
git commit -m "ui: refresh statistics after manual correction"
```

### Task 3: Verify and apply the existing Probably Stolen correction

**Files:**
- Create: `docs/reviews/2026-10-28-classification-correction-transaction-result.md`

- [ ] **Step 1: Run focused and full verification**

```powershell
pytest -q tests/test_classification_correction_service.py tests/test_classification_correction.py tests/test_stage_c_shell.py
pytest -q
python -m compileall -q src tests
python tests/test_gui_smoke.py
```

Expected: all tests pass and all commands exit 0.

- [ ] **Step 2: Build the isolated release**

Run: `python tools/build_release.py --stage-only`

Expected: validated staging release with Qt and credential smoke passing.

- [ ] **Step 3: Stop DayLens safely and back up the database**

Use the existing maintenance-exit protocol, require runtime state `clean`, and create a timestamped SQLite backup under `data/backups`. Validate both databases with `PRAGMA quick_check`.

- [ ] **Step 4: Apply the already-saved correction**

Call `apply_classification_correction` for `Probably Stolen.exe / Probably Stolen / gaming / 2026-10-28`. Expected result: 6 sessions and 2319 effective seconds move from `other` to `gaming`, all time sums stay equal, and the process appears only in the gaming custom rule. A second call must update zero sessions and no rule.

- [ ] **Step 5: Publish and restart visibly**

Archive the existing `release_previous` to a unique workspace-contained non-junction path, atomically publish `release_staging`, refresh the desktop shortcut, and launch `release/DayLens.exe` once visibly. Verify one responsive process, advancing runtime heartbeat and a new session after at least one sample interval.

- [ ] **Step 6: Record evidence and commit**

Record exact test counts, backup/audit paths, changed row/time totals, executable hashes and live PID in the review document.

```powershell
git add docs/reviews/2026-10-28-classification-correction-transaction-result.md
git commit -m "docs: record classification correction verification"
```

