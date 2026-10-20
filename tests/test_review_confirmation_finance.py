from pathlib import Path

from daylens.services.intelligence_evidence import ReviewQueue, load_patterns
from daylens.services.intelligence_scheduler import IntelligenceScheduler
from daylens.services.intelligence_state import DEFAULT_SETTINGS, save_settings
from daylens.classifier import Classifier
from daylens.utils import normalize_category_display_name, normalize_category_bucket_key
from daylens.services.dashboard_service import build_distribution_sections


def test_short_title_confirmation_applies_after_reload_without_broad_pattern(tmp_path):
    queue = ReviewQueue(tmp_path)
    queue.upsert({'id': 'legacy-id', 'app': 'lost_castle.exe', 'title': 'Lost_Castle',
                  'category': 'gaming', 'certainty': 'medium'})
    queue.resolve('legacy-id', 'gaming')
    assert ReviewQueue(tmp_path).items() == []
    assert load_patterns(tmp_path) == []
    scheduler = IntelligenceScheduler(tmp_path)
    decision = scheduler.observe('lost_castle.exe', 'Lost_Castle', 'other', 'new-rules')
    assert decision['category'] == 'gaming'
    assert decision['apply']
    assert scheduler.observe('lost_castle.exe', 'Another title', 'other', 'new-rules') is None


def test_private_short_title_confirmation_uses_original_local_identity(tmp_path):
    save_settings(tmp_path, dict(DEFAULT_SETTINGS, enabled=True))
    class Provider:
        def classify(self, rows):
            assert all('manual_id' not in row for row in rows)
            return {row['id']: {'category':'reading','certainty':'medium','reason':'文档'} for row in rows}
    scheduler = IntelligenceScheduler(tmp_path, provider=Provider())
    title = 'Document alice@example.com'
    for _ in range(6):
        scheduler.observe('chrome.exe', title, 'browser_general', 'v1', active_seconds=5)
    scheduler.process_pending(force=True)
    queue = ReviewQueue(tmp_path)
    review = queue.items()[0]
    assert 'alice@example.com' not in (tmp_path / 'classification_reviews.json').read_text(encoding='utf-8')
    queue.resolve(review['id'], 'reading')
    scheduler.reload()
    assert scheduler.observe('chrome.exe', title, 'browser_general', 'v2')['category'] == 'reading'
    other = scheduler.observe('chrome.exe', 'Document bob@example.com', 'browser_general', 'v2')
    assert not other or not other['apply']


def test_finance_rules_and_display_are_independent():
    classifier = Classifier(str(Path(__file__).parents[1] / 'config/config.yaml'))
    for process, title in [('hexin.exe','同花顺'), ('chrome.exe','股票 AI 助手')]:
        result = classifier.classify(process, title)
        assert result['category_key'] == 'finance'
        assert result['active_rule'] == 'interactive_required'
    assert normalize_category_display_name('finance') == '投资理财'
    assert normalize_category_bucket_key('finance') == 'finance'
    rows = build_distribution_sections({'by_category':[
        {'category_key':'finance','effective_seconds':300},
        {'category_key':'other','effective_seconds':60},
    ]}, 360)
    assert next(row for row in rows if row['category_key'] == 'finance')['seconds'] == 300
    assert sum(row['seconds'] for row in rows) == 360


def test_ai_finance_reaches_recorded_session(monkeypatch):
    from daylens.session_tracker import SessionTracker
    monkeypatch.setattr('daylens.session_tracker._get_cursor_pos', lambda: (0, 0))
    monkeypatch.setattr('daylens.session_tracker._get_keyboard_snapshot', lambda: bytes(256))
    classifier = Classifier(str(Path(__file__).parents[1] / 'config/config.yaml'))
    class Intelligence:
        def observe(self, *args, **kwargs):
            return {'category':'finance', 'certainty':'high', 'source':'AI', 'apply':True}
    tracker = SessionTracker({'tracker':{'sample_interval_seconds':1}}, classifier)
    tracker.intelligence = Intelligence()
    sample = tracker.tick(0, {'process_name':'unknown.exe','window_title':'Market desk','pid':1})
    assert sample['category_key'] == 'finance'


def test_accept_short_title_from_live_review_table(tmp_path, monkeypatch):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from daylens.gui.pages.live_monitor import LiveMonitorPage
    app = QApplication.instance() or QApplication([])
    queue = ReviewQueue(tmp_path)
    queue.upsert({'id':'short', 'app':'lost_castle.exe', 'title':'Lost_Castle',
                  'category':'gaming', 'certainty':'medium'})
    monkeypatch.setattr(LiveMonitorPage, '_review_directory', staticmethod(lambda: tmp_path))
    page = LiveMonitorPage()
    page.review_table.selectRow(0)
    signals = []
    page.classification_corrected.connect(lambda: signals.append(True))
    page.accept_review_button.click()
    assert page.review_table.rowCount() == 0
    assert signals == [True]
    assert '已确认' in page.correction_status.text()
