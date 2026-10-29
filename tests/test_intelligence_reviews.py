from datetime import date

import pytest

from daylens.services.intelligence_reviews import IntelligenceReviews


class Provider:
    def __init__(self):
        self.calls = []

    def request_json(self, prompt, payload, **kwargs):
        self.calls.append(payload)
        return {'observations': [{'text': '处理Camera技术资料', 'evidence_ids': [payload['facts'][0]['id']]}],
                'topics': [{'name': 'Camera学习', 'evidence_ids': [payload['facts'][0]['id']]}]}


def test_daily_theme_and_review_share_one_call_and_persist(tmp_path):
    provider = Provider()
    reviews = IntelligenceReviews(tmp_path, provider)
    day = date(2026, 9, 7)
    facts = [{'id': 's1', 'title': 'HAL3', 'engaged_seconds': 60}]
    result = reviews.generate('daily', day, facts)
    assert result['status'] == 'ready'
    assert result['facts'] == facts
    restarted = IntelligenceReviews(tmp_path, provider)
    assert restarted.generate('daily', day, facts) == result
    assert len(provider.calls) == 1


def test_explicit_stale_reanalysis_archives_old_review_and_calls_provider_once_more(tmp_path):
    provider = Provider()
    reviews = IntelligenceReviews(tmp_path, provider)
    day = date(2026, 9, 7)
    facts = [{'id': 's1', 'title': 'HAL3', 'engaged_seconds': 60}]
    first = reviews.generate('daily', day, facts)

    second = reviews.generate('daily', day, facts, replace_existing=True)

    assert second['status'] == 'ready'
    assert len(provider.calls) == 2
    history = list((tmp_path / 'reviews' / 'history').glob('daily-2026-09-07-*.json'))
    assert len(history) == 1
    assert history[0].read_text(encoding='utf-8')


def test_failed_stale_reanalysis_keeps_previous_ready_review_available(tmp_path):
    provider = Provider()
    reviews = IntelligenceReviews(tmp_path, provider)
    day = date(2026, 9, 7)
    facts = [{'id': 's1', 'title': 'HAL3', 'engaged_seconds': 60}]
    first = reviews.generate('daily', day, facts)

    def fail(*_args, **_kwargs):
        raise RuntimeError('temporary provider failure')

    provider.request_json = fail
    with pytest.raises(RuntimeError):
        reviews.generate('daily', day, facts, replace_existing=True)

    assert reviews.load('daily', day) == first


def test_weekly_uses_summaries_not_raw_session_payload(tmp_path):
    provider = Provider()
    reviews = IntelligenceReviews(tmp_path, provider)
    day = date(2026, 9, 7)
    reviews.generate('daily', day, [{'id': 's1', 'title': 'RAW_PRIVATE_TITLE'}])
    facts = reviews.compressed_facts('weekly', day)
    assert len(facts) == 1
    assert 'RAW_PRIVATE_TITLE' not in str(facts)
    assert facts[0]['period'] == '2026-09-07'


def test_fake_evidence_rejected_and_no_automatic_retry(tmp_path):
    provider = Provider()
    provider.request_json = lambda *a, **k: {'observations': [{'text': 'wrong', 'evidence_ids': ['fake']}], 'topics': []}
    reviews = IntelligenceReviews(tmp_path, provider)
    day = date(2026, 9, 7)
    with pytest.raises(RuntimeError):
        reviews.generate('daily', day, [{'id': 's1'}])
    assert reviews.generate('daily', day, [{'id': 's1'}])['status'] == 'failed'


def test_failed_review_retries_only_when_explicitly_allowed(tmp_path):
    class FailOnceProvider(Provider):
        def request_json(self, prompt, payload, **kwargs):
            self.calls.append(payload)
            if len(self.calls) == 1:
                raise RuntimeError('temporary provider failure')
            return {
                'observations': [
                    {'text': '处理Camera技术资料', 'evidence_ids': [payload['facts'][0]['id']]},
                ],
                'topics': [
                    {'name': 'Camera学习', 'evidence_ids': [payload['facts'][0]['id']]},
                ],
            }

    provider = FailOnceProvider()
    reviews = IntelligenceReviews(tmp_path, provider)
    day = date(2026, 9, 8)
    facts = [{'id': 's1', 'title': 'Camera', 'engaged_seconds': 60}]

    with pytest.raises(RuntimeError):
        reviews.generate('daily', day, facts)
    assert reviews.generate('daily', day, facts)['status'] == 'failed'
    result = reviews.generate('daily', day, facts, retry_failed=True)

    assert result['status'] == 'ready'
    assert len(provider.calls) == 2
