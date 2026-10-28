# AI Same-Day Fallback Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically reclassify today's exact-title fallback rows when AI returns an adopted high-confidence category, and immediately add non-browser desktop processes to the corresponding local rule.

**Architecture:** Add a focused transactional service for AI-applied backfill and rule promotion, then let `SessionTracker` emit a once-per-process/title/category application event after any fallback session has been safely persisted. `RecordingWorker` owns the database/rule mutation, reloads the classifier when a process rule changes, and signals the GUI to invalidate existing statistics caches.

**Tech Stack:** Python 3, SQLite, PySide6 signals/QThread, pytest, existing DayLens classifier/intelligence services.

---

## File Structure

- Create `src/daylens/services/ai_classification_backfill_service.py`: transactional exact-title fallback update, time-conservation validation, browser exclusion, process-rule promotion, audit output.
- Modify `src/daylens/services/classification_correction_service.py`: expose the already-tested process-rule movement helper for reuse without changing manual-correction behavior.
- Modify `src/daylens/session_tracker.py`: detect adopted high-confidence AI results and emit one idempotent application callback after a safe session boundary.
- Modify `src/daylens/gui/worker.py`: run the service in the recording thread, reload classifier after rule changes, and emit a history-change signal.
- Modify `src/daylens/gui/main_window.py`: connect the worker history-change signal to the existing cache invalidation/rule-page refresh handler.
- Create `tests/test_ai_classification_backfill_service.py`: transaction, matching, browser, idempotency, and conservation coverage.
- Modify `tests/test_ai_classification.py`: tracker callback timing and confidence-policy coverage.
- Modify `tests/test_worker.py` or the closest existing worker test module: worker/service integration and GUI notification coverage.
- Create `docs/reviews/2026-10-28-ai-same-day-fallback-backfill-result.md`: real commands, counts, backup, audit, release hash, and runtime verification.

### Task 1: Transactional AI backfill service

**Files:**
- Create: `tests/test_ai_classification_backfill_service.py`
- Create: `src/daylens/services/ai_classification_backfill_service.py`
- Modify: `src/daylens/services/classification_correction_service.py`

- [ ] **Step 1: Write failing exact-title and conservation tests**

Create fixtures with today's `Hades2.exe / Hades II` fallback row, another title in the same process, an older-day row, and five timing counters. Assert the wished-for API:

```python
result = apply_ai_classification_backfill(
    db_path=str(db_path),
    process_name="Hades2.exe",
    window_title="Hades II",
    normalized_title="Hades II",
    category_key="gaming",
    categories=categories,
    day="2026-10-28",
)
assert result.updated_sessions == 1
assert result.updated_effective_seconds == 46
assert result.rule_changed is True
assert result.time_conserved is True
```

Verify only the exact-title fallback row changes, all five counters and timestamps remain byte-for-byte equal, and the process exists only in the `gaming` custom rule.

- [ ] **Step 2: Run the new test and verify RED**

Run: `python -m pytest tests/test_ai_classification_backfill_service.py -q`

Expected: collection/import failure because `apply_ai_classification_backfill` does not exist.

- [ ] **Step 3: Implement the minimal transactional service**

Implement a frozen result dataclass containing `updated_sessions`, `updated_effective_seconds`, `rule_changed`, `shared_browser`, `time_conserved`, and `audit_path`. In one `BEGIN IMMEDIATE` transaction:

1. Select today's rows by case-insensitive process.
2. Match normalized title using the same canonical title key as manual correction.
3. Restrict updates to `category_key IN ('other', 'browser_general')`.
4. Update classification fields to the target category and `classification_version='ai-high-backfill-v1'`.
5. For non-browser processes, call the shared process-rule move helper.
6. Re-read and assert all five timing totals and timestamps are unchanged.
7. Commit and write a title-free audit JSON under `data/logs`.

Do not save a manual override or artificial title pattern.

- [ ] **Step 4: Add browser and idempotency tests**

Assert `chrome.exe` rows are backfilled but Chrome is never added to a process rule. Repeating an identical call must return `updated_sessions=0` and `rule_changed=false`.

- [ ] **Step 5: Verify GREEN**

Run: `python -m pytest tests/test_ai_classification_backfill_service.py tests/test_classification_correction_service.py -q`

Expected: all tests pass and manual correction behavior remains unchanged.

- [ ] **Step 6: Commit the service**

```powershell
git add src/daylens/services/ai_classification_backfill_service.py src/daylens/services/classification_correction_service.py tests/test_ai_classification_backfill_service.py
git commit -m "feat: backfill high-confidence AI classifications"
```

### Task 2: Emit adopted-AI events from the tracker

**Files:**
- Modify: `tests/test_ai_classification.py`
- Modify: `src/daylens/session_tracker.py`

- [ ] **Step 1: Write failing tracker callback tests**

Construct a tracker whose intelligence returns local fallback first and adopted high-confidence `gaming` next. Pass `on_ai_classification_applied=events.append`. Assert:

- the old fallback session is persisted before the callback runs;
- the event contains process, raw title, normalized title, base/final categories, certainty, source, and selected date;
- one process/title/category event is emitted only once despite later ticks;
- medium, low, conflict, pending, invalid, or non-applied decisions emit nothing.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/test_ai_classification.py -q`

Expected: constructor rejects `on_ai_classification_applied` or no event is emitted.

- [ ] **Step 3: Implement the callback boundary**

Add the optional constructor callback and a bounded in-memory set keyed by `(process.casefold(), normalized_title.casefold(), final_category)`. When an AI result is actually adopted from `other` or `browser_general`:

1. Safely persist the current same-page fallback session through existing `finish_current('ai_classification')`.
2. Invoke the callback only after persistence succeeds.
3. Mark the key delivered only when the callback succeeds.
4. Catch callback errors so sampling continues; leave the key retryable on a later tick.

Cached high-confidence AI results on the first tick must also emit once so an existing cache can create the process rule.

- [ ] **Step 4: Verify GREEN and tracker regressions**

Run: `python -m pytest tests/test_ai_classification.py tests/test_all.py tests/test_data_quality_service.py -q`

Expected: all tests pass; session counters remain unchanged.

- [ ] **Step 5: Commit tracker integration**

```powershell
git add src/daylens/session_tracker.py tests/test_ai_classification.py
git commit -m "feat: emit adopted AI classification events"
```

### Task 3: Worker mutation, classifier reload, and GUI refresh

**Files:**
- Modify: `tests/test_worker.py` or the matching recording-worker test file found by `rg --files tests | rg 'worker|recording'`
- Modify: `src/daylens/gui/worker.py`
- Modify: `src/daylens/gui/main_window.py`

- [ ] **Step 1: Write failing worker integration tests**

Inject a service result into a worker callback test. Assert that the worker:

- calls the backfill service with its canonical database and intelligence paths;
- reloads the tracker classifier only when `rule_changed=true`;
- emits a dictionary through a new `classification_history_changed` signal;
- reports failures as degraded diagnostics without stopping recording.

- [ ] **Step 2: Run the focused worker tests and verify RED**

Run the exact test module with `python -m pytest <worker-test-path> -q`.

Expected: callback/signal is absent.

- [ ] **Step 3: Implement worker handling**

Add `classification_history_changed = Signal(object)`, pass `_apply_ai_classification` to `SessionTracker`, call `apply_ai_classification_backfill`, reload the classifier through `replace_classifier` when required, and emit the result payload. Connect the worker signal in `MainWindow._connect_recording_worker()` to the existing `_on_classification_history_changed()` handler.

- [ ] **Step 4: Verify GREEN and GUI cache invalidation**

Run: `python -m pytest <worker-test-path> tests/test_classification_correction.py tests/test_stage_c_shell.py -q`

Expected: service integration, rules-page refresh, and statistics cache invalidation pass.

- [ ] **Step 5: Commit worker/UI integration**

```powershell
git add src/daylens/gui/worker.py src/daylens/gui/main_window.py <worker-test-path>
git commit -m "feat: apply AI backfills during recording"
```

### Task 4: Real-data correction and release verification

**Files:**
- Create: `docs/reviews/2026-10-28-ai-same-day-fallback-backfill-result.md`
- Runtime data only: `data/usage.db`, `data/backups/`, `data/logs/`

- [ ] **Step 1: Run complete automated verification**

Run:

```powershell
python -m pytest -q
python -m compileall -q src tests
python tests/test_gui_smoke.py
git diff --check
```

Expected: zero failures and zero compile/diff errors.

- [ ] **Step 2: Build the staged release**

Run: `python tools/build_release.py --stage-only`

Expected: PyInstaller build, Qt smoke, and credential smoke pass.

- [ ] **Step 3: Safely stop DayLens and back up the database**

Use the existing maintenance shutdown protocol. Copy `data/usage.db` to a timestamped file under `data/backups/` and verify both files with `PRAGMA quick_check` before any real-data mutation.

- [ ] **Step 4: Apply the service to the known Hades case**

Call the production service for `Hades2.exe / Hades II -> gaming` on `2026-10-28`. Verify:

- the 46-second fallback row is now `gaming`;
- all Hades timing totals remain conserved;
- `Hades2.exe` exists only in the `gaming` process rule;
- a second call returns zero updates and no rule change.

- [ ] **Step 5: Publish, restart, and inspect the GUI**

Atomically publish staging through the existing release procedure, preserve `release_previous`, refresh the shortcut, and start DayLens once. Verify one responsive process, a visible main window, advancing runtime heartbeat, and that statistics no longer show a separate Hades “其他” row.

- [ ] **Step 6: Record evidence and commit**

Write the exact test counts, backup/audit paths, before/after rows, time conservation, executable hashes, PID, and heartbeat into the review document.

```powershell
git add docs/reviews/2026-10-28-ai-same-day-fallback-backfill-result.md
git commit -m "docs: record AI classification backfill verification"
```
