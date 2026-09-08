# Automatic Intelligence Reports Implementation Plan

> Execute inline with superpowers:executing-plans, without parallel agents.

**Goal:** Readable budget input and scheduled AI summaries inside existing reports.

**Architecture:** Reuse the existing report background queue. A pure due-period selector and durable scheduler state control AI calls. A shared Markdown writer preserves the marked AI section on every native export.

**Tech Stack:** Python, PySide6, JSON state, existing SQLite reads and DeepSeek budget provider.

## Tasks

- [ ] Add failing tests in `tests/test_scheduled_intelligence_reports.py`: 23:00 boundary, Sunday/month end ordering, activation date, year boundary, catch-up and duplicate runs; use injected generator and temporary files.
- [ ] Add `services/report_sections.py` with a reentrant write lock and marked-section preservation; integrate `exporter._atomic_write_text`; test repeated attachment and native overwrite preservation.
- [ ] Add `services/intelligence_report_schedule.py`: local activation date, due periods, budget/disabled/no-data deferral, completion states, serial native creation and summary attachment. Reuse existing reviews and provider. Budget refusal before transmission must not become a terminal failed attempt.
- [ ] Connect scheduler to `ReportJob` and existing GUI background queue; remove manual AI bar; show concise automatic status in ReportsPage. Preserve native report generation controls.
- [ ] Include `QDoubleSpinBox` in input style; update settings text to describe automatic reporting and sanitized evidence transmission.
- [ ] Run `python -m pytest tests/test_scheduled_intelligence_reports.py tests/test_intelligence_reviews.py -q`, then full `python -m pytest -q`, `compileall`, diff checks, offscreen GUI smoke and packaged Qt/credentials smoke.
- [ ] Publish only after normal exit, retaining original release path and canonical database. Record verified completion and commit only scoped changes.

## Invariants

- Scheduling starts on first enabled run, not at the earliest historical database date.
- Daily summaries precede the dependent weekly/monthly summary; pending earlier summaries defer dependency generation.
- Reuse ready cached results, never re-request failed or uncertain periods.
- Monthly budget and per-kind daily request ceilings remain unchanged. Catch-up can span subsequent days.
- AI section is appended to existing report text; no original document body is removed by attachment. Native refresh keeps its usual statistics-refresh semantics but retains the AI section.
- Network calls and report I/O run outside the GUI thread. No new database or external scheduler.

## Verification checkpoint — 2026-09-08

Implementation tasks and pre-release verification are complete. Full suite: 887 passed. Directed schedule tests: 13 passed. `compileall` and diff checks passed. Offscreen 1280×720 reports/settings inspected; budget text is visible on a dark background. Staged release passed bundled Qt and actual temporary-credential read/write/delete checks. API transport was mocked in feature tests; no real API requests were made for testing.

Deployment is pending the user's normal application exit. Preserve unrelated pre-existing changes in today_overview.py and test_top_app_icons.py; do not include them in this feature commit.
