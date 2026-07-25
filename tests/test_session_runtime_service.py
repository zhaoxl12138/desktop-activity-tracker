from datetime import datetime

import pytest

from daylens.services import session_runtime_service
from daylens.services.session_runtime_service import SessionRuntimeStore
from daylens.session_tracker import ActivitySession


def _session(session_id="session"):
    now = datetime.now()
    return ActivitySession(
        session_id=session_id,
        start_time=now,
        end_time=now,
        date=now.strftime("%Y-%m-%d"),
        process_name="Code.exe",
        exe_path="",
        window_title="main.py",
        normalized_title="main.py",
        category_key="coding",
        category_name="Coding",
        active_rule="interactive_required",
        duration_seconds=1,
        effective_seconds=1,
    )


def test_persist_session_replay_uses_session_id_as_idempotency_key(tmp_path):
    store = SessionRuntimeStore(str(tmp_path / "usage.db"))
    session = _session("stable-id")
    first_row_id = store.persist_session(session)
    session._db_row_id = -1
    session.duration_seconds = 2
    session.effective_seconds = 2

    replay_row_id = store.persist_session(session)

    rows = store._conn.execute(
        "SELECT id,duration_seconds FROM activity_sessions "
        "WHERE session_id = 'stable-id'"
    ).fetchall()
    store.close()
    assert replay_row_id == first_row_id
    assert rows == [(first_row_id, 2)]


def test_persist_session_recovers_when_cached_row_was_removed(tmp_path):
    store = SessionRuntimeStore(str(tmp_path / "usage.db"))
    session = _session("removed")
    first_row_id = store.persist_session(session)
    store._conn.execute("DELETE FROM activity_sessions WHERE id = ?", (first_row_id,))
    store._conn.commit()

    replacement_row_id = store.persist_session(session)

    count = store._conn.execute(
        "SELECT COUNT(*) FROM activity_sessions WHERE session_id = 'removed'"
    ).fetchone()[0]
    store.close()
    assert replacement_row_id > 0
    assert count == 1


def test_persist_session_rejects_invalid_insert_success_result(
    tmp_path, monkeypatch
):
    store = SessionRuntimeStore(str(tmp_path / "usage.db"))
    monkeypatch.setattr(
        session_runtime_service.database,
        "insert_session",
        lambda *_args: 0,
    )

    with pytest.raises(RuntimeError, match="valid row id"):
        store.persist_session(_session("invalid"))

    store.close()
