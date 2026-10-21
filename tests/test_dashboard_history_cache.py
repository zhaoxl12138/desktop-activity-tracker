from daylens.services.dashboard_history_cache import DashboardHistoryCache


def test_completed_history_cache_ignores_live_today_changes():
    cache = DashboardHistoryCache()
    calls = []
    revision = (10, 99, "attention-v1", "rules-v2")

    def load():
        calls.append("load")
        return {"daily": [{"date": "2026-10-20"}]}, [{"session_id": "old"}], {"totals": {}}

    first = cache.get_or_load(
        db_path="usage.db",
        dates=["2026-10-01", "2026-10-20"],
        revision=revision,
        loader=load,
    )
    second = cache.get_or_load(
        db_path="usage.db",
        dates=["2026-10-01", "2026-10-20"],
        revision=revision,
        loader=load,
    )

    assert first is second
    assert calls == ["load"]


def test_completed_history_cache_invalidates_on_metric_or_classification_revision():
    cache = DashboardHistoryCache()
    calls = 0

    def load():
        nonlocal calls
        calls += 1
        return {"daily": []}, [], {"totals": {}}

    for revision in (
        (10, 99, "attention-v1", "rules-v1"),
        (10, 99, "attention-v2", "rules-v1"),
        (10, 99, "attention-v2", "rules-v2"),
    ):
        cache.get_or_load(
            db_path="usage.db",
            dates=["2026-10-01", "2026-10-20"],
            revision=revision,
            loader=load,
        )

    assert calls == 3


def test_completed_history_cache_is_bounded():
    cache = DashboardHistoryCache(max_entries=2)
    for index in range(3):
        cache.get_or_load(
            db_path=f"usage-{index}.db",
            dates=["2026-10-20"],
            revision=(index,),
            loader=lambda: ({"daily": []}, [], {"totals": {}}),
        )

    assert cache.size == 2
