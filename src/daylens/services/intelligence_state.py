"""Local AI preferences and durable decisions; never contains API credentials."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from .classification_state_service import state_operation, read_state, write_state


DEFAULT_SETTINGS = {
    'enabled': False, 'classification_enabled': True, 'reports_enabled': False,
    'task_analysis_enabled': False, 'task_cloud_enabled': False,
    'behavior_analysis_enabled': False,
    'monthly_budget_micros': 4_000_000,
}


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='ai-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_settings(directory):
    path = Path(directory) / 'settings.json'
    result = dict(DEFAULT_SETTINGS)
    if not path.exists():
        return result
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        for key in ('enabled', 'classification_enabled', 'reports_enabled',
                    'task_analysis_enabled', 'task_cloud_enabled', 'behavior_analysis_enabled'):
            if type(data.get(key)) is bool:
                result[key] = data[key]
        value = data.get('monthly_budget_micros')
        if type(value) is int and 0 <= value <= 5_000_000:
            result['monthly_budget_micros'] = value
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        # A bad config never enables transmission.
        return dict(DEFAULT_SETTINGS)


def save_settings(directory, settings):
    clean = {key: settings.get(key, default) for key, default in DEFAULT_SETTINGS.items()}
    if any(type(clean[k]) is not bool for k in ('enabled', 'classification_enabled', 'reports_enabled',
                                                'task_analysis_enabled', 'task_cloud_enabled', 'behavior_analysis_enabled')):
        raise ValueError('AI开关格式无效')
    if type(clean['monthly_budget_micros']) is not int or not 0 <= clean['monthly_budget_micros'] <= 5_000_000:
        raise ValueError('月预算应在0至5元之间')
    atomic_json(Path(directory) / 'settings.json', clean)


def title_context(process, title, settings, rule_version):
    process, title = str(process or '').strip().casefold(), str(title or '').strip()
    if not process or not title:
        return None
    identity_title = re.sub(r'\s+', ' ', title).strip()
    identity_title = re.sub(r'\s*[-—|]\s*(?:Google Chrome|Microsoft Edge|Mozilla Firefox)$', '', identity_title, flags=re.I)
    # Never read URLs; titles that embed one have it removed before transmission.
    title = re.sub(r'https?://\S+|www\.\S+', '[网址]', title, flags=re.I)
    title = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[邮箱]', title)
    title = re.sub(r'(?<!\d)\d{7,}(?!\d)', '[号码]', title)
    title = re.sub(r'[A-Za-z]:[\\/][^\s]+', '[路径]', title)
    title = re.sub(r'(?i)\b(?:sk-|Bearer\s+)[A-Za-z0-9_-]+', '[密钥]', title)
    title = re.sub(r'\s+', ' ', title).strip()
    title = re.sub(r'\s*[-—|]\s*(?:Google Chrome|Microsoft Edge|Mozilla Firefox)$', '', title, flags=re.I)
    if not title or title in ('新标签页', 'New Tab', '[网址]', '[路径]'):
        return None
    # Identity is a local hash of the full title. Redacted titles may look the
    # same but must not share corrections (e.g. two different private documents).
    fingerprint = '|'.join((process, identity_title.casefold(), str(rule_version), 'flash:classify-v2'))
    identity = hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:24]
    return {'id': identity, 'app': process[:80], 'title': title[:180]}


def load_overrides(directory):
    try:
        data = read_state(directory, 'manual_decisions.json', {})
        from .intelligence_client import LEGAL_CATEGORIES
        if not isinstance(data, dict):
            return {}
        return {key: value for key, value in data.items()
                if isinstance(value, dict) and isinstance(value.get('category'), str)
                and (value['category'] in LEGAL_CATEGORIES or _valid_custom(value))}
    except (OSError, ValueError, TypeError):
        return {}


@state_operation
def save_override(directory, process, title, category, *, scope='similar', categories=None):
    from .classification_decisions import decision_command
    return decision_command(_save_override)(directory, process, title, category, scope=scope, categories=categories)


def _valid_custom(value):
    from ..category_registry import TIMING_POLICIES
    return value.get('custom_category') is True and value.get('timing_policy_id') in TIMING_POLICIES


def _save_override(directory, process, title, category, *, scope, categories):
    from .intelligence_client import LEGAL_CATEGORIES
    from ..category_registry import category_definition
    definition = category_definition(category, categories)
    if definition is None or not definition.manual_allowed:
        raise ValueError('不支持的分类')
    if scope not in ('exact', 'similar'):
        raise ValueError('不支持的纠错范围')
    context = title_context(process, title, dict(DEFAULT_SETTINGS), 'manual-v1')
    if context is None:
        raise ValueError('该标题无法保存纠正')
    overrides = load_overrides(directory)
    overrides[context['id']] = {'category': category, 'certainty': 'high',
                                'reason': '用户指定当前应用与标题', 'source': '手动',
                                'app':context['app'], 'title':context['title'], 'scope':scope,
                                'created_at':datetime.now().isoformat(timespec='seconds'), 'enabled':True}
    if category not in LEGAL_CATEGORIES:
        overrides[context['id']].update(custom_category=True, timing_policy_id=definition.timing_policy)
    write_state(directory, 'manual_decisions.json', overrides)
    if scope == 'exact':
        return
    # Exact identity remains for privacy-sensitive titles; the explainable,
    # same-application pattern lets a correction help closely related pages.
    from .intelligence_evidence import save_pattern
    try:
        pattern = save_pattern(directory, process, title, category, categories=categories)
        overrides[context['id']]['pattern_id'] = pattern['id']
        write_state(directory, 'manual_decisions.json', overrides)
    except ValueError:
        # A sparse/private title can still be corrected exactly without
        # creating an unsafe broad similarity rule.
        pass
