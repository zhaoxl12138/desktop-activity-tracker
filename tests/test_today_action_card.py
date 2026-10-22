"""The homepage keeps goals and tasks legible without two tall cards."""

from PySide6.QtWidgets import QApplication, QBoxLayout


def _app():
    return QApplication.instance() or QApplication([])


def test_action_card_shows_only_first_goal_and_task_with_full_title_tooltips():
    from daylens.gui.widgets.today_action_card import TodayActionCard

    app = _app()
    card = TodayActionCard()
    card.resize(1000, 140)
    card.show()
    card.set_goal_model({"status": "ready", "goals": [
        {"title": "相机课程", "type": "time_commitment", "target_minutes": 60,
         "actual_seconds": 1200, "difference_seconds": 2400,
         "evidence_status": "ready"},
        {"title": "不应出现在首页的第二目标", "type": "outcome", "confirmed": False},
    ]})
    card.set_task_model({"status": "ready", "tasks": [
        {"name": "相机驱动学习", "status": "confirmed", "engaged_seconds": 1200},
        {"name": "不应出现在首页的第二任务", "status": "candidate", "engaged_seconds": 600},
    ]})
    app.processEvents()
    assert card.title.text() == "今日行动"
    assert "相机课程" in card.goal_summary.fullText()
    assert "不应出现在首页" not in card.goal_summary.fullText()
    assert card.goal_summary.toolTip() == card.goal_summary.fullText()
    assert "相机驱动学习" in card.task_summary.fullText()
    assert "不应出现在首页" not in card.task_summary.fullText()
    assert card.task_summary.toolTip() == card.task_summary.fullText()
    assert card.goal_summary.maxLines() == card.task_summary.maxLines() == 1
    card.close()


def test_action_card_keeps_error_states_independent_and_never_infers_completion():
    from daylens.gui.widgets.today_action_card import TodayActionCard

    _app()
    card = TodayActionCard()
    card.set_goal_model({"status": "unavailable", "goals": []})
    card.set_task_model({"status": "disabled", "tasks": []})
    assert card.goal_status.text() == "暂不可用"
    assert "暂不可读" in card.goal_summary.fullText()
    assert card.task_status.text() == "未开启"
    assert "开启本地任务分析" in card.task_summary.fullText()
    card.set_goal_model({"status": "ready", "goals": [
        {"title": "完成笔记", "type": "outcome", "confirmed": False}
    ]})
    card.set_task_model({"status": "unavailable", "tasks": []})
    assert "等待用户确认" in card.goal_summary.fullText()
    assert card.task_status.text() == "暂不可用"
    assert "暂不可读" in card.task_summary.fullText()
    card.close()


def test_action_card_routes_sections_separately_and_stacks_on_narrow_width():
    from daylens.gui.widgets.today_action_card import TodayActionCard

    _app()
    card = TodayActionCard()
    events = []
    card.goals_requested.connect(lambda: events.append("goals"))
    card.tasks_requested.connect(lambda: events.append("tasks"))
    card.goal_button.click()
    card.task_button.click()
    assert events == ["goals", "tasks"]
    assert card.sections_layout.direction() == QBoxLayout.LeftToRight
    card.set_compact(True)
    assert card.sections_layout.direction() == QBoxLayout.TopToBottom
    card.set_compact(False)
    assert card.sections_layout.direction() == QBoxLayout.LeftToRight
    card.close()


def test_today_overview_omits_action_card_without_leaving_a_grid_row(tmp_path):
    from daylens.gui.pages.today_overview import TodayOverviewPage

    _app()
    page = TodayOverviewPage(str(tmp_path / "usage.db"))
    page.set_content_width(1200)
    assert not hasattr(page, "action_card")
    assert page._card_grid.itemAtPosition(3, 0) is None
    assert not hasattr(page, "task_insight_card")
    assert not hasattr(page, "daily_goal_card")
    page.set_content_width(800)
    assert page._card_grid.count() == 5
    assert page._card_grid.itemAtPosition(4, 0).widget() is page.top_app_card
    assert page._card_grid.itemAtPosition(5, 0) is None
    page.close()
