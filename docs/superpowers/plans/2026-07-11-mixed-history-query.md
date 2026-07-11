# Mixed History Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve legacy log-only dates in range statistics and entertainment trends after session records exist.

**Architecture:** Split requested dates by whether sessions exist, aggregate each source with existing functions, and merge payloads without mixing sources within a date.

**Tech Stack:** Python, SQLite, pytest.

---

### Task 1: Reproduce mixed-source history loss

**Files:**
- Create: `tests/test_mixed_history_queries.py`

- [ ] Create a temporary initialized database with a legacy video log yesterday and a video session today.
- [ ] Assert `query_date_range_stats` returns both dates and their combined total.
- [ ] Assert `query_entertainment_trend(days=2)` returns both entertainment durations.
- [ ] Run `python -m pytest -q tests/test_mixed_history_queries.py` and verify both tests fail because yesterday is zero.

### Task 2: Merge range payloads by date source

**Files:**
- Modify: `src/daylens/repositories/stats_repository.py`
- Test: `tests/test_mixed_history_queries.py`

- [ ] Query distinct session dates only within the requested date list.
- [ ] Call `query_date_range_from_sessions` for session dates and `query_date_range_from_logs` for remaining dates.
- [ ] Add `_merge_range_payloads(dates, payloads)` that preserves daily order; sums category rows by `(category_key, category_name)` and app rows by `(process_name, category_key)`; recalculates totals from merged daily rows.
- [ ] Run the range test and verify PASS.

### Task 3: Merge entertainment trend by date source

**Files:**
- Modify: `src/daylens/repositories/stats_repository.py`
- Test: `tests/test_mixed_history_queries.py`

- [ ] Replace the global session-count switch with session aggregation for requested dates plus a legacy query restricted to dates absent from the session-date set.
- [ ] Return results in chronological requested-date order.
- [ ] Run `python -m pytest -q tests/test_mixed_history_queries.py` and verify PASS.
- [ ] Commit with `git commit -m "fix: preserve legacy dates in mixed history queries"`.

### Task 4: Verify and publish

- [ ] Run full pytest and compileall.
- [ ] Fast-forward merge into local main and rerun tests.
- [ ] Build release, refresh shortcuts, restart, and verify one process uses `release/DayLens.exe`.
