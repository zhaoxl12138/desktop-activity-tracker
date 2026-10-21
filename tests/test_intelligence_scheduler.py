from daylens.services.intelligence_scheduler import IntelligenceScheduler
from daylens.services.intelligence_state import DEFAULT_SETTINGS, save_settings, title_context
from daylens.services.intelligence_state import save_override
from daylens.services.intelligence_evidence import ReviewQueue, load_patterns
from daylens.services.intelligence_state import atomic_json


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.category = 'coding'
        self.certainty = 'high'

    def classify(self, items):
        self.calls.append(items)
        return {x['id']: {'category': self.category, 'certainty': self.certainty,
                          'reason': '技术学习'} for x in items}


def build(tmp_path, clock=lambda: 0):
    save_settings(tmp_path, dict(DEFAULT_SETTINGS, enabled=True))
    provider = FakeProvider()
    return IntelligenceScheduler(tmp_path, provider=provider, clock=clock), provider


def see(scheduler, title='HAL3 Request', seconds=1):
    return scheduler.observe('chrome.exe', title, 'browser_general', 'v1', active_seconds=seconds)


def assert_pending(decision, reason=''):
    assert decision == {
        'status': 'pending',
        'source': 'AI待识别',
        'category': '',
        'certainty': '',
        'reason': reason,
        'suggested_category': '',
        'evidence': [],
        'pattern_id': '',
        'apply': False,
    }


def test_only_thirty_active_seconds_qualifies_and_single_title_flushes(tmp_path):
    now = [0]
    scheduler, provider = build(tmp_path, lambda: now[0])
    for _ in range(29):
        see(scheduler)
    for _ in range(100):
        see(scheduler, seconds=0)
    scheduler.process_pending(force=True)
    assert not provider.calls
    see(scheduler)
    scheduler.process_pending()
    assert not provider.calls
    now[0] = 16
    scheduler.process_pending()
    assert len(provider.calls) == 1
    assert see(scheduler)['category'] == 'coding'


def test_five_titles_share_call_and_cache_survives_restart(tmp_path):
    scheduler, provider = build(tmp_path)
    for n in range(5):
        for _ in range(30):
            see(scheduler, title=f'HAL3 {n}')
    scheduler.process_pending()
    assert len(provider.calls) == 1
    assert len(provider.calls[0]) == 5
    restarted = IntelligenceScheduler(tmp_path, provider=provider)
    assert see(restarted, title='HAL3 0')['category'] == 'coding'
    assert_pending(see(restarted, title='unrelated'))


def test_disable_during_request_ignores_result(tmp_path):
    scheduler, provider = build(tmp_path)
    def interrupted(items):
        save_settings(tmp_path, dict(DEFAULT_SETTINGS, enabled=False))
        scheduler.reload()
        return {x['id']: {'category': 'coding', 'certainty': 'high', 'reason': ''} for x in items}
    provider.classify = interrupted
    for _ in range(30):
        see(scheduler)
    scheduler.process_pending(force=True)
    assert not scheduler.cache
    assert see(scheduler) is None


def test_media_and_known_rules_do_not_get_reclassified(tmp_path):
    scheduler, provider = build(tmp_path)
    for _ in range(40):
        assert scheduler.observe('QyClient.exe', 'HAL3', 'video', 'v1', active_seconds=1) is None
        assert scheduler.observe('chrome.exe', 'HAL3', 'coding', 'v1', active_seconds=1) is None
    scheduler.process_pending(force=True)
    assert not provider.calls


def test_redaction_and_rule_version_ignore_legacy_exclusions(tmp_path):
    settings = dict(DEFAULT_SETTINGS, excluded_words=['私人'], excluded_apps=['secret.exe'])
    assert title_context('chrome.exe', '私人文档', settings, 'v1') is not None
    assert title_context('secret.exe', 'HAL3', settings, 'v1') is not None
    context = title_context('chrome.exe', 'HAL3 a@example.com 13812345678 https://secret/a?token=x', settings, 'v1')
    assert 'example.com' not in context['title']
    assert '13812345678' not in context['title']
    assert 'token=x' not in context['title']
    assert context['id'] != title_context('chrome.exe', 'HAL3 a@example.com 13812345678 https://secret/a?token=x', settings, 'v2')['id']


def test_redacted_titles_do_not_share_manual_decisions(tmp_path):
    settings = dict(DEFAULT_SETTINGS)
    a = title_context('chrome.exe', 'Document alice@example.com', settings, 'v1')
    b = title_context('chrome.exe', 'Document bob@example.com', settings, 'v1')
    assert a['title'] == b['title']
    assert a['id'] != b['id']
    save_override(tmp_path, 'chrome.exe', 'Document alice@example.com', 'coding')
    scheduler = IntelligenceScheduler(tmp_path, provider=FakeProvider())
    assert scheduler.observe('chrome.exe', 'Document alice@example.com', 'browser_general', 'v1')['source'] == '手动'
    assert scheduler.observe('chrome.exe', 'Document bob@example.com', 'browser_general', 'v1') is None


def test_missing_key_does_not_apply_ai_cache(tmp_path):
    scheduler, provider = build(tmp_path)
    for _ in range(30):
        see(scheduler)
    scheduler.process_pending(force=True)
    provider.key_reader = lambda: None
    scheduler.reload()
    assert see(scheduler) is None


def test_queue_is_bounded_and_late_result_stays_with_its_title(tmp_path):
    scheduler, provider = build(tmp_path)
    for n in range(40):
        for _ in range(6):
            see(scheduler, title=f'Title {n}', seconds=5)
    assert len(scheduler.pending) == 30
    scheduler.process_pending(force=True)
    assert_pending(see(scheduler, title='unrelated'))
    assert see(scheduler, title='Title 0')['category'] == 'coding'


def test_eligible_uncached_title_exposes_pending_state(tmp_path):
    scheduler, _provider = build(tmp_path)

    assert_pending(see(scheduler, seconds=1))


def test_cached_medium_result_remains_a_suggestion(tmp_path):
    scheduler, _provider = build(tmp_path)
    context = title_context('chrome.exe', 'HAL3 Request', scheduler.settings, 'v1')
    scheduler.cache[context['id']] = {
        'category': 'reading',
        'certainty': 'medium',
        'reason': '标题含义不充分',
    }

    decision = see(scheduler)

    assert decision['category'] == 'reading'
    assert decision['certainty'] == 'medium'
    assert decision['reason'] == '标题含义不充分'


def test_manual_similar_pattern_has_priority_even_over_known_local_rule(tmp_path):
    save_override(tmp_path, 'chrome.exe', '学习中心 - 视频课程 - 自考公共课', 'reading')
    scheduler = IntelligenceScheduler(tmp_path, provider=FakeProvider())

    decision = scheduler.observe(
        'chrome.exe', '学习中心 - 视频课程 - 自考专业课', 'office', 'v1', active_seconds=1,
    )

    assert decision['apply'] is True
    assert decision['category'] == 'reading'
    assert decision['source'] == '人工模式'
    assert decision['pattern_id']


def test_ai_context_contains_only_recent_redacted_titles_from_same_app(tmp_path):
    scheduler, provider = build(tmp_path)
    scheduler.observe('edge.exe', 'Other app secret', 'browser_general', 'v1', active_seconds=1)
    for index in range(7):
        scheduler.observe(
            'chrome.exe', f'Lesson {index} alice@example.com https://private/{index}',
            'browser_general', 'v1', active_seconds=1,
        )
    for _ in range(30):
        scheduler.observe('chrome.exe', 'Learning hub', 'browser_general', 'v1', active_seconds=1)
    scheduler.process_pending(force=True)

    sent = next(item for item in provider.calls[0] if item['title'] == 'Learning hub')
    assert sent['base_category'] == 'browser_general'
    assert 1 <= len(sent['recent_titles']) <= 5
    assert all(row['app'] == 'chrome.exe' for row in sent['recent_titles'])
    assert all('example.com' not in row['title'] and 'private/' not in row['title']
               for row in sent['recent_titles'])
    assert all(set(row) == {'app', 'title', 'active_seconds', 'confirmed_category'}
               for row in sent['recent_titles'])
    stored = __import__('json').loads(
        (tmp_path / 'classification_cache.json').read_text(encoding='utf-8'))
    cached_context = stored[sent['id']]['context']
    assert set(cached_context) == {'id', 'app', 'title', 'base_category'}


def test_medium_ai_result_applies_only_with_confirmed_recent_evidence(tmp_path):
    save_override(tmp_path, 'chrome.exe', 'Python课程中心', 'reading')
    scheduler, provider = build(tmp_path)
    scheduler.reload()
    provider.category = 'reading'
    provider.certainty = 'medium'
    scheduler.observe('chrome.exe', 'Python课程中心', 'browser_general', 'v1', active_seconds=5)
    for _ in range(6):
        scheduler.observe('chrome.exe', '考试安排中心', 'browser_general', 'v1', active_seconds=5)
    scheduler.process_pending(force=True)

    decision = scheduler.observe(
        'chrome.exe', '考试安排中心', 'browser_general', 'v1', active_seconds=1,
    )
    assert decision['apply'] is True
    assert decision['category'] == 'reading'
    assert 'recent_confirmed' in decision['evidence']


def test_uncertain_ai_result_is_saved_for_review_without_applying(tmp_path):
    scheduler, provider = build(tmp_path)
    provider.category = 'reading'
    provider.certainty = 'medium'
    for _ in range(30):
        see(scheduler, title='Ambiguous learning portal')
    scheduler.process_pending(force=True)

    decision = see(scheduler, title='Ambiguous learning portal')
    rows = ReviewQueue(tmp_path).items()
    assert decision['apply'] is False
    assert decision['source'] == 'AI待确认'
    assert rows[0]['suggested_category'] == 'reading'
    assert rows[0]['certainty'] == 'medium'


def test_cache_drops_expired_entries_and_is_bounded(tmp_path):
    entries = {
        f'id-{index}': {
            'category': 'reading', 'certainty': 'high', 'reason': '课程',
            'cached_at': '2026-10-17T08:00:00',
        }
        for index in range(1005)
    }
    entries['expired'] = {
        'category': 'reading', 'certainty': 'high', 'reason': '旧记录',
        'cached_at': '2020-01-01T00:00:00',
    }
    atomic_json(tmp_path / 'classification_cache.json', entries)

    scheduler = IntelligenceScheduler(tmp_path, provider=FakeProvider())

    assert len(scheduler.cache) == 1000
    assert 'expired' not in scheduler.cache


def test_pattern_usage_metadata_is_persisted_without_sampling_thread_io(tmp_path):
    save_override(tmp_path, 'chrome.exe', '学习中心 - 视频课程 - 自考公共课', 'reading')
    scheduler = IntelligenceScheduler(tmp_path, provider=FakeProvider())

    scheduler.observe(
        'chrome.exe', '学习中心 - 视频课程 - 自考专业课',
        'browser_general', 'v1', active_seconds=1,
    )
    scheduler.close()

    pattern = load_patterns(tmp_path)[0]
    assert pattern['hit_count'] == 1
    assert pattern['last_used_at'] >= pattern['created_at']
