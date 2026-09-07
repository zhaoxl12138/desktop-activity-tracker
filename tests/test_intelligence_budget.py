from datetime import datetime

import pytest

from daylens.services.intelligence_budget import IntelligenceBudget, BudgetUnavailable


def test_reservation_survives_restart_and_timeout(tmp_path):
    path = tmp_path / 'budget.json'
    budget = IntelligenceBudget(path, monthly_micros=5000)
    request = budget.reserve(1000, 100)
    restarted = IntelligenceBudget(path, monthly_micros=5000)
    with pytest.raises(BudgetUnavailable):
        restarted.reserve(1000, 100)
    restarted.settle(request, None)
    assert restarted.snapshot()['cost_micros'] == 3900


def test_usage_settles_once_and_keeps_original_month(tmp_path):
    budget = IntelligenceBudget(tmp_path / 'budget.json')
    september = datetime(2026, 9, 30, 23, 59)
    request = budget.reserve(1000, 100, now=september)
    budget.settle(request, {'prompt_tokens': 100, 'completion_tokens': 20})
    budget.settle(request, {'prompt_tokens': 9999, 'completion_tokens': 9999})
    assert budget.snapshot(september)['cost_micros'] == 480
    assert budget.snapshot(datetime(2026, 10, 1))['cost_micros'] == 0


def test_daily_cap_counts_titles_not_batches(tmp_path):
    budget = IntelligenceBudget(tmp_path / 'budget.json')
    for _ in range(6):
        budget.reserve(800, 150, units=5)
    with pytest.raises(BudgetUnavailable):
        budget.reserve(800, 150)
    assert budget.snapshot()['today_titles'] == 30


@pytest.mark.parametrize('usage', [None, {}, {'prompt_tokens': True, 'completion_tokens': 0},
                                      {'prompt_tokens': -1, 'completion_tokens': 20}])
def test_invalid_usage_does_not_refund_budget(tmp_path, usage):
    budget = IntelligenceBudget(tmp_path / 'budget.json')
    request = budget.reserve(1000, 100)
    budget.settle(request, usage)
    assert budget.snapshot()['cost_micros'] == 3900


def test_corrupted_state_blocks_new_calls(tmp_path):
    path = tmp_path / 'budget.json'
    path.write_text('{broken')
    with pytest.raises(BudgetUnavailable):
        IntelligenceBudget(path).reserve(1000, 100)


def test_real_usage_over_reservation_blocks_next_call(tmp_path):
    budget = IntelligenceBudget(tmp_path / 'budget.json', monthly_micros=5000)
    request = budget.reserve(100, 10)
    budget.settle(request, {'prompt_tokens': 2000, 'completion_tokens': 500})
    with pytest.raises(BudgetUnavailable):
        budget.reserve(1, 1)
