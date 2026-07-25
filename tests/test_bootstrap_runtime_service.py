from daylens.services import bootstrap_runtime_service


def test_prepare_runtime_closes_schema_connection_then_only_inspects_quality(
    monkeypatch,
):
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
        bootstrap_runtime_service,
        "inspect_data_quality",
        lambda _path: calls.append("inspect") or {
            "issue_count": 0,
            "affected_dates": [],
        },
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

    assert "repair" not in calls
    assert calls[:4] == ["init", ("close", connection), "inspect", "shared"]


def test_prepare_runtime_reports_quality_issues_without_repairing(
    monkeypatch, capsys
):
    connection = object()
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "get_db_path",
        lambda _config: "usage.db",
    )
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "init_db",
        lambda _path: connection,
    )
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "close_db",
        lambda _connection: None,
    )
    monkeypatch.setattr(
        bootstrap_runtime_service,
        "inspect_data_quality",
        lambda _path: {
            "issue_count": 3,
            "affected_dates": ["2026-07-01", "2026-07-02"],
        },
        raising=False,
    )
    monkeypatch.setattr(
        bootstrap_runtime_service,
        "auto_repair_legacy_sessions",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("startup must not repair history")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "init_shared_read_conn",
        lambda _path: None,
    )
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "merge_db_settings",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        bootstrap_runtime_service.database,
        "merge_custom_rules",
        lambda *_args: None,
    )

    bootstrap_runtime_service.prepare_runtime_config({})

    error_output = capsys.readouterr().err
    assert "3" in error_output
    assert "2026-07-01" in error_output
