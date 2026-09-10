from datetime import date, datetime

import pytest

from daylens.services.intelligence_state import save_settings


def test_due_periods_cutoff_order_and_activation():
    from daylens.services.intelligence_report_schedule import due_periods
    start = date(2026, 5, 31)  # Sunday and month end
    assert due_periods(start, datetime(2026, 5, 31, 22, 59)) == []
    assert due_periods(start, datetime(2026, 5, 31, 23)) == [
        ('daily', start), ('weekly', start), ('monthly', start)]
    assert due_periods(date(2026, 12, 31), datetime(2027, 1, 1, 9)) == [
        ('daily', date(2026, 12, 31)), ('monthly', date(2026, 12, 31))]


def test_daily_facts_uses_normalized_title_from_range_query(monkeypatch, tmp_path):
    from daylens.services import intelligence_report_service as service

    monkeypatch.setattr(service.database, 'query_sessions_for_dates', lambda *_: [{
        'session_id': 'session-1',
        'process_name': 'code.exe',
        'normalized_title': 'DayLens report fix',
        'category_key': 'coding',
        'duration_seconds': 300,
        'engaged_seconds': 300,
        'passive_seconds': 0,
        'idle_seconds': 0,
    }])

    facts = service.daily_facts('unused', date(2026, 9, 10), {
        'excluded_apps': [], 'excluded_words': [],
    })

    assert len(facts) == 1
    assert facts[0]['title'] == 'DayLens report fix'
    assert facts[0]['engaged_seconds'] == 300


def test_scheduler_reconsiders_legacy_skipped_days_after_fact_source_fix(tmp_path, monkeypatch):
    import json
    from daylens.services import intelligence_report_schedule as schedule
    from daylens.services.intelligence_state import atomic_json

    directory = tmp_path / 'ai'
    save_settings(directory, {'enabled': True, 'reports_enabled': True})
    atomic_json(directory / 'report_schedule.json', {
        'version': 1,
        'started_on': '2026-09-08',
        'done': {'daily:2026-09-08': 'skipped'},
    })
    monkeypatch.setattr(schedule, 'read_key', lambda: 'dummy')
    monkeypatch.setattr(schedule, 'ensure_native_report', lambda *args: tmp_path / 'daily.md')
    monkeypatch.setattr(schedule, 'attach_summary', lambda *args: None)
    calls = []

    def generate(db, kind, day, **kwargs):
        calls.append((kind, day))
        return dict(status='ready', period=day.isoformat(), kind=kind,
                    captured_at='2026-09-10T12:00:00', facts=[], topics=[], observations=[])

    schedule.run_scheduled_reviews(
        'unused', tmp_path, directory=directory, generator=generate,
        now=datetime(2026, 9, 9, 9),
    )

    assert calls == [('daily', date(2026, 9, 8))]
    state = json.loads((directory / 'report_schedule.json').read_text(encoding='utf-8'))
    assert state['done']['daily:2026-09-08'] == 'ready'


def test_section_preserved_across_native_refresh(tmp_path):
    from daylens import exporter
    from daylens.services.report_sections import attach_summary
    report = tmp_path / 'report.md'
    report.write_text('Original notes', encoding='utf-8')
    attach_summary(report, 'AI summary')
    attach_summary(report, 'AI summary')
    assert report.read_text(encoding='utf-8').count('AI summary') == 1
    assert 'Original notes' in report.read_text(encoding='utf-8')
    exporter._atomic_write_text(str(report), 'Updated native statistics')
    content = report.read_text(encoding='utf-8')
    assert 'AI summary' in content and 'Updated native statistics' in content


def test_scheduler_catchup_and_no_duplicate(tmp_path, monkeypatch):
    from daylens.services import intelligence_report_schedule as schedule
    directory = tmp_path / 'ai'
    save_settings(directory, {'enabled': True, 'reports_enabled': True})
    calls = []
    monkeypatch.setattr(schedule, 'read_key', lambda: 'dummy')
    monkeypatch.setattr(schedule, 'ensure_native_report', lambda db, root, kind, day:
                        tmp_path / (kind + day.isoformat() + '.md'))
    def generate(db, kind, day, **kwargs):
        calls.append((kind, day))
        return dict(status='ready', period=day.isoformat(), kind=kind,
                    captured_at='2026-09-09T09:00:00', facts=[], topics=[], observations=[])
    args = dict(directory=directory, generator=generate)
    schedule.run_scheduled_reviews('unused', tmp_path, now=datetime(2026, 9, 8, 12), **args)
    assert calls == []
    schedule.run_scheduled_reviews('unused', tmp_path, now=datetime(2026, 9, 9, 9), **args)
    schedule.run_scheduled_reviews('unused', tmp_path, now=datetime(2026, 9, 9, 10), **args)
    assert calls == [('daily', date(2026, 9, 8))]


def test_budget_refusal_is_retryable_not_failed_period(tmp_path):
    from daylens.services.intelligence_client import RequestDeferred
    from daylens.services.intelligence_reviews import IntelligenceReviews
    class Provider:
        def request_json(self, *args, **kwargs):
            raise RequestDeferred('budget exhausted before send')
    reviews = IntelligenceReviews(tmp_path, Provider())
    with pytest.raises(RequestDeferred):
        reviews.generate('daily', date(2026, 9, 8), [{'id': 'one'}])
    assert reviews.load('daily', date(2026, 9, 8)) is None


def test_review_keeps_supported_items_when_one_model_item_is_invalid(tmp_path):
    from daylens.services.intelligence_reviews import IntelligenceReviews

    class Provider:
        def request_json(self, *args, **kwargs):
            return {
                'observations': [
                    {'text': '持续处理项目资料', 'evidence_ids': ['one']},
                    {'text': '连续工作100小时', 'evidence_ids': ['one']},
                ],
                'topics': [
                    {'name': '项目资料', 'evidence_ids': ['one']},
                    {'name': '代码检查', 'evidence_ids': ['one', 'two']},
                ],
            }

    facts = [
        {'id': 'one', 'app': 'editor', 'title': 'Project notes', 'engaged_seconds': 300},
        {'id': 'two', 'app': 'editor', 'title': 'Code review', 'engaged_seconds': 240},
    ]
    result = IntelligenceReviews(tmp_path, Provider()).generate(
        'daily', date(2026, 9, 8), facts,
    )

    assert result['status'] == 'ready'
    assert result['observations'] == [
        {'text': '持续处理项目资料', 'evidence_ids': ['one']},
    ]
    assert result['topics'] == [
        {'name': '项目资料', 'evidence_ids': ['one']},
        {'name': '代码检查', 'evidence_ids': ['two']},
    ]


def test_budget_style_includes_double_spinbox():
    from daylens.gui.style import get_input_style
    assert 'QDoubleSpinBox' in get_input_style()


def test_missing_key_and_disabled_do_not_send(tmp_path, monkeypatch):
    from daylens.services import intelligence_report_schedule as schedule
    directory = tmp_path / 'ai'
    calls = []
    generate = lambda *a, **k: calls.append(a)
    args = dict(directory=directory, generator=generate, now=datetime(2026, 9, 8, 23))
    schedule.run_scheduled_reviews('unused', tmp_path, **args)
    assert not (directory / 'report_schedule.json').exists()
    save_settings(directory, {'enabled': True, 'reports_enabled': True})
    monkeypatch.setattr(schedule, 'read_key', lambda: None)
    result = schedule.run_scheduled_reviews('unused', tmp_path, **args)
    assert result['pending'] == 1 and not calls


def test_backlog_preserves_dependencies_and_skips_empty_days(tmp_path, monkeypatch):
    import json
    from daylens.services import intelligence_report_schedule as schedule
    from daylens.services.intelligence_client import RequestDeferred
    from daylens.services.intelligence_reviews import NoReviewData
    from daylens.services.intelligence_state import atomic_json
    directory = tmp_path / 'ai'
    save_settings(directory, {'enabled': True, 'reports_enabled': True})
    atomic_json(directory / 'report_schedule.json', dict(version=1, started_on='2026-05-30', done={}))
    monkeypatch.setattr(schedule, 'read_key', lambda: 'dummy')
    calls = []
    def generate(db, kind, day, **kw):
        calls.append((kind, day))
        if day.day == 30:
            raise NoReviewData()
        raise RequestDeferred()
    result = schedule.run_scheduled_reviews('unused', tmp_path, directory=directory,
                 generator=generate, now=datetime(2026, 6, 1, 9))
    assert calls == [('daily', date(2026, 5, 30)), ('daily', date(2026, 5, 31))]
    assert result['pending'] == 3  # May 31 daily -> weekly -> monthly
    state = json.loads((directory / 'report_schedule.json').read_text(encoding='utf-8'))
    assert state['done'] == {'daily:2026-05-30': 'skipped'}


def test_failed_cached_period_never_retries_network_and_state_visible(tmp_path, monkeypatch):
    from daylens.services import intelligence_report_schedule as schedule
    directory = tmp_path / 'ai'
    save_settings(directory, {'enabled': True, 'reports_enabled': True})
    monkeypatch.setattr(schedule, 'read_key', lambda: 'dummy')
    calls = []
    def generate(*a, **k):
        calls.append(a)
        return {'status': 'failed'}
    for hour in (23, 23):
        schedule.run_scheduled_reviews('unused', tmp_path, directory=directory,
                    generator=generate, now=datetime(2026, 9, 8, hour))
    assert len(calls) == 1
    assert '未完成 1 份' in schedule.schedule_status(directory)


def test_month_end_includes_unfinished_week_daily_summaries(tmp_path):
    from daylens.services.intelligence_reviews import IntelligenceReviews
    from daylens.services.intelligence_state import atomic_json
    reviews = IntelligenceReviews(tmp_path, None)
    day = date(2026, 9, 30)  # Wednesday
    atomic_json(reviews.path('daily', day), dict(status='ready', topics=[], observations=[]))
    facts = reviews.compressed_facts('monthly', day)
    assert [f['period'] for f in facts] == ['2026-09-30']


def test_corrupt_schedule_fails_closed(tmp_path, monkeypatch):
    from daylens.services import intelligence_report_schedule as schedule
    directory = tmp_path / 'ai'
    save_settings(directory, {'enabled': True, 'reports_enabled': True})
    (directory / 'report_schedule.json').write_text('{broken', encoding='utf-8')
    def unexpected():
        pytest.fail('Should not even read credentials with corrupt schedule')
    monkeypatch.setattr(schedule, 'read_key', unexpected)
    result = schedule.run_scheduled_reviews('unused', tmp_path, directory=directory)
    assert '损坏' in result['status']


def test_native_creation_uses_requested_historical_period(tmp_path, monkeypatch):
    from daylens.services import intelligence_report_schedule as schedule
    calls = []
    monkeypatch.setattr(schedule.exporter, 'export_weekly_report', lambda *args: calls.append(args))
    path = schedule.ensure_native_report('db', tmp_path, 'weekly', date(2027, 1, 3))
    assert calls[0][1:3] == (2026, 53)
    assert path.name == '2026-12-28_2027-01-03_weekly.md'


def test_full_pipeline_appends_to_existing_report_once_without_real_api(tmp_path, monkeypatch):
    import json
    from daylens import exporter
    from daylens.services import intelligence_report_schedule as schedule
    from daylens.services import intelligence_report_service as service
    from daylens.services.intelligence_client import DeepSeekProvider
    directory = tmp_path / 'ai'
    save_settings(directory, {'enabled': True, 'reports_enabled': True})
    monkeypatch.setattr(schedule, 'read_key', lambda: 'dummy')
    monkeypatch.setattr(service, 'read_key', lambda: 'dummy')
    monkeypatch.setattr(service, 'daily_facts', lambda *a: [dict(
        id='one', app='editor', title='Camera learning', engaged_seconds=300, session_refs=['local-session'])])
    calls = []
    def transport(body, key):
        calls.append(json.loads(body))
        content = {'topics': [{'name': 'Camera学习', 'evidence_ids': ['one']}],
                   'observations': [{'text': '阅读Camera资料', 'evidence_ids': ['one']}]}
        return {'usage': {'prompt_tokens': 100, 'completion_tokens': 50},
                'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(content)}}]}
    monkeypatch.setattr(service, 'DeepSeekProvider', lambda budget, reader:
                        DeepSeekProvider(budget, reader, transport=transport))
    reports = tmp_path / 'reports'
    path = exporter.daily_report_path(str(reports / 'daily'), '2026-09-08')
    exporter._atomic_write_text(path, 'Existing report and personal notes')
    for _ in range(2):
        schedule.run_scheduled_reviews('unused', reports, directory=directory,
                                       now=datetime(2026, 9, 8, 23))
    from pathlib import Path
    text = Path(path).read_text(encoding='utf-8')
    assert 'Existing report and personal notes' in text
    assert text.count('## 智能汇总') == 1 and 'Camera学习' in text
    assert len(calls) == 1
    assert 'local-session' not in json.dumps(calls)


def test_monthly_summary_payload_stays_bounded(tmp_path):
    import json
    from datetime import timedelta
    from daylens.services.intelligence_reviews import IntelligenceReviews, REVIEW_PROMPT
    from daylens.services.intelligence_state import atomic_json
    reviews = IntelligenceReviews(tmp_path, None)
    for i in range(30):
        day = date(2026, 9, 1) + timedelta(days=i)
        summary = dict(status='ready', observations=[{'text': '学' * 250, 'evidence_ids': ['id' * 64] * 20}] * 4,
                       topics=[{'name': '学' * 250, 'evidence_ids': ['id' * 64] * 20}] * 5)
        atomic_json(reviews.path('daily', day), summary)
    facts = reviews.compressed_facts('monthly', date(2026, 9, 30))
    messages = [{'role': 'system', 'content': REVIEW_PROMPT},
                {'role': 'user', 'content': json.dumps({'kind': 'monthly', 'period': '2026-09', 'facts': facts}, ensure_ascii=False)}]
    assert len(json.dumps(messages, ensure_ascii=False).encode('utf-8')) < 22000
    assert len(facts) == 30
