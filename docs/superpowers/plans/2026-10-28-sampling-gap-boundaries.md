# DayLens Sampling Gap Boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Represent short unobserved sampler stalls as gaps between sessions without crediting or fabricating time.

**Architecture:** Reuse the existing transactional system-gap closure path. Select a reason from elapsed wall time, preserve the long-gap resume policy, and immediately resume ordinary sampling after a short gap.

**Tech Stack:** Python, pytest, SQLite session persistence

---

### Task 1: Lock short-gap semantics

**Files:**
- Modify: `tests/test_timeline_logic.py`
- Modify: `tests/test_session_tracker_policies.py`

- [ ] Add a failing test for a 10-second gap producing `sampling_gap` and a new one-second session.
- [ ] Add a passing guard that normal jitter below the threshold does not split.
- [ ] Extend failure rollback coverage to the new boundary reason.

### Task 2: Reuse the hard-boundary transaction

**Files:**
- Modify: `src/daylens/session_tracker.py`

- [ ] Derive short and system thresholds from the existing sample and idle settings.
- [ ] Feed the selected reason into the existing persistence and rollback path.
- [ ] Keep `_awaiting_activity` true only after a system gap.
- [ ] Run the focused tracker tests.

### Task 3: Verify and publish

**Files:**
- Create: `docs/reviews/2026-10-28-sampling-gap-boundaries-result.md`

- [ ] Run the full test suite, `compileall`, three GUI smoke scales and `git diff --check`.
- [ ] Build an isolated release, publish through maintenance exit, restart once and verify heartbeat plus measurement sampling.
