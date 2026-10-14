"""Build short, sanitized evidence for budgeted report generation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .. import database, get_data_dir
from ..utils import WORK_CATEGORY_KEYS, fmt_seconds
from .intelligence_budget import IntelligenceBudget
from .intelligence_client import DeepSeekProvider
from .intelligence_credentials import read_key
from .intelligence_reviews import IntelligenceReviews
from .intelligence_state import load_settings, title_context


def daily_facts(db_path, day, settings):
    sessions = database.query_sessions_for_dates(db_path, [day.isoformat()])
    grouped = {}
    seen = set()
    for session in sessions:
        identity = str(session.get('session_id') or '')
        if not identity or identity in seen:
            continue
        seen.add(identity)
        if session.get('category_key') not in WORK_CATEGORY_KEYS:
            continue
        title = session.get('normalized_title') or session.get('window_title')
        context = title_context(session.get('process_name'), title, settings, 'review-v1')
        seconds = session.get('engaged_seconds')
        if context is None or type(seconds) is not int or seconds <= 0:
            continue
        duration, passive, idle = (session.get(k) for k in ('duration_seconds', 'passive_seconds', 'idle_seconds'))
        if (any(type(x) is not int or x < 0 for x in (duration, passive, idle))
                or seconds + passive + idle != duration):
            continue
        fact = grouped.setdefault(context['id'], {
            'id': context['id'], 'app': context['app'], 'title': context['title'][:100],
            'engaged_seconds': 0, 'session_refs': [],
        })
        fact['engaged_seconds'] += seconds
        if identity:
            fact['session_refs'].append(identity)
    return sorted(grouped.values(), key=lambda x: -x['engaged_seconds'])[:20]


def generate_budget_review(
    db_path,
    kind,
    day: date | None = None,
    *,
    directory=None,
    retry_failed=False,
):
    directory = Path(directory or Path(get_data_dir()) / 'intelligence')
    settings = load_settings(directory)
    if not settings['enabled'] or not settings['reports_enabled']:
        raise ValueError('请先在设置中心开启智能增强和智能复盘')
    if not read_key():
        raise ValueError('请先配置DeepSeek API密钥')
    day = day or date.today()
    provider = DeepSeekProvider(IntelligenceBudget(directory / 'budget.json', settings['monthly_budget_micros']), read_key)
    reviews = IntelligenceReviews(directory, provider)
    existing = reviews.load(kind, day)
    if (existing is not None
            and not (retry_failed and existing.get('status') == 'failed')):
        return existing
    facts = daily_facts(db_path, day, settings) if kind == 'daily' else reviews.compressed_facts(kind, day)
    # Session references remain local. Opaque fact IDs are sufficient in prompts.
    payload_facts = [{k: v for k, v in f.items() if k != 'session_refs'} for f in facts]
    try:
        result = reviews.generate(
            kind,
            day,
            payload_facts,
            retry_failed=retry_failed,
        )
    except RuntimeError:
        # A transmitted request writes a durable failed marker before this
        # service returns. Let the scheduler apply its one-next-day-retry
        # policy without losing the original failure state.
        failed = reviews.load(kind, day)
        if failed and failed.get('status') == 'failed':
            return failed
        raise
    # Preserve the locally obtained references separately from model output.
    if kind == 'daily' and result.get('status') == 'ready':
        from .intelligence_state import atomic_json
        result['local_evidence'] = {f['id']: f['session_refs'] for f in facts}
        atomic_json(reviews.path(kind, day), result)
    return result


def render_review(result):
    if result.get('status') != 'ready':
        return '该周期智能复盘未完成，已保留调用状态以避免重复扣费。原生报告仍然可用。'
    lines = [f"智能复盘 · {result['period']}",
             f"生成于 {result.get('captured_at', '未知')}（按当时已记录数据汇总）", '',
             '仅覆盖已纳入的记录/摘要，不代表全部时间；解释由AI生成。', '']
    facts = {f['id']: f for f in result.get('facts', [])}
    for topic in result.get('topics', []):
        refs = topic['evidence_ids']
        seconds = sum(facts[x].get('engaged_seconds', 0) for x in set(refs))
        suffix = ' · 参与 ' + fmt_seconds(seconds) if result['kind'] == 'daily' else ''
        lines.append(topic['name'] + suffix)
    lines.extend(['', 'AI观察：'])
    for observation in result.get('observations', []):
        lines.append('• ' + observation['text'])
        for identity in observation['evidence_ids']:
            fact = facts[identity]
            if 'title' in fact:
                lines.append(f"  依据：{fact['app']} · {fact['title']} · {fmt_seconds(fact['engaged_seconds'])}")
            else:
                lines.append('  依据摘要：' + fact['period'])
    return '\n'.join(lines)
