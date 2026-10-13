from daylens.services.intelligence_scheduler import IntelligenceScheduler
from daylens.services.intelligence_state import DEFAULT_SETTINGS, save_settings, title_context
from daylens.services.intelligence_state import save_override


class FakeProvider:
    def __init__(self):
        self.calls = []

    def classify(self, items):
        self.calls.append(items)
        return {x['id']: {'category': 'coding', 'certainty': 'high', 'reason': '技术学习'} for x in items}


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


def test_redaction_exclusion_and_rule_version(tmp_path):
    settings = dict(DEFAULT_SETTINGS, excluded_words=['私人'], excluded_apps=['secret.exe'])
    assert title_context('chrome.exe', '私人文档', settings, 'v1') is None
    assert title_context('secret.exe', 'HAL3', settings, 'v1') is None
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
