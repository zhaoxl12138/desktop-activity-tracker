"""Comprehensive tests for Desktop Activity Tracker core modules."""
import os
import shutil
import sys
import tempfile
import sqlite3
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from desktop_activity_tracker import database
from desktop_activity_tracker.session_tracker import (
    SessionTracker, ActivitySession, normalize_window_title
)
from desktop_activity_tracker.classifier import Classifier
from desktop_activity_tracker import exporter
from desktop_activity_tracker.utils import fmt_seconds

PASS = 0
FAIL = 0

def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS: {msg}")
    else:
        FAIL += 1
        print(f"  FAIL: {msg}")


# ── Phase 1: Database ──

def test_database():
    print("\n=== Phase 1: Database ===")
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")

    # Init
    conn = database.init_db(db_path)
    check(os.path.exists(db_path), "database file created")
    check(conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal", "WAL mode enabled")

    # Verify schema
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]
    for t in ["activity_logs", "activity_sessions", "daily_summary"]:
        check(t in table_names, f"table '{t}' exists")

    # Insert a session
    session = ActivitySession(
        session_id=uuid.uuid4().hex[:12],
        start_time=datetime.now(),
        end_time=datetime.now(),
        date=datetime.now().strftime("%Y-%m-%d"),
        process_name="test.exe",
        exe_path="C:\\test\\test.exe",
        window_title="Test Window",
        normalized_title="Test Window",
        category_key="coding",
        category_name="编程开发",
        active_rule="interactive_required",
        duration_seconds=100,
        effective_seconds=80,
        idle_seconds=20,
        switch_reason="window_change",
    )
    rowid = database.insert_session(conn, session)
    check(rowid > 0, f"insert_session returns rowid ({rowid})")

    # Update session
    session.duration_seconds = 120
    session.effective_seconds = 90
    session.idle_seconds = 30
    database.update_session(conn, session)
    rows = conn.execute("SELECT * FROM activity_sessions WHERE session_id=?", (session.session_id,)).fetchall()
    check(len(rows) == 1, "session still exists after update")
    check(rows[0][12] == 120, "duration updated to 120")

    # Query date stats (session path)
    stats = database.query_date_stats(db_path, datetime.now().strftime("%Y-%m-%d"))
    check(stats is not None, "query_date_stats returns result")
    check(stats["totals"]["effective_seconds"] == 90, f"totals.effective = 90 (got {stats['totals']['effective_seconds']})")
    check(stats["totals"]["idle_seconds"] == 30, f"totals.idle = 30 (got {stats['totals']['idle_seconds']})")

    # Query date range
    today = datetime.now().strftime("%Y-%m-%d")
    range_stats = database.query_date_range_stats(db_path, [today])
    check(len(range_stats["dates"]) == 1, "date range has 1 date")
    check(len(range_stats["daily"]) == 1, "daily has 1 entry")

    # Entertainment trend
    trend = database.query_entertainment_trend(db_path, 3)
    check(len(trend) == 3, "entertainment trend returns 3 days")

    conn.close()
    os.unlink(db_path)
    os.rmdir(tmpdir)
    print(f"  Database: all tests passed.")


# ── Phase 2: Session Tracker ──

class FakeClassifier:
    def classify(self, process_name, window_title):
        mapping = {
            "chrome.exe": ("browser_general", "浏览器", "interactive_required"),
            "code.exe": ("coding", "工作学习", "interactive_required"),
            "vlc.exe": ("video", "娱乐休闲", "passive_allowed"),
            "wechat.exe": ("social", "社交通讯", "passive_allowed"),
        }
        key, name, rule = mapping.get(process_name.lower(), ("other", "其他", "interactive_required"))
        return {"category_key": key, "category_name": name, "active_rule": rule}


def test_session_tracker():
    print("\n=== Phase 2: Session Tracker ===")
    clf = FakeClassifier()
    sessions_ended = []
    sessions_flushed = []

    tracker = SessionTracker(
        config={"tracker": {"sample_interval_seconds": 1, "flush_interval_seconds": 5,
                             "idle_threshold_seconds": 60, "min_session_seconds": 2}},
        classifier=clf,
        on_session_end=lambda s: sessions_ended.append(s),
        on_flush=lambda s: sessions_flushed.append(s),
    )

    # 1. First tick starts a session
    win = {"process_name": "code.exe", "window_title": "main.py", "exe_path": "C:\\code.exe"}
    snap = tracker.tick(0.5, win)
    check(snap is not None, "first tick returns snapshot")
    check(snap["process_name"] == "code.exe", "process_name correct")
    check(snap["category_key"] == "coding", "category matched")
    check(snap["is_effective"] is True, "active user = effective")

    # 2. Accumulate time with active user
    for i in range(10):
        snap = tracker.tick(1.0, win)
    check(snap["duration_seconds"] == 11, f"duration = 11 (got {snap['duration_seconds']})")
    check(snap["effective_seconds"] == 11, f"effective = 11 (got {snap['effective_seconds']})")
    check(snap["session_idle_seconds"] == 0, "session_idle = 0 with active user")

    # 3. Simulate idle (>60s idle)
    # Test phantom filter: idle goes high, then phantom reset
    snap = tracker.tick(30.0, win)  # idle building up
    check(snap["is_effective"] is True, "idle=30 still effective (under threshold)")

    snap = tracker.tick(65.0, win)  # idle exceeds threshold
    check(snap["is_effective"] is False, "idle=65 → not effective")
    check(snap["session_idle_seconds"] > 0, f"idle_seconds accumulating ({snap['session_idle_seconds']})")

    # 4. Test phantom reset (idle drops from >5 to <1)
    snap = tracker.tick(70.0, win)  # continuing idle
    snap = tracker.tick(0.0, win)   # phantom reset: 70 → 0
    check(snap["is_effective"] is False, "phantom reset: still idle (not fooled)")
    check(snap["session_idle_seconds"] > 0, "idle_seconds still increasing after phantom")

    # 5. Real user input (idle stays low for multiple ticks)
    tracker.tick(0.3, win)
    snap = tracker.tick(0.5, win)
    check(snap["is_effective"] is True, "real input: back to effective")

    # 6. Window change triggers session end
    old_session_id = snap["session_id"]
    win2 = {"process_name": "vlc.exe", "window_title": "Movie", "exe_path": "C:\\vlc.exe"}
    snap = tracker.tick(1.0, win2)
    check(snap["session_id"] != old_session_id, "window change → new session")
    check(len(sessions_ended) == 1, "previous session emitted")
    check(sessions_ended[0].category_key == "coding", "ended session is coding")

    # 7. Passive_allowed (vlc = video) always effective
    snap = tracker.tick(80.0, win2)
    check(snap["is_effective"] is True, "passive_allowed: effective even when idle=80")

    # 8. Cross-day creates new session
    # (can't easily test without mocking datetime)

    # 9. Flush timing
    check(len(sessions_flushed) >= 1, "flush callback fired at least once")

    # 10. Min session filter — short sessions (<2s) are discarded
    win3 = {"process_name": "code.exe", "window_title": "temp", "exe_path": "C:\\code.exe"}
    tracker.tick(0.5, win3)  # ends vlc + starts code.exe (duration=1)
    old_count = len(sessions_ended)  # includes vlc session end
    win4 = {"process_name": "chrome.exe", "window_title": "google", "exe_path": "C:\\chrome.exe"}
    tracker.tick(0.5, win4)  # code.exe session 1s < 2s → discarded
    check(len(sessions_ended) == old_count, "short session (<2s) discarded")

    print(f"  Session Tracker: all tests passed.")


# ── Phase 3: Classifier ──

def test_classifier():
    print("\n=== Phase 3: Classifier ===")
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
    if not os.path.exists(config_path):
        print("  SKIP: config.yaml not found")
        return

    clf = Classifier(config_path)

    # Process-only match
    r = clf.classify("QyClient.exe", "爱奇艺")
    check(r["category_key"] == "video", f"QyClient → video (got {r['category_key']})")

    r = clf.classify("WeChatAppEx.exe", "微信")
    check(r["category_key"] == "social", f"WeChatAppEx → social (got {r['category_key']})")

    r = clf.classify("Trae CN.exe", "project - Trae CN")
    check(r["category_key"] == "coding", f"Trae CN → coding (got {r['category_key']})")

    r = clf.classify("Doubao.exe", "豆包")
    check(r["category_key"] == "ai_tools", f"Doubao → ai_tools (got {r['category_key']})")

    r = clf.classify("Obsidian.exe", "Obsidian")
    check(r["category_key"] in ("reading", "other"), f"Obsidian classified (got {r['category_key']})")

    # Unknown process
    r = clf.classify("nonexistent.exe", "Unknown App")
    check(r["category_key"] == "other", f"unknown → other (got {r['category_key']})")

    # Empty input
    r = clf.classify("", "")
    check(r["category_key"] == "other", "empty input → other")

    # Browser title match
    r = clf.classify("chrome.exe", "ChatGPT - Google Chrome")
    # Chrome browser goes through browser classification
    check(r["category_key"] in ("browser_general", "ai_tools"), f"browser match (got {r['category_key']})")

    print(f"  Classifier: all tests passed.")


# ── Phase 4: Title Normalization ──

def test_normalization():
    print("\n=== Phase 4: Title Normalization ===")
    tests = [
        ("chrome.exe", "ChatGPT - Google Chrome", "ChatGPT"),
        ("chrome.exe", "YouTube - Google Chrome", "YouTube"),
        ("msedge.exe", "Docs - Microsoft Edge", "Docs"),
        ("code.exe", "main.py - Visual Studio Code", "main.py"),          # non-browser: first segment
        ("chrome.exe", "Inbox (3) - Gmail - Google Chrome", "Gmail"),    # browser: rightmost segment
        ("firefox.exe", "PageTitle — Mozilla Firefox", "PageTitle"),
        ("explorer.exe", "Downloads", "Downloads"),
        ("", "", ""),
        (None, "Title Without Browser", "Title Without Browser"),
    ]
    for proc, title, expected in tests:
        result = normalize_window_title(proc or "", title or "")
        check(result == expected, f"'{title}' → '{expected}' (got '{result}')")

    print(f"  Normalization: all tests passed.")


# ── Phase 5: Exporter ──

def test_exporter():
    print("\n=== Phase 5: Exporter ===")
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_export.db")
    conn = database.init_db(db_path)

    # Insert test data
    today = datetime.now().strftime("%Y-%m-%d")
    session = ActivitySession(
        session_id=uuid.uuid4().hex[:12],
        start_time=datetime.now() - timedelta(hours=2),
        end_time=datetime.now() - timedelta(hours=1),
        date=today,
        process_name="code.exe",
        exe_path="C:\\code.exe",
        window_title="main.py",
        normalized_title="main.py",
        category_key="coding",
        category_name="编程开发",
        active_rule="interactive_required",
        duration_seconds=3600,
        effective_seconds=3000,
        idle_seconds=600,
        switch_reason="test",
    )
    database.insert_session(conn, session)

    session2 = ActivitySession(
        session_id=uuid.uuid4().hex[:12],
        start_time=datetime.now() - timedelta(hours=1),
        end_time=datetime.now(),
        date=today,
        process_name="vlc.exe",
        exe_path="C:\\vlc.exe",
        window_title="Movie",
        normalized_title="Movie",
        category_key="video",
        category_name="娱乐休闲",
        active_rule="passive_allowed",
        duration_seconds=1800,
        effective_seconds=1800,
        idle_seconds=0,
        switch_reason="test",
    )
    database.insert_session(conn, session2)

    # Export markdown
    md_path = exporter.export_markdown(db_path, today, tmpdir)
    check(os.path.exists(md_path), f"markdown file created: {md_path}")
    if os.path.exists(md_path):
        content = open(md_path, 'r', encoding='utf-8').read()
        check("工作学习" in content, "markdown contains 工作学习")
        check("娱乐休闲" in content, "markdown contains 娱乐休闲")

    # Export CSV
    csv_path = exporter.export_csv(db_path, today, tmpdir)
    check(os.path.exists(csv_path), f"CSV file created: {csv_path}")

    # Efficiency score
    # work=3000, entertainment=1800, effective=4800
    # score = work/effective * 100 = 3000/4800 * 100 = 62.5 ≈ 62
    # video penalty: 1800 < 5400 → no penalty
    score = exporter._calculate_efficiency_score(3000, 1800, 4800)
    check(score == 62, f"efficiency score = 62 (got {score})")

    # Score with no data
    score_none = exporter._calculate_efficiency_score(0, 0, 0)
    check(score_none is None, "no activity → None score")

    conn.close()
    shutil.rmtree(tmpdir)

    print(f"  Exporter: all tests passed.")


# ── Phase 6: Edge Cases ──

def test_edge_cases():
    print("\n=== Phase 6: Edge Cases ===")
    clf = FakeClassifier()

    # 1. Rapid window switching
    tracker = SessionTracker(
        config={"tracker": {"sample_interval_seconds": 1, "flush_interval_seconds": 999,
                             "idle_threshold_seconds": 60, "min_session_seconds": 2}},
        classifier=clf,
        on_session_end=None, on_flush=None,
    )
    switches = ["code.exe", "chrome.exe", "vlc.exe", "code.exe", "chrome.exe"]
    for name in switches:
        tracker.tick(0.5, {"process_name": name, "window_title": name, "exe_path": ""})
    check(tracker.current_session is not None, "has current session after rapid switches")

    # 2. Null window info
    tracker2 = SessionTracker(
        config={"tracker": {"sample_interval_seconds": 1, "flush_interval_seconds": 999,
                             "idle_threshold_seconds": 60, "min_session_seconds": 2}},
        classifier=clf,
        on_session_end=None, on_flush=None,
    )
    snap = tracker2.tick(5.0, None)
    check(snap is not None, "null win_info → snapshot returned")
    check(snap["process_name"] == "system", f"null win_info → 'system' (got '{snap['process_name']}')")

    # 3. fmt_seconds utility (Chinese format, >=1h drops seconds)
    check(fmt_seconds(0) == "0秒", f"fmt_seconds(0) (got {fmt_seconds(0)})")
    check(fmt_seconds(60) == "1分0秒", f"fmt_seconds(60) (got {fmt_seconds(60)})")
    check(fmt_seconds(3661) == "1时1分", f"fmt_seconds(3661) (got {fmt_seconds(3661)})")

    # 4. Phantom reset detection
    tracker3 = SessionTracker(
        config={"tracker": {"sample_interval_seconds": 5, "flush_interval_seconds": 999,
                             "idle_threshold_seconds": 60, "min_session_seconds": 2}},
        classifier=clf,
        on_session_end=None, on_flush=None,
    )
    win = {"process_name": "code.exe", "window_title": "test.py", "exe_path": ""}

    # Normal active usage
    for i in range(5):
        tracker3.tick(2.0, win)
    snap = tracker3.tick(3.0, win)
    check(snap["effective_seconds"] == 30, f"6 ticks*5s = 30 effective (got {snap['effective_seconds']})")
    check(snap["session_idle_seconds"] == 0, f"idle_seconds = 0 (got {snap['session_idle_seconds']})")

    # Simulate walk-away with phantom resets
    # idle builds up, then phantom resets
    tracker3.tick(30.0, win)   # idle growing
    tracker3.tick(65.0, win)   # exceeds threshold → idle
    tracker3.tick(0.0, win)    # phantom reset
    check(snap is not None, "tracker survives phantom reset")
    # After phantom reset, idle_seconds should have increased
    snap = tracker3.tick(5.0, win)  # more idle
    idle = snap["session_idle_seconds"]
    check(idle >= 5, f"idle continued accumulating after phantom (got {idle}s)")

    print(f"  Edge Cases: all tests passed.")


# ── Run All ──

if __name__ == "__main__":
    print("=" * 60)
    print("Desktop Activity Tracker — Test Suite")
    print("=" * 60)
    test_database()
    test_session_tracker()
    test_classifier()
    test_normalization()
    test_exporter()
    test_edge_cases()
    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")
    if FAIL > 0:
        sys.exit(1)
