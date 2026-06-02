"""Audio output detection via Windows Core Audio API.

Uses IAudioSessionControl2::GetState() to determine whether a process
is actively playing audio. Cached to avoid COM overhead every tick.
"""

import time
from pycaw.pycaw import AudioUtilities


class AudioDetector:
    """Cached per-process audio state checker."""

    def __init__(self, check_interval=3.0):
        self._interval = check_interval
        self._last_check: float = 0.0
        self._last_pid: int | None = None
        self._cached: bool = True  # Start True — don't penalise cold start

    def is_playing(self, pid: int | None) -> bool:
        """Check whether a process has an active audio session.

        Returns True when:
         - pid is None (no PID info -> assume playing, don't penalise)
         - COM query fails (default-safe)
         - The process has an audio session with state Active (1)
         - No audio session found for this PID (child process may handle audio)
        """
        if pid is None:
            return True

        now = time.time()
        if pid == self._last_pid and now - self._last_check < self._interval:
            return self._cached

        self._last_pid = pid
        self._last_check = now

        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                if s.ProcessId == pid:
                    # 0=Inactive, 1=Active, 2=Expired
                    self._cached = s._ctl.GetState() == 1
                    return self._cached
            self._cached = True  # No audio session found — assume playing (UI may have child process for audio)
        except Exception:
            self._cached = True  # On error, assume playing (safe default)

        return self._cached

    def is_any_playing(self) -> bool:
        """Check whether ANY process is actively playing audio on the system.

        Used as a global signal: if audio is playing anywhere, the user is
        likely consuming content even if the foreground window doesn't own
        the audio session directly.
        """
        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                try:
                    if s._ctl.GetState() == 1:  # Active
                        return True
                except Exception:
                    continue
        except Exception:
            return True  # On error, assume playing (safe default)
        return False
