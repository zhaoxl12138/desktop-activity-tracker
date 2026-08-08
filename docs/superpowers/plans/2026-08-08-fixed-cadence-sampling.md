# Fixed Cadence Sampling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate systematic sampling drift without changing DayLens classification, idle policy, session accounting, or persistence formats.

**Architecture:** Add a small monotonic-deadline cadence helper to the recording worker. The worker sleeps only for the remaining interval and rebases after a full missed interval so it never enters a catch-up loop.

**Tech Stack:** Python 3, PySide6 `QThread`, pytest

---

### Task 1: Capture fixed-cadence behavior with failing tests

**Files:**
- Modify: `tests/test_recording_worker.py`

- [x] Add a deterministic fake monotonic clock and tests proving that 60 ms of processing reduces a one-second sleep to 940 ms.
- [x] Add a test proving that lateness of at least one complete interval rebases the deadline rather than requesting repeated catch-up samples.
- [x] Add tests proving pause/resume and sampling-interval hot reload reset the cadence.
- [x] Run the new tests and verify that they fail because the worker still sleeps for the full configured interval.

### Task 2: Implement minimal fixed-deadline scheduling

**Files:**
- Modify: `src/daylens/gui/worker.py:280-306`
- Test: `tests/test_recording_worker.py`

- [x] Add worker-owned cadence state based on the already injected monotonic clock.
- [x] Replace the unconditional full-interval sleep with remaining-deadline sleep.
- [x] Rebase after a complete missed interval and while paused.
- [x] Reset cadence when hot-reloaded settings change the sample interval.
- [x] Run the focused tests and verify they pass.

### Task 3: Regression verification

**Files:**
- No production file changes expected.

- [x] Run recording worker, session policy, timeline, lock/sleep, and data-quality tests.
- [x] Run the complete pytest suite.
- [x] Inspect the diff to confirm classification, idle policy, database, and report code are unchanged.
- [x] Commit only the fixed-cadence implementation, its tests, and these two approved design documents.
