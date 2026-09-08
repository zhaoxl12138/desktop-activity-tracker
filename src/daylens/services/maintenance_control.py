"""Local one-shot request for DayLens to perform its own safe shutdown."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from .intelligence_state import atomic_json


def request_path(data_dir):
    return Path(data_dir) / 'maintenance-request.json'


def result_path(data_dir):
    return Path(data_dir) / 'maintenance-result.json'


def _process_is_daylens(pid):
    try:
        import psutil
        process = psutil.Process(int(pid))
        return process.is_running() and process.name().casefold() == 'daylens.exe'
    except Exception:
        return False


def _write_request(data_dir, request_id, now):
    atomic_json(request_path(data_dir), {
        'version': 1, 'id': request_id, 'action': 'exit',
        'requested_at': now.isoformat(timespec='seconds'),
    })


def request_exit(data_dir, *, now=None):
    now = now or datetime.now()
    runtime_path = Path(data_dir) / 'logs' / 'runtime-state.json'
    try:
        runtime = json.loads(runtime_path.read_text(encoding='utf-8'))
        if runtime.get('status') != 'running' or not _process_is_daylens(runtime['pid']):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError('DayLens未运行，无需退出') from None
    request_id = uuid.uuid4().hex
    result_path(data_dir).unlink(missing_ok=True)
    _write_request(data_dir, request_id, now)
    return request_id


def consume_request(data_dir, *, now=None):
    now = now or datetime.now()
    path = request_path(data_dir)
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        requested = datetime.fromisoformat(value['requested_at'])
        valid = (value.get('version') == 1 and value.get('action') == 'exit'
                 and isinstance(value.get('id'), str)
                 and 0 <= (now - requested).total_seconds() <= 120)
    except (OSError, ValueError, KeyError, TypeError):
        valid, value = False, {}
    path.unlink(missing_ok=True)
    return {'action': 'exit', 'id': value['id']} if valid else None


def record_result(data_dir, request_id, status, message):
    atomic_json(result_path(data_dir), {
        'version': 1, 'id': request_id, 'status': status,
        'message': str(message or '')[:300],
        'completed_at': datetime.now().isoformat(timespec='seconds'),
    })


def read_result(data_dir, request_id):
    try:
        result = json.loads(result_path(data_dir).read_text(encoding='utf-8'))
        return result if result.get('version') == 1 and result.get('id') == request_id else None
    except (OSError, ValueError, TypeError):
        return None


def request_exit_and_wait(data_dir, timeout_seconds=45):
    request_id = request_exit(data_dir)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = read_result(data_dir, request_id)
        if result is not None:
            if result.get('status') == 'completed':
                return result
            raise RuntimeError(result.get('message') or 'DayLens未能安全退出')
        time.sleep(0.2)
    raise RuntimeError('DayLens安全退出超时，程序仍保持运行')
