# AI Title Fallback Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make unknown DayLens titles visibly pending until DeepSeek returns, then prospectively apply every supported high-confidence category while preserving media playback gating, privacy, caching, and budget limits.

**Architecture:** Keep the existing order of manual override, local rules, and AI fallback. `IntelligenceScheduler.observe()` returns explicit pending or cached metadata without adding database fields; `SessionTracker` applies only high-confidence non-fallback categories and retains existing category timing policies. Existing JSON cache and budget files remain the only AI state.

**Tech Stack:** Python 3.14, PySide6, pytest, JSON state files, existing DeepSeek provider, PyInstaller.

---

### Task 1: Expose AI pending and confirmation states

**Files:**
- Modify: `src/daylens/services/intelligence_scheduler.py`
- Test: `tests/test_intelligence_scheduler.py`

- [ ] **Step 1: Write failing scheduler tests**

Assert that an eligible uncached title returns safe pending metadata, cached medium/low results remain suggestions, and disabled or missing-key operation still returns `None`:

```python
decision = see(scheduler, seconds=1)
assert decision == {
    'status': 'pending', 'source': 'AI待识别',
    'category': '', 'certainty': '', 'reason': '',
}
```

- [ ] **Step 2: Run test to verify RED**

Run: `python -m pytest -q tests/test_intelligence_scheduler.py`

Expected: pending assertions fail because `observe()` currently returns `None`.

- [ ] **Step 3: Implement explicit fallback metadata**

Add and use this helper only after eligibility, privacy, setting, and key checks:

```python
@staticmethod
def _pending_decision(reason=''):
    return {'status': 'pending', 'source': 'AI待识别',
            'category': '', 'certainty': '', 'reason': reason}
```

Do not change the 30-second threshold, batch size, daily cap, redaction, or cache identity.

- [ ] **Step 4: Run scheduler tests to verify GREEN**

Run: `python -m pytest -q tests/test_intelligence_scheduler.py`

Expected: all scheduler tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- src/daylens/services/intelligence_scheduler.py tests/test_intelligence_scheduler.py
git commit -m "feat: expose pending AI title classifications"
```

### Task 2: Apply all safe high-confidence AI categories

**Files:**
- Modify: `src/daylens/session_tracker.py`
- Test: `tests/test_intelligence_tracking.py`

- [ ] **Step 1: Write failing tracker tests**

Cover high-confidence `video` and `gaming`, medium-confidence suggestions, and pending display state:

```python
tracker.intelligence.decision = {
    'category': 'video', 'certainty': 'high', 'reason': '影视播放'
}
snapshot = tracker.tick(0, video_window)
assert snapshot['category_key'] == 'video'
assert snapshot['classification_detail']['source'] == 'AI'
```

- [ ] **Step 2: Run test to verify RED**

Run: `python -m pytest -q tests/test_intelligence_tracking.py`

Expected: video and gaming remain rejected; pending and medium results still show `规则`.

- [ ] **Step 3: Implement tracker policy**

Use this allowlist and exclude only fallback buckets:

```python
AI_APPLIED_CATEGORIES = {
    'coding', 'reading', 'office', 'ai_tools', 'creative',
    'social', 'tools', 'gaming', 'video',
}
```

Apply only for fallback base categories, `high` certainty, and configured target categories. Derive the display source as `AI`, `AI待识别`, `AI待确认`, or `规则`; preserve the existing prospective split and do not rewrite prior counters.

- [ ] **Step 4: Run tracker tests to verify GREEN**

Run: `python -m pytest -q tests/test_intelligence_tracking.py`

Expected: all tracker AI policy tests pass.

- [ ] **Step 5: Commit**

```powershell
git add -- src/daylens/session_tracker.py tests/test_intelligence_tracking.py
git commit -m "feat: apply high confidence AI title categories"
```

### Task 3: Prove entertainment timing remains gated

**Files:**
- Test: `tests/test_intelligence_tracking.py`
- Test: `tests/test_session_tracker_policies.py`

- [ ] **Step 1: Add media accounting regression tests**

Use the existing fake audio detector to prove an AI-classified video accrues passive time only while playback is detected and a silent or paused tail follows existing idle and auto-close behavior:

```python
assert session.category_key == 'video'
assert session.passive_seconds == audible_seconds
assert session.duration_seconds == (
    session.engaged_seconds + session.passive_seconds + session.idle_seconds
)
```

- [ ] **Step 2: Run media tests**

Run: `python -m pytest -q tests/test_intelligence_tracking.py tests/test_session_tracker_policies.py`

Expected: all pass without changing the audio, GPU, or network playback detector.

- [ ] **Step 3: Commit**

```powershell
git add -- tests/test_intelligence_tracking.py tests/test_session_tracker_policies.py
git commit -m "test: preserve media gating for AI title results"
```

### Task 4: Verify, package, and replace the canonical release

**Files:**
- Verify: `src/daylens/services/intelligence_scheduler.py`
- Verify: `src/daylens/session_tracker.py`
- Verify: `D:/OfficeSoftware/DayLens/release/DayLens.exe`

- [ ] **Step 1: Run focused and full verification**

```powershell
python -m pytest -q tests/test_intelligence_scheduler.py tests/test_intelligence_tracking.py tests/test_session_tracker_policies.py
python -m pytest -q
python -m compileall -q src
git diff --check
```

Expected: zero failures and zero compile or diff errors.

- [ ] **Step 2: Build staging release**

Run: `python tools/build_release.py --stage-only`

Expected: `Validated staging release prepared at: D:\OfficeSoftware\DayLens\release_staging`.

- [ ] **Step 3: Stop, replace, and restart safely**

Run `release/DayLens.exe maintenance-exit`, verify `runtime-state.json` reports `status=clean`, move the old canonical release to a timestamped recoverable backup, move staging to `release`, and start only `D:\OfficeSoftware\DayLens\release\DayLens.exe`.

- [ ] **Step 4: Runtime smoke**

Verify canonical process path, runtime heartbeat, `PRAGMA quick_check=ok`, retained Windows credential presence, readable classification cache, and absence of any new database path.

- [ ] **Step 5: Inspect final repository state**

```powershell
git status --short
git log -4 --oneline
```

Expected: only pre-existing unrelated user changes remain uncommitted.
