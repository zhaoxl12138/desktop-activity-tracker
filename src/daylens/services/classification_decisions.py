"""User commands and bounded undo history on the existing JSON transaction."""
from copy import deepcopy
from datetime import datetime
from functools import wraps
import threading
from pathlib import Path
from .classification_state_service import read_state, write_state, state_transaction

_DECISIONS = ('manual_decisions.json', 'title_patterns.json')
_LOCAL = threading.local()


def _snapshot(directory):
    return {name: read_state(directory, name, {}) for name in _DECISIONS}


def _without_hits(value):
    if isinstance(value, dict):
        return {k:_without_hits(v) for k,v in value.items() if k not in ('hit_count','last_used_at')}
    if isinstance(value, list):
        return [_without_hits(v) for v in value]
    return value


def decision_command(function):
    @wraps(function)
    def wrapped(directory, *args, **kwargs):
        with state_transaction(directory):
            key = str(Path(directory).resolve())
            active = getattr(_LOCAL,'active',set())
            if key in active:
                return function(directory,*args,**kwargs)
            before = _snapshot(directory)
            active.add(key)
            _LOCAL.active = active
            try:
                result = function(directory, *args, **kwargs)
            finally:
                active.remove(key)
            after = _snapshot(directory)
            if _without_hits(before) != _without_hits(after):
                history = read_state(directory, 'classification_operations.json', {'items':[]})
                history['items'] = (history.get('items', []) + [{
                    'command':function.__name__, 'at':datetime.now().isoformat(timespec='seconds'),
                    'before':before, 'after':after}])[-30:]
                write_state(directory, 'classification_operations.json', history)
            return result
    return wrapped


@decision_command
def set_decision_enabled(directory, identity, enabled):
    from .intelligence_evidence import set_pattern_enabled
    rows = read_state(directory, 'manual_decisions.json', {})
    if identity not in rows:
        raise ValueError('决定已不存在，请刷新')
    row = rows[identity]
    row['enabled'] = bool(enabled)
    write_state(directory, 'manual_decisions.json', rows)
    if row.get('pattern_id'):
        set_pattern_enabled(directory, row['pattern_id'], enabled)


@decision_command
def update_decision_category(directory, identity, category, *, categories=None):
    from .intelligence_evidence import update_pattern_category
    from ..category_registry import category_choices
    rows = read_state(directory, 'manual_decisions.json', {})
    row = rows.get(identity)
    if row is None or category not in dict((key,name) for name,key in category_choices(categories)):
        raise ValueError('决定或分类不可用')
    row['category'] = category
    from ..category_registry import category_definition, AI_CATEGORY_IDS
    if category not in AI_CATEGORY_IDS:
        row.update(custom_category=True, timing_policy_id=category_definition(category,categories).timing_policy)
    write_state(directory, 'manual_decisions.json', rows)
    if row.get('pattern_id'):
        update_pattern_category(directory, row['pattern_id'], category, categories=categories)


@decision_command
def delete_decision(directory, identity):
    from .intelligence_evidence import delete_pattern
    rows = read_state(directory, 'manual_decisions.json', {})
    row = rows.pop(identity, None)
    if row is None:
        return False
    write_state(directory, 'manual_decisions.json', rows)
    # Do not delete an expansion that is explicitly linked by another decision.
    if row.get('pattern_id') and not any(r.get('pattern_id') == row['pattern_id'] for r in rows.values()):
        delete_pattern(directory, row['pattern_id'])
    return True


def undo_last(directory):
    with state_transaction(directory):
        history = read_state(directory, 'classification_operations.json', {'items':[]})
        if not history.get('items'):
            return False
        operation = history['items'][-1]
        if _without_hits(_snapshot(directory)) != _without_hits(operation['after']):
            raise ValueError('决定已被其他操作修改，不能覆盖；请刷新后处理')
        restored = deepcopy(operation['before'])
        # Undo user choices, not subsequently accumulated hit counters.
        current = read_state(directory, 'title_patterns.json', {}).get('patterns', [])
        by_id = {row['id']:row for row in current}
        for row in restored['title_patterns.json'].get('patterns', []):
            latest = by_id.get(row['id'], {})
            for key in ('hit_count','last_used_at'):
                if key in latest:
                    row[key] = latest[key]
        current_decisions = read_state(directory,'manual_decisions.json',{})
        for identity,row in restored['manual_decisions.json'].items():
            for key in ('hit_count','last_used_at'):
                if key in current_decisions.get(identity,{}):
                    row[key] = current_decisions[identity][key]
        for name, payload in restored.items():
            write_state(directory, name, payload)
        history['items'].pop()
        write_state(directory, 'classification_operations.json', history)
        return True
