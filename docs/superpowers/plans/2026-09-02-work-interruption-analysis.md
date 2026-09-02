# 工作干扰分析卡 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the home-page focus timeline with an explanation of which recorded non-work activity interrupted work and for how long.

**Architecture:** Add a pure `build_interruption_analysis` service that consumes the dashboard's already-loaded today sessions and emits a compact, presentation-stable model. Add a dedicated widget for the three summary facts and source ranking, then place it above the existing work-episode list in `TodayOverviewPage`.

**Tech Stack:** Python 3.14, PySide6, SQLite-backed existing dashboard snapshot, pytest.

---

### Task 1: Build the interruption analysis model

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Test: `tests/test_dashboard_service.py`

- [ ] **Step 1: Write failing service tests**

```python
def test_interruption_analysis_merges_non_work_sessions_until_work_resumes():
    work_before = _rhythm_session("2026-09-02", "09:00:00", "09:10:00", 600)
    social = {**_rhythm_session("2026-09-02", "09:10:00", "09:13:00", 180), "category_key": "social", "process_name": "WeChat.exe"}
    video = {**_rhythm_session("2026-09-02", "09:13:00", "09:15:00", 120), "category_key": "video", "process_name": "QyClient.exe"}
    work_after = _rhythm_session("2026-09-02", "09:15:00", "09:25:00", 600)

    analysis = dashboard_service.build_interruption_analysis(
        [work_before, social, video, work_after],
        lambda process, _details: {"WeChat.exe": "微信", "QyClient.exe": "腾讯视频"}.get(process, process),
    )

    assert analysis["total_count"] == 1
    assert analysis["total_seconds"] == 300
    assert analysis["primary_source"] == {"label": "微信", "count": 1, "seconds": 180, "kind": "social"}


def test_interruption_analysis_excludes_long_gaps_and_invalid_intervals():
    work_before = _rhythm_session("2026-09-02", "09:00:00", "09:10:00", 600)
    social = {**_rhythm_session("2026-09-02", "09:10:00", "09:12:00", 120), "category_key": "social"}
    work_after = _rhythm_session("2026-09-02", "09:26:00", "09:36:00", 600)
    malformed = {**social, "session_id": "bad", "start_time": "invalid"}

    analysis = dashboard_service.build_interruption_analysis(
        [work_before, social, malformed, work_after], lambda process, _details: process
    )

    assert analysis["status"] == "empty"
    assert analysis["total_count"] == 0
    assert analysis["sources"] == []
```

- [ ] **Step 2: Verify the new tests fail**

Run: `python -m pytest tests/test_dashboard_service.py -k interruption_analysis -q`

Expected: FAIL because `build_interruption_analysis` does not exist.

- [ ] **Step 3: Implement the pure service model**

Add `INTERRUPTION_WINDOW_SECONDS = 15 * 60`, a session ordering helper, and:

```python
def build_interruption_analysis(sessions: list[dict], resolve_display) -> dict[str, object]:
    """Summarize complete work → non-work → work interruptions for one day."""
```

Only accept valid intervals. Partition ordered sessions into a work prefix, consecutive non-work run, and following work session. Include a run only when its elapsed interval is at most the constant. Attribute the single event to the non-work source with the greatest recorded effective seconds; break ties by display label. Map `social` to `social`, `video`/`gaming` to `entertainment`, `idle` to `idle`, browser category keys to `browser`, and all remaining categories to `other`. Return `ready`, `empty`, or `unavailable`-compatible stable fields from the approved spec.

- [ ] **Step 4: Verify service tests pass**

Run: `python -m pytest tests/test_dashboard_service.py -k interruption_analysis -q`

Expected: PASS.

- [ ] **Step 5: Commit the model**

```bash
git add src/daylens/services/dashboard_service.py tests/test_dashboard_service.py
git commit -m "feat: summarize work interruption sources"
```

### Task 2: Put the model into the existing home snapshot

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Test: `tests/test_dashboard_service.py`

- [ ] **Step 1: Write a failing snapshot integration test**

```python
def test_dashboard_snapshot_includes_interruption_analysis_without_extra_queries(monkeypatch):
    calls = {"today_sessions": 0, "range_sessions": 0}
    monkeypatch.setattr(dashboard_service.database, "query_today_sessions", lambda *_args: calls.__setitem__("today_sessions", calls["today_sessions"] + 1) or [])
    monkeypatch.setattr(dashboard_service.database, "query_sessions_for_dates", lambda *_args: calls.__setitem__("range_sessions", calls["range_sessions"] + 1) or [])
    snapshot = load_today_snapshot("unused.db", lambda process, _details: process)
    assert snapshot["interruption_analysis"]["status"] in {"ready", "empty", "unavailable"}
    assert calls["today_sessions"] == 1
    assert calls["range_sessions"] == 1
```

- [ ] **Step 2: Verify it fails**

Run: `python -m pytest tests/test_dashboard_service.py -k snapshot_includes_interruption_analysis -q`

Expected: FAIL because the snapshot lacks `interruption_analysis`.

- [ ] **Step 3: Add snapshot wiring**

Compute the analysis from the existing `sessions` value inside `load_today_snapshot`; wrap unexpected model failures as `{"status": "unavailable", "total_count": 0, "total_seconds": 0, "primary_source": None, "sources": []}`. Add the model to the returned snapshot without changing query functions.

- [ ] **Step 4: Verify it passes**

Run: `python -m pytest tests/test_dashboard_service.py -k snapshot_includes_interruption_analysis -q`

Expected: PASS.

- [ ] **Step 5: Commit snapshot integration**

```bash
git add src/daylens/services/dashboard_service.py tests/test_dashboard_service.py
git commit -m "feat: expose interruptions on dashboard snapshot"
```

### Task 3: Render the work interruption analysis card

**Files:**
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Test: `tests/test_dashboard_widgets.py`

- [ ] **Step 1: Write failing widget tests**

```python
def test_work_interruption_card_renders_summary_and_top_three_sources():
    card = dashboard_widgets.WorkInterruptionCard()
    card.set_data({
        "status": "ready", "total_count": 4, "total_seconds": 900,
        "primary_source": {"label": "微信", "count": 2, "seconds": 480, "kind": "social"},
        "sources": [
            {"label": "微信", "count": 2, "seconds": 480, "kind": "social"},
            {"label": "腾讯视频", "count": 1, "seconds": 240, "kind": "entertainment"},
            {"label": "离开电脑", "count": 1, "seconds": 180, "kind": "idle"},
            {"label": "Chrome", "count": 1, "seconds": 60, "kind": "browser"},
        ],
    })
    assert card._conclusion_label.text() == "今天被打断 4 次，主要来自 微信"
    assert len(card._source_rows) == 3
```

- [ ] **Step 2: Verify it fails**

Run: `python -m pytest tests/test_dashboard_widgets.py -k work_interruption_card -q`

Expected: FAIL because `WorkInterruptionCard` does not exist.

- [ ] **Step 3: Implement the widget**

Create `WorkInterruptionCard(QFrame)` beside existing dashboard cards. It must render plain-text labels, a conclusion, three compact metric cells (`明显干扰`, `离开工作`, `主要来源`), and no more than three source rows. Use fixed category colors: social primary blue, entertainment orange, idle grey, browser cyan-blue, other muted blue. Empty and unavailable states must hide source rows and present the approved explanatory copy.

- [ ] **Step 4: Verify widget tests pass**

Run: `python -m pytest tests/test_dashboard_widgets.py -k work_interruption_card -q`

Expected: PASS.

- [ ] **Step 5: Commit the widget**

```bash
git add src/daylens/gui/widgets/dashboard_widgets.py tests/test_dashboard_widgets.py
git commit -m "feat: add work interruption card"
```

### Task 4: Replace the focus timeline on the overview page

**Files:**
- Modify: `src/daylens/gui/pages/today_overview.py`
- Modify: `tests/test_homepage_redesign.py`
- Modify: `tests/test_ui_responsive_layout.py`

- [ ] **Step 1: Write failing page and responsive-layout tests**

```python
def test_today_overview_replaces_focus_timeline_with_interruption_card(tmp_path):
    page = TodayOverviewPage(str(tmp_path / "usage.db"))
    assert not hasattr(page, "focus_axis")
    assert page.interruption_card is not None
    assert page.work_episode_widget is not None
```

Add a responsive assertion at 1280×720 that the interruption card, work-episode list, and right column stay inside their parent bounds.

- [ ] **Step 2: Verify tests fail**

Run: `python -m pytest tests/test_homepage_redesign.py tests/test_ui_responsive_layout.py -k "interruption or dashboard" -q`

Expected: FAIL because `focus_axis` still exists and no interruption card is wired.

- [ ] **Step 3: Wire the new card**

Remove the `FocusTimelineBarWidget` import, the 24-hour tick row, legend, focus hint, and `focus_axis.set_minutes(...)` call. Add `self.interruption_card = WorkInterruptionCard()` above the unchanged `关键工作片段` section, and call `self.interruption_card.set_data(dict(snapshot.get("interruption_analysis", {}) or {}))` in `apply_snapshot`.

- [ ] **Step 4: Verify page tests pass**

Run: `python -m pytest tests/test_homepage_redesign.py tests/test_ui_responsive_layout.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the page replacement**

```bash
git add src/daylens/gui/pages/today_overview.py tests/test_homepage_redesign.py tests/test_ui_responsive_layout.py
git commit -m "feat: replace focus timeline with interruption analysis"
```

### Task 5: Final verification and release

**Files:**
- Verify: `src/`
- Verify: `tests/`

- [ ] **Step 1: Run full verification**

Run:

```bash
python -m pytest -q
python -m compileall -q src
git diff --check
```

Expected: all tests pass, compilation produces no output, and the diff check produces no output.

- [ ] **Step 2: Build and smoke-test the release**

Run: `python tools/build_release.py`

Confirm the release process is started only from `D:\OfficeSoftware\DayLens\release\DayLens.exe` and that the existing `D:\OfficeSoftware\DayLens\data\usage.db` remains in place.

- [ ] **Step 3: Commit the plan documentation**

```bash
git add docs/superpowers/plans/2026-09-02-work-interruption-analysis.md
git commit -m "docs: plan work interruption analysis"
```
