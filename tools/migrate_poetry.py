#!/usr/bin/env python3
"""Migrate poetry from chinese-poetry JSON to DayLens poetry_lines table."""

import json
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent / "chinese-poetry"
DB_PATH = Path(__file__).parent.parent / "data" / "usage.db"

AUTHORS = {
    "屈原",
    "曹操", "曹植", "陶渊明",
    "李白", "杜甫", "王维", "白居易", "李商隐", "杜牧", "孟浩然", "刘禹锡",
    "王之涣", "王昌龄", "张若虚", "温庭筠",
    "李煜",
    "苏轼", "辛弃疾", "李清照", "柳永", "陆游", "欧阳修",
    "晏几道", "秦观", "周邦彦", "姜夔", "王安石",
    "元好问",
    "纳兰性德", "王国维", "龚自珍",
}

_TRAD = {
    "蘇軾": "苏轼", "歐陽修": "欧阳修", "陸游": "陆游", "晏幾道": "晏几道",
    "秦觀": "秦观", "周邦彥": "周邦彦", "辛棄疾": "辛弃疾", "李清照": "李清照",
    "元好問": "元好问", "王維": "王维", "溫庭筠": "温庭筠", "劉禹錫": "刘禹锡",
    "張若虛": "张若虚", "李商隱": "李商隐", "王昌齡": "王昌龄", "王之渙": "王之涣",
    "陶淵明": "陶渊明", "龔自珍": "龚自珍", "王國維": "王国维",
}


def _norm(name):
    return _TRAD.get(name, name)


def _import_json(conn, filepath, category="", author_override=None):
    with open(filepath, encoding="utf-8") as f:
        poems = json.load(f)
    if not isinstance(poems, list):
        return 0
    count = 0
    for p in poems:
        if not isinstance(p, dict):
            continue
        author = author_override or _norm(p.get("author", ""))
        if author not in AUTHORS:
            continue
        title = p.get("title", "") or p.get("rhythmic", "")
        # Some files use "content" or "para" instead of "paragraphs"
        lines = p.get("paragraphs") or p.get("content") or p.get("para") or []
        for line in lines:
            line = line.strip()
            if line:
                conn.execute(
                    "INSERT OR IGNORE INTO poetry_lines (author, content, origin, category) VALUES (?,?,?,?)",
                    (author, line, title, category),
                )
                count += 1
    return count


def main():
    conn = sqlite3.connect(str(DB_PATH))
    total = 0

    for f in sorted((DATA_DIR / "全唐诗").glob("poet.tang.*.json")):
        n = _import_json(conn, f, "唐诗")
        if n:
            print(f"  {f.name}: {n} lines")
        total += n

    for f in sorted((DATA_DIR / "宋词").glob("ci.song.*.json")):
        n = _import_json(conn, f, "宋词")
        if n:
            print(f"  {f.name}: {n} lines")
        total += n

    for sub in ["huajianji", "nantang"]:
        subdir = DATA_DIR / "五代诗词" / sub
        if subdir.is_dir():
            for f in subdir.glob("*.json"):
                n = _import_json(conn, f, "五代诗词")
                if n:
                    print(f"  五代/{sub}/{f.name}: {n} lines")
                total += n

    n = _import_json(conn, DATA_DIR / "楚辞" / "chuci.json", "楚辞")
    print(f"  楚辞: {n} lines")
    total += n

    n = _import_json(conn, DATA_DIR / "纳兰性德" / "纳兰性德诗集.json", "清词")
    print(f"  纳兰性德: {n} lines")
    total += n

    n = _import_json(conn, DATA_DIR / "曹操诗集" / "caocao.json", "魏晋", author_override="曹操")
    print(f"  曹操: {n} lines")
    total += n

    conn.commit()
    conn.close()
    print(f"\nTotal: {total} lines imported")


if __name__ == "__main__":
    main()
