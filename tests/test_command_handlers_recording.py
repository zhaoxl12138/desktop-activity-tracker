import signal
from types import SimpleNamespace

import pytest

from daylens.services import command_handlers


class FakeRecordingLock:
    def close(self):
        pass


@pytest.fixture(autouse=True)
def isolate_recording_lock(monkeypatch):
    fake_lock = FakeRecordingLock()
    monkeypatch.setattr(
        command_handlers,
        "acquire_recording_lock",
        lambda: (True, fake_lock),
    )
    return fake_lock


def test_cli_shutdown_persists_short_tail_via_tracker_protocol(monkeypatch):
    tail = SimpleNamespace(duration_seconds=1, switch_reason="")
    persisted = []
    finish_reasons = []
    signal_handlers = {}
    startup_order = []

    class FakeStore:
        def __init__(self, _db_path):
            self.closed = False

        def persist_session(self, session):
            persisted.append(session)
            return 1

        def close(self):
            self.closed = True

    class FakeTracker:
        def __init__(self, *, on_session_end, **_kwargs):
            startup_order.append("tracker")
            self.on_session_end = on_session_end
            self.current_session = tail

        def tick(self, _idle_seconds, _window):
            return None

        def finish_current(self, reason):
            finish_reasons.append(reason)
            self.current_session.switch_reason = reason
            result = self.on_session_end(self.current_session)
            self.current_session = None
            return result

    class FakeSpool:
        path = "usage.db.session-recovery.json"

        def __init__(self, _db_path):
            pass

        def replay(self, _store):
            startup_order.append("replay")
            return 0

        def store_sessions(self, _sessions):
            raise AssertionError("shutdown should persist directly")

    store_holder = {}

    def create_store(db_path):
        store = FakeStore(db_path)
        store_holder["store"] = store
        return store

    monkeypatch.setattr(
        command_handlers.database,
        "get_db_path",
        lambda _config: "usage.db",
    )
    monkeypatch.setattr(
        command_handlers,
        "Classifier",
        lambda *_args: object(),
    )
    monkeypatch.setattr(command_handlers, "SessionRuntimeStore", create_store)
    monkeypatch.setattr(command_handlers, "SessionRecoverySpool", FakeSpool)
    monkeypatch.setattr(command_handlers, "SessionTracker", FakeTracker)
    monkeypatch.setattr(
        command_handlers,
        "get_idle_seconds",
        lambda: startup_order.append("sample") or 0,
    )
    monkeypatch.setattr(
        command_handlers,
        "get_foreground_window_info",
        lambda: None,
    )
    monkeypatch.setattr(
        command_handlers.signal,
        "signal",
        lambda sig, handler: signal_handlers.__setitem__(sig, handler),
    )
    monkeypatch.setattr(
        command_handlers.time,
        "sleep",
        lambda _seconds: signal_handlers[signal.SIGINT](signal.SIGINT, None),
    )

    command_handlers.handle_start(
        {
            "tracker": {
                "sample_interval_seconds": 1,
                "flush_interval_seconds": 5,
                "idle_threshold_seconds": 60,
                "min_session_seconds": 2,
            }
        },
        "config.yaml",
    )

    assert finish_reasons == ["shutdown"]
    assert startup_order[:3] == ["replay", "tracker", "sample"]
    assert persisted == [tail]
    assert tail.switch_reason == "shutdown"
    assert store_holder["store"].closed is True


def _run_cli_with_finish_results(monkeypatch, finish_results):
    signal_handlers = {}
    finish_reasons = []
    results = iter(finish_results)

    class FakeStore:
        def __init__(self, _db_path):
            self.closed = False

        def persist_session(self, _session):
            return 1

        def close(self):
            self.closed = True

    class FakeTracker:
        def __init__(self, **_kwargs):
            self.current_session = SimpleNamespace(
                session_id="cli-tail",
                duration_seconds=1,
            )

        def tick(self, _idle_seconds, _window):
            return None

        def finish_current(self, reason):
            finish_reasons.append(reason)
            result = next(results)
            if isinstance(result, BaseException):
                raise result
            if result:
                self.current_session = None
            return result

    store_holder = {}

    def create_store(db_path):
        store = FakeStore(db_path)
        store_holder["store"] = store
        return store

    monkeypatch.setattr(
        command_handlers.database,
        "get_db_path",
        lambda _config: "usage.db",
    )
    monkeypatch.setattr(command_handlers, "Classifier", lambda *_args: object())
    monkeypatch.setattr(command_handlers, "SessionRuntimeStore", create_store)
    monkeypatch.setattr(command_handlers, "SessionTracker", FakeTracker)
    monkeypatch.setattr(command_handlers, "get_idle_seconds", lambda: 0)
    monkeypatch.setattr(
        command_handlers,
        "get_foreground_window_info",
        lambda: None,
    )
    monkeypatch.setattr(
        command_handlers.signal,
        "signal",
        lambda sig, handler: signal_handlers.__setitem__(sig, handler),
    )
    monkeypatch.setattr(
        command_handlers.time,
        "sleep",
        lambda _seconds: signal_handlers[signal.SIGINT](signal.SIGINT, None),
    )
    config = {
        "tracker": {
            "sample_interval_seconds": 1,
            "flush_interval_seconds": 5,
            "idle_threshold_seconds": 60,
            "min_session_seconds": 2,
            "persistence_shutdown_retry_attempts": 3,
        }
    }

    return (
        lambda: command_handlers.handle_start(config, "config.yaml"),
        finish_reasons,
        store_holder,
    )


def test_cli_shutdown_retries_false_finish_until_success(monkeypatch, capsys):
    run, finish_reasons, store_holder = _run_cli_with_finish_results(
        monkeypatch,
        [False, True],
    )

    run()

    assert finish_reasons == ["shutdown", "shutdown"]
    assert store_holder["store"].closed is True
    assert "数据库已安全关闭" in capsys.readouterr().out


def test_cli_shutdown_persistent_failure_spools_then_closes(monkeypatch, capsys):
    run, finish_reasons, store_holder = _run_cli_with_finish_results(
        monkeypatch,
        [OSError("database busy"), False, False],
    )
    spooled = []

    class FakeSpool:
        path = "usage.db.session-recovery.json"

        def __init__(self, _db_path):
            pass

        def replay(self, _store):
            return 0

        def store_sessions(self, sessions):
            spooled.extend(sessions)
            return len(spooled)

    monkeypatch.setattr(command_handlers, "SessionRecoverySpool", FakeSpool)

    with pytest.raises(RuntimeError, match="session-recovery.json"):
        run()

    assert finish_reasons == ["shutdown", "shutdown", "shutdown"]
    assert [session.session_id for session in spooled] == ["cli-tail"]
    assert store_holder["store"].closed is True
    output = capsys.readouterr()
    assert "session-recovery.json" in output.err
    assert "数据库已安全关闭" not in output.out


def test_cli_sampling_sleeps_after_errors_instead_of_hot_loop(monkeypatch):
    signal_handlers = {}
    idle_calls = []
    sleep_calls = []

    class FakeStore:
        def __init__(self, _db_path):
            pass

        def persist_session(self, _session):
            return 1

        def close(self):
            pass

    class FakeTracker:
        def __init__(self, **_kwargs):
            pass

        def tick(self, _idle_seconds, _window):
            return None

        def finish_current(self, _reason):
            return True

    def get_idle_seconds():
        idle_calls.append(True)
        if len(idle_calls) == 1:
            raise OSError("sampling failed")
        if len(idle_calls) == 3:
            signal_handlers[signal.SIGINT](signal.SIGINT, None)
        return 0

    def sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) == 2:
            signal_handlers[signal.SIGINT](signal.SIGINT, None)

    monkeypatch.setattr(
        command_handlers.database,
        "get_db_path",
        lambda _config: "usage.db",
    )
    monkeypatch.setattr(command_handlers, "Classifier", lambda *_args: object())
    monkeypatch.setattr(command_handlers, "SessionRuntimeStore", FakeStore)
    monkeypatch.setattr(command_handlers, "SessionTracker", FakeTracker)
    monkeypatch.setattr(command_handlers, "get_idle_seconds", get_idle_seconds)
    monkeypatch.setattr(
        command_handlers,
        "get_foreground_window_info",
        lambda: None,
    )
    monkeypatch.setattr(
        command_handlers.signal,
        "signal",
        lambda sig, handler: signal_handlers.__setitem__(sig, handler),
    )
    monkeypatch.setattr(command_handlers.time, "sleep", sleep)

    command_handlers.handle_start(
        {"tracker": {"sample_interval_seconds": 2}},
        "config.yaml",
    )

    assert len(idle_calls) == 2
    assert sleep_calls == [2, 2]
