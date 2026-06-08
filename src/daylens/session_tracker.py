"""Session tracker — 1s sampling + session aggregation + state machine."""

import ctypes
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime


# ── Input polling (cursor + keyboard, immune to phantom HID events) ──

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _get_cursor_pos():
    pt = _POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def _get_keyboard_snapshot() -> bytes:
    """Return 256-byte snapshot using GetAsyncKeyState (works from any thread).

    Unlike GetKeyboardState which requires a message pump, GetAsyncKeyState
    reads the physical key state directly.
    - 0x8000: key currently held down
    - 0x0001: key was pressed since last call (catches quick taps between ticks)
    """
    buf = bytearray(256)
    for vk in range(256):
        state = ctypes.windll.user32.GetAsyncKeyState(vk)
        if state & 0x8001:  # currently down OR pressed since last poll
            buf[vk] = 0x80
    return bytes(buf)


# ── Browser title normalization patterns ──

BROWSER_SUFFIXES = [
    " - Google Chrome", " - Microsoft Edge", " — Mozilla Firefox",
    " - Internet Explorer", " - Chromium",
]

_BROWSER_PROCS = {"chrome.exe", "msedge.exe", "iexplore.exe", "firefox.exe", "chromium.exe"}

_NUMERIC_PARENTHESIS = re.compile(r'\(\d+\)')
_DYNAMIC_TITLE_PREFIX = re.compile(r'^[\u2800-\u28ff\u25e0-\u25ff\u2600-\u27bf]+\s+')


def normalize_window_title(process_name, window_title):
    """Strip browser/editor suffixes and remove noise to get a stable session key.

    Returns the normalized title, or empty string if nothing meaningful remains.
    """
    if not window_title:
        return ""

    title = window_title.strip()
    is_browser = (process_name or "").lower() in _BROWSER_PROCS

    title = _DYNAMIC_TITLE_PREFIX.sub('', title).strip()

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


# ── Activity domains for session grouping ──────────────────────────
# Sessions split only when the user crosses domain boundaries,
# not within the same domain. This keeps work-tool hopping
# (VS Code ↔ Obsidian ↔ Chrome) as one continuous session.

_ACTIVITY_DOMAINS: dict[str, set[str]] = {
    "work_study": {
        "coding", "ai_tools", "reading", "creative", "tools",
        "browser_general", "office",
    },
    "entertainment": {"video", "gaming"},
    "social":       {"social"},
}

def _get_domain(category_key: str) -> str:
    if not category_key:
        return "idle"
    for domain, keys in _ACTIVITY_DOMAINS.items():
        if category_key in keys:
            return domain
    return "idle" if category_key in {"idle", "other"} else "work_study"


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
            config.get("flush_interval_seconds", 5))
        self.idle_threshold = tracker.get("idle_threshold_seconds",
            config.get("idle_threshold_seconds", 60))
        self.entertainment_idle_threshold = tracker.get(
            "entertainment_idle_threshold_seconds", 300)
        self.min_session = tracker.get("min_session_seconds",
            config.get("min_session_seconds", 2))
        self.cross_group_grace = tracker.get("cross_group_grace_seconds", 30)

        self.classifier = classifier
        self._on_session_end = on_session_end
        self._on_flush = on_flush
        self._audio_detector = audio_detector

        self._current: ActivitySession | None = None
        self._pending_switch: dict | None = None  # cross-domain grace period state
        self._tick_count = 0
        self._last_pid = None
        self._last_process_name = ""
        self._last_exe_path = ""

        # Idle detection via cursor position + keyboard state.
        # Phantom HID events reset GetLastInputInfo() but don't move the
        # mouse or press keys, so we track those directly.
        self._persistent_idle: float = 0.0
        self._last_cursor_pos: tuple[int, int] | None = None
        self._last_kb_state: bytes | None = None
        self._activity_from_hook: bool = False  # set by pynput listener
        self._idle_corrected: bool = False  # back-correct threshold window once per idle period

    # ── Public API ──────────────────────────────────────────────────

    @property
    def current_session(self) -> ActivitySession | None:
        return self._current

    def finish_current(self, reason="manual"):
        """End the current session without starting a replacement session."""
        if self._current is None:
            return
        self._current.end_time = datetime.now()
        self._current.switch_reason = reason
        self._emit_session()

    def mark_user_active(self):
        """Called from pynput keyboard listener (any thread) on keypress.

        Resets the persistent idle timer instantly so typing always
        interrupts idle without waiting for the next polling tick.
        """
        self._persistent_idle = 0.0
        self._idle_corrected = False
        self._last_cursor_pos = None
        self._last_kb_state = None
        self._activity_from_hook = True

    def _idle_limit(self) -> int:
        """Return the idle threshold for the current session category."""
        if self._current is not None and self._current.category_key == "video":
            return self.entertainment_idle_threshold
        return self.idle_threshold

    # ── Tick ────────────────────────────────────────────────────────

    def tick(self, idle_seconds, win_info):
        """Called every sample_interval by the worker loop.

        Session splitting uses activity domains instead of per-window keys:
          - Same domain (e.g. VS Code → Obsidian) → continues one session
          - Cross-domain (e.g. coding → video) → 30s grace period, then split
        """

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")

        # Resolve window info
        if win_info and (win_info.get("process_name") or win_info.get("window_title")):
            process_name = win_info.get("process_name", "")
            exe_path = win_info.get("exe_path", "")
            raw_title = win_info.get("window_title", "")
            hwnd = win_info.get("hwnd")
        else:
            process_name = "system"
            exe_path = ""
            raw_title = "idle/desktop"
            hwnd = None

        # Cache psutil-heavy lookups
        if process_name != self._last_process_name:
            self._last_pid = win_info.get("pid") if win_info else None
            self._last_process_name = process_name
            self._last_exe_path = exe_path

        # Classify
        if process_name == "system":
            cat_key = "idle"
            cat_name = "空闲"
            active_rule = "interactive_required"
        else:
            if process_name in ("python.exe", "pythonw.exe") and "daylens" in raw_title.lower():
                cat_key = "tools"
                cat_name = "系统工具"
                active_rule = "interactive_required"
            else:
                cat = self.classifier.classify(process_name, raw_title)
                cat_key = cat["category_key"]
                cat_name = cat["category_name"]
                active_rule = cat["active_rule"]

        norm_title = normalize_window_title(process_name, raw_title)
        new_domain = _get_domain(cat_key)

        if self._current is not None:
            current_domain = _get_domain(self._current.category_key)

            # ── Cross-day ──────────────────────────────────────────
            if self._current.date != date_str:
                self._current.end_time = now
                self._current.switch_reason = "cross_day"
                self._emit_session()
                self._pending_switch = None

            # ── Cross-domain ───────────────────────────────────────
            elif current_domain != new_domain:
                self._handle_cross_domain(
                    now, date_str, new_domain,
                    process_name, exe_path, raw_title, norm_title,
                    cat_key, cat_name, active_rule,
                )
                self._tick_count += 1
                if self._tick_count % self.flush_interval == 0 and self._on_flush:
                    self._on_flush(self._current)
                return self._make_snapshot(idle_seconds)

            # ── Same domain ────────────────────────────────────────
            else:
                self._pending_switch = None
                self._current.process_name = process_name
                self._current.window_title = raw_title
                self._current.normalized_title = norm_title
                self._current.category_key = cat_key
                self._current.category_name = cat_name
                self._current.active_rule = active_rule

        # Start new session if needed
        if self._current is None:
            self._pending_switch = None
            self._persistent_idle = 0.0
            self._last_cursor_pos = None
            self._last_kb_state = None
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

        self._tick_current(idle_seconds, now, hwnd)
        self._tick_count += 1
        if self._tick_count % self.flush_interval == 0 and self._on_flush:
            self._on_flush(self._current)
        return self._make_snapshot(idle_seconds)

    # ── Cross-domain grace period ────────────────────────────────────

    def _handle_cross_domain(self, now, date_str, new_domain,
                             process_name, exe_path, raw_title, norm_title,
                             cat_key, cat_name, active_rule):
        """Grace period before confirming a cross-domain session switch.

        - First detection → start 30s timer, keep ticking current session.
        - Same target domain still active → check timer, confirm if expired.
        - Switched to yet another domain → reset timer to new target.
        - Activity during grace period is credited as effective (user is
          actively using the new app), not idle.
        """
        if self._pending_switch is None or self._pending_switch["domain"] != new_domain:
            self._pending_switch = {
                "domain": new_domain,
                "since": now,
                "process_name": process_name,
                "exe_path": exe_path,
                "raw_title": raw_title,
                "norm_title": norm_title,
                "cat_key": cat_key,
                "cat_name": cat_name,
                "active_rule": active_rule,
                "effective_during_grace": 0,
                "idle_during_grace": 0,
            }
            self._tick_grace_current(now)
            return

        # Always tick first so every second is accounted correctly
        self._tick_grace_current(now)
        elapsed = (now - self._pending_switch["since"]).total_seconds()
        if elapsed < self.cross_group_grace:
            return

        # ── Grace period expired → confirm switch ──────────────────
        p = self._pending_switch
        self._current.end_time = p["since"]
        self._current.switch_reason = "domain_change"
        self._emit_session()

        eff = p["effective_during_grace"]
        idle = p["idle_during_grace"]
        self._current = ActivitySession(
            session_id=uuid.uuid4().hex[:12],
            start_time=p["since"],   # backdate to switch point
            end_time=now,
            date=date_str,
            process_name=p["process_name"],
            exe_path=p["exe_path"],
            window_title=p["raw_title"],
            normalized_title=p["norm_title"],
            category_key=p["cat_key"],
            category_name=p["cat_name"],
            active_rule=p["active_rule"],
            duration_seconds=int(elapsed),
            effective_seconds=eff,
            idle_seconds=idle,
        )
        self._pending_switch = None
        self._persistent_idle = 0.0
        self._last_cursor_pos = None
        self._last_kb_state = None

    def _tick_grace_current(self, now):
        """Tick the current session during cross-domain grace period,
        crediting effective vs idle based on actual activity detection.
        """
        self._current.end_time = now
        self._current.duration_seconds += self.sample_interval

        cursor_pos = _get_cursor_pos()
        cursor_moved = (
            self._last_cursor_pos is not None
            and cursor_pos != self._last_cursor_pos
        )
        kb_state = _get_keyboard_snapshot()
        kb_changed = (
            self._last_kb_state is not None
            and kb_state != self._last_kb_state
        )
        self._last_cursor_pos = cursor_pos
        self._last_kb_state = kb_state

        active = self._activity_from_hook or cursor_moved or kb_changed
        self._activity_from_hook = False

        if active:
            self._current.effective_seconds += self.sample_interval
            self._persistent_idle = 0.0
        else:
            self._current.idle_seconds += self.sample_interval

        p = self._pending_switch
        if p is not None:
            p["effective_during_grace"] += self.sample_interval if active else 0
            p["idle_during_grace"] += 0 if active else self.sample_interval

    # ── Internals ──────────────────────────────────────────────────

    def _tick_current(self, idle_seconds, now, hwnd=None):
        if self._current is None:
            return
        self._current.end_time = now
        self._current.duration_seconds += self.sample_interval

        # ── Cursor / keyboard tracking ─────────────────────────────────
        # Only cursor movement and real keystrokes count as user activity.
        # Window handle changes are NOT used — system popups, notifications,
        # and background processes can shift hwnd without user input.
        cursor_pos = _get_cursor_pos()
        cursor_moved = (
            self._last_cursor_pos is not None
            and cursor_pos != self._last_cursor_pos
        )
        kb_state = _get_keyboard_snapshot()
        kb_changed = (
            self._last_kb_state is not None
            and kb_state != self._last_kb_state
        )
        self._last_cursor_pos = cursor_pos
        self._last_kb_state = kb_state

        if self._activity_from_hook or cursor_moved or kb_changed:
            self._persistent_idle = 0.0
            self._idle_corrected = False
            self._activity_from_hook = False
        else:
            self._persistent_idle += self.sample_interval

        # ── Threshold: audio peak detection for entertainment ──────────
        # Audio actually playing (peak > 0) → user is definitely watching,
        # no idle timeout. Silent (paused) → standard 60s rule.
        if (
            self._current.category_key == "video"
            and self._audio_detector is not None
            and self._audio_detector.is_any_playing()
        ):
            # Audio peaks detected → always effective, reset idle timer
            self._persistent_idle = 0.0
            self._idle_corrected = False
            self._current.effective_seconds += self.sample_interval
            return

        if self._persistent_idle <= self._idle_limit():
            self._current.effective_seconds += self.sample_interval
        else:
            if not self._idle_corrected:
                # First idle tick: the threshold window (idle_threshold seconds)
                # was counted as effective while pending confirmation.
                # Move it from effective → idle so the last app doesn't get
                # credit for time the user was already away.
                correction = min(self._idle_limit(), self._current.effective_seconds)
                self._current.effective_seconds -= correction
                self._current.idle_seconds += correction
                self._idle_corrected = True
            self._current.idle_seconds += self.sample_interval

            # Idle time accumulates within the current session.
            # The focus timeline naturally shows the idle gap because
            # the session's effective_seconds stops growing while idle.

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
        if s:
            cat_key = s.category_key or ""
            is_ent = cat_key == "video"
            audio_playing = (
                is_ent and self._audio_detector is not None
                and self._audio_detector.is_any_playing()
            )
            is_eff = audio_playing or (self._persistent_idle <= self._idle_limit())
        else:
            cat_key = ""
            audio_playing = False
            is_eff = False

        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "date": s.date if s else datetime.now().strftime("%Y-%m-%d"),
            "session_id": s.session_id if s else "",
            "process_name": s.process_name if s else "",
            "exe_path": s.exe_path if s else "",
            "window_title": s.window_title if s else "",
            "normalized_title": s.normalized_title if s else "",
            "category_key": cat_key,
            "category_name": s.category_name if s else "",
            "active_rule": s.active_rule if s else "",
            "duration_seconds": s.duration_seconds if s else 0,
            "effective_seconds": s.effective_seconds if s else 0,
            "idle_seconds": idle_seconds,
            "session_idle_seconds": s.idle_seconds if s else 0,
            "persistent_idle": self._persistent_idle,
            "audio_playing": audio_playing,
            "is_user_active": self._persistent_idle <= self._idle_limit(),
            "is_effective": is_eff,
            "pending_switch_domain": self._pending_switch["domain"] if self._pending_switch else None,
            "pending_switch_elapsed": (
                int((datetime.now() - self._pending_switch["since"]).total_seconds())
                if self._pending_switch else 0
            ),
        }
