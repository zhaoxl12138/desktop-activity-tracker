"""Deterministic local fingerprints for report evidence freshness."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from .. import database
from .classification_semantics import resolve_classification_semantics


FINGERPRINT_VERSION = "report-evidence-v1"


def report_dates(kind: str, day: date) -> list[str]:
    if kind == "daily":
        return [day.isoformat()]
    if kind == "weekly":
        start = day - timedelta(days=day.weekday())
        return [(start + timedelta(days=i)).isoformat() for i in range(7)]
    if kind == "monthly":
        start = day.replace(day=1)
        return [(start + timedelta(days=i)).isoformat()
                for i in range((day - start).days + 1)]
    raise ValueError("Unsupported report kind")


def evidence_fingerprint(db_path: str, kind: str, dates: list[str]) -> str:
    """Hash report-relevant facts without copying titles into metadata."""
    if not dates:
        return ""
    if not Path(db_path).is_file():
        raise FileNotFoundError(db_path)
    with database.read_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, session_id, date, category_key, active_rule,
                   effective_seconds, engaged_seconds, passive_seconds,
                   idle_seconds, metric_version, classification_version
            FROM activity_sessions
            WHERE date BETWEEN ? AND ?
            ORDER BY id
            """,
            (dates[0], dates[-1]),
        ).fetchall()
        legacy = conn.execute(
            """
            SELECT COUNT(*), COALESCE(MAX(id), 0),
                   COALESCE(SUM(duration_seconds), 0)
            FROM activity_logs WHERE date BETWEEN ? AND ?
            """,
            (dates[0], dates[-1]),
        ).fetchone()
    facts = []
    for row in rows:
        raw_version = str(row["classification_version"] or "legacy")
        semantics = resolve_classification_semantics(raw_version)
        facts.append([
            int(row["id"]), str(row["session_id"] or ""), str(row["date"] or ""),
            str(row["category_key"] or ""), str(row["active_rule"] or ""),
            int(row["effective_seconds"] or 0), int(row["engaged_seconds"] or 0),
            int(row["passive_seconds"] or 0), int(row["idle_seconds"] or 0),
            str(row["metric_version"] or "legacy"), semantics.policy_version,
            semantics.source, raw_version,
        ])
    payload = {
        "version": FINGERPRINT_VERSION,
        "kind": str(kind),
        "dates": list(dates),
        "sessions": facts,
        "legacy": list(legacy) if legacy else [0, 0, 0],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
