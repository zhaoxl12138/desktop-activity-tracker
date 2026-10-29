"""Build short, sanitized evidence for budgeted report generation."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

from .. import database, get_data_dir
from ..utils import WORK_CATEGORY_KEYS, fmt_seconds
from .intelligence_budget import IntelligenceBudget
from .intelligence_client import DeepSeekProvider
from .intelligence_credentials import read_key
from .intelligence_reviews import IntelligenceReviews
from .intelligence_state import load_settings, title_context
from .intelligence_privacy import report_facts, privacy_revision
from .intelligence_client import RequestDeferred


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
        if title_context(session.get('process_name'), session.get('window_title') or session.get('normalized_title'), settings, 'privacy') is None:
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
    regenerate_stale=False,
):
    from ..app_paths import AppPaths
    directory = Path(directory or AppPaths.from_database(db_path).intelligence_dir)
    settings = load_settings(directory)
    if not settings['enabled'] or not settings['reports_enabled']:
        raise ValueError('请先在设置中心开启智能增强和智能复盘')
    if not read_key():
        raise ValueError('请先配置DeepSeek API密钥')
    day = day or date.today()
    provider = DeepSeekProvider(IntelligenceBudget(directory / 'budget.json', settings['monthly_budget_micros']), read_key)
    def outbound_boundary(_kind, payload):
        current = load_settings(directory)
        if (not current['enabled'] or not current['reports_enabled']
                or privacy_revision(current) != privacy_revision(settings)):
            raise RequestDeferred('隐私设置已变化，等待重新构建汇总')
        safe = report_facts(payload.get('facts', []), current)
        if not safe:
            raise RequestDeferred('没有允许发送的汇总事实')
        return dict(payload, facts=safe)
    provider.privacy_filter = outbound_boundary
    reviews = IntelligenceReviews(directory, provider, privacy_settings=settings)
    existing = reviews.load(kind, day)
    from .report_evidence_service import evidence_fingerprint, report_dates
    dates = report_dates(kind, day)
    try:
        current_fingerprint = evidence_fingerprint(db_path, kind, dates)
    except (OSError, ValueError, sqlite3.Error):
        # Existing mocked/legacy generation paths may not expose a readable
        # database. They remain usable but are explicitly fingerprint-less.
        current_fingerprint = ""
    if (existing is not None
            and not (retry_failed and existing.get('status') == 'failed')):
        stored_fingerprint = str(existing.get('evidence_fingerprint') or '')
        stale = bool(existing.get('status') == 'ready' and stored_fingerprint
                     and stored_fingerprint != current_fingerprint)
        if not stale or not regenerate_stale:
            return dict(
                existing,
                evidence_status=("stale" if stale else
                                 "legacy" if existing.get('status') == 'ready' and not stored_fingerprint
                                 else "current"),
            )
    facts = daily_facts(db_path, day, settings) if kind == 'daily' else reviews.compressed_facts(kind, day)
    # Session references remain local. Opaque fact IDs are sufficient in prompts.
    payload_facts = [{k: v for k, v in f.items() if k != 'session_refs'} for f in facts]
    try:
        result = reviews.generate(
            kind,
            day,
            payload_facts,
            retry_failed=retry_failed,
            replace_existing=bool(regenerate_stale),
        )
    except RuntimeError:
        # A transmitted request writes a durable failed marker before this
        # service returns. Let the scheduler apply its one-next-day-retry
        # policy without losing the original failure state.
        failed = reviews.load(kind, day)
        if failed and failed.get('status') == 'failed':
            return failed
        raise
    # Bind every ready summary to the exact local evidence used at generation.
    if result.get('status') == 'ready':
        from .intelligence_state import atomic_json
        result['evidence_fingerprint'] = current_fingerprint
        result['evidence_status'] = 'current'
        if kind == 'daily':
            result['local_evidence'] = {f['id']: f['session_refs'] for f in facts}
        atomic_json(reviews.path(kind, day), result)
    return result


def render_review(result):
    if result.get('status') != 'ready':
        return '该周期智能复盘未完成，已保留调用状态以避免重复扣费。原生报告仍然可用。'
    from ..time_model import TIME_DEFINITION
    lines = [f"智能复盘 · {result['period']}",
             f"生成于 {result.get('captured_at', '未知')}（按当时已记录数据汇总）", '',
             '仅覆盖已纳入的记录/摘要，不代表全部时间；解释由AI生成。', TIME_DEFINITION, '']
    if result.get('evidence_status') == 'stale':
        lines[2:2] = ['⚠ 该汇总基于旧数据；历史分类或记录已变化。',
                      '如需更新，请主动重新分析；不会自动产生API费用。', '']
    elif result.get('evidence_status') == 'legacy':
        lines[2:2] = ['该旧汇总没有证据指纹，无法验证是否仍为最新。', '']
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
