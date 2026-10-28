from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from daylens.classifier import Classifier as ConfigClassifier
from daylens.session_tracker import SessionTracker


class Classifier:
    classification_version = 'rules-base'
    categories = {
        'coding': {'display_name': '技术学习', 'active_rule': 'interactive_required'},
        'reading': {'display_name': '阅读学习', 'active_rule': 'interactive_required'},
        'video': {'display_name': '影音娱乐', 'active_rule': 'passive_allowed'},
        'gaming': {'display_name': '游戏娱乐', 'active_rule': 'interactive_required'},
    }

    def classify(self, *_):
        return {'category_key': 'browser_general', 'category_name': '浏览器',
                'active_rule': 'interactive_required'}


class Intelligence:
    decision = None

    def observe(self, *args, **kwargs):
        return self.decision


class MutableAudio:
    def __init__(self, playing=True):
        self.playing = playing

    def is_playing(self, _pid):
        return self.playing


def test_ai_splits_prospectively_without_grace_or_rewriting_prior_time(monkeypatch):
    now = [datetime(2026, 9, 7, 10)]
    class Clock(datetime):
        @classmethod
        def now(cls):
            return now[0]
    monkeypatch.setattr('daylens.session_tracker.datetime', Clock)
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    recorded = []
    def persist(session):
        recorded.append(replace(session))
        return True
    tracker = SessionTracker(
        {'tracker': {'sample_interval_seconds': 1, 'idle_threshold_seconds': 60,
                     'min_session_seconds': 0, 'flush_interval_seconds': 300}},
        Classifier(), on_session_end=persist,
        monotonic_clock=lambda: now[0].timestamp(),
    )
    intelligence = Intelligence()
    tracker.intelligence = intelligence
    window = {'process_name': 'chrome.exe', 'window_title': 'HAL3 Request', 'pid': 42}
    for _ in range(8):
        tracker.mark_user_active()
        tracker.tick(0, window)
        now[0] += timedelta(seconds=1)
    old = replace(tracker.current_session)
    intelligence.decision = {'category': 'coding', 'certainty': 'high', 'reason': '技术学习'}
    snapshot = tracker.tick(0, window)
    assert snapshot['category_key'] == 'coding'
    assert snapshot['classification_detail']['source'] == 'AI'
    assert snapshot['pending_switch_domain'] is None
    assert recorded[-1].category_key == 'browser_general'
    assert recorded[-1].engaged_seconds == old.engaged_seconds
    assert tracker.current_session.session_id != old.session_id
    ai_time = tracker.current_session.engaged_seconds
    now[0] += timedelta(seconds=1)
    intelligence.decision = None
    snapshot = tracker.tick(0, window)
    assert snapshot['category_key'] == 'browser_general'
    assert recorded[-1].category_key == 'coding'
    assert recorded[-1].engaged_seconds == ai_time
    for session in recorded:
        assert session.duration_seconds == session.engaged_seconds + session.passive_seconds + session.idle_seconds


def test_adopted_high_ai_event_runs_after_fallback_session_is_persisted(monkeypatch):
    now = [datetime(2026, 10, 28, 16, 51, 3)]

    class Clock(datetime):
        @classmethod
        def now(cls):
            return now[0]

    monkeypatch.setattr('daylens.session_tracker.datetime', Clock)
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    recorded = []
    events = []

    def persist(session):
        recorded.append(replace(session))
        return True

    def applied(payload):
        events.append((payload, len(recorded), recorded[-1].category_key))
        return True

    tracker = SessionTracker(
        {'tracker': {'sample_interval_seconds': 1, 'min_session_seconds': 0}},
        Classifier(), on_session_end=persist,
        on_ai_classification_applied=applied,
    )
    intelligence = Intelligence()
    tracker.intelligence = intelligence
    window = {'process_name': 'Hades2.exe', 'window_title': 'Hades II', 'pid': 42}
    tracker.tick(0, window)
    now[0] += timedelta(seconds=46)
    intelligence.decision = {
        'status': 'applied', 'source': 'AI', 'category': 'gaming',
        'certainty': 'high', 'reason': 'Hades II is a video game', 'apply': True,
    }

    tracker.tick(0, window)

    assert len(events) == 1
    payload, persisted_count, persisted_category = events[0]
    assert persisted_count == 1
    assert persisted_category == 'browser_general'
    assert payload == {
        'process_name': 'Hades2.exe',
        'window_title': 'Hades II',
        'normalized_title': 'Hades II',
        'base_category': 'browser_general',
        'category_key': 'gaming',
        'certainty': 'high',
        'source': 'AI',
        'day': '2026-10-28',
    }


def test_cached_high_ai_event_is_emitted_once_on_first_tick(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    events = []
    tracker = SessionTracker(
        {'tracker': {'sample_interval_seconds': 1}}, Classifier(),
        on_ai_classification_applied=lambda payload: events.append(payload) or True,
    )
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {
        'category': 'gaming', 'certainty': 'high', 'reason': 'video game',
    }
    window = {'process_name': 'Hades2.exe', 'window_title': 'Hades II', 'pid': 2}

    tracker.tick(0, window)
    tracker.tick(0, window)

    assert len(events) == 1
    assert events[0]['category_key'] == 'gaming'


@pytest.mark.parametrize('certainty', ['medium', 'low', 'conflict'])
def test_non_high_ai_result_never_emits_rule_event(monkeypatch, certainty):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    events = []
    tracker = SessionTracker(
        {'tracker': {'sample_interval_seconds': 1}}, Classifier(),
        on_ai_classification_applied=lambda payload: events.append(payload) or True,
    )
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {
        'status': 'applied', 'source': 'AI', 'category': 'reading',
        'certainty': certainty, 'reason': 'evidence', 'apply': True,
    }

    tracker.tick(0, {'process_name': 'app.exe', 'window_title': 'Title', 'pid': 3})

    assert events == []


def test_high_confidence_video_category_applies_prospectively(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    tracker = SessionTracker({'tracker': {'sample_interval_seconds': 1}}, Classifier())
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {'category': 'video', 'certainty': 'high', 'reason': '电影'}
    snapshot = tracker.tick(0, {'process_name': 'chrome.exe', 'window_title': 'Film', 'pid': 1})
    assert snapshot['category_key'] == 'video'
    assert snapshot['classification_detail']['source'] == 'AI'
    assert snapshot['classification_detail']['suggested_category'] == 'video'


def test_high_confidence_gaming_category_applies_to_unknown_title(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    tracker = SessionTracker({'tracker': {'sample_interval_seconds': 1}}, Classifier())
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {'category': 'gaming', 'certainty': 'high', 'reason': '游戏'}

    snapshot = tracker.tick(0, {'process_name': 'unknown.exe', 'window_title': 'Game', 'pid': 2})

    assert snapshot['category_key'] == 'gaming'
    assert snapshot['classification_detail']['source'] == 'AI'


def test_shipped_config_accepts_high_confidence_ai_gaming(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    config_path = Path(__file__).parents[1] / 'config' / 'config.yaml'
    classifier = ConfigClassifier(str(config_path))
    tracker = SessionTracker({'tracker': {'sample_interval_seconds': 1}}, classifier)
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {
        'category': 'gaming', 'certainty': 'high', 'reason': 'Game executable',
    }

    snapshot = tracker.tick(
        0,
        {'process_name': 'LostCastle2.exe', 'window_title': 'LostCastle2', 'pid': 22},
    )

    assert classifier.categories['gaming']['active_rule'] == 'interactive_required'
    assert snapshot['category_key'] == 'gaming'
    assert snapshot['category_name'] == '游戏娱乐'
    assert snapshot['classification_detail']['source'] == 'AI'


def test_medium_confidence_result_stays_fallback_and_is_marked_for_confirmation(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    tracker = SessionTracker({'tracker': {'sample_interval_seconds': 1}}, Classifier())
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {
        'category': 'reading', 'certainty': 'medium', 'reason': '标题含义不充分',
    }

    snapshot = tracker.tick(0, {'process_name': 'chrome.exe', 'window_title': 'Research', 'pid': 3})

    assert snapshot['category_key'] == 'browser_general'
    assert snapshot['classification_detail']['source'] == 'AI待确认'
    assert snapshot['classification_detail']['suggested_category'] == 'reading'


def test_medium_result_with_confirmed_evidence_is_applied(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    tracker = SessionTracker({'tracker': {'sample_interval_seconds': 1}}, Classifier())
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {
        'status': 'applied', 'source': 'AI', 'category': 'reading',
        'suggested_category': 'reading', 'certainty': 'medium',
        'reason': '近期已确认课程标题', 'evidence': ['recent_confirmed'],
        'pattern_id': '', 'apply': True,
    }

    snapshot = tracker.tick(0, {'process_name': 'chrome.exe', 'window_title': '学习中心', 'pid': 3})

    assert snapshot['category_key'] == 'reading'
    assert snapshot['classification_detail']['source'] == 'AI'
    assert snapshot['classification_detail']['final_category'] == 'reading'
    assert snapshot['classification_detail']['evidence'] == ['recent_confirmed']


def test_manual_pattern_can_override_a_known_local_category(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    tracker = SessionTracker({'tracker': {'sample_interval_seconds': 1}}, Classifier())
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {
        'status': 'applied', 'source': '人工模式', 'category': 'reading',
        'suggested_category': 'reading', 'certainty': 'high',
        'reason': '命中用户确认的相似标题模式', 'evidence': ['manual_pattern'],
        'pattern_id': 'pattern-1', 'apply': True,
    }

    snapshot = tracker.tick(0, {'process_name': 'WINWORD.EXE', 'window_title': '课程笔记', 'pid': 7})

    assert snapshot['category_key'] == 'reading'
    assert snapshot['classification_detail']['source'] == '人工模式'
    assert snapshot['classification_detail']['pattern_id'] == 'pattern-1'


def test_pending_ai_result_is_visible_without_changing_fallback_category(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    tracker = SessionTracker({'tracker': {'sample_interval_seconds': 1}}, Classifier())
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {
        'status': 'pending', 'source': 'AI待识别',
        'category': '', 'certainty': '', 'reason': '',
    }

    snapshot = tracker.tick(0, {'process_name': 'chrome.exe', 'window_title': 'Unknown', 'pid': 4})

    assert snapshot['category_key'] == 'browser_general'
    assert snapshot['classification_detail']['source'] == 'AI待识别'


def test_high_confidence_fallback_ai_result_stays_unclassified(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    tracker = SessionTracker({'tracker': {'sample_interval_seconds': 1}}, Classifier())
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {
        'category': 'other', 'certainty': 'high', 'reason': '信息不足',
    }

    snapshot = tracker.tick(0, {'process_name': 'chrome.exe', 'window_title': 'Unknown', 'pid': 5})

    assert snapshot['category_key'] == 'browser_general'
    assert snapshot['classification_detail']['source'] == 'AI待确认'
    assert snapshot['classification_detail']['suggested_category'] == 'other'


def test_ai_classified_video_counts_only_detected_playback(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    audio = MutableAudio(playing=True)
    recorded = []
    tracker = SessionTracker(
        {'tracker': {
            'sample_interval_seconds': 1,
            'idle_threshold_seconds': 0,
            'entertainment_idle_threshold_seconds': 2,
            'min_session_seconds': 0,
        }},
        Classifier(),
        audio_detector=audio,
        on_session_end=lambda session: recorded.append(replace(session)),
    )
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {
        'category': 'video', 'certainty': 'high', 'reason': '影视播放',
    }
    window = {'process_name': 'chrome.exe', 'window_title': 'Film', 'pid': 5}

    for _ in range(3):
        tracker.tick(10, window)
    assert tracker.current_session.category_key == 'video'
    assert tracker.current_session.passive_seconds == 3

    audio.playing = False
    for _ in range(3):
        tracker.tick(10, window)

    assert len(recorded) == 1
    assert recorded[0].passive_seconds == 3
    assert recorded[0].idle_seconds == 0
    assert recorded[0].duration_seconds == 3
    assert recorded[0].duration_seconds == (
        recorded[0].engaged_seconds
        + recorded[0].passive_seconds
        + recorded[0].idle_seconds
    )
