import pytest


def test_category_consumers_share_registry():
    from daylens.category_registry import category_definitions, category_choices
    from daylens.services.intelligence_client import LEGAL_CATEGORIES
    from daylens.gui.widgets.classification_dialog import CATEGORY_CHOICES
    definitions = category_definitions()
    assert LEGAL_CATEGORIES == {d.id for d in definitions if d.ai_allowed}
    assert CATEGORY_CHOICES == category_choices()
    assert next(d for d in definitions if d.id == 'finance').group == 'finance'


def test_custom_category_manual_only_and_restricted_policy():
    from daylens.category_registry import category_definitions
    config = {'research': {'display_name':'研究', 'active_rule':'interactive_required'}}
    custom = next(d for d in category_definitions(config) if d.id == 'research')
    assert custom.manual_allowed and not custom.ai_allowed
    with pytest.raises(ValueError):
        category_definitions({'research': {'active_rule':'arbitrary'}})


def test_exact_only_and_undo_preserve_unrelated_decisions(tmp_path):
    from daylens.services.classification_decisions import undo_last, set_decision_enabled
    from daylens.services.intelligence_state import save_override, load_overrides
    from daylens.services.intelligence_evidence import load_patterns
    save_override(tmp_path, 'chrome.exe', '学习中心 视频课程 公共知识', 'reading', scope='exact')
    first = next(iter(load_overrides(tmp_path)))
    save_override(tmp_path, 'hexin.exe', '同花顺', 'finance', scope='exact')
    assert not load_patterns(tmp_path)
    set_decision_enabled(tmp_path, first, False)
    assert not load_overrides(tmp_path)[first]['enabled']
    assert undo_last(tmp_path)
    assert load_overrides(tmp_path)[first].get('enabled', True)
    assert len(load_overrides(tmp_path)) == 2


def test_paths_share_one_data_root_and_report_split_without_moving(tmp_path):
    from daylens.app_paths import AppPaths
    canonical = tmp_path / 'data'
    other = tmp_path / 'old-state'
    (other / 'intelligence').mkdir(parents=True)
    (other / 'intelligence/settings.json').write_text('{}')
    paths = AppPaths.from_database(canonical/'usage.db', program_dir=tmp_path)
    assert paths.intelligence_dir == canonical/'intelligence'
    assert paths.reports_dir == canonical/'reports'
    with pytest.raises(ValueError, match='分散'):
        paths.check_state_locations([other/'intelligence'])
    assert not canonical.exists()


def test_time_definition_conservation_and_unknown_gap():
    from daylens.time_model import TimeBreakdown
    value = TimeBreakdown(600, 120, 30)
    assert value.effective_seconds == 720
    assert value.observed_seconds == 750
    assert value.gap_label == '未知'
    assert '有效活动' in value.description


def test_same_category_confirmation_is_applied_not_pending():
    from daylens.classification_result import classification_result
    result = classification_result('reading', 'reading', 'interactive_required',
        {'category':'reading', 'source':'手动', 'certainty':'high', 'apply':True},
        revision=7, captured_at='2026-10-20 10:00:00', application_type='browser')
    assert result['source'] == '手动'
    assert result['final_category'] == 'reading'
    assert result['decision_revision'] == 7
    assert result['timing_policy_id'] == 'interactive_required'
    assert result['effective_at'] == '2026-10-20 10:00:00'


def test_management_tabs_and_explicit_correction_scope(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    from daylens.gui.pages.classification_management import ClassificationManagementPage
    from daylens.gui.pages.live_monitor import LiveMonitorPage
    from daylens.gui.widgets.classification_dialog import ClassificationDialog
    monkeypatch.setattr(LiveMonitorPage, '_review_directory', staticmethod(lambda:tmp_path))
    live = LiveMonitorPage()
    live._review_directory = lambda: tmp_path
    rules = __import__('PySide6.QtWidgets', fromlist=['QWidget']).QWidget()
    page = ClassificationManagementPage(live, rules)
    assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == ['待确认','人工纠错','本地规则']
    assert '当天' in page.manual_hint.text()
    assert '仅对后续记录生效' not in page.manual_hint.text()
    dialog = ClassificationDialog(app_name='chrome.exe',title='课程',current_category='reading')
    assert dialog.scope_combo.count() == 2
    assert dialog.selected_scope() in {'exact','similar'}
    page.close()
    live.close()


def test_undo_refuses_untracked_newer_change(tmp_path):
    from daylens.services.classification_decisions import undo_last
    from daylens.services.intelligence_state import save_override
    from daylens.services.classification_state_service import read_state, write_state
    save_override(tmp_path, 'app.exe', 'Public knowledge', 'reading', scope='exact')
    rows = read_state(tmp_path, 'manual_decisions.json', {})
    rows[next(iter(rows))]['category'] = 'finance'
    write_state(tmp_path, 'manual_decisions.json', rows)
    with pytest.raises(ValueError, match='其他操作'):
        undo_last(tmp_path)


def test_distribution_covers_all_effective_time_without_relabeling_hidden():
    from daylens.services.dashboard_service import build_distribution_model
    stats = {'by_category':[
        {'category_key':'reading','effective_seconds':600},
        {'category_key':'video','effective_seconds':120},
        {'category_key':'tools','effective_seconds':100},
        {'category_key':'browser_general','effective_seconds':80},
        {'category_key':'other','effective_seconds':20},
    ]}
    model = build_distribution_model(stats,920)
    assert sum(row['seconds'] for row in model['all']) == 920
    assert model['visible'][-1]['category_key'] == 'tools'
    assert model['visible'][-1]['seconds'] == 100
    assert model['hidden_seconds'] == 100
    assert model['hidden_count'] == 2


def test_custom_category_correction_survives_reload(tmp_path):
    from daylens.services.intelligence_state import save_override, load_overrides
    config = {'research':{'display_name':'研究','active_rule':'interactive_required'}}
    save_override(tmp_path,'app.exe','公共项目 资料研究','research',scope='exact',categories=config)
    assert next(iter(load_overrides(tmp_path).values()))['category'] == 'research'


def test_home_donut_uses_effective_category_segments(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from daylens.gui.pages.today_overview import TodayOverviewPage
    page = TodayOverviewPage(str(tmp_path/'usage.db'))
    page._apply_snapshot({'today':'2026-10-20','totals':{
        'effective_seconds':720,'engaged_seconds':600,'passive_seconds':120,'idle_seconds':30},
        'distribution_sections':[{'category_key':'work','label':'工作学习','seconds':600},
                                 {'category_key':'video','label':'娱乐休闲','seconds':120}]})
    assert page.donut_widget._total_seconds == 720
    assert page.donut_widget._primary_label == '有效活动'
    assert [row[1] for row in page.donut_widget._segments] == [600,120]
    assert '主动参与' in page.active_status_label.text()
    page.close()


def test_review_exact_scope_can_be_undone_after_private_identity_mapping(tmp_path):
    from daylens.services.intelligence_evidence import ReviewQueue, load_patterns
    from daylens.services.intelligence_state import title_context, DEFAULT_SETTINGS, load_overrides
    from daylens.services.classification_decisions import undo_last
    context = title_context('chrome.exe','课程 Public topic 123456789',dict(DEFAULT_SETTINGS),'rules-v3')
    context['manual_id'] = title_context('chrome.exe','课程 Public topic 123456789',dict(DEFAULT_SETTINGS),'manual-v1')['id']
    context.update(suggested_category='reading',certainty='medium',reason='course')
    queue = ReviewQueue(tmp_path)
    queue.upsert(context)
    queue.resolve(context['id'],'reading',scope='exact')
    assert list(load_overrides(tmp_path)) == [context['manual_id']]
    assert not load_patterns(tmp_path)
    assert undo_last(tmp_path)
    assert not load_overrides(tmp_path)


def test_exact_hits_increment_without_overwriting_enabled_state(tmp_path):
    from daylens.services.intelligence_scheduler import IntelligenceScheduler
    from daylens.services.intelligence_state import save_override, load_overrides
    from daylens.services.classification_decisions import set_decision_enabled
    save_override(tmp_path,'chrome.exe','Public project learning','reading',scope='exact')
    scheduler = IntelligenceScheduler(tmp_path,provider=object())
    scheduler.observe('chrome.exe','Public project learning','browser_general','v1')
    identity = next(iter(load_overrides(tmp_path)))
    set_decision_enabled(tmp_path,identity,False)
    scheduler._flush_patterns()
    row = load_overrides(tmp_path)[identity]
    assert row['hit_count'] == 1
    assert not row['enabled']


def test_undo_keeps_exact_hit_counts_accumulated_after_user_command(tmp_path):
    from daylens.services.intelligence_state import save_override, load_overrides
    from daylens.services.classification_decisions import set_decision_enabled, undo_last
    from daylens.services.classification_state_service import ClassificationStateService
    save_override(tmp_path,'app.exe','Public project','reading',scope='exact')
    identity = next(iter(load_overrides(tmp_path)))
    set_decision_enabled(tmp_path,identity,False)
    ClassificationStateService(tmp_path).add_hits({'manual:'+identity:{'count':5,'last_used_at':'2026-10-20T18:00:00'}})
    undo_last(tmp_path)
    row = load_overrides(tmp_path)[identity]
    assert row['enabled'] and row['hit_count'] == 5


def test_management_worker_replacement_reaches_existing_rule_editor(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QWidget
    app = QApplication.instance() or QApplication([])
    from daylens.gui.pages.live_monitor import LiveMonitorPage
    from daylens.gui.pages.classification_management import ClassificationManagementPage
    monkeypatch.setattr(LiveMonitorPage,'_review_directory',staticmethod(lambda:tmp_path))
    live = LiveMonitorPage()
    rules = QWidget()
    rules.worker = object()
    page = ClassificationManagementPage(live,rules)
    replacement = object()
    page.worker = replacement
    assert rules.worker is replacement
    page.close()
    live.close()
