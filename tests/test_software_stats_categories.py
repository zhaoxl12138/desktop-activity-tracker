import sqlite3
from datetime import datetime

from daylens import database
from daylens.services import software_stats_service


def test_browser_titles_keep_their_own_categories(tmp_path):
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    today = datetime.now().strftime("%Y-%m-%d")
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
                "video",
                f"{today} 10:00:00",
                f"{today} 10:10:00",
                today,
                "chrome.exe",
                "YouTube",
                "video",
                "娱乐休闲",
                600,
                600,
                0,
            ),
            (
                "code",
                f"{today} 11:00:00",
                f"{today} 11:10:00",
                today,
                "chrome.exe",
                "GitHub",
                "coding",
                "编程开发",
                600,
                600,
                0,
            ),
        ],
    )
    conn.commit()
    conn.close()

    rows = software_stats_service.load_software_rows(
        str(db_path),
        {"chrome.exe": "Chrome"},
    )
    categories = {row["title"]: row["category_key"] for row in rows}

    assert categories["YouTube"] == "entertainment"
    assert categories["GitHub"] == "work"
