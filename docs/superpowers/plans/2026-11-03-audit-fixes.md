# Audit fixes implementation plan

> **For agentic workers:** Use superpowers:executing-plans in the existing isolated worktree. Follow test-driven-development and verification-before-completion.

**Goal:** Repair the six reproduced consistency, feedback and layout defects without changing accounting or generating AI calls.

**Architecture:** Reuse correction transactions, completed-history caches, local report evidence validators and atomic report/sync writes. Keep asynchronous report freshness delivery separate from the report page and reject obsolete selection results.

**Tech Stack:** Python, sqlite3, PySide6, pytest, existing PyInstaller publication tools.

## Tasks

- [x] Baseline: `python -m pytest -q` — 1,445 passed.
- [x] Correction: simulate audit I/O failure; assert full row/rule equality. Write audit before SQL commit and remove an audit if commit fails. Keep existing override compensation.
- [x] History cache: regress category/counter/title changes, today-only writes and concurrent correction. Hash mutable session rows, keep an append/delete identity for legacy logs, pin cache keys and loads to one SQLite read snapshot.
- [x] Reports: test daily/weekly/monthly stale status, original LF/CRLF appendix bytes, changed file identities and obsolete selection deliveries. Use local `summary_status` and a bounded single-flight worker without restoring preview or calling AI.
- [x] Sync: test native/Obsidian failure separation, strict missing-source errors, concurrent stale copies and automatic batch continuation. Keep legacy exporter defaults compatible.
- [x] Selection: assert cached daily → weekly → daily selection/actions agree; refresh an expired listing on reactivation.
- [x] Duration: measure 120/1200-hour labels and font changes; verify both themes and three DPI scales.
- [x] Verification: full pytest, compileall, Ruff E9/F821, GUI smoke, navigation/report/activity layouts and targeted audit layout checks, plus history-digest benchmarks. See `docs/reviews/2026-11-04-audit-fixes.md`.
- [x] Review: independent review and follow-up passed, including real two-process Obsidian publication and quick-report partial-failure cases.
- [ ] Release: fast-forward local main, run existing safe release build, preserve rollback binaries, restart and verify one responding formal process/heartbeat. Record hashes/results, commit documentation. Do not push without a user request.
