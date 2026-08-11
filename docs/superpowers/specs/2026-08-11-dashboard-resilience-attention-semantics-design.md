# Dashboard Resilience and Attention Semantics Design

## Goal

Keep the Dashboard usable when persisted session rows contain malformed numeric or timestamp fields, while ensuring new attention snapshots consistently present engaged time as “参与时长” and legacy snapshots explicitly retain “有效时长” semantics.

## Selected approach

Use the raw range aggregates as the source of truth for trust assessment, and create strict, sanitized session copies only at the Dashboard consumption boundary. A valid duration contribution is a finite, non-negative integer value and a valid interval has two parseable timestamps with an end no earlier than its start. Invalid values contribute nothing to hourly series, best-window, focus, interruption, workflow, and session widgets; the original malformed row remains represented in the aggregate anomaly counts. If injected session rows expose an anomaly that is missing from a mocked or stale aggregate, Dashboard trust is forced low instead of silently retaining high trust.

The timeline service applies the same strict validation before distributing a database row. This keeps `build_focus_summary` compatible with corrupt rows without hiding the anomaly from trusted aggregation.

## Snapshot semantics

Existing snapshot keys remain unchanged. New snapshots add explicit semantic metadata:

- `totals.primary_metric` is `engaged`; `engaged_seconds` is the primary duration.
- `trend.thirty_day_metric` is `engaged`; 30-day points use daily `engaged_seconds`.
- If a legacy caller omits `engaged_seconds` or the semantic marker, the UI falls back to `effective_seconds` and labels it “有效时长”.

For new snapshots the donut uses engaged, passive, and idle segments, with its center value labeled “参与时长”. The adjacent category legend remains a category breakdown. The top summary capsule also uses engaged seconds and the same label. The 30-day legend reads “每日参与时间”; legacy snapshots read “每日有效时间”. Today’s hourly series still uses the established effective-time data, so any visible ratio label for that series uses “有效” rather than “活跃”.

## Error handling

- Invalid session numerics, booleans, NaN, infinities, and malformed or reversed timestamps never escape as conversion errors.
- Invalid contributions are skipped rather than clamped into meaningful time.
- Trusted aggregation remains authoritative; normal aggregate anomaly detection yields low trust and a data-health insight.
- Unexpected trusted-calculation failures retain the existing behavior of hiding the insight card.
- Old snapshot keys and rendering remain supported.

## Tests

- A real SQLite database with malformed numeric and timestamp fields returns a complete Dashboard snapshot with low trust and a data-health insight.
- Injected malformed sessions do not crash hourly, best-window, timeline, or Qt rendering paths and cannot retain high trust.
- New snapshots use engaged seconds for the donut, top capsule, and 30-day series and render “参与” wording.
- Legacy snapshots fall back to effective seconds and render “有效” wording.
- Focused Dashboard/widget/homepage/GUI smoke tests run before the full suite, followed by compile and diff checks.
