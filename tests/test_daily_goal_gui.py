from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QTableWidget
from types import SimpleNamespace
from datetime import date

from daylens.services.daily_goal_service import GoalStore


def test_goal_card_and_page_render_plan_input_and_missing_evidence(tmp_path):
    from daylens.gui.widgets.daily_goal_widgets import DailyGoalCard
    from daylens.gui.pages.daily_goals import DailyGoalsPage

    app = QApplication.instance() or QApplication([])
    card = DailyGoalCard()
    page = DailyGoalsPage(tmp_path)
    page.day_picker.setDate(QDate.fromString("2026-10-22", "yyyy-MM-dd"))
    model = {"day": "2026-10-22", "status": "ready", "revision": 1,
             "goals": [{"id": "g1", "type": "time_commitment", "title": "相机课程",
                        "target_kind": "category", "target_id": "reading",
                        "target_minutes": 90, "confirmed": False, "confirmed_at": None,
                        "actual_seconds": None, "difference_seconds": None,
                        "evidence_status": "insufficient_data"}]}
    card.set_model(model)
    page.set_model(model)
    assert "证据不足" in card.goal_labels[0].text()
    assert "相机课程" in page.goal_cards[0].title.fullText()
    assert page.goal_cards[0].title.toolTip() == "相机课程"
    assert "暂无可靠进度" in page.goal_cards[0].state.text()
    card.set_model({"day": "2026-10-22", "status": "unavailable", "goals": []})
    page.set_model({"day": "2026-10-22", "status": "unavailable", "goals": [],
                    "revision": 0})
    assert "不可用" in card.status.text()
    assert "不可读" in page.status.text()
    card.close()
    page.close()
    app.processEvents()


def test_goal_summary_explains_unconfirmed_task_and_untrusted_evidence():
    from daylens.gui.widgets.daily_goal_widgets import goal_summary

    goal = {"type": "time_commitment", "title": "课程", "target_minutes": 60,
            "actual_seconds": None, "difference_seconds": None,
            "evidence_status": "unconfirmed_task"}
    assert "任务未确认" in goal_summary(goal)
    assert "旧口径或异常" in goal_summary({**goal, "evidence_status": "untrusted"})


def test_goal_page_adds_time_and_outcome_then_confirms_only_outcome(tmp_path, monkeypatch):
    from daylens.gui.pages.daily_goals import DailyGoalsPage

    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    page.day_picker.setDate(QDate.fromString("2026-10-22", "yyyy-MM-dd"))
    page.set_model({"day": "2026-10-22", "status": "no_goals", "revision": 0,
                    "goals": []})
    monkeypatch.setattr(QInputDialog, "getItem", lambda *_args, **_kwargs:
                        ("工作学习", True))
    monkeypatch.setattr(QInputDialog, "getText", lambda *_args, **_kwargs:
                        ("相机驱动学习", True))
    monkeypatch.setattr(QInputDialog, "getInt", lambda *_args, **_kwargs:
                        (90, True))
    page._add_time()
    first = GoalStore(tmp_path).load()
    assert first["days"]["2026-10-22"][0]["target_minutes"] == 90
    page.set_model({"day": "2026-10-22", "status": "ready", "revision": 1,
                    "goals": first["days"]["2026-10-22"]})
    page._add_outcome()
    second = GoalStore(tmp_path).load()
    assert len(second["days"]["2026-10-22"]) == 2
    page.set_model({"day": "2026-10-22", "status": "ready", "revision": 2,
                    "goals": second["days"]["2026-10-22"]})
    page._toggle_outcome(second["days"]["2026-10-22"][1]["id"])
    final = GoalStore(tmp_path).load()
    assert final["days"]["2026-10-22"][1]["confirmed"] is True
    assert final["days"]["2026-10-22"][0]["confirmed"] is False
    page.close()
    app.processEvents()


def test_time_goal_offers_only_major_categories_and_uses_category_name(tmp_path, monkeypatch):
    from daylens.gui.pages.daily_goals import DailyGoalsPage

    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    page.day_picker.setDate(QDate.fromString("2026-10-22", "yyyy-MM-dd"))
    page.set_model({"day": "2026-10-22", "status": "no_goals", "revision": 0,
                    "goals": []})
    page.set_available_tasks({"day": "2026-10-22", "tasks": [
        {"id": "task-first", "name": "相机课程", "status": "confirmed"},
        {"id": "task-second", "name": "相机课程", "status": "confirmed"},
    ]})

    def choose(_self, _title, _label, options, *_args):
        assert options == ["工作学习", "娱乐休闲", "社交通讯", "投资理财", "浏览器", "系统工具", "其他"]
        return "工作学习", True

    monkeypatch.setattr(QInputDialog, "getItem", choose)
    monkeypatch.setattr(QInputDialog, "getText", lambda *_args, **_kwargs:
                        ("相机课程", True))
    monkeypatch.setattr(QInputDialog, "getInt", lambda *_args, **_kwargs:
                        (60, True))
    page._add_time()
    goal = GoalStore(tmp_path).load()["days"]["2026-10-22"][0]
    assert goal["target_id"] == "work"
    assert goal["title"] == "工作学习"
    assert goal["target_kind"] == "category"
    page.close()
    app.processEvents()


def test_changing_goal_date_clears_prior_day_task_targets(tmp_path):
    from daylens.gui.pages.daily_goals import DailyGoalsPage

    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    page.day_picker.setDate(QDate.fromString("2026-10-22", "yyyy-MM-dd"))
    page.set_available_tasks({"day": "2026-10-22", "tasks": [
        {"id": "old-task", "name": "旧任务", "status": "confirmed"}]})
    assert page.available_tasks
    page.day_picker.setDate(QDate.fromString("2026-10-23", "yyyy-MM-dd"))
    assert page.available_tasks == []
    page.close()
    app.processEvents()


def test_unavailable_goal_result_is_displayed_without_revision_retry(tmp_path, monkeypatch):
    from daylens.gui import main_window

    day = date.today().isoformat()
    GoalStore(tmp_path).save_day(day, [{"id": "g1", "type": "outcome",
                                       "title": "完成笔记", "target_kind": None,
                                       "target_id": None, "target_minutes": None,
                                       "confirmed": False, "confirmed_at": None}],
                                 expected_revision=0)
    seen = []
    goals = SimpleNamespace(selected_day=lambda: day,
                            set_model=lambda value: seen.append(value))
    fake = SimpleNamespace(paths=SimpleNamespace(intelligence_dir=tmp_path),
                           pages={"goals": goals})
    monkeypatch.setattr(main_window.QTimer, "singleShot", lambda *_args:
                        (_ for _ in ()).throw(AssertionError("unexpected reload")))
    model = {"day": day, "status": "unavailable", "revision": 0, "goals": []}
    main_window.MainWindow._on_background_task_completed(fake, f"goal:load:{day}", model)
    assert seen == [model]


def test_goal_workspace_empty_state_has_compact_creation_and_no_table(tmp_path):
    from daylens.gui.pages.daily_goals import DailyGoalsPage

    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    page.set_model({"day": page.selected_day(), "status": "no_goals",
                    "revision": 0, "goals": []})
    page.resize(1000, 650)
    page.show()
    app.processEvents()
    assert page.findChildren(QTableWidget) == []
    from daylens.gui import style as ui_style
    assert ui_style.COLORS["panel_bg"] in page.content.styleSheet()
    assert page.empty_state.isVisible()
    assert page.new_goal_button.isVisible()
    assert page.empty_time_button.isVisible()
    assert page.empty_outcome_button.isVisible()
    assert "0 / 3" in page.summary_count.text()
    assert page.empty_state.height() <= 360
    page.close()


def test_goal_workspace_cards_keep_actions_scoped_and_status_truthful(tmp_path, monkeypatch):
    from daylens.gui.pages.daily_goals import DailyGoalsPage

    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    day = page.selected_day()
    goals = [
        {"id": "time-1", "type": "time_commitment", "title": "学习 Camera",
         "target_kind": "category", "target_id": "reading", "target_minutes": 120,
         "actual_seconds": 4500, "difference_seconds": 2700,
         "evidence_status": "ready", "confirmed": False, "confirmed_at": None},
        {"id": "outcome-1", "type": "outcome", "title": "完成笔记",
         "target_kind": None, "target_id": None, "target_minutes": None,
         "confirmed": False, "confirmed_at": None},
    ]
    page.set_model({"day": day, "status": "ready", "revision": 0, "goals": goals})
    page.resize(1100, 700)
    page.show()
    app.processEvents()
    assert len(page.goal_cards) == 2
    assert not page.empty_state.isVisible()
    assert page.goal_cards[0].progress.isVisible()
    assert not page.goal_cards[0].confirm_button.isVisible()
    assert page.goal_cards[0].progress.value() == 62
    assert "62.5%" in page.goal_cards[0].state.text()
    assert not page.goal_cards[1].progress.isVisible()
    assert page.goal_cards[1].confirm_button.isVisible()
    from daylens.gui import style as ui_style
    assert ui_style.COLORS["panel_bg_alt"] in page.day_picker.styleSheet()
    assert ui_style.COLORS["panel_bg_alt"] in page.goal_cards[1].menu_button.styleSheet()
    assert ui_style.COLORS["panel_bg_alt"] in page.prev_button.styleSheet()
    assert ui_style.COLORS["panel_bg_alt"] in page.today_button.styleSheet()
    assert page.summary_count.text() == "2 / 3"
    assert page.summary_time.text() == "0"
    assert page.summary_outcomes.text() == "0"
    assert page.card_grid.itemAtPosition(0, 0).widget() is page.goal_cards[0]
    assert page.card_grid.itemAtPosition(0, 1).widget() is page.goal_cards[1]
    page.resize(620, 700)
    app.processEvents()
    assert page.card_grid.itemAtPosition(1, 0).widget() is page.goal_cards[1]
    page.close()


def test_goal_workspace_unavailable_is_not_empty_and_limit_disables_create(tmp_path):
    from daylens.gui.pages.daily_goals import DailyGoalsPage

    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    day = page.selected_day()
    page.set_model({"day": day, "status": "unavailable", "revision": 0, "goals": []})
    assert not page.empty_state.isVisible()
    assert not page.new_goal_button.isEnabled()
    assert "不可读" in page.status.text()
    three = [{"id": f"g{i}", "type": "outcome", "title": f"目标{i}",
              "target_kind": None, "target_id": None, "target_minutes": None,
              "confirmed": False, "confirmed_at": None} for i in range(3)]
    page.set_model({"day": day, "status": "ready", "revision": 1, "goals": three})
    assert len(page.goal_cards) == 3
    assert not page.new_goal_button.isEnabled()
    assert "最多" in page.new_goal_button.toolTip()
    page.close()


def test_goal_workspace_date_change_shows_loading_not_today_empty(tmp_path):
    from daylens.gui.pages.daily_goals import DailyGoalsPage

    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    page.day_picker.setDate(QDate.fromString("2026-10-20", "yyyy-MM-dd"))
    assert not page.empty_state.isVisible()
    assert "加载" in page.status.text()
    assert page.summary_count.text() == "— / 3"
    page.set_model({"day": "2026-10-20", "status": "no_goals",
                    "revision": 0, "goals": []})
    assert "2026" in page.empty_state.title.text()
    assert "今天" not in page.status.text()
    page.close()


def test_goal_card_menu_edits_and_deletes_only_its_own_id(tmp_path, monkeypatch):
    from daylens.gui.pages.daily_goals import DailyGoalsPage
    from PySide6.QtWidgets import QMessageBox

    app = QApplication.instance() or QApplication([])
    day = date.today().isoformat()
    items = [
        {"id": "keep", "type": "outcome", "title": "保留",
         "target_kind": None, "target_id": None, "target_minutes": None,
         "confirmed": False, "confirmed_at": None},
        {"id": "change", "type": "outcome", "title": "原名称",
         "target_kind": None, "target_id": None, "target_minutes": None,
         "confirmed": False, "confirmed_at": None},
    ]
    store = GoalStore(tmp_path)
    store.save_day(day, items, expected_revision=0)
    page = DailyGoalsPage(tmp_path)
    page.set_model({"day": day, "status": "ready", "revision": 1, "goals": items})
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_kw: ("新名称", True))
    page.goal_cards[1].menu_button.menu().actions()[0].trigger()
    changed = store.load()["days"][day]
    assert [goal["title"] for goal in changed] == ["保留", "新名称"]
    page.set_model({"day": day, "status": "ready", "revision": 2, "goals": changed})
    monkeypatch.setattr(QMessageBox, "exec", lambda *_a, **_kw: QMessageBox.Yes)
    page.goal_cards[1].menu_button.menu().actions()[1].trigger()
    remaining = store.load()["days"][day]
    assert [goal["id"] for goal in remaining] == ["keep"]
    page.close()
    app.processEvents()


def test_time_goal_over_target_keeps_true_ratio_while_bar_is_capped():
    from daylens.gui.widgets.goal_workspace_widgets import GoalTile

    app = QApplication.instance() or QApplication([])
    card = GoalTile({"id": "over", "type": "time_commitment", "title": "练习",
                     "target_kind": "category", "target_id": "coding",
                     "target_minutes": 60, "actual_seconds": 5400,
                     "evidence_status": "ready"})
    assert card.progress.value() == 100
    assert "150%" in card.state.text()
    card.close()
    app.processEvents()


def test_goal_refresh_reuses_card_and_preserves_focus(tmp_path):
    from daylens.gui.pages.daily_goals import DailyGoalsPage

    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    goal = {"id": "stable", "type": "time_commitment", "title": "课程",
            "target_kind": "category", "target_id": "reading", "target_minutes": 60,
            "actual_seconds": 600, "difference_seconds": 3000,
            "evidence_status": "ready", "confirmed": False, "confirmed_at": None}
    page.set_model({"day": page.selected_day(), "status": "ready",
                    "revision": 1, "goals": [goal]})
    page.show()
    app.processEvents()
    card = page.goal_cards[0]
    card.menu_button.setFocus()
    page.set_model({"day": page.selected_day(), "status": "ready",
                    "revision": 1, "goals": [{**goal, "actual_seconds": 900}]})
    app.processEvents()
    assert page.goal_cards[0] is card
    assert card.menu_button.hasFocus()
    assert "15" in card.state.text()
    page.close()


def test_goal_title_and_delete_confirmation_use_plain_text(tmp_path, monkeypatch):
    from daylens.gui.pages.daily_goals import DailyGoalsPage
    from PySide6.QtWidgets import QMessageBox

    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    goal = {"id": "literal", "type": "outcome", "title": "<b>报告</b>",
            "target_kind": None, "target_id": None, "target_minutes": None,
            "confirmed": False, "confirmed_at": None}
    page.set_model({"day": page.selected_day(), "status": "ready",
                    "revision": 0, "goals": [goal]})
    assert page.goal_cards[0].title.textFormat() == Qt.PlainText
    captured = []
    monkeypatch.setattr(QMessageBox, "exec", lambda dialog:
                        (captured.append((dialog.textFormat(), dialog.text())), QMessageBox.No)[1])
    page._delete("literal")
    assert captured == [(Qt.PlainText, "确定删除目标“<b>报告</b>”？")]
    page.close()
    app.processEvents()


def test_empty_create_buttons_disable_while_saving(tmp_path, monkeypatch):
    from daylens.gui.pages.daily_goals import DailyGoalsPage

    app = QApplication.instance() or QApplication([])
    page = DailyGoalsPage(tmp_path)
    page.set_model({"day": page.selected_day(), "status": "no_goals",
                    "revision": 0, "goals": []})
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_kw: ("成果", True))
    page._add_outcome()
    assert page._saving
    assert not page.empty_time_button.isEnabled()
    assert not page.empty_outcome_button.isEnabled()
    page.close()
    app.processEvents()
