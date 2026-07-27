from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from desktop_activity_tracker.repositories.poetry_repository import get_random_poetry
from desktop_activity_tracker.services import shell_service


@contextmanager
def _read_conn(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def test_get_random_poetry_returns_two_lines_from_allowed_authors(tmp_path):
    db_path = tmp_path / "poetry.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE poetry_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            content TEXT NOT NULL UNIQUE,
            origin TEXT,
            category TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO poetry_lines (author, content, origin, category) VALUES (?, ?, ?, ?)",
        [
            ("苏轼", "明月几时有", "水调歌头", ""),
            ("苏轼", "把酒问青天", "水调歌头", ""),
            ("柳永", "寒蝉凄切", "雨霖铃", ""),
            ("柳永", "对长亭晚", "雨霖铃", ""),
            ("柳永", "骤雨初歇", "雨霖铃", ""),
        ],
    )
    conn.commit()
    conn.close()

    row = get_random_poetry(_read_conn, str(db_path))

    assert row is not None
    assert row["author"] in {"苏轼", "柳永"}
    if row["author"] == "柳永":
        assert row["origin"] == "雨霖铃"
        assert row["content"] == "寒蝉凄切\n对长亭晚"
    else:
        assert row["origin"] == "水调歌头"
        assert row["content"] == "明月几时有\n把酒问青天"


def test_load_poetry_hint_includes_author_only(monkeypatch):
    monkeypatch.setattr(
        shell_service.database,
        "get_random_poetry",
        lambda db_path: {
            "author": "纳兰性德",
            "origin": "浣溪沙",
            "content": "谁念西风独自凉\n萧萧黄叶闭疏窗",
            "category": "",
        },
    )

    hint = shell_service.load_poetry_hint("dummy.db", "fallback")

    assert hint == "谁念西风独自凉\n萧萧黄叶闭疏窗 ——纳兰性德"


def test_load_poetry_hint_cleans_extra_blank_lines(monkeypatch):
    monkeypatch.setattr(
        shell_service.database,
        "get_random_poetry",
        lambda db_path: {"author": "李白", "content": "  第一行  \r\n\n 第二行\t", "origin": "", "category": ""},
    )

    assert shell_service.load_poetry_hint("dummy.db", "fallback") == "第一行\n第二行 ——李白"


def test_get_random_poetry_preserves_full_lines_for_font_aware_ui_elision(
    tmp_path,
):
    db_path = tmp_path / "poetry.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE poetry_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            content TEXT NOT NULL UNIQUE,
            origin TEXT,
            category TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO poetry_lines (author, content, origin, category) VALUES (?, ?, ?, ?)",
        [
            ("李白", "这是第一句特别长特别长特别长特别长甲乙丙丁", "长诗", ""),
            ("李白", "这是第二句特别长特别长特别长特别长甲乙丙丁", "长诗", ""),
        ],
    )
    conn.commit()
    conn.close()

    row = get_random_poetry(_read_conn, str(db_path))

    assert row is not None
    lines = row["content"].split("\n")
    assert len(lines) == 2
    assert lines == [
        "这是第一句特别长特别长特别长特别长甲乙丙丁",
        "这是第二句特别长特别长特别长特别长甲乙丙丁",
    ]


def test_load_poetry_hint_does_not_apply_character_count_truncation(
    monkeypatch,
):
    first = "这是第一句特别长特别长特别长特别长甲乙丙丁"
    second = "这是第二句特别长特别长特别长特别长甲乙丙丁"
    monkeypatch.setattr(
        shell_service.database,
        "get_random_poetry",
        lambda _db_path: {
            "author": "李白",
            "content": f"{first}\n{second}",
            "origin": "长诗",
            "category": "",
        },
    )

    assert shell_service.load_poetry_hint("dummy.db", "fallback") == (
        f"{first}\n{second} ——李白"
    )
