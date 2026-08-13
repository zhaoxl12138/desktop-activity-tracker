from desktop_activity_tracker.audio_detector import AudioDetector


class _Meter:
    def __init__(self, peak):
        self.peak = peak

    def GetPeakValue(self):
        return self.peak


class _AudioSession:
    def __init__(self, pid, peak):
        self.ProcessId = pid
        self._meter = _Meter(peak)
        self._ctl = self

    def QueryInterface(self, _interface):
        return self._meter


def test_missing_target_audio_session_uses_other_process_audio(monkeypatch):
    detector = AudioDetector(check_interval=0)
    monkeypatch.setattr(
        "desktop_activity_tracker.audio_detector.AudioUtilities.GetAllSessions",
        lambda: [_AudioSession(999, 0.25)],
    )

    assert detector.is_playing(12345) is True


def test_audio_query_error_is_conservative_and_keeps_video_playing(monkeypatch):
    detector = AudioDetector(check_interval=0)

    def fail_query():
        raise RuntimeError("audio session unavailable")

    monkeypatch.setattr(
        "desktop_activity_tracker.audio_detector.AudioUtilities.GetAllSessions",
        fail_query,
    )

    assert detector.is_playing(12345) is True
