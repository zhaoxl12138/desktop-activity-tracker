import signal
from types import SimpleNamespace

from daylens.services import command_handlers


def test_cli_shutdown_persists_short_tail_via_tracker_protocol(monkeypatch):
    tail = SimpleNamespace(duration_seconds=1, switch_reason="")
    persisted = []
    finish_reasons = []
    signal_handlers = {}

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
    assert persisted == [tail]
    assert tail.switch_reason == "shutdown"
    assert store_holder["store"].closed is True
