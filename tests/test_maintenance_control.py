from datetime import datetime, timedelta
from types import SimpleNamespace


def test_request_consume_and_complete_are_scoped_to_data_dir(tmp_path, monkeypatch):
    from daylens.services import maintenance_control as control
    runtime = tmp_path / 'logs' / 'runtime-state.json'
    runtime.parent.mkdir()
    runtime.write_text('{"status":"running","pid":123}', encoding='utf-8')
    monkeypatch.setattr(control, '_process_is_daylens', lambda pid: pid == 123)
    request_id = control.request_exit(tmp_path, now=datetime(2026, 9, 8, 12))
    request = control.consume_request(tmp_path, now=datetime(2026, 9, 8, 12, 0, 30))
    assert request == {'action': 'exit', 'id': request_id}
    assert control.consume_request(tmp_path, now=datetime(2026, 9, 8, 12, 0, 31)) is None
    control.record_result(tmp_path, request_id, 'completed', '')
    assert control.read_result(tmp_path, request_id)['status'] == 'completed'


def test_stale_request_is_consumed_without_exiting(tmp_path):
    from daylens.services import maintenance_control as control
    control._write_request(tmp_path, 'old', datetime(2026, 9, 8, 11))
    assert control.consume_request(tmp_path, now=datetime(2026, 9, 8, 12)) is None
    assert not control.request_path(tmp_path).exists()


def test_request_rejected_when_runtime_not_running(tmp_path):
    import pytest
    from daylens.services.maintenance_control import request_exit
    with pytest.raises(RuntimeError, match='未运行'):
        request_exit(tmp_path)


def test_background_maintenance_exit_uses_safe_shutdown_without_dialog(monkeypatch, tmp_path):
    from daylens.gui import main_window
    from daylens.gui.main_window import MainWindow
    from daylens.services.gui_shutdown_service import WorkerShutdownResult
    events = []
    worker = object()
    window = SimpleNamespace(worker=worker, db_path=str(tmp_path / 'usage.db'))
    monkeypatch.setattr(MainWindow, '_suspend_dashboard_refresh', lambda self: events.append('suspend') or True)
    monkeypatch.setattr(main_window, 'stop_recording_worker_safely', lambda item:
                        events.append(('worker', item)) or WorkerShutdownResult(True, item, 1000))
    monkeypatch.setattr(main_window.QApplication, 'instance', staticmethod(
        lambda: SimpleNamespace(quit=lambda: events.append('quit'))))
    monkeypatch.setattr(main_window, 'record_maintenance_result',
                        lambda *args: events.append(('result', args[2])))
    MainWindow._perform_safe_quit(window, request_id='req')
    assert events == ['suspend', ('worker', worker), ('result', 'completed'), 'quit']


def test_background_maintenance_exit_reports_failure_and_resumes(monkeypatch, tmp_path):
    from daylens.gui import main_window
    from daylens.gui.main_window import MainWindow
    from daylens.services.gui_shutdown_service import WorkerShutdownResult
    events = []
    worker = object()
    window = SimpleNamespace(worker=worker, db_path=str(tmp_path / 'usage.db'))
    monkeypatch.setattr(MainWindow, '_suspend_dashboard_refresh', lambda self: True)
    monkeypatch.setattr(MainWindow, '_resume_dashboard_refresh', lambda self: events.append('resume'))
    monkeypatch.setattr(main_window, 'stop_recording_worker_safely', lambda item:
                        WorkerShutdownResult(False, item, 1000, 'pending persistence'))
    monkeypatch.setattr(main_window, 'record_maintenance_result',
                        lambda *args: events.append(('result', args[2], args[3])))
    MainWindow._perform_safe_quit(window, request_id='req')
    assert events == ['resume', ('result', 'failed', 'pending persistence')]
