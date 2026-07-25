"""Narrow runtime persistence helpers for session-tracking loops."""

from __future__ import annotations

from .. import database


class SessionRuntimeStore:
    def __init__(self, db_path: str):
        self._conn = database.init_db(db_path)

    def persist_session(self, session) -> int:
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
            raise RuntimeError("session persistence did not return a valid row id")
        session._db_row_id = row_id
        return row_id

    def close(self) -> None:
        database.close_db(self._conn)
