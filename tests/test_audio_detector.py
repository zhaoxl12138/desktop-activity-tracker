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


class _Proc:
    def __init__(self, pid, children=()):
        self.pid = pid
        self._children = tuple(children)

    def children(self, recursive=False):
        if recursive:
            result = []
            for child in self._children:
                result.append(child)
                result.extend(child.children(recursive=True))
            return result
        return list(self._children)


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


def test_process_tree_audio_detects_child_process_playback(monkeypatch):
    detector = AudioDetector(check_interval=0)
    child = _Proc(222)
    monkeypatch.setattr(
        "daylens.audio_detector.psutil.Process",
        lambda pid: _Proc(pid, [child]),
    )
    monkeypatch.setattr(
        "daylens.audio_detector.AudioUtilities.GetAllSessions",
        lambda: [_AudioSession(111, 0.0), _AudioSession(222, 0.25)],
    )

    assert detector.is_playing(111) is True


def test_process_tree_lookup_error_still_uses_global_audio_fallback(monkeypatch):
    detector = AudioDetector(check_interval=0)

    def fail_process(_pid):
        raise RuntimeError("process access denied")

    monkeypatch.setattr(
        "daylens.audio_detector.psutil.Process", fail_process
    )
    monkeypatch.setattr(
        "daylens.audio_detector.AudioUtilities.GetAllSessions",
        lambda: [_AudioSession(999, 0.25)],
    )

    assert detector.is_playing(12345) is True


def test_work_voice_output_requires_audio_from_target_process_tree(monkeypatch):
    detector = AudioDetector(check_interval=0)
    monkeypatch.setattr(
        "daylens.audio_detector.psutil.Process",
        lambda pid: _Proc(pid),
    )
    monkeypatch.setattr(
        "daylens.audio_detector.AudioUtilities.GetAllSessions",
        lambda: [_AudioSession(999, 0.25)],
    )

    assert detector.is_voice_active(12345, "") is False


def test_work_voice_output_detects_target_child_process(monkeypatch):
    detector = AudioDetector(check_interval=0)
    child = _Proc(222)
    monkeypatch.setattr(
        "daylens.audio_detector.psutil.Process",
        lambda pid: _Proc(pid, [child]),
    )
    monkeypatch.setattr(
        "daylens.audio_detector.AudioUtilities.GetAllSessions",
        lambda: [_AudioSession(999, 0.25), _AudioSession(222, 0.1)],
    )
    monkeypatch.setattr(detector, "_microphone_input_active", lambda *_: False)

    assert detector.is_voice_active(111, "") is True


def test_work_voice_detects_owned_microphone_input(monkeypatch):
    detector = AudioDetector(check_interval=0)
    monkeypatch.setattr(
        "daylens.audio_detector.AudioUtilities.GetAllSessions",
        lambda: [],
    )
    monkeypatch.setattr(detector, "_microphone_input_active", lambda *_: True)

    assert detector.is_voice_active(111, r"C:\\Apps\\WorkVoice.exe") is True


def test_microphone_requires_both_target_ownership_and_input_peak(monkeypatch):
    detector = AudioDetector(check_interval=0)
    monkeypatch.setattr(detector, "_microphone_has_signal", lambda: True)
    monkeypatch.setattr(detector, "_target_owns_microphone", lambda *_: False)

    assert detector._microphone_input_active(111, r"C:\\Apps\\WorkVoice.exe") is False

    monkeypatch.setattr(detector, "_target_owns_microphone", lambda *_: True)
    assert detector._microphone_input_active(111, r"C:\\Apps\\WorkVoice.exe") is True

    monkeypatch.setattr(detector, "_microphone_has_signal", lambda: False)
    assert detector._microphone_input_active(111, r"C:\\Apps\\WorkVoice.exe") is False
