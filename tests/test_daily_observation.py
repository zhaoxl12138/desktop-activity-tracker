from daylens.services.daily_observation import candidate_observations, generate_daily_observation
from daylens.services.intelligence_state import save_settings


def _snapshot():
    return {
        "today": "2026-10-21",
        "totals": {"effective_seconds": 7200},
        "rhythm": {"today": {"comparison": {"comparable": True, "delta_seconds": -1200}}},
        "interruption_analysis": {"status": "ready", "total_count": 4, "total_seconds": 900},
        "entertainment_history": {"week": {"points": [
            {"date": "2026-10-21", "seconds": 4500, "limit_seconds": 3600, "has_data": True}
        ]}},
    }


def test_candidates_use_aggregate_evidence_only():
    snapshot = _snapshot()
    snapshot["sessions"] = [{"window_title": "secret project", "process_name": "private.exe"}]
    facts = candidate_observations(snapshot)
    assert {item["id"] for item in facts} == {"rhythm", "interruptions", "entertainment"}
    assert "secret" not in str(facts)
    assert "private" not in str(facts)
    assert "20分钟" in next(item["text"] for item in facts if item["id"] == "rhythm")


def test_no_unsupported_comparison_or_short_day():
    snapshot = _snapshot()
    snapshot["rhythm"]["today"]["comparison"]["comparable"] = False
    assert "rhythm" not in {item["id"] for item in candidate_observations(snapshot)}
    snapshot["totals"]["effective_seconds"] = 100
    assert candidate_observations(snapshot) == []


def test_once_per_day_uses_shared_switch_and_budget(tmp_path):
    save_settings(tmp_path, {"enabled": True, "reports_enabled": True, "monthly_budget_micros": 4_000_000})
    calls = []

    class Provider:
        def request_json(self, prompt, payload, **options):
            calls.append((prompt, payload, options))
            return {"id": "interruptions"}

    first = generate_daily_observation(tmp_path, _snapshot(), provider_factory=lambda *_: Provider(), key_reader=lambda: "test")
    second = generate_daily_observation(tmp_path, _snapshot(), provider_factory=lambda *_: Provider(), key_reader=lambda: "test")
    assert first == second
    assert len(calls) == 1
    assert calls[0][2]["daily_limit"] == 1
    assert calls[0][2]["kind"] == "daily_observation"
    assert "sessions" not in str(calls[0][1])
    assert first["text"] == "今天工作被明显打断4次，累计约15分钟"


def test_invalid_ai_choice_is_not_displayed_and_not_retried(tmp_path):
    save_settings(tmp_path, {"enabled": True, "reports_enabled": True, "monthly_budget_micros": 4_000_000})
    calls = []

    class Provider:
        def request_json(self, *_args, **_kwargs):
            calls.append(1)
            return {"id": "invented"}

    for _ in range(2):
        assert generate_daily_observation(tmp_path, _snapshot(), provider_factory=lambda *_: Provider(), key_reader=lambda: "test") is None
    assert len(calls) == 1


def test_disabled_ai_does_not_send_or_show_cached(tmp_path):
    assert generate_daily_observation(tmp_path, _snapshot(), key_reader=lambda: "test") is None
