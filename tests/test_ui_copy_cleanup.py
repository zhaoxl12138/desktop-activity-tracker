"""Presentation cleanup must not remove live data or actionable feedback."""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication, QLabel


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    from daylens.services import intelligence_credentials
    monkeypatch.setattr(intelligence_credentials, 'read_key', lambda: None)


def texts(widget):
    return [label.text() for label in widget.findChildren(QLabel)
            if label.isVisibleTo(widget)]


def test_report_schedule_explanation_moves_off_page_but_generation_feedback_remains(tmp_path, monkeypatch):
    from daylens.gui.pages.reports import ReportsPage
    from daylens.services import intelligence_report_schedule
    monkeypatch.setattr(intelligence_report_schedule, 'schedule_status',
                        lambda *_: '额度不足 · 待补 9 份（不重复请求）')
    app = QApplication.instance() or QApplication([])
    page = ReportsPage(str(tmp_path/'usage.db'), str(tmp_path/'reports'))
    try:
        page.resize(1200, 680)
        page.show(); page.refresh(); app.processEvents()
        assert page.automation_status.isHidden()
        assert '待补' in page.btn_daily.toolTip()
        assert '生成、查看和导出你的时间报告。' not in texts(page)
        assert '当前选中' not in texts(page)
        page._set_operation_status('日报已生成', temporary=True)
        assert page._status_timer.isActive()
        page._generation_jobs['failed'] = '日报'
        page._generation_failed('failed', '网络错误')
        assert not page._status_timer.isActive()
        assert page.automation_status.isVisibleTo(page)
        assert '生成失败' in page.automation_status.text()
        page.refresh()
        assert page.automation_status.isVisibleTo(page)
        assert '生成失败' in page.automation_status.text()
    finally:
        page.close()


def test_settings_explanations_move_to_controls_and_values_remain(tmp_path, monkeypatch):
    from tests.test_settings_page import _build_page
    app, page, _worker, _db = _build_page(tmp_path, monkeypatch)
    try:
        labels = [label.text() for label in page.findChildren(QLabel)]
        assert '调整采样频率、空闲判定和数据输出路径。' not in labels
        assert '启用后 DayLens 将随系统自动启动并最小化到托盘。' not in labels
        assert '托盘' in page.chk_startup.toolTip()
        assert '被动' in page.spin_weekday_entertainment.toolTip()
        assert page.spin_weekday_entertainment.value() == 60
        assert page.monthly_ai_cost.text()
    finally:
        page.close(); app.processEvents()


@pytest.mark.parametrize('failure_first', [False, True])
def test_multiple_report_jobs_keep_pending_and_failed_feedback(tmp_path, monkeypatch, failure_first):
    from daylens.gui.pages.reports import ReportsPage
    app = QApplication.instance() or QApplication([])
    page = ReportsPage(str(tmp_path/'usage.db'), str(tmp_path/'reports'))
    # Deliver completion signals deterministically instead of running exporters.
    monkeypatch.setattr(page.background_tasks, 'submit', lambda *_args: True)
    try:
        page.show(); app.processEvents()
        page._generate(lambda *_a: None, '日报')
        page._generate(lambda *_a: None, '周报')
        daily, weekly = tuple(page._generation_jobs)
        if failure_first:
            page._generation_failed(daily, '测试失败')
        else:
            page._generation_completed(daily, str(tmp_path/'absent.md'))
        assert weekly in page._generation_jobs
        assert '周报' in page.automation_status.text()
        assert '生成' in page.automation_status.text()
        assert not page._status_timer.isActive()
        if failure_first:
            page._generation_completed(weekly, str(tmp_path/'absent-weekly.md'))
        else:
            page._generation_failed(weekly, '测试失败')
        assert '失败' in page.automation_status.text()
        assert page.automation_status.isVisibleTo(page)
        assert not page._status_timer.isActive()
    finally:
        page.close()


def test_ai_settings_use_short_controls_with_privacy_and_limits_in_tooltips(tmp_path):
    from daylens.gui.widgets.intelligence_settings import IntelligenceSettings
    app = QApplication.instance() or QApplication([])
    card = IntelligenceSettings(directory=tmp_path)
    try:
        assert card.enabled.text() == '启用智能增强'
        assert '脱敏' in card.enabled.toolTip()
        assert card.classification.text() == '智能分类'
        assert '30' in card.classification.toolTip()
        assert '23:00' in card.reports.toolTip()
        assert not any('Flash非思考模式' in value for value in texts(card))
        assert '未配置' in card.key_state.text()
        assert card.usage.text()
        assert card.status.isHidden()
        card._test()
        assert not card.status.isHidden()
        assert '密钥' in card.status.text()
    finally:
        card.close(); app.processEvents()


def test_rule_explanations_use_tooltips_without_info_bar(tmp_path):
    from tests.test_rule_config_page import _build_page, _select_category
    page = _build_page(tmp_path)
    try:
        _select_category(page, 'coding')
        assert not hasattr(page, 'match_hint_frame')
        assert '已有标题' in page.applications_list.toolTip()
        assert '2 个应用' in page.application_heading.text()
        assert '选择分类后可编辑规则。' not in texts(page)
        assert page.btn_save.isVisibleTo(page)
    finally:
        page.close()


def test_ready_goal_page_has_no_redundant_explanation_but_unavailable_is_visible(tmp_path):
    from daylens.gui.pages.daily_goals import DailyGoalsPage
    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    try:
        page.set_model({'day': page.selected_day(), 'status':'ready', 'revision':0, 'goals':[]})
        assert page.status.isHidden()
        assert not any('管理每天' in text or '例如：学习' in text for text in texts(page))
        assert page.empty_state.title.text()
        page.set_model({'day': page.selected_day(), 'status':'unavailable', 'revision':0, 'goals':[]})
        assert not page.status.isHidden()
        assert '不可读' in page.status.text()
    finally:
        page.close(); app.processEvents()


def test_application_dialog_only_displays_notice_for_validation_errors():
    from daylens.gui.widgets.rule_application_dialog import RuleApplicationDialog
    app = QApplication.instance() or QApplication([])
    dialog = RuleApplicationDialog([])
    try:
        assert dialog.notice.isHidden()
        assert '草稿' in dialog.toolTip()
        dialog.accept()
        assert not dialog.notice.isHidden()
        assert '选择应用' in dialog.notice.text()
    finally:
        dialog.close(); app.processEvents()


def test_timeline_ticks_fit_after_removing_footer_at_large_font():
    from PySide6.QtGui import QFont
    from daylens.gui.widgets.day_activity_category_timeline import DayActivityCategoryTimeline
    app = QApplication.instance() or QApplication([])
    timeline = DayActivityCategoryTimeline()
    try:
        timeline.setFont(QFont('Microsoft YaHei', 32))
        timeline.resize(1200, timeline.minimumHeight())
        app.processEvents()
        for _second, rect, _label in timeline.hour_labels():
            assert rect.bottom() <= timeline.height()
    finally:
        timeline.close()


def test_shell_keeps_today_date_without_repeating_page_descriptions():
    from tests.test_stage_c_shell import _window
    app, window = _window()
    try:
        window.navigate_to('today'); app.processEvents()
        assert window.lbl_today.isVisibleTo(window)
        assert '年' in window.lbl_today.text()
        for key in ('reports','settings','rules','stats'):
            window.navigate_to(key); app.processEvents()
            assert not window.lbl_today.isVisibleTo(window)
        assert window.sidebar_record_status.text()
    finally:
        window.close(); app.processEvents()


def test_activity_help_moves_to_timeline_tooltip_without_losing_events(tmp_path):
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog
    from tests.test_day_activity_gui import DAYS, model, wait_for
    app = QApplication.instance() or QApplication([])
    dialog = DayActivityDialog(str(tmp_path/'usage.db'), DAYS[-1], DAYS,
                               loader=lambda *_a, **_k: model())
    try:
        dialog.show()
        wait_for(app, lambda: dialog.model.get('status') == 'ready')
        assert dialog.help_label.isHidden()
        assert '前台' in dialog.timeline.toolTip()
        assert dialog.summary_label.text()
        assert dialog.events_model.rowCount() == 1
    finally:
        dialog.close(); app.processEvents()
