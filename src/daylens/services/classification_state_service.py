"""Serialized, recoverable JSON transactions for local classification decisions."""
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import json
import os
from pathlib import Path
import threading
import time

_LOCK = threading.RLock()
_LOCAL = threading.local()
_FILES = {'title_patterns.json', 'manual_decisions.json', 'classification_reviews.json', 'classification_operations.json'}
_JOURNAL = 'classification-transaction.json'


def _raw_read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return deepcopy(default)
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError('分类状态文件损坏，已停止写入以保留原文件') from exc


def _raw_write(path, value):
    from .intelligence_state import atomic_json
    atomic_json(Path(path), value)


def _recover(directory):
    journal = directory / _JOURNAL
    value = _raw_read(journal, None)
    if value is None:
        return
    if (not isinstance(value, dict) or value.get('version') != 1
            or not isinstance(value.get('files'), dict)
            or not set(value['files']).issubset(_FILES)
            or type(value.get('revision')) is not int):
        raise RuntimeError('分类恢复日志损坏，请保留文件并检查')
    for name, payload in value['files'].items():
        _raw_write(directory / name, payload)
    _raw_write(directory / 'classification_revision.json', {'revision':value['revision']})
    journal.unlink()


@contextmanager
def state_transaction(directory):
    directory = Path(directory).resolve()
    key = str(directory)
    with _LOCK:
        active = getattr(_LOCAL, 'active', {})
        if key in active:
            yield active[key]
            return
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'classification.lock').open('a+b') as handle:
            handle.seek(0, os.SEEK_END)
            if not handle.tell():
                handle.write(b'0')
                handle.flush()
            deadline = time.monotonic() + 5
            while True:
                try:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('分类状态正在保存，请稍后重试') from None
                    time.sleep(.01)
            try:
                _recover(directory)
                changes = {}
                active[key] = changes
                _LOCAL.active = active
                try:
                    yield changes
                    if changes:
                        revision = int(_raw_read(directory / 'classification_revision.json', {}).get('revision', 0)) + 1
                        _raw_write(directory / _JOURNAL, {'version':1, 'revision':revision, 'files':changes})
                        _recover(directory)
                finally:
                    active.pop(key, None)
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)


def state_operation(function):
    @wraps(function)
    def wrapped(directory, *args, **kwargs):
        with state_transaction(directory):
            return function(directory, *args, **kwargs)
    return wrapped


def read_state(directory, name, default):
    with state_transaction(directory) as changes:
        return deepcopy(changes[name]) if name in changes else _raw_read(Path(directory) / name, default)


def write_state(directory, name, value):
    if name not in _FILES:
        raise ValueError('Unsupported classification state file')
    with state_transaction(directory) as changes:
        changes[name] = deepcopy(value)


def state_revision(directory):
    with state_transaction(directory):
        return int(_raw_read(Path(directory) / 'classification_revision.json', {}).get('revision', 0))


class ClassificationStateService:
    """One facade for mutating decisions, shared by GUI and recording tasks."""
    def __init__(self, directory):
        self.directory = Path(directory)

    @property
    def revision(self):
        return state_revision(self.directory)

    def add_hits(self, hits):
        from .intelligence_evidence import load_patterns, save_patterns
        with state_transaction(self.directory):
            rows = load_patterns(self.directory)
            changed = False
            for row in rows:
                hit = hits.get(row.get('id'))
                if hit:
                    row['hit_count'] = int(row.get('hit_count') or 0) + hit['count']
                    row['last_used_at'] = max(str(row.get('last_used_at') or ''), hit['last_used_at'])
                    changed = True
            if changed:
                save_patterns(self.directory, rows)
            decisions = read_state(self.directory, 'manual_decisions.json', {})
            changed = False
            for identity, row in decisions.items():
                hit = hits.get('manual:'+identity)
                if hit:
                    row['hit_count'] = int(row.get('hit_count') or 0) + hit['count']
                    row['last_used_at'] = max(str(row.get('last_used_at') or ''), hit['last_used_at'])
                    changed = True
            if changed:
                write_state(self.directory, 'manual_decisions.json', decisions)
