# Audit fixes implementation plan

> **For agentic workers:** Use superpowers:executing-plans in the existing isolated worktree. Follow test-driven-development and verification-before-completion.

**Goal:** Repair the six reproduced consistency, feedback and layout defects without changing accounting or generating AI calls.

**Architecture:** Reuse correction transactions, completed-history caches, local report evidence validators and atomic report/sync writes. Keep asynchronous report freshness delivery separate from the report page and reject obsolete selection results.

**Tech Stack:** Python, sqlite3, PySide6, pytest, existing PyInstaller publication tools.

## Tasks

- [ ] Baseline: `python -m pytest -q`; record the actual result.
- [ ] Correction: add an audit-write failure regression beside the override-failure test in `tests/test_classification_correction_service.py`. Assert complete row/rule equality after failure. Move audit persistence before SQL commit and clean up an audit if commit fails. Run the file, then commit.
- [ ] History cache: add real-DB tests in `tests/test_dashboard_history_cache.py` for category-only and counter/title-only changes under unchanged versions; assert today-only writes do not change yesterday's digest. Hash stable rows in `query_completed_history_revision`, pin the two source tables to one snapshot and retain missing-schema fallback. Verify actual dashboard entertainment values refresh after correction, then commit.
- [ ] Reports: add stale-summary regeneration tests to `tests/test_report_v2.py` for daily/weekly/monthly, asserting the old AI section remains byte-for-byte and no network is possible. Mark only stale/unverifiable states when explicitly regenerating. Add a single-flight local freshness controller, tests for rapid selection/close, and short report-detail feedback. Reuse `PreviewCache` and `summary_status`, never recreate the preview widget. Run report/evidence/queue tests, then commit.
- [ ] Sync: add service and GUI regressions simulating destination copy failure; assert no success dialog and no source/destination damage. Add strict propagation for report service callers while preserving legacy best-effort defaults. Run archive, report service/page and report-job tests, then commit.
- [ ] Selection: select a daily row, switch weekly and back within the cache TTL; assert row/model/action state agree. Restore from the current table on the cached path. Also refresh stale page contents on reactivation. Run reports page tests, then commit.
- [ ] Duration: add font-metric tests for 120/1200-hour initial/update labels. Derive minimum text width from the actual QLabel font, refresh on font changes and test dark/light/high-DPI. Run category/layout tests, then commit.
- [ ] Verification: full pytest, compileall, Ruff E9/F821, GUI smoke, navigation/report/activity layouts at 100/125/150% and 1280x720/1920x1080, plus a bounded history-digest benchmark. Record actual commands/results in `docs/reviews/2026-11-03-audit-fixes.md`.
- [ ] Review: inspect the combined diff for missing failure paths and request independent read-only review using requesting-code-review.
- [ ] Release: fast-forward local main, run existing safe release build, preserve rollback binaries, restart and verify one responding formal process/heartbeat. Record hashes/results, commit documentation. Do not push without a user request.
