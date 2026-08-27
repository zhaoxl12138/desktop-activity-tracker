"""Audio output detection via Windows Core Audio API.

Uses IAudioMeterInformation::GetPeakValue() to read actual audio signal
level. Unlike GetState(), this returns 0.0 when playback is paused even
if the audio session stays open.
"""

import ctypes
import os
import time
from ctypes import byref, c_float, c_uint32, create_unicode_buffer, POINTER

import psutil
from comtypes import (
    CLSCTX_ALL,
    COINIT_MULTITHREADED,
    COMMETHOD,
    CoInitializeEx,
    CoUninitialize,
    GUID,
    HRESULT,
    IUnknown,
)
from pycaw.pycaw import AudioUtilities

try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only application
    winreg = None


class IAudioMeterInformation(IUnknown):
    _iid_ = GUID('{C02216F6-8C67-4B5B-9D00-D008E73E0064}')
    _methods_ = [
        COMMETHOD([], HRESULT, 'GetPeakValue',
                  (['out'], POINTER(c_float), 'pfPeak')),
    ]


_PEAK_THRESHOLD = 0.001  # below this → effectively silent


def initialize_audio_com() -> None:
    """Own a COM apartment on the recording thread."""
    CoInitializeEx(COINIT_MULTITHREADED)


def uninitialize_audio_com() -> None:
    """Release the recording thread's COM apartment."""
    CoUninitialize()


class AudioDetector:
    """Audio detector using peak meter (actual signal, not session state)."""

    def __init__(self, check_interval=3.0):
        self._interval = check_interval
        self._last_check: float = 0.0
        self._last_pid: int | None = None
        self._cached: bool = True
        self._voice_last_check: float = 0.0
        self._voice_last_key: tuple[int | None, str] | None = None
        self._voice_cached: bool = False
        self._microphone_device = None
        self._microphone_meter = None

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

    def is_voice_active(self, pid: int | None, exe_path: str = "") -> bool:
        """Return whether the target work app is sending or receiving speech.

        Unlike the video detector, this deliberately has no global-audio
        fallback: background music or a notification must not turn idle work
        into engaged time.
        """
        key = (pid, os.path.normcase(exe_path or ""))
        now = time.time()
        if (
            key == self._voice_last_key
            and now - self._voice_last_check < self._interval
        ):
            return self._voice_cached

        self._voice_last_key = key
        self._voice_last_check = now
        self._voice_cached = (
            self._process_output_active(pid)
            or self._microphone_input_active(pid, exe_path)
        )
        return self._voice_cached

    def _process_output_active(self, pid: int | None) -> bool:
        if pid is None:
            return False
        try:
            target_pids = self._process_tree_pids(pid)
            for session in AudioUtilities.GetAllSessions():
                if session.ProcessId not in target_pids:
                    continue
                try:
                    meter = session._ctl.QueryInterface(IAudioMeterInformation)
                    if meter.GetPeakValue() > _PEAK_THRESHOLD:
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _microphone_input_active(
        self,
        pid: int | None,
        exe_path: str,
    ) -> bool:
        if not self._microphone_has_signal():
            return False
        return self._target_owns_microphone(pid, exe_path)

    def _microphone_has_signal(self) -> bool:
        try:
            meter = self._get_microphone_meter()
            return meter.GetPeakValue() > _PEAK_THRESHOLD
        except Exception:
            self._release_microphone_meter()
            return False

    def _get_microphone_meter(self):
        if self._microphone_meter is not None:
            return self._microphone_meter
        device = AudioUtilities.GetMicrophone()
        unknown = device.Activate(
            IAudioMeterInformation._iid_,
            CLSCTX_ALL,
            None,
        )
        # QueryInterface owns an independent reference. Avoid ctypes.cast:
        # two Python COM pointer wrappers around the same unowned reference
        # can both call Release and crash in _ctypes during collection.
        meter = unknown.QueryInterface(IAudioMeterInformation)
        self._microphone_device = device
        self._microphone_meter = meter
        return meter

    def _release_microphone_meter(self) -> None:
        meter = self._microphone_meter
        device = self._microphone_device
        self._microphone_meter = None
        self._microphone_device = None
        # CPython decrements these COM references immediately on the calling
        # thread, while its COM apartment is still initialized.
        del meter
        del device

    def close(self) -> None:
        self._release_microphone_meter()
        self._voice_cached = False
        self._voice_last_key = None

    @classmethod
    def _target_owns_microphone(
        cls,
        pid: int | None,
        exe_path: str,
    ) -> bool:
        if winreg is None:
            return False

        identities: set[str] = set()
        paths: set[str] = set()
        if exe_path:
            paths.add(os.path.normcase(os.path.abspath(exe_path)))
        if pid is not None:
            for target_pid in cls._process_tree_pids(pid):
                try:
                    process = psutil.Process(target_pid)
                    paths.add(os.path.normcase(process.exe()))
                except (psutil.Error, OSError, ValueError, TypeError):
                    pass
                family = cls._package_family_name(target_pid)
                if family:
                    identities.add(family.casefold())

        root_path = (
            r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager"
            r"\ConsentStore\microphone"
        )
        for family in identities:
            if cls._microphone_registry_entry_active(root_path, family):
                return True

        nonpackaged_root = root_path + r"\NonPackaged"
        for path in paths:
            encoded = path.replace("\\", "#")
            if cls._microphone_registry_entry_active(nonpackaged_root, encoded):
                return True
        return False

    @staticmethod
    def _microphone_registry_entry_active(root_path: str, name: str) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, root_path + "\\" + name) as key:
                start = int(winreg.QueryValueEx(key, "LastUsedTimeStart")[0] or 0)
                stop = int(winreg.QueryValueEx(key, "LastUsedTimeStop")[0] or 0)
                return start > 0 and (stop == 0 or start > stop)
        except (OSError, TypeError, ValueError):
            return False

    @staticmethod
    def _package_family_name(pid: int) -> str:
        if os.name != "nt":
            return ""
        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not process:
            return ""
        try:
            length = c_uint32(0)
            ctypes.windll.kernel32.GetPackageFamilyName(
                process,
                byref(length),
                None,
            )
            if not length.value:
                return ""
            buffer = create_unicode_buffer(length.value)
            result = ctypes.windll.kernel32.GetPackageFamilyName(
                process,
                byref(length),
                buffer,
            )
            return buffer.value if result == 0 else ""
        finally:
            ctypes.windll.kernel32.CloseHandle(process)
