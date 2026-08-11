"""Session tracker — 1s sampling + session aggregation + state machine."""

import ctypes
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta


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

_BROWSER_PROCS = {"chrome.exe", "msedge.exe", "msedgewebview2.exe", "iexplore.exe", "firefox.exe", "chromium.exe"}

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


# ── Transient window title filter ──────────────────────────────────
# Video players briefly expose internal widget class names (e.g.
# "QyWindow.GroupName.QyPlayerApp-Shadow") during buffering, ad
# breaks, or overlay transitions. These are code identifiers, not
# real content titles, and should never trigger a title_change split.
#
# Strategy: detect structural traits of internal window class names
# rather than hardcoding vendor-specific strings. Works across all
# players (iQiyi, Tencent Video, PotPlayer, VLC, etc.).

# Dot-separated CamelCase namespace: "Foo.Bar.Baz-Suffix"
_INTERNAL_CLASS_PATH = re.compile(r'\w+\.\w+(?:\.\w+)*')

# Internal window class name suffixes
_INTERNAL_WND_SUFFIX = re.compile(
    r'(?:Wnd|Dlg|Ctrl|Shadow|Overlay|Popup|Child|Host|Panel'
    r'|Container|Widget|Window|Frame)$'
)


def _is_transient_title(title: str) -> bool:
    """Return True if title is a transient/internal player window title."""
    if not title:
        return True
    # Real content titles always contain natural language
    # (spaces for word separation, or CJK characters).
    has_spaces = ' ' in title
    has_cjk = any('一' <= c <= '鿿' for c in title)
    if has_spaces or has_cjk:
        return False
    # Dot-separated class path → internal Qt/UI framework name
    if _INTERNAL_CLASS_PATH.search(title):
        return True
    # Common internal window class name suffixes
    if _INTERNAL_WND_SUFFIX.search(title):
        return True
    return False


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
    initial_title: str = ""
    _db_row_id: int = field(default=-1, repr=False)
    engaged_seconds: int = 0
    passive_seconds: int = 0
    metric_version: str = "attention-v1"
    classification_version: str = "legacy"


# ── Session tracker state machine ──


class SessionTracker:
    """Manages the current ActivitySession lifecycle.

    The caller (RecordingWorker) is responsible for pause/stop control.
    This class only handles session state transitions and counter ticks.
    """

    def __init__(self, config, classifier,
                 on_session_end=None, on_flush=None,
                 audio_detector=None, monotonic_clock=None):
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
        self.classification_version = getattr(
            classifier,
            "classification_version",
            "legacy",
        )
        self._on_session_end = on_session_end
        self._on_flush = on_flush
        self._audio_detector = audio_detector
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._last_flush_at = self._monotonic_clock()

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
        self._awaiting_activity: bool = False  # don't create new session while idle after auto-close
        self._last_tick_wall_time: datetime | None = None

    # ── Public API ──────────────────────────────────────────────────

    @property
    def current_session(self) -> ActivitySession | None:
        return self._current

    def finish_current(self, reason="manual"):
        """End the current session without starting a replacement session."""
        if self._current is None:
            return True
        self._current.end_time = datetime.now()
        self._current.switch_reason = reason
        return self._emit_session()

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
        self._awaiting_activity = False

    def _idle_limit(self, active_rule=None) -> int:
        """Return the idle threshold for the active session policy."""
        if active_rule is None and self._current is not None:
            active_rule = self._current.active_rule
        if active_rule == "passive_allowed":
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

        # Lock/sleep can pause the worker for minutes or hours. Treat a large
        # sampling gap as a hard boundary instead of attributing the gap to
        # the foreground application.
        if (
            self._last_tick_wall_time is not None
            and (now - self._last_tick_wall_time).total_seconds()
            > max(120, self.idle_threshold * 2)
        ):
            if self._current is not None:
                self._current.end_time = self._last_tick_wall_time
                self._current.switch_reason = "system_gap"
                self._emit_session()
            self._pending_switch = None
            self._persistent_idle = 0.0
            self._awaiting_activity = True
        self._last_tick_wall_time = now

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
        pid = win_info.get("pid") if win_info else None
        if process_name != self._last_process_name or pid != self._last_pid:
            self._last_pid = pid
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
                switched_immediately = self._handle_cross_domain(
                    now, date_str, new_domain,
                    process_name, exe_path, raw_title, norm_title,
                    cat_key, cat_name, active_rule,
                )
                if switched_immediately:
                    self._tick_current(idle_seconds, now, hwnd)
                self._maybe_flush()
                return self._make_snapshot(idle_seconds)

            # ── Same domain ────────────────────────────────────────
            else:
                if self._pending_switch is not None:
                    self._current.duration_seconds += (
                        self._pending_switch["effective_during_grace"]
                        + self._pending_switch["idle_during_grace"]
                    )
                    self._current.effective_seconds += self._pending_switch["effective_during_grace"]
                    self._current.idle_seconds += self._pending_switch["idle_during_grace"]
                    self._pending_switch = None

                # A session is an app-level record. Switching from Cursor to
                # Obsidian (even inside the same work domain) must not rewrite
                # the original process/title into one long session.
                app_changed = (
                    process_name.lower() != self._current.process_name.lower()
                    or cat_key != self._current.category_key
                )
                if app_changed:
                    self._current.end_time = now
                    self._current.switch_reason = "app_change"
                    self._emit_session()
                    self._pending_switch = None

                if not app_changed:
                    # For video sessions, detect title changes (e.g. episode switch)
                    # and split into a new session.
                    title_changed = (
                        cat_key == "video" and norm_title
                        and self._current.initial_title
                        and norm_title != self._current.initial_title
                    )
                    if title_changed and not _is_transient_title(norm_title):
                        self._current.end_time = now
                        self._current.switch_reason = "title_change"
                        self._emit_session()
                        self._pending_switch = None
                    else:
                        self._pending_switch = None
                        self._current.process_name = process_name
                        self._current.window_title = raw_title
                        # Don't overwrite title with transient/internal window names
                        if not _is_transient_title(norm_title):
                            self._current.normalized_title = norm_title
                        self._current.category_key = cat_key
                        self._current.category_name = cat_name
                        self._current.active_rule = active_rule

        # If previous session was auto-closed due to entertainment idle,
        # don't create a new session until the user is actually active.
        if self._current is None and self._awaiting_activity:
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
            if not (self._activity_from_hook or cursor_moved or kb_changed):
                return self._make_snapshot(idle_seconds)
            self._awaiting_activity = False

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
                initial_title=norm_title,
                classification_version=self.classification_version,
            )

        self._tick_current(idle_seconds, now, hwnd)
        self._tick_count += 1
        self._maybe_flush()
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

        Entertainment (video/gaming) is exempt from the grace period —
        the user intentionally opened a video player, no need to wait.
        """
        # Entertainment: switch immediately, no grace period
        if new_domain == "entertainment":
            p = self._pending_switch
            if p is None or p.get("domain") != new_domain:
                if p is not None:
                    effective = p["effective_during_grace"]
                    idle = p["idle_during_grace"]
                    self._current.duration_seconds += effective + idle
                    self._current.effective_seconds += effective
                    self._current.idle_seconds += idle
                p = {
                    "domain": new_domain,
                    "since": now,
                    "process_name": process_name,
                    "exe_path": exe_path,
                    "raw_title": raw_title,
                    "norm_title": norm_title,
                    "cat_key": cat_key,
                    "cat_name": cat_name,
                    "active_rule": active_rule,
                    "pid": self._last_pid,
                    "effective_during_grace": 0,
                    "idle_during_grace": 0,
                    "idle_corrected": False,
                }
                self._pending_switch = p
                self._persistent_idle = 0.0
                self._idle_corrected = False
                self._last_cursor_pos = None
                self._last_kb_state = None
            else:
                p.update(
                    {
                        "process_name": process_name,
                        "exe_path": exe_path,
                        "raw_title": raw_title,
                        "norm_title": norm_title,
                        "cat_key": cat_key,
                        "cat_name": cat_name,
                        "active_rule": active_rule,
                        "pid": self._last_pid,
                    }
                )

            self._current.end_time = p["since"]
            self._current.switch_reason = "domain_change"
            if not self._emit_session():
                self._tick_grace_current(now)
                return False

            effective = p["effective_during_grace"]
            idle = p["idle_during_grace"]
            if effective + idle == 0:
                self._persistent_idle = 0.0
                self._idle_corrected = False
            self._last_cursor_pos = None
            self._last_kb_state = None
            self._current = ActivitySession(
                session_id=uuid.uuid4().hex[:12],
                start_time=p["since"],
                end_time=now,
                date=date_str,
                process_name=p["process_name"],
                exe_path=p["exe_path"],
                window_title=p["raw_title"],
                normalized_title=p["norm_title"],
                category_key=p["cat_key"],
                category_name=p["cat_name"],
                active_rule=p["active_rule"],
                duration_seconds=effective + idle,
                effective_seconds=effective,
                idle_seconds=idle,
                initial_title=p["norm_title"],
                classification_version=self.classification_version,
            )
            self._pending_switch = None
            return True

        if self._pending_switch is None or self._pending_switch["domain"] != new_domain:
            if self._pending_switch is not None:
                self._current.duration_seconds += (
                    self._pending_switch["effective_during_grace"]
                    + self._pending_switch["idle_during_grace"]
                )
                self._current.effective_seconds += self._pending_switch["effective_during_grace"]
                self._current.idle_seconds += self._pending_switch["idle_during_grace"]
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
                "pid": self._last_pid,
                "effective_during_grace": 0,
                "idle_during_grace": 0,
                "idle_corrected": False,
            }
            self._tick_grace_current(now)
            return False

        # Always tick first so every second is accounted correctly
        self._tick_grace_current(now)
        elapsed = (now - self._pending_switch["since"]).total_seconds()
        if elapsed < self.cross_group_grace:
            return False

        # ── Grace period expired → confirm switch ──────────────────
        p = self._pending_switch
        self._current.end_time = p["since"]
        self._current.switch_reason = "domain_change"
        if not self._emit_session():
            return False

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
            initial_title=p["norm_title"],
            classification_version=self.classification_version,
        )
        self._pending_switch = None
        self._last_cursor_pos = None
        self._last_kb_state = None
        return False

    def _maybe_flush(self):
        """Persist the current session after real monotonic time has elapsed."""
        now = self._monotonic_clock()
        if now - self._last_flush_at < self.flush_interval:
            return
        self._last_flush_at = now
        if self._on_flush and self._current is not None:
            self._on_flush(self._current)

    def _tick_grace_current(self, now):
        """Tick the current session during cross-domain grace period,
        crediting effective vs idle based on actual activity detection.
        """
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

        p = self._pending_switch
        if p is None:
            return

        audio_playing = self._is_audio_playing(
            p.get("cat_key", ""),
            p.get("pid", self._last_pid),
        )
        if active or audio_playing:
            self._persistent_idle = 0.0
            self._idle_corrected = False
            p["idle_corrected"] = False
        else:
            self._persistent_idle += self.sample_interval

        idle_limit = self._idle_limit(
            p.get(
                "active_rule",
                self._current.active_rule if self._current is not None else None,
            )
        )
        if self._persistent_idle <= idle_limit:
            p["effective_during_grace"] += self.sample_interval
            return

        if not p.get("idle_corrected", False):
            correction = min(
                idle_limit,
                p["effective_during_grace"],
            )
            p["effective_during_grace"] -= correction
            p["idle_during_grace"] += correction
            p["idle_corrected"] = True
        p["idle_during_grace"] += self.sample_interval

    # ── Internals ──────────────────────────────────────────────────

    def _is_audio_playing(self, category_key, pid):
        return (
            category_key == "video"
            and self._audio_detector is not None
            and self._audio_detector.is_playing(pid)
        )

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
        if self._is_audio_playing(
            self._current.category_key,
            self._last_pid,
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

            # Auto-close entertainment sessions when idle exceeds threshold.
            # Prevents a 3-hour movie session from spanning 19:29-22:34
            # when the user actually left at 20:00 and came back at 22:00.
            if (self._current.category_key == "video"
                    and self._persistent_idle > self._idle_limit()):
                # Backdate end_time to when the user actually stopped
                # (now minus the idle threshold window).
                limit = self._idle_limit()
                backdate = now - timedelta(seconds=limit)
                active_duration = max(0, self._current.duration_seconds - int(self._persistent_idle))
                self._current.end_time = backdate
                self._current.duration_seconds = active_duration
                self._current.effective_seconds = min(
                    self._current.effective_seconds, active_duration
                )
                self._current.idle_seconds = 0
                self._current.switch_reason = "entertainment_idle"
                self._emit_session()
                self._awaiting_activity = True

    def _emit_session(self):
        if self._current is None:
            return True
        if self._on_session_end:
            persisted = self._on_session_end(self._current)
            if persisted is False:
                return False
        self._current = None
        return True

    def _make_snapshot(self, idle_seconds):
        """Build a UI-compatible snapshot dict for the sample_updated signal.

        When a cross-domain switch is pending (grace period), display
        the pending target's category so the real-time monitor reflects
        what the user is actually doing right now. Session persistence
        still waits for the grace period to complete.
        """
        s = self._current
        p = self._pending_switch

        if s:
            cat_key = s.category_key or ""
            cat_name = s.category_name or ""
        else:
            cat_key = ""
            cat_name = ""

        # Use pending switch target for real-time display
        if p:
            cat_key = p.get("cat_key", cat_key)
            cat_name = p.get("cat_name", cat_name)

        active_rule = (
            p.get("active_rule", s.active_rule if s else "")
            if p else (s.active_rule if s else "")
        )
        audio_playing = self._is_audio_playing(
            cat_key,
            p.get("pid", self._last_pid) if p else self._last_pid,
        )
        idle_limit = self._idle_limit(active_rule)
        is_eff = audio_playing or (self._persistent_idle <= idle_limit)
        if s is None and not p:
            audio_playing = False
            is_eff = False

        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "date": s.date if s else datetime.now().strftime("%Y-%m-%d"),
            "session_id": s.session_id if s else "",
            "process_name": (p.get("process_name", s.process_name if s else "") if p else (s.process_name if s else "")),
            "exe_path": (p.get("exe_path", s.exe_path if s else "") if p else (s.exe_path if s else "")),
            "window_title": (p.get("raw_title", s.window_title if s else "") if p else (s.window_title if s else "")),
            "normalized_title": (p.get("norm_title", s.normalized_title if s else "") if p else (s.normalized_title if s else "")),
            "category_key": cat_key,
            "category_name": cat_name,
            "active_rule": active_rule,
            "duration_seconds": s.duration_seconds if s else 0,
            "effective_seconds": s.effective_seconds if s else 0,
            "idle_seconds": idle_seconds,
            "session_idle_seconds": s.idle_seconds if s else 0,
            "persistent_idle": self._persistent_idle,
            "audio_playing": audio_playing,
            "is_user_active": self._persistent_idle <= idle_limit,
            "is_effective": is_eff,
            "pending_switch_domain": self._pending_switch["domain"] if self._pending_switch else None,
            "pending_switch_elapsed": (
                int((datetime.now() - self._pending_switch["since"]).total_seconds())
                if self._pending_switch else 0
            ),
        }
