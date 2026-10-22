from daylens.services.intelligence_state import load_settings, save_settings
from PySide6.QtWidgets import QApplication
from daylens.gui.widgets.intelligence_settings import IntelligenceSettings


def test_task_switches_are_independent_opt_in_and_legacy_settings_still_read(tmp_path):
    assert load_settings(tmp_path)["task_analysis_enabled"] is False
    assert load_settings(tmp_path)["task_cloud_enabled"] is False


def test_settings_widget_saves_local_and_cloud_switches_independently(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = IntelligenceSettings(directory=tmp_path)
    assert widget.task_local.isChecked() is False
    assert widget.task_cloud.isChecked() is False
    widget.task_local.setChecked(True)
    widget.task_cloud.setChecked(True)
    widget._save()
    assert load_settings(tmp_path)["task_analysis_enabled"] is True
    assert load_settings(tmp_path)["task_cloud_enabled"] is True
    widget.close()
    app.processEvents()
    save_settings(tmp_path, {"enabled": True, "classification_enabled": True,
                             "reports_enabled": False, "monthly_budget_micros": 4_000_000,
                             "task_analysis_enabled": True, "task_cloud_enabled": False})
    assert load_settings(tmp_path)["task_analysis_enabled"] is True
    assert load_settings(tmp_path)["task_cloud_enabled"] is False
