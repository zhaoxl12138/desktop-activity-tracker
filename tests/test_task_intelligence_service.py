import json
from datetime import datetime

from daylens.services.intelligence_state import save_settings
from daylens.services.task_grouping_service import build_task_analysis
from daylens.services.task_intelligence_service import prepare_task_payload, request_task_suggestion


def row(identity, start, end, app, title, engaged=120):
    return {"session_id": identity, "date": "2026-10-21",
            "start_time": f"2026-10-21 {start}", "end_time": f"2026-10-21 {end}",
            "process_name": app, "normalized_title": title,
            "category_key": "coding", "engaged_seconds": engaged,
            "effective_seconds": engaged, "passive_seconds": 0,
            "idle_seconds": 0, "duration_seconds": engaged,
            "metric_version": "attention-v1"}


def _candidate():
    rows = [
        row("s1", "09:00:00", "09:02:00", "code.exe", "Camera driver notes 123456789", engaged=120),
        row("s2", "09:02:10", "09:04:10", "chrome.exe", "Camera driver docs john@example.com", engaged=120),
    ]
    return rows, build_task_analysis(rows, "2026-10-21")


def test_preview_contains_only_redacted_bounded_evidence():
    rows, analysis = _candidate()
    prepared = prepare_task_payload(rows, analysis)
    serialized = str(prepared["payload"])
    assert "123456789" not in serialized
    assert "john@example.com" not in serialized
    assert "s1" not in serialized and "s2" not in serialized
    assert prepared["digest"]


def test_title_with_space_containing_local_path_is_not_sent():
    rows, analysis = _candidate()
    rows[0]["normalized_title"] = "Camera driver C:/Users/John Doe/private report.txt"
    prepared = prepare_task_payload(rows, analysis)
    serialized = str(prepared["payload"])
    assert "John" not in serialized and "private report" not in serialized


def test_disabled_cloud_never_invokes_provider(tmp_path):
    rows, analysis = _candidate()
    prepared = prepare_task_payload(rows, analysis)

    class Provider:
        def request_json(self, *_args, **_kwargs):
            raise AssertionError("network should remain off")

    assert request_task_suggestion(tmp_path, prepared, provider=Provider(),
                                   key_reader=lambda: "fake",
                                   approved_digest=prepared["digest"]) is None


def test_approved_request_rejects_unknown_evidence_and_is_idempotent(tmp_path):
    rows, analysis = _candidate()
    prepared = prepare_task_payload(rows, analysis)
    save_settings(tmp_path, {"enabled": True, "task_analysis_enabled": True,
                             "task_cloud_enabled": True})
    calls = []

    class Provider:
        def request_json(self, prompt, payload, **options):
            calls.append(options)
            return {"items": [{"candidate_id": payload["candidates"][0]["id"],
                               "suggested_name": "相机驱动学习", "confidence": "high",
                               "reason": "标题主题相同", "evidence_ids": ["fabricated"]}]}

    assert request_task_suggestion(tmp_path, prepared, provider=Provider(),
                                   key_reader=lambda: "fake",
                                   approved_digest=prepared["digest"]) is None
    assert len(calls) == 1


def test_no_explicit_preview_approval_means_no_cloud_request(tmp_path):
    rows, analysis = _candidate()
    prepared = prepare_task_payload(rows, analysis)
    save_settings(tmp_path, {"enabled": True, "task_analysis_enabled": True,
                             "task_cloud_enabled": True})

    class Provider:
        def request_json(self, *_args, **_kwargs):
            raise AssertionError("must not send without approval")

    assert request_task_suggestion(tmp_path, prepared, provider=Provider(),
                                   key_reader=lambda: "fake") is None


def test_malformed_unhashable_model_evidence_safely_degrades(tmp_path):
    rows, analysis = _candidate()
    prepared = prepare_task_payload(rows, analysis)
    save_settings(tmp_path, {"enabled": True, "task_analysis_enabled": True,
                             "task_cloud_enabled": True})

    class Provider:
        def request_json(self, _prompt, payload, **_options):
            return {"items": [{"candidate_id": payload["candidates"][0]["id"],
                               "suggested_name": "测试", "confidence": "high",
                               "reason": "证据", "evidence_ids": [["bad"]]}]}

    assert request_task_suggestion(tmp_path, prepared, provider=Provider(),
                                   key_reader=lambda: "fake",
                                   approved_digest=prepared["digest"]) is None


def test_valid_suggestion_uses_only_approved_evidence_and_reuses_cache(tmp_path):
    rows, analysis = _candidate()
    prepared = prepare_task_payload(rows, analysis)
    save_settings(tmp_path, {"enabled": True, "task_analysis_enabled": True,
                             "task_cloud_enabled": True})
    sent = []

    class Provider:
        def request_json(self, _prompt, payload, **_options):
            sent.append(payload)
            candidate = payload["candidates"][0]
            return {"items": [{"candidate_id": candidate["id"],
                               "suggested_name": "相机驱动学习", "confidence": "high",
                               "reason": "标题共同主题", "evidence_ids": [candidate["evidence"][0]["id"]]}]}

    first = request_task_suggestion(tmp_path, prepared, provider=Provider(),
                                    key_reader=lambda: "fake",
                                    approved_digest=prepared["digest"])
    second = request_task_suggestion(tmp_path, prepared, provider=Provider(),
                                     key_reader=lambda: "fake",
                                     approved_digest=prepared["digest"])
    assert first == second
    assert first[0]["needs_confirmation"] is True
    assert len(sent) == 1


def test_preview_invalidates_if_fresh_evidence_changes(tmp_path):
    rows, analysis = _candidate()
    prepared = prepare_task_payload(rows, analysis)
    save_settings(tmp_path, {"enabled": True, "task_analysis_enabled": True,
                             "task_cloud_enabled": True})

    class Provider:
        def request_json(self, *_args, **_kwargs):
            raise AssertionError("stale preview must not send")

    assert request_task_suggestion(
        tmp_path, prepared, provider=Provider(), key_reader=lambda: "fake",
        approved_digest=prepared["digest"],
        fresh_prepared=lambda: {"digest": "changed", "payload": prepared["payload"]},
    ) is None


def test_ai_can_only_suggest_links_to_candidates_in_the_approved_batch(tmp_path):
    rows, analysis = _candidate()
    second = [
        row("s3", "10:00:00", "10:02:00", "code.exe", "Camera module", engaged=120),
        row("s4", "10:02:10", "10:04:10", "chrome.exe", "Camera module docs", engaged=120),
    ]
    rows += second
    analysis = build_task_analysis(rows, "2026-10-21")
    prepared = prepare_task_payload(rows, analysis)
    assert len(prepared["payload"]["candidates"]) == 2
    save_settings(tmp_path, {"enabled": True, "task_analysis_enabled": True,
                             "task_cloud_enabled": True})

    class Provider:
        def __init__(self, target):
            self.target = target

        def request_json(self, _prompt, payload, **_options):
            candidate = payload["candidates"][0]
            return {"items": [{"candidate_id": candidate["id"],
                               "suggested_name": "相机学习", "confidence": "medium",
                               "reason": "主题相同", "evidence_ids": [candidate["evidence"][0]["id"]],
                               "related_candidate_ids": [self.target]}]}

    allowed = prepared["payload"]["candidates"][1]["id"]
    accepted = request_task_suggestion(tmp_path, prepared, provider=Provider(allowed),
                                       key_reader=lambda: "fake",
                                       approved_digest=prepared["digest"])
    assert accepted[0]["related_candidate_ids"] == [allowed]

    other = tmp_path / "other"
    save_settings(other, {"enabled": True, "task_analysis_enabled": True,
                          "task_cloud_enabled": True})
    rejected = request_task_suggestion(other, prepared, provider=Provider("fabricated"),
                                       key_reader=lambda: "fake",
                                       approved_digest=prepared["digest"])
    assert rejected is None


def test_corrupt_cached_suggestion_is_rejected(tmp_path):
    rows, analysis = _candidate()
    prepared = prepare_task_payload(rows, analysis)
    save_settings(tmp_path, {"enabled": True, "task_analysis_enabled": True,
                             "task_cloud_enabled": True})
    cache = {"version": 1, "entries": {prepared["digest"]: {
        "created_at": datetime.now().isoformat(),
        "items": [{"candidate_id": "fabricated", "suggested_name": "假的",
                   "confidence": "high", "reason": "伪造", "evidence_ids": ["fabricated"],
                   "needs_confirmation": True, "source": "AI 建议"}],
    }}}
    (tmp_path / "task_ai_cache.json").write_text(json.dumps(cache), encoding="utf-8")

    class Provider:
        def request_json(self, *_args, **_kwargs):
            raise RuntimeError("offline")

    assert request_task_suggestion(tmp_path, prepared, provider=Provider(),
                                   key_reader=lambda: "fake",
                                   approved_digest=prepared["digest"]) is None


def test_common_model_field_variants_are_normalized_without_losing_id_checks(tmp_path):
    rows, analysis = _candidate()
    prepared = prepare_task_payload(rows, analysis)
    save_settings(tmp_path, {"enabled": True, "task_analysis_enabled": True,
                             "task_cloud_enabled": True})

    class Provider:
        def request_json(self, _prompt, payload, **_options):
            candidate = payload["candidates"][0]
            return {"tasks": [{
                "candidate_id": candidate["id"],
                "task_name": "相机驱动学习",
                "confidence": "中",
                "reason": "标题主题一致",
                "related_candidate_ids": None,
                "explanation": "extra fields are ignored",
            }]}

    result = request_task_suggestion(
        tmp_path, prepared, provider=Provider(), key_reader=lambda: "fake",
        approved_digest=prepared["digest"],
    )

    assert result[0]["suggested_name"] == "相机驱动学习"
    assert result[0]["confidence"] == "medium"
    assert result[0]["evidence_ids"] == [
        item["id"] for item in prepared["payload"]["candidates"][0]["evidence"]
    ]


def test_detailed_task_cloud_failure_returns_safe_user_message(tmp_path):
    rows, analysis = _candidate()
    prepared = prepare_task_payload(rows, analysis)
    save_settings(tmp_path, {"enabled": True, "task_analysis_enabled": True,
                             "task_cloud_enabled": True})

    class Provider:
        def request_json(self, *_args, **_kwargs):
            raise RuntimeError("secret provider detail")

    result = request_task_suggestion(
        tmp_path, prepared, provider=Provider(), key_reader=lambda: "fake",
        approved_digest=prepared["digest"], detailed=True,
    )

    assert result == {
        "status": "failed", "items": None,
        "message": "AI请求未成功，请检查网络、密钥或服务额度",
    }
    assert "secret" not in result["message"]
