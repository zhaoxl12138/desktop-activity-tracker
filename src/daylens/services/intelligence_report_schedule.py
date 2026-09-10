"""Local 23:00 report schedule; durable catch-up, no independent process."""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from .. import exporter, get_data_dir
from .intelligence_client import RequestDeferred
from .intelligence_credentials import read_key
from .intelligence_report_service import generate_budget_review, render_review
from .intelligence_reviews import NoReviewData, review_period
from .intelligence_state import atomic_json, load_settings
from .report_sections import REPORT_WRITE_LOCK, attach_summary

_RUN_LOCK = threading.Lock()
FACT_SOURCE_VERSION = 'normalized-title-v2'


def due_periods(start: date, now: datetime):
    end = now.date() if now.hour >= 23 else now.date() - timedelta(days=1)
    result = []
    day = start
    while day <= end:
        result.append(('daily', day))
        if day.weekday() == 6:
            result.append(('weekly', day))
        if (day + timedelta(days=1)).month != day.month:
            result.append(('monthly', day))
        day += timedelta(days=1)
    return result


def ensure_native_report(db_path, reports_dir, kind, day):
    from .reports_service import weekly_report_path, monthly_report_path
    root = Path(reports_dir)
    year, week, _ = day.isocalendar()
    if kind == 'daily':
        path = Path(exporter.daily_report_path(str(root / 'daily'), day.isoformat()))
        create = lambda: exporter.export_markdown(db_path, day.isoformat(), str(root / 'daily'))
    elif kind == 'weekly':
        path = Path(weekly_report_path(str(root), year, week))
        create = lambda: exporter.export_weekly_report(db_path, year, week, str(root / 'weekly'))
    else:
        path = Path(monthly_report_path(str(root), day.year, day.month))
        create = lambda: exporter.export_monthly_report(db_path, day.year, day.month, str(root / 'monthly'))
    with REPORT_WRITE_LOCK:
        if not path.exists():
            create()
    return path


def _identity(kind, day):
    return kind + ':' + review_period(kind, day)


def _depends_on(kind, day, other_kind, other_day):
    if kind == 'weekly':
        return other_kind == 'daily' and day - timedelta(days=6) <= other_day <= day
    if kind == 'monthly':
        return other_kind in ('daily', 'weekly') and other_day.strftime('%Y-%m') == day.strftime('%Y-%m')
    return False


def run_scheduled_reviews(db_path, reports_dir, *, now=None, directory=None, generator=None):
    now = now or datetime.now()
    directory = Path(directory or Path(get_data_dir()) / 'intelligence')
    settings = load_settings(directory)
    if not settings['enabled'] or not settings['reports_enabled']:
        return {'generated_paths': [], 'status': '自动智能汇总未开启'}
    if not _RUN_LOCK.acquire(blocking=False):
        return {'generated_paths': [], 'status': '正在汇总'}
    try:
        return _run(db_path, reports_dir, now, directory, generator or generate_budget_review)
    finally:
        _RUN_LOCK.release()


def _run(db_path, reports_dir, now, directory, generate):
    state_path = directory / 'report_schedule.json'
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding='utf-8'))
            start = date.fromisoformat(state['started_on'])
            if state.get('version') != 1 or not isinstance(state['done'], dict):
                raise ValueError()
            if any(v not in ('ready', 'skipped', 'failed') for v in state['done'].values()):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            return {'generated_paths': [], 'status': '自动汇总状态损坏，已暂停以避免重复请求'}
    else:
        start = now.date()
        state = {'version': 1, 'started_on': start.isoformat(), 'done': {},
                 'fact_source_version': FACT_SOURCE_VERSION}
        atomic_json(state_path, state)
    if state.get('fact_source_version') != FACT_SOURCE_VERSION:
        # Older builds read a field that the range query did not return, so
        # genuinely populated periods were recorded as empty. Reconsider only
        # those skipped periods; ready/failed requests retain their once-only
        # guarantees and real empty periods are skipped again without an API call.
        state['done'] = {key: value for key, value in state['done'].items()
                         if value != 'skipped'}
        state['fact_source_version'] = FACT_SOURCE_VERSION
        atomic_json(state_path, state)
    due = due_periods(start, now)
    generated = []
    deferred_kinds = set()
    status = '每天23:00日报 · 周日周报 · 月末月报'
    if not read_key():
        status = '等待配置密钥；到期汇总将保留待补'
    else:
        for kind, day in due:
            identity = _identity(kind, day)
            if identity in state['done'] or kind in deferred_kinds:
                continue
            if any(_depends_on(kind, day, k, d) and _identity(k, d) not in state['done'] for k, d in due):
                continue
            try:
                result = generate(db_path, kind, day, directory=directory)
                if result.get('status') != 'ready':
                    state['done'][identity] = 'failed'
                    status = '部分智能汇总未完成，未重复请求；原生报告可用'
                else:
                    path = ensure_native_report(db_path, reports_dir, kind, day)
                    attach_summary(path, render_review(result))
                    generated.append(str(path))
                    state['done'][identity] = 'ready'
            except NoReviewData:
                state['done'][identity] = 'skipped'
            except RequestDeferred:
                deferred_kinds.add(kind)
                status = '额度或调用条件暂不满足，待后续补生成'
            except Exception:
                # The review cache determines whether a request was attempted.
                # Leave scheduling pending: cached failures never resend; cached
                # successes can retry only the local report write after I/O errors.
                deferred_kinds.add(kind)
                status = '部分汇总暂未完成，原生报告不受影响'
            atomic_json(state_path, state)
    pending = sum(_identity(k, d) not in state['done'] for k, d in due)
    failed = sum(v == 'failed' for v in state['done'].values())
    state.update(last_check=now.isoformat(timespec='seconds'), status=status,
                 pending=pending, failed=failed)
    atomic_json(state_path, state)
    return {'generated_paths': generated, 'status': status, 'pending': pending}


def schedule_status(directory=None):
    directory = Path(directory or Path(get_data_dir()) / 'intelligence')
    settings = load_settings(directory)
    if not settings['enabled'] or not settings['reports_enabled']:
        return '自动智能汇总未开启，可在设置中心启用'
    try:
        state = json.loads((directory / 'report_schedule.json').read_text(encoding='utf-8'))
        suffix = f" · 待补 {state.get('pending', 0)} 份" if state.get('pending') else ''
        if state.get('failed'):
            suffix += f" · 未完成 {state['failed']} 份（不重复请求）"
        return state['status'] + suffix
    except (OSError, ValueError, KeyError, TypeError):
        return '每天23:00日报 · 周日周报 · 月末月报；未运行时下次启动补生成'
