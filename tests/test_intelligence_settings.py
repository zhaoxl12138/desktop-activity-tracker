import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def test_saved_key_is_visibly_masked_after_settings_restart(tmp_path, monkeypatch):
    from daylens.gui.widgets import intelligence_settings as module

    _app()
    monkeypatch.setattr(module.credentials, 'read_key', lambda: 'not-exposed')
    card = module.IntelligenceSettings(directory=tmp_path)

    assert card.key.text() == ''
    assert '••••••••' in card.key.placeholderText()
    assert '已安全保存' in card.key_state.text()
    assert '替换' in card.key_state.text()
    assert 'not-exposed' not in card.key.placeholderText()
    assert 'not-exposed' not in card.key_state.text()


def test_delete_restores_empty_key_state(tmp_path, monkeypatch):
    from daylens.gui.widgets import intelligence_settings as module

    _app()
    present = [True]
    monkeypatch.setattr(module.credentials, 'read_key', lambda: 'hidden' if present[0] else None)
    monkeypatch.setattr(module.credentials, 'delete_key', lambda: present.__setitem__(0, False))
    card = module.IntelligenceSettings(directory=tmp_path)
    monkeypatch.setattr(card, '_save', lambda: None)

    card._delete_key()

    assert card.key.text() == ''
    assert '输入API密钥' in card.key.placeholderText()
    assert card.key_state.text() == '尚未配置密钥'
