from dataclasses import replace
from datetime import datetime, timedelta

from daylens.session_tracker import SessionTracker


class Classifier:
    classification_version = 'rules-base'
    categories = {'coding': {'display_name': '技术学习', 'active_rule': 'interactive_required'}}

    def classify(self, *_):
        return {'category_key': 'browser_general', 'category_name': '浏览器',
                'active_rule': 'interactive_required'}


class Intelligence:
    decision = None

    def observe(self, *args, **kwargs):
        return self.decision


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


def test_suggested_media_category_cannot_enable_passive_time(monkeypatch):
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    tracker = SessionTracker({'tracker': {'sample_interval_seconds': 1}}, Classifier())
    tracker.intelligence = Intelligence()
    tracker.intelligence.decision = {'category': 'video', 'certainty': 'high', 'reason': '电影'}
    snapshot = tracker.tick(0, {'process_name': 'chrome.exe', 'window_title': 'Film', 'pid': 1})
    assert snapshot['category_key'] == 'browser_general'
    assert snapshot['classification_detail']['suggested_category'] == 'video'
