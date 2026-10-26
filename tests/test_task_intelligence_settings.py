from daylens.services.intelligence_state import load_settings, save_settings
from PySide6.QtWidgets import QApplication, QCheckBox
from daylens.gui.widgets.intelligence_settings import IntelligenceSettings


def test_task_switches_are_independent_opt_in_and_legacy_settings_still_read(tmp_path):
    assert load_settings(tmp_path)["task_analysis_enabled"] is False
    assert load_settings(tmp_path)["task_cloud_enabled"] is False


def test_retired_task_switches_are_not_exposed_in_settings(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = IntelligenceSettings(directory=tmp_path)
    try:
        texts = [item.text() for item in widget.findChildren(QCheckBox)]
        assert not any("本地任务分析" in text or "云端任务建议" in text for text in texts)
        assert not hasattr(widget, "task_local")
        assert not hasattr(widget, "task_cloud")
    finally:
        widget.close()
        app.processEvents()


def test_saving_settings_disables_retired_switches_without_touching_decisions(tmp_path):
    from daylens.services.task_decision_service import TaskDecisionStore

    app = QApplication.instance() or QApplication([])
    active = {"enabled": True, "classification_enabled": True,
              "reports_enabled": True, "behavior_analysis_enabled": True,
              "monthly_budget_micros": 3_500_000}
    save_settings(tmp_path, {**active, "task_analysis_enabled": True,
                             "task_cloud_enabled": True})
    TaskDecisionStore(tmp_path).apply("confirm", ["s1"], "task-a", "已有任务",
                                     expected_revision=0)
    state_before = TaskDecisionStore(tmp_path).load()
    widget = IntelligenceSettings(directory=tmp_path)
    try:
        widget._save()
        settings = load_settings(tmp_path)
        assert settings["task_analysis_enabled"] is False
        assert settings["task_cloud_enabled"] is False
        assert {key: settings[key] for key in active} == active
        assert TaskDecisionStore(tmp_path).load() == state_before
    finally:
        widget.close()
        app.processEvents()
