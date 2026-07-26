from __future__ import annotations


def test_second_gui_launch_activates_existing_window(monkeypatch):
    from daylens.services import gui_bootstrap

    activated = []
    monkeypatch.setattr(
        gui_bootstrap,
        "acquire_recording_lock",
        lambda: (False, None),
    )
    monkeypatch.setattr(
        gui_bootstrap,
        "_activate_existing_window",
        lambda: activated.append(True),
    )

    is_first, handle = gui_bootstrap.ensure_single_instance()

    assert (is_first, handle) == (False, None)
    assert activated == [True]


def test_cli_recording_start_uses_the_same_recording_lock():
    from pathlib import Path

    source = Path("src/daylens/services/command_handlers.py").read_text(
        encoding="utf-8"
    )

    assert "acquire_recording_lock" in source
    assert "DayLens_RecordingInstance" in Path(
        "src/daylens/services/instance_lock.py"
    ).read_text(encoding="utf-8")
