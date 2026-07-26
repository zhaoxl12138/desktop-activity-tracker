"""Narrow runtime persistence helpers for session-tracking loops."""

from __future__ import annotations

from .. import database


class SessionRuntimeStore:
    def __init__(self, db_path: str):
        self._conn = database.init_db(db_path)

    def persist_session(
        self,
        session,
        *,
        busy_timeout_ms: int | None = None,
    ) -> int:
        previous_timeout = None
        if busy_timeout_ms is not None:
            row = self._conn.execute("PRAGMA busy_timeout").fetchone()
            previous_timeout = int(row[0]) if row is not None else 5_000
            bounded_timeout = max(0, int(busy_timeout_ms))
            self._conn.execute(f"PRAGMA busy_timeout={bounded_timeout}")
        try:
            row = self._conn.execute(
                "SELECT id FROM activity_sessions WHERE session_id = ? "
                "ORDER BY id LIMIT 1",
                (session.session_id,),
            ).fetchone()
            if row is not None:
                session._db_row_id = int(row[0])
                database.update_session(self._conn, session)
                return session._db_row_id

            row_id = database.insert_session(self._conn, session)
            if not isinstance(row_id, int) or row_id <= 0:
                raise RuntimeError(
                    "session persistence did not return a valid row id"
                )
            session._db_row_id = row_id
            return row_id
        finally:
            if previous_timeout is not None:
                self._conn.execute(f"PRAGMA busy_timeout={previous_timeout}")

    def close(self) -> None:
        database.close_db(self._conn)
