# Trusted Metrics and Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate engaged attention from passive media time, version the measurement/classification rules, and show one local evidence-backed action on the DayLens homepage.

**Architecture:** Extend the existing Session model and SQLite schema without rewriting historical rows. Keep sampling logic in `SessionTracker`, aggregation in repositories, trust evaluation and insight selection in focused pure services, and Qt rendering in a small reusable card driven entirely by the dashboard snapshot.

**Tech Stack:** Python 3.11+, SQLite, PyYAML, PySide6, pytest

---

## File map

- Modify `src/daylens/session_tracker.py`: own mutually exclusive engaged/passive/idle counters and metric version.
- Modify `src/daylens/classifier.py`: expose a deterministic fingerprint for the effective rules.
- Modify `src/daylens/repositories/connection_repository.py`: schema v4 migration.
- Modify `src/daylens/repositories/session_repository.py`: persist and update the new Session fields.
- Modify `src/daylens/repositories/stats_repository.py`: aggregate new counters and expose version metadata.
- Modify `src/daylens/services/session_recovery_service.py`: preserve the new fields in recovery spools while loading v1 spools.
- Create `src/daylens/services/trusted_metrics_service.py`: assess coverage, invariants, versions, and comparability.
- Create `src/daylens/services/insights_service.py`: select one deterministic insight from trusted aggregates.
- Modify `src/daylens/services/dashboard_service.py`: compose trusted totals and insight view data.
- Modify `src/daylens/gui/widgets/dashboard_widgets.py`: add a compact trusted-insight card.
- Modify `src/daylens/gui/pages/today_overview.py`: render engaged/passive status and insight snapshot.
- Modify `src/daylens/exporter.py`: append engaged/passive/trust fields to daily Markdown/CSV without removing legacy fields.
- Add focused tests under `tests/` for every module above.

### Task 1: Schema, Session model, persistence, and recovery

**Files:**
- Modify: `src/daylens/repositories/connection_repository.py`
- Modify: `src/daylens/session_tracker.py`
- Modify: `src/daylens/repositories/session_repository.py`
- Modify: `src/daylens/services/session_recovery_service.py`
- Modify: `tests/test_database_migrations.py`
- Modify: `tests/test_session_runtime_service.py`
- Modify: `tests/test_session_recovery_service.py`

- [ ] **Step 1: Add failing schema and persistence tests**

Add a v3 migration test asserting schema version `4`, the four new columns, and legacy defaults. Extend the runtime round-trip test with explicit values:

```python
session.engaged_seconds = 5
session.passive_seconds = 3
session.metric_version = "attention-v1"
session.classification_version = "rules-abcd1234"

row = conn.execute(
    "SELECT engaged_seconds, passive_seconds, metric_version, "
    "classification_version FROM activity_sessions WHERE session_id = ?",
    (session.session_id,),
).fetchone()
assert row == (5, 3, "attention-v1", "rules-abcd1234")
```

Add a recovery test that stores and reloads these values, plus a compatibility test loading a version-1 spool with no new keys and expecting zero/legacy defaults.

- [ ] **Step 2: Run focused tests and confirm failure**

Run:

```powershell
py -m pytest -q tests/test_database_migrations.py tests/test_session_runtime_service.py tests/test_session_recovery_service.py
```

Expected: failures for schema version/columns and missing `ActivitySession` fields.

- [ ] **Step 3: Add schema v4 and model fields**

Append columns to the canonical table definition and implement an idempotent v4 migration:

```python
for column, definition in (
    ("engaged_seconds", "INTEGER DEFAULT 0"),
    ("passive_seconds", "INTEGER DEFAULT 0"),
    ("metric_version", "TEXT DEFAULT 'legacy'"),
    ("classification_version", "TEXT DEFAULT 'legacy'"),
):
    if column not in columns:
        conn.execute(f"ALTER TABLE activity_sessions ADD COLUMN {column} {definition}")
conn.execute(
    "INSERT INTO schema_meta(key, value) VALUES('schema_version', '4') "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
)
```

Extend `ActivitySession` with backward-compatible defaults:

```python
engaged_seconds: int = 0
passive_seconds: int = 0
metric_version: str = "attention-v1"
classification_version: str = "legacy"
```

- [ ] **Step 4: Persist all fields atomically**

Add the four columns to both `INSERT OR REPLACE` and `UPDATE`. Do not infer historical values. Keep `effective_seconds` as a stored compatibility value.

- [ ] **Step 5: Upgrade the recovery spool compatibly**

Write spool version 2 with the new fields. Accept version 1 and provide defaults during deserialization:

```python
values.setdefault("engaged_seconds", 0)
values.setdefault("passive_seconds", 0)
values.setdefault("metric_version", "legacy")
values.setdefault("classification_version", "legacy")
```

Convert both new counters to `int` with the existing duration counters.

- [ ] **Step 6: Run the focused tests**

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/daylens/session_tracker.py src/daylens/repositories/connection_repository.py src/daylens/repositories/session_repository.py src/daylens/services/session_recovery_service.py tests/test_database_migrations.py tests/test_session_runtime_service.py tests/test_session_recovery_service.py
git commit -m "feat: store trusted session metrics"
```

### Task 2: Deterministic classification version

**Files:**
- Modify: `src/daylens/classifier.py`
- Modify: `src/daylens/session_tracker.py`
- Modify: `tests/test_classifier_integrity.py`
- Modify: `tests/test_session_tracker_policies.py`

- [ ] **Step 1: Write failing fingerprint tests**

Create equivalent configs with category keys and match lists in different orders and assert identical versions. Change one keyword and assert a different version:

```python
assert Classifier.rule_fingerprint(config_a) == Classifier.rule_fingerprint(config_b)
assert Classifier.rule_fingerprint(config_a) != Classifier.rule_fingerprint(config_changed)
```

Assert a newly created Session receives `tracker.classification_version`.

- [ ] **Step 2: Run the focused tests and confirm failure**

```powershell
py -m pytest -q tests/test_classifier_integrity.py tests/test_session_tracker_policies.py
```

Expected: `rule_fingerprint` and tracker version attributes are missing.

- [ ] **Step 3: Implement canonical rule hashing**

Normalize mappings by sorted key and unordered rule lists by sorted unique strings, then hash canonical JSON:

```python
@staticmethod
def rule_fingerprint(config: dict) -> str:
    categories = config.get("categories", {})
    canonical = {}
    for key in sorted(categories):
        rule = categories[key] or {}
        match = rule.get("match", {}) or {}
        canonical[key] = {
            "active_rule": str(rule.get("active_rule", "")),
            "process_names": sorted({str(v).casefold() for v in match.get("process_names", [])}),
            "title_keywords": sorted({str(v).casefold() for v in match.get("title_keywords", [])}),
            "title_patterns": sorted({str(v) for v in match.get("title_patterns", [])}),
        }
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "rules-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
```

Set `self.classification_version` during `Classifier` initialization and let `SessionTracker` read it with a `legacy` fallback.

- [ ] **Step 4: Run tests and commit**

```powershell
py -m pytest -q tests/test_classifier_integrity.py tests/test_session_tracker_policies.py
git add src/daylens/classifier.py src/daylens/session_tracker.py tests/test_classifier_integrity.py tests/test_session_tracker_policies.py
git commit -m "feat: version classification rules"
```

### Task 3: Mutually exclusive attention counters

**Files:**
- Modify: `src/daylens/session_tracker.py`
- Modify: `tests/test_session_tracker_policies.py`
- Modify: `tests/test_timeline_logic.py`

- [ ] **Step 1: Replace the legacy audio expectation with failing attention tests**

Cover four cases with a one-second sample interval and small thresholds:

```python
assert active_video.engaged_seconds == 1
assert active_video.passive_seconds == 0

assert idle_video_with_audio.engaged_seconds == 0
assert idle_video_with_audio.passive_seconds == 3

assert idle_video_without_audio.idle_seconds == 3
assert work_session.passive_seconds == 0
```

For every emitted Session assert:

```python
assert session.duration_seconds == (
    session.engaged_seconds + session.passive_seconds + session.idle_seconds
)
assert session.effective_seconds == session.engaged_seconds + session.passive_seconds
```

Add equivalent conservation checks for pending switches, failed persistence retries, cross-day, and system gaps.

- [ ] **Step 2: Run tracker tests and confirm failure**

```powershell
py -m pytest -q tests/test_session_tracker_policies.py tests/test_timeline_logic.py
```

- [ ] **Step 3: Introduce one counter-classification helper**

Use a single helper from both current and pending Session paths:

```python
def _attention_bucket(self, category_key: str, audio_playing: bool) -> str:
    if self._persistent_idle <= self.idle_threshold:
        return "engaged"
    if category_key == "video" and audio_playing:
        return "passive"
    return "idle"
```

Do not reset `_persistent_idle` when audio is playing. Increment exactly one component per tick and recompute compatibility time:

```python
bucket = self._attention_bucket(self._current.category_key, audio_playing)
if bucket == "engaged":
    self._current.engaged_seconds += self.sample_interval
elif bucket == "passive":
    self._current.passive_seconds += self.sample_interval
else:
    self._current.idle_seconds += self.sample_interval
self._current.effective_seconds = (
    self._current.engaged_seconds + self._current.passive_seconds
)
```

When the legacy threshold back-correction fires, move seconds from engaged to passive for audible video and from engaged to idle otherwise. Extend pending-switch dictionaries with `engaged_during_grace`, `passive_during_grace`, and `idle_during_grace` and derive `effective_during_grace` only for snapshots/tests that still need it.

- [ ] **Step 4: Make snapshots explicit**

Add:

```python
"engaged_seconds": s.engaged_seconds if s else 0,
"passive_seconds": s.passive_seconds if s else 0,
"attention_state": bucket,
"metric_version": s.metric_version if s else "attention-v1",
"classification_version": s.classification_version if s else self.classification_version,
```

`is_effective` remains `attention_state in {"engaged", "passive"}` for compatibility.

- [ ] **Step 5: Run tracker and recording tests**

```powershell
py -m pytest -q tests/test_session_tracker_policies.py tests/test_timeline_logic.py tests/test_recording_worker.py tests/test_session_runtime_service.py
```

Expected: all pass and no conservation assertion fails.

- [ ] **Step 6: Commit**

```powershell
git add src/daylens/session_tracker.py tests/test_session_tracker_policies.py tests/test_timeline_logic.py
git commit -m "feat: separate engaged and passive time"
```

### Task 3A: Bounded attention rewrites and shutdown recovery

**Files:**
- Modify: `src/daylens/session_tracker.py`
- Modify: `src/daylens/services/session_runtime_service.py`
- Modify: `src/daylens/gui/worker.py`
- Modify: `src/daylens/services/command_handlers.py`
- Modify: `tests/test_session_tracker_policies.py`
- Modify: `tests/test_session_runtime_service.py`
- Modify: `tests/test_recording_worker.py`
- Modify: `tests/test_command_handlers_recording.py`

- [ ] **Step 1: Add reset-epoch and bounded rewrite red tests**

Add a tracker test where two provisional Code samples are followed by an
immediate audible-video switch. Advance the new idle epoch past its threshold
and assert the old Code session remains engaged and the provisional ledger
never contains more than one threshold window. Add a permanent-False rewrite
test with `attention_rewrite_queue_size=2`; assert `pending_rewrite_sessions()`
contains two unique IDs and the next tick raises backpressure before changing
the current session.

- [ ] **Step 2: Run the tracker red tests**

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_session_tracker_policies.py -k "idle_epoch or rewrite_backpressure"
```

Expected: the old Code session is rewritten by the new video epoch and the
explicit rewrite callback/snapshot API is absent.

- [ ] **Step 3: Centralize idle-epoch resets and add an explicit callback**

Add `_reset_idle_epoch()` that resets `_persistent_idle`, `_idle_corrected`, and
`_provisional_attention`, while leaving `_pending_attention_rewrites` intact.
Use it at every real idle-epoch reset site. Add the constructor callback
`on_session_rewrite`, document that it must perform an idempotent upsert by
`session_id`, and remove the fallback to `on_session_end`.

- [ ] **Step 4: Add bounded ownership and drain APIs**

Configure `attention_rewrite_queue_size` with a finite default. Before moving a
provisional ledger, reserve capacity for every unique persisted owner. If the
reservation cannot fit, raise `AttentionRewriteBackpressure` without moving the
ledger; while saturated, retry before sampling and refuse to advance until
capacity is available. Expose immutable `pending_rewrite_sessions()`, explicit
`drain_pending_rewrites()`, and acknowledgement by session ID after recovery
spooling.

- [ ] **Step 5: Add runtime and worker recovery red tests**

Add a `SessionRuntimeStore.rewrite_session()` test showing that the same
`session_id` updates the existing row. Add worker tests proving its normal
rewrite adapter hands failures to `_pending_persists`, and cleanup spools both
tracker-held rewrites and the current tail. Replay that spool into a succeeding
store and assert every ID is restored exactly once.

- [ ] **Step 6: Implement explicit adapters and shutdown aggregation**

Make `SessionRuntimeStore.rewrite_session()` delegate to its existing
idempotent upsert. Pass a dedicated worker rewrite adapter into SessionTracker.
During cleanup, drain tracker rewrites around the existing worker queue drains;
if any remain, merge them with `_pending_persists` and `_retained_tail` by
`session_id` before `SessionRecoverySpool.store_sessions()`, then acknowledge
tracker ownership only after the atomic spool succeeds. Apply the same snapshot
merge in CLI shutdown recovery.

- [ ] **Step 7: Verify and commit**

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_session_tracker_policies.py tests/test_session_runtime_service.py tests/test_recording_worker.py tests/test_command_handlers_recording.py tests/test_session_recovery_service.py
python -m pytest -q
python -m compileall -q src tests
git diff --check
git add docs/superpowers/plans/2026-08-11-trusted-metrics-insights.md src/daylens/session_tracker.py src/daylens/services/session_runtime_service.py src/daylens/gui/worker.py src/daylens/services/command_handlers.py tests/test_session_tracker_policies.py tests/test_session_runtime_service.py tests/test_recording_worker.py tests/test_command_handlers_recording.py
git commit -m "fix: bound and recover attention rewrites"
```

### Task 3B: Safe runtime shrink and isolated rewrite snapshots

**Files:**
- Modify: `src/daylens/session_tracker.py`
- Modify: `src/daylens/gui/worker.py`
- Modify: `tests/test_session_tracker_policies.py`
- Modify: `tests/test_recording_worker.py`

- [ ] **Step 1: Add the runtime-shrink red test**

Create three persisted provisional owners while the configured rewrite
capacity is three, then request capacity one before the idle threshold is
confirmed. Assert the effective capacity remains three until correction can
invoke a succeeding rewrite callback for every owner, then converges to one.
Assert a subsequent tick advances instead of repeatedly raising
`AttentionRewriteBackpressure`.

- [ ] **Step 2: Run and confirm the shrink failure**

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_session_tracker_policies.py -k "runtime_shrink"
```

Expected: direct capacity shrink leaves three reserved owners against capacity
one, so correction raises before invoking the healthy callback.

- [ ] **Step 3: Implement deferred capacity convergence**

Add a tracker method that records the requested capacity and computes the
effective capacity as at least the union of pending rewrite IDs and persisted
provisional owner IDs. Recompute after correction, retry, acknowledgement, and
idle-ledger reset. Have worker hot reload call this public method so published
settings retain the requested value while tracker state exposes the temporarily
safe effective value.

- [ ] **Step 4: Add the isolated-snapshot red test**

Queue a corrected rewrite, obtain `pending_rewrite_sessions()`, mutate every
counter and title on the returned session, then fetch a second snapshot and
assert all tracker-owned values remain unchanged. Acknowledge the rewrite by
the copied session's `session_id` and assert the internal queue is empty.

- [ ] **Step 5: Return deep snapshot copies**

Build the tuple with `copy.deepcopy()` for each queued `ActivitySession`.
Keep callback drain on tracker-owned sessions and acknowledgement keyed only by
the string `session_id`, never object identity.

- [ ] **Step 6: Verify and append the fix commit**

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_session_tracker_policies.py tests/test_recording_worker.py tests/test_session_runtime_service.py tests/test_command_handlers_recording.py tests/test_session_recovery_service.py tests/test_timeline_logic.py
python -m pytest -q
python -m compileall -q src tests
git diff --check
git add docs/superpowers/plans/2026-08-11-trusted-metrics-insights.md src/daylens/session_tracker.py src/daylens/gui/worker.py tests/test_session_tracker_policies.py tests/test_recording_worker.py
git commit -m "fix: make rewrite capacity updates safe"
```

### Task 4: Aggregation and trust assessment

**Files:**
- Modify: `src/daylens/repositories/stats_repository.py`
- Create: `src/daylens/services/trusted_metrics_service.py`
- Modify: `src/daylens/database.py`
- Create: `tests/test_trusted_metrics_service.py`
- Modify: `tests/test_range_aggregation.py`

- [ ] **Step 1: Write failing aggregation and trust tests**

Build temporary databases containing all-v4, mixed-version, and legacy rows. Assert date and range totals include:

```python
assert totals["engaged_seconds"] == 120
assert totals["passive_seconds"] == 60
assert totals["work_engaged_seconds"] == 90
assert totals["metric_versions"] == ["attention-v1"]
assert totals["classification_versions"] == ["rules-a"]
```

Trust cases:

```python
assert assess_range(rows, expected_dates)["level"] == "high"
assert assess_range(mixed_rules, expected_dates)["level"] == "medium"
assert assess_range(mostly_legacy, expected_dates)["level"] == "low"
assert compare_ranges(left, right)["comparable"] is False
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -m pytest -q tests/test_range_aggregation.py tests/test_trusted_metrics_service.py
```

- [ ] **Step 3: Extend session aggregations**

Add `SUM(engaged_seconds)`, `SUM(passive_seconds)`, and version sets to date/range queries. For legacy log fallback return zero engaged/passive and `['legacy']` versions. Extend merge payloads without changing existing keys.

- [ ] **Step 4: Implement the pure trust service**

Define:

```python
def assess_range(summary: dict, expected_dates: list[str]) -> dict[str, object]:
    expected = set(expected_dates)
    recorded = set(summary.get("dates_with_data", []))
    coverage_ratio = len(recorded & expected) / len(expected) if expected else 1.0
    session_count = int(summary.get("session_count", 0) or 0)
    legacy_count = int(summary.get("legacy_session_count", 0) or 0)
    legacy_ratio = legacy_count / session_count if session_count else 1.0
    anomaly_count = int(summary.get("anomaly_count", 0) or 0)
    anomaly_ratio = anomaly_count / session_count if session_count else 0.0
    metric_versions = sorted(set(summary.get("metric_versions", [])))
    classification_versions = sorted(set(summary.get("classification_versions", [])))
    reasons = []
    if coverage_ratio < 0.8:
        reasons.append("记录日期覆盖不足80%")
    if legacy_ratio > 0.2:
        reasons.append("旧计量口径占比超过20%")
    if anomaly_ratio > 0.005:
        reasons.append("计时组成异常率超过0.5%")
    if len(metric_versions) != 1:
        reasons.append("范围内存在多个计量版本")
    if reasons:
        level = "low"
    elif legacy_ratio > 0 or len(classification_versions) != 1:
        level = "medium"
    else:
        level = "high"
    return {
        "level": level,
        "reasons": reasons,
        "coverage_ratio": coverage_ratio,
        "legacy_ratio": legacy_ratio,
        "metric_versions": metric_versions,
        "classification_versions": classification_versions,
        "category_comparable": level != "low" and len(classification_versions) == 1,
    }


def compare_ranges(left: dict, right: dict) -> dict[str, object]:
    metric_comparable = (
        left.get("level") != "low"
        and right.get("level") != "low"
        and left.get("metric_versions") == right.get("metric_versions")
    )
    category_comparable = (
        metric_comparable
        and left.get("classification_versions") == right.get("classification_versions")
    )
    return {
        "comparable": metric_comparable,
        "category_comparable": category_comparable,
        "reason": "" if metric_comparable else "计量版本或数据质量不一致",
    }
```

Return `level`, `reasons`, `coverage_ratio`, `legacy_ratio`, `metric_versions`, `classification_versions`, and `category_comparable`. Apply the thresholds from the design exactly and keep reason strings stable for tests/UI.

- [ ] **Step 5: Run tests and commit**

```powershell
py -m pytest -q tests/test_range_aggregation.py tests/test_trusted_metrics_service.py tests/test_mixed_history_queries.py
git add src/daylens/repositories/stats_repository.py src/daylens/services/trusted_metrics_service.py src/daylens/database.py tests/test_range_aggregation.py tests/test_trusted_metrics_service.py
git commit -m "feat: assess metric trust and comparability"
```

### Task 5: Deterministic local insight selection

**Files:**
- Create: `src/daylens/services/insights_service.py`
- Create: `tests/test_insights_service.py`

- [ ] **Step 1: Write failing priority and suppression tests**

Tests must cover data-health, best-window, interruption, trend, workflow, and sample-insufficient inputs. Assert only one result:

```python
insight = select_primary_insight(payload)
assert insight == {
    "kind": "best_window",
    "title": "你的优势时段是 09:00–11:00",
    "evidence": "最近14天有6个工作日，32%的工作参与时间集中在这里。",
    "action": "把最难的任务优先放进这个两小时窗口。",
    "confidence": "high",
    "date_range": ["2026-07-28", "2026-08-10"],
}
```

Low trust must always win and must not include productivity judgment. Mixed classification versions must suppress category trend and interruption candidates.

- [ ] **Step 2: Run and confirm failure**

```powershell
py -m pytest -q tests/test_insights_service.py
```

- [ ] **Step 3: Implement small candidate builders**

Create focused functions:

```python
def select_primary_insight(payload: dict) -> dict | None:
    trust = payload["trust"]
    if trust["level"] == "low":
        reason = trust["reasons"][0] if trust["reasons"] else "新口径数据仍在积累"
        return {
            "kind": "data_health",
            "title": "先让数据口径稳定",
            "evidence": reason,
            "action": "继续记录，新旧口径不会被直接混合比较。",
            "confidence": "low",
            "date_range": payload["date_range"],
        }
    builders = (
        build_best_window_candidate,
        build_interruption_candidate,
        build_trend_candidate,
        build_workflow_candidate,
    )
    for builder in builders:
        candidate = builder(payload)
        if candidate is not None:
            candidate["confidence"] = trust["level"]
            candidate["date_range"] = payload["date_range"]
            return candidate
    return None
```

The four candidate builders use the exact thresholds from the design and return a complete dictionary with `kind`, `title`, `evidence`, and `action`, or `None`. `select_primary_insight()` evaluates them in the design priority order and returns the first non-`None` result. Use only supplied aggregates; this module must not import SQLite, Qt, or network libraries.

- [ ] **Step 4: Run tests and commit**

```powershell
py -m pytest -q tests/test_insights_service.py
git add src/daylens/services/insights_service.py tests/test_insights_service.py
git commit -m "feat: generate one trusted local insight"
```

### Task 6: Dashboard snapshot and compact UI

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Modify: `src/daylens/gui/pages/today_overview.py`
- Modify: `tests/test_dashboard_service.py`
- Modify: `tests/test_dashboard_widgets.py`
- Modify: `tests/test_homepage_redesign.py`

- [ ] **Step 1: Write failing snapshot and widget tests**

Replace `test_today_snapshot_no_longer_exposes_insights` with assertions for:

```python
assert snapshot["totals"]["engaged_seconds"] == 0
assert snapshot["totals"]["passive_seconds"] == 0
assert snapshot["trust"]["level"] == "low"
assert snapshot["insight"]["kind"] == "data_health"
```

Add a widget test that sets a complete insight, verifies all three lines and confidence text, then sets `None` and verifies the waiting state. Add a responsive-layout test at 1280×720.

- [ ] **Step 2: Run and confirm failure**

```powershell
py -m pytest -q tests/test_dashboard_service.py tests/test_dashboard_widgets.py tests/test_homepage_redesign.py
```

- [ ] **Step 3: Compose the snapshot off the GUI thread**

Have `load_today_snapshot` query today plus rolling 14/7-day ranges once, call the trust and insights services, and append:

```python
"totals": {
    **legacy_totals,
    "engaged_seconds": engaged_seconds,
    "passive_seconds": passive_seconds,
},
"trust": trust,
"insight": insight,
```

Retain every existing snapshot key so tray and old widgets remain compatible.

- [ ] **Step 4: Add `TrustedInsightCard`**

Create a fixed, compact `QFrame` with three eliding/wrapping labels and a confidence badge. Its public API is:

```python
class TrustedInsightCard(QFrame):
    def set_insight(self, insight: dict[str, object] | None) -> None:
        if not insight:
            self.title_label.setText("洞察积累中")
            self.evidence_label.setText("继续记录以形成可靠基线")
            self.action_label.clear()
            self.confidence_label.setText("数据不足")
            return
        self.title_label.setText(str(insight.get("title", "今日建议")))
        self.evidence_label.setText(str(insight.get("evidence", "")))
        self.action_label.setText(str(insight.get("action", "")))
        confidence = str(insight.get("confidence", "low"))
        self.confidence_label.setText(
            {"high": "高可信", "medium": "中可信", "low": "低可信"}.get(
                confidence, "低可信"
            )
        )
```

Use existing `COLORS` and dashboard card style; do not hardcode a separate theme.

- [ ] **Step 5: Wire the homepage**

Place the insight card above the trend chart. Change the status row labels to `参与` and `被动媒体`, show a yellow `口径待稳定` badge for medium/low trust, and call `set_insight(snapshot.get("insight"))` in `apply_snapshot`. When classification versions differ, show `分类规则已变化，分类趋势暂不可比` under the trend controls instead of a numeric category delta.

- [ ] **Step 6: Run UI tests and commit**

```powershell
py -m pytest -q tests/test_dashboard_service.py tests/test_dashboard_widgets.py tests/test_homepage_redesign.py tests/test_ui_responsive_layout.py tests/test_gui_smoke.py
git add src/daylens/services/dashboard_service.py src/daylens/gui/widgets/dashboard_widgets.py src/daylens/gui/pages/today_overview.py tests/test_dashboard_service.py tests/test_dashboard_widgets.py tests/test_homepage_redesign.py
git commit -m "feat: show trusted attention insight"
```

### Task 7: Daily report and export compatibility

**Files:**
- Modify: `src/daylens/exporter.py`
- Modify: `tests/test_software_stats_export.py`
- Modify: `tests/test_report_atomic_writes.py`
- Add: `tests/test_trusted_report_fields.py`

- [ ] **Step 1: Write failing report tests**

Generate a daily Markdown report from v4 rows and assert it contains:

```text
- 参与时间：
- 被动媒体：
- 数据可信度：
```

Assert legacy `活跃时间` and existing timeline/category sections remain present. For CSV, assert new columns are appended after old columns.

- [ ] **Step 2: Run and confirm failure**

```powershell
py -m pytest -q tests/test_software_stats_export.py tests/test_report_atomic_writes.py tests/test_trusted_report_fields.py
```

- [ ] **Step 3: Append trusted fields without renaming legacy columns**

Use aggregated `engaged_seconds` and `passive_seconds`. Call `trusted_metrics_service` for the date and render `高/中/低` plus the first reason. When the date is legacy-only, render zero new counters and low confidence rather than deriving false history.

- [ ] **Step 4: Run report tests and commit**

```powershell
py -m pytest -q tests/test_software_stats_export.py tests/test_report_atomic_writes.py tests/test_trusted_report_fields.py tests/test_reports_service.py
git add src/daylens/exporter.py tests/test_software_stats_export.py tests/test_report_atomic_writes.py tests/test_trusted_report_fields.py
git commit -m "feat: export trusted attention metrics"
```

### Task 8: Full verification, data migration rehearsal, and release build

**Files:**
- Modify only if verification exposes a defect.

- [ ] **Step 1: Run formatting/health checks**

```powershell
git diff --check
py -m compileall -q src
```

Expected: no output and exit code 0.

- [ ] **Step 2: Run the complete test suite**

```powershell
py -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Rehearse migration on a copy, never on live data**

Copy `data/usage.db` with SQLite backup API into a temporary directory, run `database.init_db()` against the copy, and assert schema version 4, unchanged pre-migration row count, and legacy defaults for old rows. Delete only the explicitly created temporary directory after validation.

- [ ] **Step 4: Run the release build**

```powershell
py tools/build_release.py
```

Expected: exit code 0 and `release/DayLens.exe` exists.

- [ ] **Step 5: Review working tree and commit any verification-only fix**

```powershell
git status --short
git log -8 --oneline
```

Do not stage existing untracked PDF, historical plans/specs, or debug screenshots.
