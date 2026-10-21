import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit

from daylens.gui.widgets.intelligence_settings import IntelligenceSettings
from daylens.services.intelligence_privacy import privacy_revision
from daylens.services.intelligence_state import (
    DEFAULT_SETTINGS,
    atomic_json,
    load_settings,
    save_settings,
    title_context,
)


def test_legacy_exclusions_are_not_loaded_or_saved(tmp_path):
    atomic_json(tmp_path / "settings.json", {
        "enabled": True,
        "excluded_apps": ["secret.exe"],
        "excluded_words": ["私人"],
    })
    loaded = load_settings(tmp_path)
    assert loaded["enabled"] is True
    assert "excluded_apps" not in loaded
    assert "excluded_words" not in loaded
    save_settings(tmp_path, loaded)
    persisted = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert "excluded_apps" not in persisted
    assert "excluded_words" not in persisted


def test_legacy_exclusions_do_not_block_redacted_title():
    settings = dict(DEFAULT_SETTINGS, excluded_apps=["secret.exe"], excluded_words=["私人"])
    context = title_context("secret.exe", "私人 a@example.com 13812345678", settings, "v1")
    assert context is not None
    assert "example.com" not in context["title"]
    assert "13812345678" not in context["title"]
    assert privacy_revision(settings) == privacy_revision(DEFAULT_SETTINGS)


def test_ai_settings_widget_has_no_exclusion_editors(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "daylens.gui.widgets.intelligence_settings.credentials.read_key",
        lambda: None,
    )
    app = QApplication.instance() or QApplication([])
    widget = IntelligenceSettings(directory=tmp_path)
    try:
        assert not hasattr(widget, "apps")
        assert not hasattr(widget, "words")
        placeholders = [edit.placeholderText() for edit in widget.findChildren(QLineEdit)]
        assert all("排除" not in placeholder for placeholder in placeholders)
    finally:
        widget.timer.stop()
        widget.close()
        widget.deleteLater()
        app.processEvents()
