from __future__ import annotations

import sqlite3

from daylens import database


def test_range_stats_keep_process_and_category_as_separate_dimensions(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT INTO activity_sessions
            (session_id,start_time,end_time,date,process_name,normalized_title,
             category_key,category_name,duration_seconds,effective_seconds,
             idle_seconds)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                "youtube",
                "2026-07-20 10:00:00",
                "2026-07-20 10:10:00",
                "2026-07-20",
                "chrome.exe",
                "YouTube",
                "video",
                "娱乐休闲",
                600,
                600,
                0,
            ),
            (
                "github",
                "2026-07-20 11:00:00",
                "2026-07-20 11:10:00",
                "2026-07-20",
                "chrome.exe",
                "GitHub",
                "coding",
                "工作学习",
                600,
                600,
                0,
            ),
        ],
    )
    conn.commit()
    conn.close()

    result = database.query_date_range_stats(
        str(db_path),
        ["2026-07-20"],
    )

    browser_rows = [
        row for row in result["by_app"]
        if row["process_name"] == "chrome.exe"
    ]
    assert {
        (row["category_key"], row["effective_seconds"])
        for row in browser_rows
    } == {("video", 600), ("coding", 600)}


def test_legacy_range_uses_same_work_and_entertainment_category_sets(tmp_path):
    db_path = tmp_path / "usage.db"
    conn = database.init_db(str(db_path))
    for index, (category_key, seconds) in enumerate(
        [("office", 120), ("creative", 180), ("gaming", 240)]
    ):
        database.insert_activity_log(
            conn,
            {
                "timestamp": f"2026-07-19 10:0{index}:00",
                "date": "2026-07-19",
                "process_name": f"{category_key}.exe",
                "window_title": category_key,
                "category_key": category_key,
                "category_name": category_key,
                "active_rule": "interactive_required",
                "is_user_active": True,
                "is_effective": True,
                "idle_seconds": 0,
                "duration_seconds": seconds,
            },
        )
    database.close_db(conn)

    result = database.query_date_range_stats(
        str(db_path),
        ["2026-07-19"],
    )

    assert result["totals"]["work_seconds"] == 300
    assert result["totals"]["video_seconds"] == 240
