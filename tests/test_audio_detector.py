from desktop_activity_tracker.audio_detector import AudioDetector


def test_missing_target_audio_session_does_not_use_other_process_audio(monkeypatch):
    detector = AudioDetector(check_interval=0)
    monkeypatch.setattr(
        "desktop_activity_tracker.audio_detector.AudioUtilities.GetAllSessions",
        lambda: [],
    )
    monkeypatch.setattr(detector, "is_any_playing", lambda: True)

    assert detector.is_playing(12345) is False
