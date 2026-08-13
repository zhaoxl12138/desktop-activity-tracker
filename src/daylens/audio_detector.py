"""Audio output detection via Windows Core Audio API.

Uses IAudioMeterInformation::GetPeakValue() to read actual audio signal
level. Unlike GetState(), this returns 0.0 when playback is paused even
if the audio session stays open.
"""

import time
from ctypes import c_float, POINTER

import psutil
from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
from pycaw.pycaw import AudioUtilities


class IAudioMeterInformation(IUnknown):
    _iid_ = GUID('{C02216F6-8C67-4B5B-9D00-D008E73E0064}')
    _methods_ = [
        COMMETHOD([], HRESULT, 'GetPeakValue',
                  (['out'], POINTER(c_float), 'pfPeak')),
    ]


_PEAK_THRESHOLD = 0.001  # below this → effectively silent


class AudioDetector:
    """Audio detector using peak meter (actual signal, not session state)."""

    def __init__(self, check_interval=3.0):
        self._interval = check_interval
        self._last_check: float = 0.0
        self._last_pid: int | None = None
        self._cached: bool = True

    @staticmethod
    def _process_tree_pids(pid: int) -> set[int]:
        """Return a target process PID and all currently visible descendants."""
        pids = {int(pid)}
        try:
            process = psutil.Process(int(pid))
            pids.update(int(child.pid) for child in process.children(recursive=True))
        except (psutil.Error, OSError, ValueError, TypeError):
            pass
        return pids

    def is_playing(self, pid: int | None) -> bool:
        if pid is None:
            return True

        now = time.time()
        if pid == self._last_pid and now - self._last_check < self._interval:
            return self._cached

        self._last_pid = pid
        self._last_check = now

        try:
            sessions = AudioUtilities.GetAllSessions()
            target_pids = self._process_tree_pids(pid)
            target_sessions = [s for s in sessions if s.ProcessId in target_pids]
            for s in target_sessions:
                try:
                    meter = s._ctl.QueryInterface(IAudioMeterInformation)
                    if meter.GetPeakValue() > _PEAK_THRESHOLD:
                        self._cached = True
                        return self._cached
                except Exception:
                    continue
            if target_sessions:
                # A known target tree with only silent meters is paused/silent;
                # unrelated system audio must not turn it into a playing video.
                self._cached = False
                return self._cached
            # No session for the target tree: shared/child output may be
            # unattributable, so retain the historical global fallback.
            self._cached = self.is_any_playing()
        except Exception:
            # Unknown is safer for continuity: do not cut a video session
            # merely because Core Audio was temporarily unavailable.
            self._cached = True

        return self._cached

    def is_any_playing(self) -> bool:
        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                try:
                    meter = s._ctl.QueryInterface(IAudioMeterInformation)
                    if meter.GetPeakValue() > _PEAK_THRESHOLD:
                        return True
                except Exception:
                    continue
        except Exception:
            return True
        return False
