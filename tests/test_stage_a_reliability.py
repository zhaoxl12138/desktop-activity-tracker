import os
import time
from datetime import date

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from daylens.services.intelligence_state import DEFAULT_SETTINGS, save_settings, save_override
from daylens.services.intelligence_scheduler import IntelligenceScheduler
from daylens.services.intelligence_evidence import (
    ReviewQueue, load_patterns, update_pattern_category, set_pattern_enabled,
)


class Provider:
    def __init__(self):
        self.calls = []
    def classify(self, rows):
        self.calls.append(rows)
        return {r['id']: {'category':'reading','certainty':'high','reason':'course'} for r in rows}


def test_legacy_exclusion_does_not_remove_redacted_recent_title(tmp_path):
    save_settings(tmp_path, dict(DEFAULT_SETTINGS, enabled=True, excluded_words=['PrivateProject']))
    provider = Provider()
    scheduler = IntelligenceScheduler(tmp_path, provider=provider)
    scheduler.observe('chrome.exe','PrivateProject planning alice@example.com','browser_general','v1', active_seconds=5)
    for _ in range(6):
        scheduler.observe('chrome.exe','HAL3 Request','browser_general','v1',active_seconds=5)
    scheduler.process_pending(force=True)
    assert provider.calls
    assert 'PrivateProject' in str(provider.calls)
    assert 'alice@example.com' not in str(provider.calls)


def test_disabling_ai_blocks_outbound_request(tmp_path):
    import pytest
    from daylens.services.intelligence_client import RequestDeferred

    save_settings(tmp_path, dict(DEFAULT_SETTINGS, enabled=True))
    provider = Provider()
    scheduler = IntelligenceScheduler(tmp_path, provider=provider)
    save_settings(tmp_path, dict(DEFAULT_SETTINGS, enabled=False))
    with pytest.raises(RequestDeferred):
        scheduler._outbound_boundary('classification', [{
            'id': 'one', 'app': 'chrome.exe', 'title': 'PrivateProject',
            'base_category': 'browser_general', 'active_seconds': 30,
        }])


def test_stale_pattern_hits_cannot_revert_manual_edit(tmp_path):
    save_override(tmp_path,'chrome.exe','学习中心 - 视频课程 - 自考公共课','reading')
    scheduler = IntelligenceScheduler(tmp_path, provider=Provider())
    scheduler.observe('chrome.exe','学习中心 - 视频课程 - 自考专业课','browser_general','v1')
    row = load_patterns(tmp_path)[0]
    update_pattern_category(tmp_path,row['id'],'video')
    scheduler._flush_patterns()
    current = load_patterns(tmp_path)[0]
    assert current['category'] == 'video'
    assert current['hit_count'] == 1


def test_ignored_review_cannot_be_restored_by_stale_writer(tmp_path):
    first = ReviewQueue(tmp_path)
    first.upsert({'id':'a','app':'chrome.exe','title':'Course','category':'reading'})
    stale = ReviewQueue(tmp_path)
    first.ignore('a')
    stale.upsert({'id':'b','app':'chrome.exe','title':'Course B','category':'reading'})
    stale.upsert({'id':'a','app':'chrome.exe','title':'Course','category':'reading'})
    assert [r['id'] for r in ReviewQueue(tmp_path).items()] == ['b']


def test_disabling_decision_also_disables_linked_exact_override(tmp_path):
    save_override(tmp_path,'chrome.exe','学习中心 - 视频课程','reading')
    set_pattern_enabled(tmp_path,load_patterns(tmp_path)[0]['id'],False)
    scheduler = IntelligenceScheduler(tmp_path, provider=Provider())
    assert scheduler.observe('chrome.exe','学习中心 - 视频课程','browser_general','v1') is None


def test_selected_sample_does_not_drift_after_live_insert(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from daylens.gui.pages.live_monitor import LiveMonitorPage, ClassificationDialog
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(LiveMonitorPage,'_review_directory',staticmethod(lambda:tmp_path))
    page = LiveMonitorPage()
    for title in ('selected','newer'):
        page.on_sample_updated({'process_name':'chrome.exe','window_title':title})
    page.table.selectRow(1)
    page.on_sample_updated({'process_name':'chrome.exe','window_title':'newest'})
    captured = []
    monkeypatch.setattr(ClassificationDialog,'exec',lambda self:captured.append(self.title_label.text()) or 0)
    page._correct_current()
    assert captured == ['selected']


def test_slow_dashboard_still_publishes_results():
    from PySide6.QtWidgets import QApplication
    from daylens.gui.dashboard_refresh_controller import DashboardRefreshController
    app = QApplication.instance() or QApplication([])
    calls = 0
    def load():
        nonlocal calls
        calls += 1
        time.sleep(.04)
        return {'ok':True}
    controller = DashboardRefreshController(load, interval_ms=10)
    received = []
    controller.snapshot_ready.connect(received.append)
    controller.set_foreground(True)
    until = time.monotonic()+.3
    while time.monotonic()<until:
        app.processEvents()
        time.sleep(.003)
    controller.shutdown(1000)
    assert calls >= 2
    assert len(received) == 1


def test_old_summary_cannot_cross_changed_privacy_boundary(tmp_path):
    from daylens.services.intelligence_reviews import IntelligenceReviews
    from daylens.services.intelligence_state import atomic_json
    reviews = IntelligenceReviews(tmp_path, Provider(), privacy_settings=dict(DEFAULT_SETTINGS))
    atomic_json(reviews.path('daily', date(2026,10,19)), {
        'status':'ready','topics':[{'name':'Private project'}], 'observations':[{'text':'Private'}]})
    assert reviews.compressed_facts('weekly', date(2026,10,19)) == []


def test_safe_release_never_forces_a_running_process(monkeypatch):
    import importlib.util
    from pathlib import Path
    import pytest
    spec = importlib.util.spec_from_file_location('release_a', Path(__file__).parents[1]/'tools/build_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_running_daylens_pids', lambda:[123])
    calls = []
    def fail(*args, **kwargs):
        calls.append(args[0])
        raise RuntimeError('maintenance failed')
    monkeypatch.setattr(module.subprocess, 'run', fail)
    with pytest.raises(RuntimeError):
        module._stop_running_gracefully()
    assert calls and all('taskkill' not in str(call) for call in calls)


def test_state_transaction_recovers_interrupted_multifile_commit(tmp_path, monkeypatch):
    import pytest
    from daylens.services import classification_state_service as module
    from daylens.services.intelligence_state import load_overrides
    original = module._raw_write
    def fail_on_patterns(path, value):
        if path.name == 'title_patterns.json':
            raise OSError('synthetic disk interruption')
        return original(path, value)
    monkeypatch.setattr(module, '_raw_write', fail_on_patterns)
    with pytest.raises(OSError):
        save_override(tmp_path,'chrome.exe','学习中心 视频课程','reading')
    assert (tmp_path/'classification-transaction.json').exists()
    monkeypatch.setattr(module, '_raw_write', original)
    assert load_patterns(tmp_path)[0]['category'] == 'reading'
    assert next(iter(load_overrides(tmp_path).values()))['category'] == 'reading'
    assert not (tmp_path/'classification-transaction.json').exists()
    assert module.state_revision(tmp_path) == 1


def test_concurrent_decisions_do_not_drop_other_titles(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from daylens.services.intelligence_state import load_overrides
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i:save_override(tmp_path,'chrome.exe',f'Title {i}','reading'), range(20)))
    assert len(load_overrides(tmp_path)) == 20


def test_saved_and_applied_are_distinct_ui_states(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from daylens.gui.pages.live_monitor import LiveMonitorPage
    from daylens.services.classification_state_service import state_revision
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(LiveMonitorPage,'_review_directory',staticmethod(lambda:tmp_path))
    page = LiveMonitorPage()
    save_override(tmp_path,'chrome.exe','Course','reading')
    page._decision_saved('已确认')
    assert '等待应用' in page.correction_status.text()
    page.on_classification_applied(state_revision(tmp_path)-1)
    assert '等待应用' in page.correction_status.text()
    page.on_classification_applied(state_revision(tmp_path))
    assert '已对后续记录生效' in page.correction_status.text()


def test_context_change_discards_old_dashboard_result():
    import threading
    from PySide6.QtWidgets import QApplication
    from daylens.gui.dashboard_refresh_controller import DashboardRefreshController
    app = QApplication.instance() or QApplication([])
    release = threading.Event()
    calls = []
    def loader():
        calls.append(1)
        if len(calls) == 1:
            release.wait(1)
            return {'context':'old'}
        return {'context':'new'}
    controller = DashboardRefreshController(loader,interval_ms=60000)
    result = []
    controller.snapshot_ready.connect(result.append)
    controller.set_foreground(True)
    controller.invalidate_context()
    release.set()
    until = time.monotonic()+1
    while not result and time.monotonic()<until:
        app.processEvents()
        time.sleep(.003)
    controller.shutdown(1000)
    assert [r.payload for r in result] == [{'context':'new'}]


def test_cross_process_writers_share_the_state_lock(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    from daylens.services.intelligence_state import load_overrides
    program = ('import sys; from daylens.services.intelligence_state import save_override; '
               '[save_override(sys.argv[1],sys.argv[2],str(i),"reading") for i in range(10)]')
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1]/'src'))
    children = [subprocess.Popen([sys.executable,'-c',program,str(tmp_path),app],env=env)
                for app in ('first.exe','second.exe')]
    try:
        assert all(child.wait(timeout=15)==0 for child in children)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
    assert len(load_overrides(tmp_path)) == 20
