import json

import pytest

from daylens.services.intelligence_budget import IntelligenceBudget
from daylens.services.intelligence_client import DeepSeekProvider, IntelligenceError


def response(items, finish='stop'):
    return {'usage': {'prompt_tokens': 800, 'completion_tokens': 100},
            'choices': [{'finish_reason': finish,
                         'message': {'content': json.dumps({'items': items})}}]}


ITEM = {'id': 'title1', 'category': 'coding', 'certainty': 'high', 'reason': 'Camera HAL技术学习'}
CONTEXT = [{'id': 'title1', 'app': 'chrome.exe', 'title': 'HAL3 Request / Result'}]


def test_batched_json_non_thinking_and_usage(tmp_path):
    sent = []
    def transport(body, key):
        sent.append(json.loads(body))
        return response([ITEM])
    budget = IntelligenceBudget(tmp_path / 'budget.json')
    client = DeepSeekProvider(budget, lambda: 'fake-test-key', transport=transport)
    assert client.classify(CONTEXT)['title1']['category'] == 'coding'
    assert sent[0]['thinking'] == {'type': 'disabled'}
    assert sent[0]['max_tokens'] == 512
    assert budget.snapshot()['cost_micros'] == 3300


@pytest.mark.parametrize('item', [dict(ITEM, category='invented'), dict(ITEM, id='another'),
                                dict(ITEM, certainty='100%'), dict(ITEM, reason=None)])
def test_invalid_decisions_are_discarded_but_billed(tmp_path, item):
    budget = IntelligenceBudget(tmp_path / 'budget.json')
    client = DeepSeekProvider(budget, lambda: 'fake', transport=lambda *_: response([item]))
    with pytest.raises(IntelligenceError):
        client.classify(CONTEXT)
    assert budget.snapshot()['cost_micros'] == 3300


def test_missing_key_never_reserves_or_calls_network(tmp_path):
    budget = IntelligenceBudget(tmp_path / 'budget.json')
    def unexpected(*_):
        pytest.fail('Network must not be reached')
    client = DeepSeekProvider(budget, lambda: None, transport=unexpected)
    with pytest.raises(IntelligenceError):
        client.classify(CONTEXT)
    assert budget.snapshot()['today_requests'] == 0


def test_timeout_is_not_retried_and_secret_is_not_exposed(tmp_path):
    budget = IntelligenceBudget(tmp_path / 'budget.json')
    def failed(*_):
        raise RuntimeError('SECRET-KEY and private title')
    client = DeepSeekProvider(budget, lambda: 'fake', transport=failed)
    with pytest.raises(IntelligenceError) as caught:
        client.classify(CONTEXT)
    assert 'SECRET' not in str(caught.value)
    assert budget.snapshot()['today_requests'] == 1
    assert budget.snapshot()['uncertain_requests'] == 1


def test_truncated_response_cannot_be_accepted(tmp_path):
    client = DeepSeekProvider(IntelligenceBudget(tmp_path / 'budget.json'), lambda: 'fake',
                              transport=lambda *_: response([ITEM], 'length'))
    with pytest.raises(IntelligenceError):
        client.classify(CONTEXT)
