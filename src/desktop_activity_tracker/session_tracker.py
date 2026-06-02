"""Session tracker — 1s sampling + session aggregation + state machine."""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime


# ── Browser title normalization patterns ──

BROWSER_SUFFIXES = [
    " - Google Chrome", " - Microsoft Edge", " — Mozilla Firefox",
    " - Internet Explorer", " - Chromium",
]

_BROWSER_PROCS = {"chrome.exe", "msedge.exe", "iexplore.exe", "firefox.exe", "chromium.exe"}

_NUMERIC_PARENTHESIS = re.compile(r'\(\d+\)')


def normalize_window_title(process_name, window_title):
    """Strip browser/editor suffixes and remove noise to get a stable session key.

    Returns the normalized title, or empty string if nothing meaningful remains.
    """
    if not window_title:
        return ""

    title = window_title.strip()
    is_browser = (process_name or "").lower() in _BROWSER_PROCS

    # Strip known browser suffixes
    for suffix in BROWSER_SUFFIXES:
        if title.lower().endswith(suffix.lower()):
            title = title[:-len(suffix)].strip()

    # Remove trailing number counts like "Inbox (3)"
    title = _NUMERIC_PARENTHESIS.sub('', title).strip()

    # For titles with separators, extract the meaningful segment:
    # - Browsers: rightmost segment (website name)
    #   "Foo - Gmail - Google Chrome" → "Gmail"
    # - Non-browsers: leftmost segment (file/document name)
    #   "main.py - Visual Studio Code" → "main.py"
    for sep in [" - ", " — ", " | "]:
        if sep in title:
            parts = [p.strip() for p in title.split(sep) if p.strip()]
            if parts:
                title = parts[0] if not is_browser else parts[-1]

    # Clean up any remaining numeric counts
    title = _NUMERIC_PARENTHESIS.sub('', title).strip()

    return title


# ── Session data class ──


@dataclass
class ActivitySession:
    session_id: str
    start_time: datetime
    end_time: datetime
    date: str
    process_name: str
    exe_path: str
    window_title: str
    normalized_title: str
    category_key: str
    category_name: str
    active_rule: str
    duration_seconds: int = 0
    effective_seconds: int = 0
    idle_seconds: int = 0
    switch_reason: str = ""
    _db_row_id: int = field(default=-1, repr=False)

    @property
    def session_key(self):
        """Composite key used to detect window changes."""
        return (self.process_name, self.normalized_title, self.category_key)


# ── Session tracker state machine ──


class SessionTracker:
    """Manages the current ActivitySession lifecycle.

    The caller (RecordingWorker) is responsible for pause/stop control.
    This class only handles session state transitions and counter ticks.
    """

    def __init__(self, config, classifier,
                 on_session_end=None, on_flush=None,
                 audio_detector=None):
        tracker = config.get("tracker", {})
        self.sample_interval = tracker.get("sample_interval_seconds",
            config.get("sample_interval_seconds", 1))
        self.flush_interval = tracker.get("flush_interval_seconds",
            config.get("flush_interval_seconds", 10))
        self.idle_threshold = tracker.get("idle_threshold_seconds",
            config.get("idle_threshold_seconds", 60))
        self.min_session = tracker.get("min_session_seconds",
            config.get("min_session_seconds", 2))

        self.classifier = classifier
        self._on_session_end = on_session_end
        self._on_flush = on_flush
        self._audio_detector = audio_detector

        self._current: ActivitySession | None = None
        self._tick_count = 0
        self._consecutive_win_failures = 0
        self._last_pid = None
        self._last_process_name = ""
        self._last_exe_path = ""

        # Phantom input filter — some systems have drivers/services that
        # generate spurious HID events, resetting GetLastInputInfo() every
        # ~5–10s. We detect phantom resets by the sharp drop in raw idle
        # (3–12s in one tick) and accumulate idle by wall-clock time.
        self._last_raw_idle: float = 0.0
        self._effective_idle: float = 0.0
        self._phantom_active: bool = False
        self._phantom_ticks: int = 0
        self._phantom_low_ticks: int = 0
        self._oscillation_ticks: int = 0

    # ── Public API ──────────────────────────────────────────────────

    @property
    def current_session(self) -> ActivitySession | None:
        return self._current

    # ── Tick ────────────────────────────────────────────────────────

    def tick(self, idle_seconds, win_info):
        """Called every sample_interval by the worker loop.

        Returns a dict with the latest sample snapshot for UI signals.
        """

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")

        # Resolve window info
        if win_info and (win_info.get("process_name") or win_info.get("window_title")):
            process_name = win_info.get("process_name", "")
            exe_path = win_info.get("exe_path", "")
            raw_title = win_info.get("window_title", "")
        else:
            process_name = "system"
            exe_path = ""
            raw_title = "idle/desktop"

        # Cache psutil-heavy lookups
        if process_name != self._last_process_name:
            self._last_pid = win_info.get("pid") if win_info else None
            self._last_process_name = process_name
            self._last_exe_path = exe_path

        # Classify
        if process_name == "system":
            cat_key = "other"
            cat_name = "空闲"
            active_rule = "interactive_required"
        else:
            cat = self.classifier.classify(process_name, raw_title)
            cat_key = cat["category_key"]
            cat_name = cat["category_name"]
            active_rule = cat["active_rule"]

        # Normalize title
        norm_title = normalize_window_title(process_name, raw_title)

        # Detect window change
        new_key = (process_name, norm_title, cat_key)

        if self._current is not None:
            # Cross-day check
            if self._current.date != date_str:
                self._current.end_time = now
                self._current.switch_reason = "cross_day"
                self._emit_session()

            # Window change
            elif self._current.session_key != new_key:
                # Ignore single-frame detection failures
                if win_info is None or not win_info.get("process_name"):
                    self._consecutive_win_failures += 1
                    if self._consecutive_win_failures < 2:
                        # Continue ticking current session (add idle)
                        self._tick_current(idle_seconds, now)
                        return self._make_snapshot(idle_seconds)
                else:
                    self._consecutive_win_failures = 0

                self._current.end_time = now
                self._current.switch_reason = "window_change"
                self._emit_session()
            else:
                self._consecutive_win_failures = 0

        # Start new session if needed
        if self._current is None:
            self._current = ActivitySession(
                session_id=uuid.uuid4().hex[:12],
                start_time=now,
                end_time=now,
                date=date_str,
                process_name=process_name,
                exe_path=self._last_exe_path,
                window_title=raw_title,
                normalized_title=norm_title,
                category_key=cat_key,
                category_name=cat_name,
                active_rule=active_rule,
            )

        # Tick counters
        self._tick_current(idle_seconds, now)

        # Periodic flush
        self._tick_count += 1
        if self._tick_count % self.flush_interval == 0 and self._on_flush:
            self._on_flush(self._current)

        return self._make_snapshot(idle_seconds)

    # ── Internals ──────────────────────────────────────────────────

    def _tick_current(self, idle_seconds, now):
        if self._current is None:
            return
        self._current.end_time = now
        self._current.duration_seconds += self.sample_interval

        if self._current.active_rule == "passive_allowed":
            # Entertainment categories: check audio output to avoid
            # counting paused/idle video as effective time.
            if (self._current.category_key in ("video", "gaming")
                    and self._audio_detector is not None
                    and not self._audio_detector.is_playing(self._last_pid)):
                self._current.idle_seconds += self.sample_interval
            else:
                self._current.effective_seconds += self.sample_interval
            self._effective_idle = 0.0
            self._phantom_active = False
            self._phantom_ticks = 0
            self._phantom_low_ticks = 0
            self._oscillation_ticks = 0
            self._last_raw_idle = idle_seconds
            return

        # ── Phantom HID reset detection ───────────────────────────
        # Some drivers/services generate spurious HID events every
        # 5–10s, resetting GetLastInputInfo().  A genuine user coming
        # back from long idle would see idle drop from 60+ to 0 — too
        # large for a phantom reset (capped at 12s).  We detect sharp
        # drops (3–12s) while idle was in [3, idle_threshold).
        idle_delta = self._last_raw_idle - idle_seconds
        is_phantom = (
            3 <= idle_delta <= 12
            and 3 <= self._last_raw_idle < self.idle_threshold
        )

        if is_phantom:
            self._effective_idle += self.sample_interval
            self._phantom_active = True
            self._phantom_low_ticks = 0
            self._oscillation_ticks = 0

        elif self._phantom_active:
            self._effective_idle += self.sample_interval
            self._phantom_ticks += 1

            # Exit A: raw idle is genuinely growing → real idle
            if idle_seconds > 15:
                self._phantom_active = False
                self._phantom_ticks = 0
            # Exit B: user has been actively typing for 5+ ticks
            elif idle_seconds < 2:
                self._phantom_low_ticks += 1
                if self._phantom_low_ticks >= 5:
                    self._phantom_active = False
                    self._phantom_ticks = 0
                    self._phantom_low_ticks = 0
                    self._effective_idle = idle_seconds
            else:
                self._phantom_low_ticks = 0
            # Exit C: safety timeout (10 min) — treat as real idle
            if self._phantom_ticks > 600:
                self._phantom_active = False
                self._phantom_ticks = 0
                self._effective_idle = self.idle_threshold + 1

        elif idle_seconds < 2 and self._last_raw_idle < 2:
            # Rapid 0–1 oscillation zone — don't reset; accumulate
            # via wall clock after 10 ticks tolerance.
            self._oscillation_ticks += 1
            if self._oscillation_ticks > 10:
                self._effective_idle += self.sample_interval
            else:
                self._effective_idle = max(self._effective_idle, idle_seconds)

        elif idle_seconds >= self._last_raw_idle:
            # Idle stable or increasing — normal accumulation
            self._effective_idle = max(self._effective_idle, idle_seconds)
            self._oscillation_ticks = 0

        else:
            # Small natural decrease → genuine user activity
            self._effective_idle = idle_seconds
            self._phantom_active = False
            self._oscillation_ticks = 0

        self._last_raw_idle = idle_seconds

        if self._effective_idle <= self.idle_threshold:
            self._current.effective_seconds += self.sample_interval
        else:
            self._current.idle_seconds += self.sample_interval

    def _emit_session(self):
        if self._current is None:
            return
        if self._current.duration_seconds < self.min_session:
            self._current = None
            return
        if self._on_session_end:
            self._on_session_end(self._current)
        self._current = None

    def _make_snapshot(self, idle_seconds):
        """Build a UI-compatible snapshot dict for the sample_updated signal."""
        s = self._current
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "date": s.date if s else datetime.now().strftime("%Y-%m-%d"),
            "session_id": s.session_id if s else "",
            "process_name": s.process_name if s else "",
            "exe_path": s.exe_path if s else "",
            "window_title": s.window_title if s else "",
            "normalized_title": s.normalized_title if s else "",
            "category_key": s.category_key if s else "",
            "category_name": s.category_name if s else "",
            "active_rule": s.active_rule if s else "",
            "duration_seconds": s.duration_seconds if s else 0,
            "effective_seconds": s.effective_seconds if s else 0,
            "idle_seconds": idle_seconds,
            "session_idle_seconds": s.idle_seconds if s else 0,
            "is_user_active": idle_seconds <= self.idle_threshold,
            "is_effective": (
                s.active_rule == "passive_allowed" or
                self._effective_idle <= self.idle_threshold
            ) if s else False,
        }
