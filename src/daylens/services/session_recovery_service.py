"""Durable local recovery spool for sessions not persisted during shutdown."""

from __future__ import annotations

import json
import os
import tempfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ..session_tracker import ActivitySession


_SCHEMA_VERSION = 2
_LEGACY_SESSION_FIELDS = (
    "session_id",
    "start_time",
    "end_time",
    "date",
    "process_name",
    "exe_path",
    "window_title",
    "normalized_title",
    "category_key",
    "category_name",
    "active_rule",
    "duration_seconds",
    "effective_seconds",
    "idle_seconds",
    "switch_reason",
    "initial_title",
)
_TRUSTED_METRIC_FIELDS = (
    "engaged_seconds",
    "passive_seconds",
    "metric_version",
    "classification_version",
)
_SESSION_FIELDS = _LEGACY_SESSION_FIELDS + _TRUSTED_METRIC_FIELDS


def default_recovery_path(db_path: str | os.PathLike[str]) -> Path:
    """Return the database-specific sidecar path used for local recovery."""

    return Path(f"{db_path}.session-recovery.json")


class SessionRecoverySpool:
    """Atomically preserve and replay unresolved ``ActivitySession`` objects."""

    def __init__(
        self,
        db_path: str | os.PathLike[str],
        *,
        recovery_path: str | os.PathLike[str] | None = None,
    ):
        self.path = (
            Path(recovery_path)
            if recovery_path is not None
            else default_recovery_path(db_path)
        )

    def load_sessions(self) -> list[ActivitySession]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Session recovery spool could not be read") from error
        if not isinstance(payload, dict) or payload.get("version") not in (1, 2):
            raise RuntimeError("Unsupported session recovery spool format")
        version = payload["version"]
        records = payload.get("sessions")
        if not isinstance(records, list):
            raise RuntimeError("Invalid session recovery spool records")
        return [self._deserialize_session(record, version) for record in records]

    def store_sessions(self, sessions: Iterable[ActivitySession]) -> int:
        """Merge sessions by ID and atomically replace the recovery sidecar."""

        merged: OrderedDict[str, ActivitySession] = OrderedDict(
            (session.session_id, session) for session in self.load_sessions()
        )
        for session in sessions:
            session_id = str(getattr(session, "session_id", ""))
            if not session_id:
                raise ValueError("Recovery session must have a session_id")
            merged[session_id] = session
        if not merged:
            return 0
        self._atomic_write(list(merged.values()))
        return len(merged)

    def replay(self, store) -> int:
        """Replay every spooled session and delete only after full success."""

        sessions = self.load_sessions()
        for session in sessions:
            result = store.persist_session(session)
            self._validate_persist_result(result)
        if sessions:
            self.clear()
        return len(sessions)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)

    def _atomic_write(self, sessions: list[ActivitySession]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    {
                        "version": _SCHEMA_VERSION,
                        "sessions": [
                            self._serialize_session(session) for session in sessions
                        ],
                    },
                    stream,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _serialize_session(session: ActivitySession) -> dict[str, object]:
        record: dict[str, object] = {}
        for name in _SESSION_FIELDS:
            value = getattr(session, name)
            if isinstance(value, datetime):
                value = value.isoformat()
            record[name] = value
        return record

    @staticmethod
    def _deserialize_session(record: object, version: int) -> ActivitySession:
        if not isinstance(record, dict):
            raise RuntimeError("Invalid session recovery record")
        required_fields = (
            _LEGACY_SESSION_FIELDS if version == 1 else _SESSION_FIELDS
        )
        missing = [name for name in required_fields if name not in record]
        if missing:
            raise RuntimeError("Incomplete session recovery record")
        try:
            values = {name: record[name] for name in _LEGACY_SESSION_FIELDS}
            if version == 1:
                values.update(
                    engaged_seconds=0,
                    passive_seconds=0,
                    metric_version="legacy",
                    classification_version="legacy",
                )
            else:
                values.update(
                    {name: record[name] for name in _TRUSTED_METRIC_FIELDS}
                )
            session_id = values["session_id"]
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("missing session id")
            values["start_time"] = datetime.fromisoformat(str(values["start_time"]))
            values["end_time"] = datetime.fromisoformat(str(values["end_time"]))
            for name in (
                "duration_seconds",
                "effective_seconds",
                "idle_seconds",
                "engaged_seconds",
                "passive_seconds",
            ):
                values[name] = int(values[name])
            return ActivitySession(**values, _db_row_id=-1)
        except (TypeError, ValueError) as error:
            raise RuntimeError("Invalid session recovery record") from error

    @staticmethod
    def _validate_persist_result(result) -> None:
        if result is None or result is False:
            raise RuntimeError("Recovery persistence did not report success")
        if isinstance(result, int) and result <= 0:
            raise RuntimeError("Recovery persistence returned an invalid row id")
