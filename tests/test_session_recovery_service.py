from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from daylens.services.session_recovery_service import SessionRecoverySpool
from daylens.session_tracker import ActivitySession


def _session(session_id: str, *, title: str = "编辑器") -> ActivitySession:
    start = datetime(
        2026,
        7,
        25,
        9,
        10,
        11,
        123456,
        tzinfo=timezone(timedelta(hours=8)),
    )
    return ActivitySession(
        session_id=session_id,
        start_time=start,
        end_time=start + timedelta(seconds=7),
        date="2026-07-25",
        process_name="Code.exe",
        exe_path=r"D:\Apps\Code.exe",
        window_title=title,
        normalized_title=title,
        category_key="coding",
        category_name="编码",
        active_rule="interactive_required",
        duration_seconds=7,
        effective_seconds=6,
        idle_seconds=1,
        switch_reason="shutdown",
        initial_title="初始标题",
        _db_row_id=99,
    )


def test_recovery_spool_round_trips_and_replays_all_before_delete(tmp_path):
    recovery_path = tmp_path / "usage.db.session-recovery.json"
    spool = SessionRecoverySpool("usage.db", recovery_path=recovery_path)
    original = _session("session-1")

    assert spool.store_sessions([original]) == 1

    loaded = spool.load_sessions()
    assert loaded == [
        ActivitySession(
            **{
                **original.__dict__,
                "_db_row_id": -1,
            }
        )
    ]

    replayed = []

    class Store:
        def persist_session(self, session):
            replayed.append(session)
            return len(replayed)

    assert spool.replay(Store()) == 1
    assert [session.session_id for session in replayed] == ["session-1"]
    assert recovery_path.exists() is False


def test_recovery_spool_keeps_file_until_every_replay_succeeds(tmp_path):
    recovery_path = tmp_path / "recovery.json"
    spool = SessionRecoverySpool("usage.db", recovery_path=recovery_path)
    spool.store_sessions([_session("one"), _session("two")])

    class Store:
        def __init__(self):
            self.calls = []

        def persist_session(self, session):
            self.calls.append(session.session_id)
            if session.session_id == "two":
                raise OSError("database busy")
            return 1

    store = Store()
    with pytest.raises(OSError, match="database busy"):
        spool.replay(store)

    assert store.calls == ["one", "two"]
    assert [item.session_id for item in spool.load_sessions()] == ["one", "two"]
    assert recovery_path.exists() is True


def test_recovery_spool_atomic_replace_failure_preserves_previous_file(
    tmp_path,
    monkeypatch,
):
    recovery_path = tmp_path / "recovery.json"
    spool = SessionRecoverySpool("usage.db", recovery_path=recovery_path)
    spool.store_sessions([_session("one")])
    previous = recovery_path.read_bytes()

    monkeypatch.setattr(
        "daylens.services.session_recovery_service.os.replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        spool.store_sessions([_session("two")])

    assert recovery_path.read_bytes() == previous
    assert list(tmp_path.glob("*.tmp")) == []
