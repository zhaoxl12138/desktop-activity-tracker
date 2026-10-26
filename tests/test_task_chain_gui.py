from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QInputDialog

from daylens.gui.widgets.task_insight_widgets import TaskInsightCard
from daylens.gui.pages.task_chain_detail import TaskChainPage
from daylens.services.task_decision_service import TaskDecisionStore


MODEL = {
    "day": "2026-10-21", "status": "ready", "revision": 0,
    "tasks": [{"id": "task-a", "name": "相机任务", "engaged_seconds": 120,
               "status": "confirmed", "source_session_ids": ["s1", "s2"]}],
    "transitions": [{"event_type": "non_work_interruption",
                     "source_task_id": "task-a", "returned_to_source_task": "yes",
                     "interruption_session_ids": ["v"]}],
    "evidence": {"s1": {"app": "code.exe", "title": "Camera", "start_time": "09:00",
                        "end_time": "09:01", "engaged_seconds": 60},
                 "s2": {"app": "chrome.exe", "title": "Camera docs", "start_time": "09:01",
                        "end_time": "09:02", "engaged_seconds": 60},
                 "v": {"app": "player.exe", "title": "Film", "start_time": "09:01",
                       "end_time": "09:01:30", "engaged_seconds": 0}},
}


def test_task_card_and_detail_show_evidence_and_separate_task_event_label(tmp_path):
    app = QApplication.instance() or QApplication([])
    card = TaskInsightCard()
    detail = TaskChainPage(tmp_path)
    card.set_model(MODEL)
    detail.set_model(MODEL)
    assert "相机任务" in card.task_labels[0].text()
    assert "插入" in card.observation.text()
    assert detail.tasks_table.rowCount() == 1
    assert detail.evidence_list.count() == 2
    assert "player.exe" in detail.events_list.item(0).text()
    card.set_model({**MODEL, "cloud_enabled": True})
    assert card.status.text() == "AI 已开启"
    card.close()
    detail.close()
    app.processEvents()


def test_task_page_confirm_button_persists_selected_task_without_db_write(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    page = TaskChainPage(tmp_path)
    page.day_picker.setDate(QDate.fromString(MODEL["day"], "yyyy-MM-dd"))
    model = {**MODEL, "tasks": [{**MODEL["tasks"][0], "status": "needs_confirmation",
                                  "name": "相机课程", "name_source": "local_default"}]}
    page.set_model(model)
    monkeypatch.setattr(
        QInputDialog, "getText",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("确认默认名称时不应再要求用户输入")
        ),
    )
    refreshed = []
    page.refresh_requested.connect(refreshed.append)
    page._action("confirm")
    state = TaskDecisionStore(tmp_path).load()
    assert state["assignments"] == {"s1": "task-a", "s2": "task-a"}
    assert state["names"]["task-a"] == "相机课程"
    assert page.model["revision"] == 1
    assert page.model["tasks"][0]["status"] == "confirmed"
    assert page.tasks_table.item(0, 2).text() == "已确认"
    assert refreshed == ["2026-10-21"]
    page.close()
    app.processEvents()


def test_grouped_topic_has_one_click_merge_and_confirm(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = TaskChainPage(tmp_path)
    page.day_picker.setDate(QDate.fromString(MODEL["day"], "yyyy-MM-dd"))
    task = {**MODEL["tasks"][0], "id": "topic-a", "status": "needs_confirmation",
            "review_status": "auto_identified",
            "source_candidate_ids": ["first", "second"]}
    page.set_model({**MODEL, "tasks": [task]})
    assert page.action_buttons["confirm"].text() == "固定此任务（可选）"
    assert page.tasks_table.item(0, 2).text() == "自动识别"
    card = TaskInsightCard()
    card.set_model({**MODEL, "tasks": [task], "transitions": []})
    assert "自动识别" in card.task_labels[0].text()
    assert "无需确认" in card.observation.text()
    card.close()
    page.action_buttons["confirm"].click()
    state = TaskDecisionStore(tmp_path).load()
    assert state["assignments"] == {"s1": "topic-a", "s2": "topic-a"}
    page.set_model({**MODEL, "tasks": [{**task, "id": "scattered-a"}]})
    assert page.action_buttons["confirm"].text() == "固定此任务（可选）"
    page.close()
    app.processEvents()


def test_ai_suggestion_replaces_local_default_and_is_used_by_one_click_confirm(
        tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    page = TaskChainPage(tmp_path)
    page.day_picker.setDate(QDate.fromString(MODEL["day"], "yyyy-MM-dd"))
    page.set_model({
        **MODEL,
        "tasks": [{**MODEL["tasks"][0], "status": "needs_confirmation",
                   "name": "ChatGPT 对话", "name_source": "local_default"}],
    })
    page.set_ai_suggestions([{
        "candidate_id": "task-a", "suggested_name": "AI 化优化方案",
        "confidence": "high", "reason": "标题证据一致", "evidence_ids": ["s1"],
        "related_candidate_ids": [],
    }])
    monkeypatch.setattr(
        QInputDialog, "getText",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("AI 已生成名称时不应再要求用户输入")
        ),
    )

    assert page.tasks_table.item(0, 0).text() == "AI 化优化方案"
    page._action("confirm")

    assert TaskDecisionStore(tmp_path).load()["names"]["task-a"] == "AI 化优化方案"
    page.close()
    app.processEvents()


def test_cloud_failure_reason_is_visible_instead_of_generic_message(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = TaskChainPage(tmp_path)

    page.set_ai_suggestions(None, "DeepSeek返回格式不兼容，请稍后重试")

    assert page.ai_result.text() == "DeepSeek返回格式不兼容，请稍后重试"
    page.close()
    app.processEvents()
