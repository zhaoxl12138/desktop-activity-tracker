#!/usr/bin/env python3
"""Fetch classical Chinese poetry from the chinese-poetry GitHub repo.

Downloads Song dynasty ci (宋词) JSON files and stores individual lines
from 8 target poets into the DayLens database.

Target poets: 纳兰性德, 辛弃疾, 苏轼, 柳永, 晏几道, 王国维, 秦观, 陆游

Usage:
    python tools/fetch_poetry.py          # download + store
    python tools/fetch_poetry.py --count  # show per-author counts
"""

import argparse
import json
import os
import sys
import time
from urllib.parse import quote

import requests

# Make daylens importable when running as script
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from daylens.database import get_poetry_count, insert_poetry_line, init_db
from daylens import get_data_dir

TARGET_AUTHORS = {
    "纳兰性德", "辛弃疾", "苏轼", "柳永",
    "晏几道", "王国维", "秦观", "陆游",
}

# chinese-poetry repo — Song ci JSON files (now under 宋词/ directory)
CI_BASE = "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/%E5%AE%8B%E8%AF%8D"

# Actual file names in the repo (no leading zeros)
CI_FILES = (
    ["ci.song.0.json"]
    + [f"ci.song.{i}.json" for i in range(1000, 22000, 1000)]
    + [f"ci.song.{i}.json" for i in range(10000, 21000, 10000)]
    + ["ci.song.2019y.json"]
)

# 纳兰性德 — separate directory (Qing dynasty poet)
NALAN_URL = (
    "https://raw.githubusercontent.com/chinese-poetry/chinese-poetry/master/"
    "%E7%BA%B3%E5%85%B0%E6%80%A7%E5%BE%B7/"
    "%E7%BA%B3%E5%85%B0%E6%80%A7%E5%BE%B7%E8%AF%97%E9%9B%86.json"
)


def fetch_json(url: str, retries: int = 3) -> list | None:
    """Fetch and parse a JSON file from URL."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
        except Exception as e:
            print(f"  Attempt {attempt + 1}/{retries} failed: {e}")
            time.sleep(1)
    return None


def extract_lines(poems: list) -> list[tuple[str, str, str, str]]:
    """Extract individual lines from poem objects.

    Song ci format: {"author": "苏轼", "paragraphs": ["..."], "rhythmic": "念奴娇"}
    纳兰性德 format: {"author": "纳兰性德", "para": ["..."], "title": "长相思·山一程"}
    Returns: [(author, line, origin, category), ...]
    """
    results = []
    for poem in poems:
        author = poem.get("author", "").strip()
        if author not in TARGET_AUTHORS:
            continue
        paragraphs = poem.get("paragraphs") or poem.get("para") or []
        rhythmic = poem.get("rhythmic", "") or ""
        title = poem.get("title", "") or ""
        if rhythmic and title and title not in rhythmic:
            origin = f"{rhythmic}·{title}"
        elif rhythmic:
            origin = rhythmic
        elif title:
            origin = title
        else:
            origin = ""
        for line in paragraphs:
            line = line.strip()
            # Skip very short fragments (punctuation only, section markers)
            if len(line) < 4:
                continue
            results.append((author, line, origin, "ci"))
    return results


def main():
    parser = argparse.ArgumentParser(description="Fetch classical Chinese poetry")
    parser.add_argument("--count", action="store_true", help="Show per-author counts")
    args = parser.parse_args()

    data_dir = get_data_dir()
    db_path = os.path.join(data_dir, "usage.db")

    # Ensure DB exists
    if not os.path.exists(db_path):
        init_db(db_path)

    if args.count:
        _show_counts(db_path)
        return

    print("Fetching classical Chinese poetry from chinese-poetry repo...")
    print(f"Target poets: {', '.join(sorted(TARGET_AUTHORS))}\n")

    total_inserted = 0

    # ── Song ci files ──
    for i, filename in enumerate(CI_FILES):
        url = f"{CI_BASE}/{filename}"
        print(f"[{i+1}/{len(CI_FILES)}] {filename}...", end=" ", flush=True)
        poems = fetch_json(url)
        if poems is None:
            print("FAILED (skipping)")
            continue
        lines = extract_lines(poems)
        count = 0
        for author, content, origin, category in lines:
            if insert_poetry_line(db_path, author, content, origin, category):
                count += 1
        print(f"OK: {len(poems)} poems → {count} lines inserted")
        total_inserted += count
        time.sleep(0.2)  # Be polite to GitHub

    # ── 纳兰性德 collection ──
    print(f"[extra] 纳兰性德诗集.json...", end=" ", flush=True)
    poems = fetch_json(NALAN_URL)
    if poems is None:
        print("FAILED (skipping)")
    else:
        lines = extract_lines(poems)
        count = 0
        for author, content, origin, category in lines:
            if insert_poetry_line(db_path, author, content, origin, category):
                count += 1
        print(f"OK: {len(poems)} poems → {count} lines inserted")
        total_inserted += count

    print(f"\nDone! Total new lines inserted: {total_inserted}")
    _show_counts(db_path)


def _show_counts(db_path):
    conn = __import__("sqlite3").connect(db_path)
    print("Per-author poetry line counts:")
    print("-" * 40)
    for author in sorted(TARGET_AUTHORS):
        row = conn.execute(
            "SELECT COUNT(*) FROM poetry_lines WHERE author = ?", (author,)
        ).fetchone()
        count = row[0] if row else 0
        status = "[OK]" if count > 0 else "[not found]"
        print(f"  {author}: {count} lines  {status}")
    conn.close()


if __name__ == "__main__":
    main()
