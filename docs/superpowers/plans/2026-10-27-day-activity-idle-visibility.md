# High-Idle Timeline Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide full foreground blocks from the day-activity category timeline when their recorded idle share exceeds 70%, without changing data or statistics.

**Architecture:** Keep `day_activity_service.py` and its source events unchanged. Centralize a per-event visibility predicate in `DayActivityCategoryTimeline`, reuse it for range fitting, painting, geometry, hit testing, and selection feedback. `DayActivityDialog` only explains why a selected event has no corresponding timeline block.

**Tech Stack:** Python 3, PySide6/QPainter, pytest-qt-style offscreen widget tests, SQLite read-only source.

**Workspace note:** This checkout has pre-existing uncommitted changes in both widget and test files. Preserve them; do not stage or commit their entire files. The design document was committed separately as `a90f753`.

---

### Task 1: Visibility rule and chart semantics

**Files:**
- Modify: `src/daylens/gui/widgets/day_activity_category_timeline.py`
- Test: `tests/test_day_activity_category_timeline.py`

- [ ] **Step 1: Write failing boundary and hit-test tests.** Add cases made with `event(..., duration_seconds=100, effective_seconds=30, idle_seconds=70)` for the visible equality boundary and `idle_seconds=71, effective_seconds=29` for the hidden case. Assert `event_rect` is empty only for the latter, its span cannot activate an event, its hover explains the hiding, and neither hidden nor explicit-idle events extends the fitted range. Check that a hidden-only model has `(range_start, range_end) == (0, 86400)` and a title that does not claim zero effective activity. Update the old explicit-idle geometry assertion to expect no painted event rectangle.
- [ ] **Step 2: Run the new tests and verify failure.** Run `python -m pytest -q tests/test_day_activity_category_timeline.py`; expect the >70% case to have a nonempty rectangle before the implementation.
- [ ] **Step 3: Implement one predicate and reuse it.** Add a method equivalent to:

```python
def is_event_hidden(self, identity):
    event = self._events.get(identity)
    if event is None:
        return False
    if self._event_groups.get(identity) == "idle":
        return True
    duration = int(event.get("duration_seconds") or 0)
    idle = int(event.get("idle_seconds") or 0)
    return duration <= 0 or idle * 10 > duration * 7
```

Use it when building the `active` range candidates, in `event_rect`, `_event_at`, and both segment/event painting loops. Preserve `totals` and source `model`. A hidden activity segment's tooltip must say it was hidden due to high idle share, not “无记录”; explicit idle gets an idle-hidden explanation. Change the no-visible-range title to “暂无可展示活动” and the footer to explain the >70% hiding rule.
- [ ] **Step 4: Run focused tests and inspect rendered widget.** Run `python -m pytest -q tests/test_day_activity_category_timeline.py`; expected result is all tests passing. Verify visible 70% mixed events retain their existing hatch and original tooltip counters.

### Task 2: Event table linkage and disclosure

**Files:**
- Modify: `src/daylens/gui/widgets/day_activity_dialog.py`
- Test: `tests/test_day_activity_gui.py`

- [ ] **Step 1: Write a failing dialog test.** Load one >70%-idle event with `effective_seconds >= 300`, select its row, and assert that the row remains in the table, the timeline has no event rectangle, and the help label says it was hidden because idle share exceeds 70%. Assert the total effective seconds and ≥5-minute event count still include it.
- [ ] **Step 2: Run the test and verify failure.** Run `python -m pytest -q tests/test_day_activity_gui.py -k hidden_idle`; expect a failure on the missing disclosure.
- [ ] **Step 3: Implement minimal dialog feedback.** Change the default `help_label` text to distinguish “空闲／高空闲留白” from missing/future/abnormal. In `_highlight`, call `self.timeline.select_event(self._selected_event_id)` and set `help_label` to a specific high-idle message when `self.timeline.is_event_hidden(self._selected_event_id)`; otherwise restore the default legend. Do not filter the event model or alter the async loader.
- [ ] **Step 4: Run dialog tests.** Run `python -m pytest -q tests/test_day_activity_gui.py`; expected result is all passing.

### Task 3: Regression, visual check, and live restart

**Files:**
- Optional review note: `docs/reviews/2026-10-27-day-activity-idle-visibility-result.md`

- [ ] **Step 1: Run targeted and full regression.** Run `python -m pytest -q tests/test_day_activity_category_timeline.py tests/test_day_activity_gui.py`, then `python -m pytest -q`. Record actual counts and failures; do not claim success without output.
- [ ] **Step 2: Compile and inspect GUI.** Run `python -m compileall -q src`. Use the existing offscreen GUI/layout smoke tooling at 1280×720 and 1920×1080, and inspect a >70% idle sample plus a <=70% sample. Verify the color block disappears, stats/table remain, and the visible range is not stretched.
- [ ] **Step 3: Restart DayLens safely.** Follow the repository's existing release/restart helper and confirm the new window is visible and sampling resumes. Keep the existing executable for rollback; do not modify the user's database.
- [ ] **Step 4: Report evidence and outstanding issues.** Include exact test commands/results, changed files, what was restarted, and any discrepancy. Because these files already contain other uncommitted changes, do not commit them wholesale without a separate diff review and user authorization.
