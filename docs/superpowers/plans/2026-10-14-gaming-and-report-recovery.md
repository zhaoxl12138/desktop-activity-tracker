# Gaming Classification and Report Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply high-confidence AI game classifications and safely retry failed AI summaries once without creating duplicate databases or uncontrolled API calls.

**Architecture:** Add an AI-only `gaming` category to both shipped configs. Extend the durable report scheduler with a separate retry queue that permits one next-day retry while retaining existing budget and daily limits. Delete only verified zero-byte database placeholders after release verification.

**Tech Stack:** Python 3.14, PySide6, YAML, JSON state files, pytest, PyInstaller.

---

### Task 1: Make the shipped classifier accept AI gaming decisions

**Files:**
- Modify: `config/config.yaml`
- Modify: `config/config.example.yaml`
- Test: `tests/test_intelligence_tracking.py`

- [ ] Add a test that loads `config/config.yaml`, confirms `gaming` exists with `interactive_required`, and verifies a high-confidence cached gaming decision changes an unknown application to `gaming`.
- [ ] Run the test and confirm it fails because the shipped config has no `gaming` entry.
- [ ] Add an empty-match `gaming` category to both configuration files; do not add broad game-launcher rules.
- [ ] Run the intelligence tracking tests and confirm they pass.
- [ ] Commit the focused change.

### Task 2: Retry a failed intelligent summary once on the next day

**Files:**
- Modify: `src/daylens/services/intelligence_reviews.py`
- Modify: `src/daylens/services/intelligence_report_service.py`
- Modify: `src/daylens/services/intelligence_report_schedule.py`
- Test: `tests/test_intelligence_reviews.py`
- Test: `tests/test_scheduled_intelligence_reports.py`

- [ ] Add failing tests for preserving same-day no-retry behavior, one next-day retry, permanent failure after the second attempt, deferred calls not consuming an attempt, and migration of legacy `failed` values.
- [ ] Run the directed tests and confirm the failures describe missing retry behavior.
- [ ] Add an explicit `retry_failed` path to review generation that only replaces a cached failed marker.
- [ ] Add durable `failures` metadata to the scheduler, migrate legacy failures, and gate retries by date and attempt count.
- [ ] Run the directed tests and confirm they pass.
- [ ] Commit the focused change.

### Task 3: Verify, publish, and remove empty database placeholders

**Files:**
- Delete after size verification: `unused.db`
- Delete after size verification: `data/activity.db`
- Delete after size verification: `data/daylens.db`

- [ ] Run the focused intelligence and scheduling tests.
- [ ] Run `python -m pytest -q`, `python -m compileall -q src`, and `git diff --check`.
- [ ] Build and smoke-test a staging release with `python tools/build_release.py --stage-only`.
- [ ] Verify the three placeholder databases are still zero bytes, then remove exactly those paths.
- [ ] Request a clean maintenance exit, swap the validated staging directory into `release`, and retain a recoverable previous-release backup.
- [ ] Start the canonical executable and verify one process, a running heartbeat, `PRAGMA quick_check = ok`, preserved credentials, and preserved classification cache.
- [ ] Commit the cleanup and release metadata changes that belong in Git; leave unrelated user changes untouched.
