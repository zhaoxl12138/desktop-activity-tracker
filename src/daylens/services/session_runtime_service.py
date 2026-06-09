"""Narrow runtime persistence helpers for session-tracking loops."""

from __future__ import annotations

from .. import database


class SessionRuntimeStore:
    def __init__(self, db_path: str):
        self._conn = database.init_db(db_path)

    def persist_session(self, session) -> int:
        if session._db_row_id > 0:
            database.update_session(self._conn, session)
            return session._db_row_id
        session._db_row_id = database.insert_session(self._conn, session)
        return session._db_row_id

    def close(self) -> None:
        database.close_db(self._conn)
