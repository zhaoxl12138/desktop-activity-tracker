"""Helpers for the category stats page."""

from __future__ import annotations

from datetime import datetime

from .. import database
from ..utils import fmt_seconds, normalize_category_bucket_key, normalize_category_display_name


def load_category_summary(db_path: str) -> dict[str, object]:
    today = datetime.now().strftime("%Y-%m-%d")
    stats = database.query_date_stats(db_path, today)
    categories = _merge_categories(stats.get("by_category", []))
    total_eff = sum(category.get("effective_seconds", 0) or 0 for category in categories)
    return {
        "today": today,
        "categories": categories,
        "total_effective_seconds": total_eff,
        "total_label": f"今日活跃时间总计：{fmt_seconds(total_eff)}  |  {len(categories)} 个分类",
    }


def load_category_detail(db_path: str, date_str: str, category_key: str, limit: int = 5) -> list[dict]:
    source_keys = {
        "work": ["ai_tools", "coding", "office", "reading", "creative"],
        "entertainment": ["video", "gaming"],
        "social": ["social"],
        "tools": ["tools", "system_tools"],
        "browser_general": ["browser_general", "browser_other"],
    }.get(category_key, [category_key])
    rows: list[dict] = []
    for source_key in source_keys:
        rows.extend(database.query_category_detail(db_path, date_str, source_key, limit))
    rows.sort(key=lambda item: int(item.get("effective_seconds", 0) or 0), reverse=True)
    return rows[:limit]


def _merge_categories(categories: list[dict]) -> list[dict]:
    order = ["work", "entertainment", "social", "tools", "browser_general", "other"]
    merged: dict[str, dict] = {}
    for category in categories:
        source_key = str(category.get("category_key", "") or "")
        source_name = str(category.get("category_name", "") or "")
        target_key = normalize_category_bucket_key(source_key, source_name)
        bucket = merged.setdefault(
            target_key,
            {
                "category_key": target_key,
                "category_name": normalize_category_display_name(source_key, source_name),
                "effective_seconds": 0,
                "idle_seconds": 0,
                "total_seconds": 0,
            },
        )
        bucket["effective_seconds"] += int(category.get("effective_seconds", 0) or 0)
        bucket["idle_seconds"] += int(category.get("idle_seconds", 0) or 0)
        bucket["total_seconds"] += int(category.get("total_seconds", 0) or 0)
    return sorted(
        merged.values(),
        key=lambda item: order.index(item["category_key"]) if item["category_key"] in order else len(order),
    )
