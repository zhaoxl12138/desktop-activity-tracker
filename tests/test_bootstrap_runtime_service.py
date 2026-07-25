from daylens.services import bootstrap_runtime_service


def test_prepare_runtime_closes_schema_connection_before_auto_repair(monkeypatch):
    calls = []
    connection = object()
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "get_db_path",
        lambda _config: "usage.db",
    )
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "init_db",
        lambda _path: calls.append("init") or connection,
    )
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "close_db",
        lambda value: calls.append(("close", value)),
    )
    monkeypatch.setattr(
        bootstrap_runtime_service,
        "auto_repair_legacy_sessions",
        lambda _path: calls.append("repair"),
        raising=False,
    )
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "init_shared_read_conn",
        lambda _path: calls.append("shared"),
    )
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "merge_db_settings",
        lambda *_args: calls.append("settings"),
    )
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "merge_custom_rules",
        lambda *_args: calls.append("rules"),
    )

    bootstrap_runtime_service.prepare_runtime_config({})

    assert calls[:4] == ["init", ("close", connection), "repair", "shared"]
