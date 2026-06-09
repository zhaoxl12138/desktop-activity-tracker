"""Poetry storage helpers split from the legacy database module."""

from __future__ import annotations

import sqlite3

ALLOWED_POETRY_AUTHORS = (
    "屈原",
    "曹操", "曹植", "陶渊明",
    "李白", "杜甫", "王维", "白居易", "李商隐", "杜牧", "孟浩然", "刘禹锡",
    "王之涣", "王昌龄", "张若虚", "温庭筠",
    "李煜",
    "苏轼", "辛弃疾", "李清照", "柳永", "陆游", "欧阳修",
    "晏几道", "秦观", "周邦彦", "姜夔", "王安石",
    "元好问",
    "纳兰性德", "王国维", "龚自珍",
)


def insert_poetry_line(db_path: str, author: str, content: str, origin: str = "", category: str = "") -> bool:
    conn = sqlite3.connect(db_path)
    try:
        before = conn.total_changes
        conn.execute(
            "INSERT OR IGNORE INTO poetry_lines (author, content, origin, category) VALUES (?, ?, ?, ?)",
            (author, content, origin, category),
        )
        conn.commit()
        return conn.total_changes > before
    finally:
        conn.close()


def get_random_poetry(read_conn, db_path: str) -> dict | None:
    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(ALLOWED_POETRY_AUTHORS))
        target = conn.execute(
            f"SELECT origin, author, category FROM poetry_lines "
            f"WHERE author IN ({placeholders}) "
            f"GROUP BY origin, author HAVING COUNT(*) >= 2 "
            f"ORDER BY RANDOM() LIMIT 1",
            ALLOWED_POETRY_AUTHORS,
        ).fetchone()
        if not target:
            return None
        rows = conn.execute(
            "SELECT content FROM poetry_lines "
            "WHERE origin = ? AND author = ? "
            "ORDER BY id",
            (target["origin"], target["author"]),
        ).fetchall()
        if len(rows) < 2:
            return None
        # Truncate to first 2 sentences (delimited by 。); fall back to first 2 lines
        full = "\n".join(row["content"] for row in rows)
        dots = [i for i, ch in enumerate(full) if ch == "。"]
        if len(dots) >= 2:
            end = dots[1] + 1
            if end < 20 and len(dots) >= 3:
                end = dots[2] + 1
            full = full[:end]
        else:
            full = "\n".join(row["content"] for row in rows[:2])

        # Reformat: exactly 2 lines, each ≤ 20 chars
        if "。" in full:
            text = full.replace("\n", "")
            sentences = [s for s in text.split("。") if s]
            text = "\n".join(s + "。" for s in sentences)
        else:
            text = full  # keep original DB line breaks

        raw_lines = [l for l in text.split("\n") if l]
        out = []
        for line in raw_lines:
            line = line[:20]
            if len(out) < 2:
                out.append(line)
            else:
                out[1] = (out[1] + line)[:20]
        while len(out) < 2:
            out.append("")
        full = "\n".join(out[:2])
        return {
            "author": target["author"],
            "content": full,
            "origin": target["origin"],
            "category": target["category"],
        }


def get_poetry_count(read_conn, db_path: str) -> int:
    with read_conn(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM poetry_lines").fetchone()
        return row[0] if row else 0
