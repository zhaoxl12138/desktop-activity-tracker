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


def test_activity_session_preserves_existing_positional_constructor_order():
    now = datetime.now()
    session = ActivitySession(
        "positional",
        now,
        now,
        now.strftime("%Y-%m-%d"),
        "Code.exe",
        "",
        "main.py",
        "main.py",
        "coding",
        "Coding",
        "interactive_required",
        5,
        4,
        1,
        "shutdown",
        "initial.py",
        99,
    )

    assert session._db_row_id == 99
    assert session.engaged_seconds == 0
    assert session.passive_seconds == 0
    assert session.metric_version == "attention-v1"
    assert session.classification_version == "legacy"


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


def test_rewrite_session_explicitly_upserts_the_existing_session_id(tmp_path):
    store = SessionRuntimeStore(str(tmp_path / "usage.db"))
    session = _session("attention-rewrite")
    session.engaged_seconds = 2
    session.effective_seconds = 2
    first_row_id = store.persist_session(session)

    session.engaged_seconds = 0
    session.effective_seconds = 0
    session.idle_seconds = 2
    rewrite_row_id = store.rewrite_session(session)

    rows = store._conn.execute(
        "SELECT id,engaged_seconds,idle_seconds FROM activity_sessions "
        "WHERE session_id = ?",
        (session.session_id,),
    ).fetchall()
    store.close()

    assert rewrite_row_id == first_row_id
    assert rows == [(first_row_id, 0, 2)]


def test_persist_session_round_trips_trusted_metrics_on_insert_and_update(tmp_path):
    store = SessionRuntimeStore(str(tmp_path / "usage.db"))
    session = _session("trusted-metrics")

    assert session.engaged_seconds == 0
    assert session.passive_seconds == 0
    assert session.metric_version == "attention-v1"
    assert session.classification_version == "legacy"

    session.engaged_seconds = 7
    session.passive_seconds = 3
    session.metric_version = "attention-v1"
    session.classification_version = "rules-a"
    store.persist_session(session)
    inserted = store._conn.execute(
        "SELECT effective_seconds, engaged_seconds, passive_seconds, "
        "metric_version, classification_version FROM activity_sessions "
        "WHERE session_id = ?",
        (session.session_id,),
    ).fetchone()

    session.effective_seconds = 11
    session.engaged_seconds = 8
    session.passive_seconds = 4
    session.metric_version = "attention-v2"
    session.classification_version = "rules-b"
    store.persist_session(session)
    updated = store._conn.execute(
        "SELECT effective_seconds, engaged_seconds, passive_seconds, "
        "metric_version, classification_version FROM activity_sessions "
        "WHERE session_id = ?",
        (session.session_id,),
    ).fetchone()
    store.close()

    assert inserted == (1, 7, 3, "attention-v1", "rules-a")
    assert updated == (11, 8, 4, "attention-v2", "rules-b")


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
