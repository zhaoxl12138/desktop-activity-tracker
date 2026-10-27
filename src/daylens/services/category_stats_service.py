"""Helpers for the category stats page."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .. import database
from ..utils import (
    BROWSER_CATEGORY_KEYS,
    ENTERTAINMENT_CATEGORY_KEYS,
    SOCIAL_CATEGORY_KEYS,
    TOOLS_CATEGORY_KEYS,
    WORK_CATEGORY_KEYS,
    fmt_seconds,
    normalize_category_bucket_key,
    normalize_category_display_name,
)


_BUCKET_SOURCE_KEYS = {
    "work": WORK_CATEGORY_KEYS,
    "entertainment": ENTERTAINMENT_CATEGORY_KEYS,
    "social": SOCIAL_CATEGORY_KEYS,
    "tools": TOOLS_CATEGORY_KEYS,
    "browser_general": BROWSER_CATEGORY_KEYS,
}


def _source_keys_for_bucket(category_key: str) -> tuple[str, ...]:
    return tuple(sorted(_BUCKET_SOURCE_KEYS.get(category_key, (category_key,))))


def load_category_summary(
    db_path: str, start_day: str | None = None, end_day: str | None = None,
) -> dict[str, object]:
    today = datetime.now().strftime("%Y-%m-%d")
    if start_day is None and end_day is None:
        start_day = end_day = today
        stats = database.query_date_stats(db_path, today)
    else:
        if start_day is None or end_day is None:
            raise ValueError("请选择完整的起止日期")
        start = date.fromisoformat(start_day)
        end = date.fromisoformat(end_day)
        span = (end - start).days
        if not 0 <= span < 366:
            raise ValueError("日期范围必须为 1 至 366 天，且开始日期不能晚于结束日期")
        dates = [(start + timedelta(days=offset)).isoformat() for offset in range(span + 1)]
        stats = database.query_date_range_stats(db_path, dates)
    categories = _merge_categories(stats.get("by_category", []))
    total_eff = sum(category.get("effective_seconds", 0) or 0 for category in categories)
    period_label = "今日" if start_day == end_day == today else (
        start_day if start_day == end_day else f"{start_day}—{end_day}"
    )
    return {
        "today": today,
        "range_start": start_day,
        "range_end": end_day,
        "categories": categories,
        "total_effective_seconds": total_eff,
        "total_label": f"{period_label}有效时间总计：{fmt_seconds(total_eff)}  |  {len(categories)} 个分类",
    }


def load_category_detail(db_path: str, date_str: str, category_key: str, limit: int = 5) -> list[dict]:
    rows: list[dict] = []
    for source_key in _source_keys_for_bucket(category_key):
        rows.extend(database.query_category_detail(db_path, date_str, source_key, limit))
    rows.sort(key=lambda item: int(item.get("effective_seconds", 0) or 0), reverse=True)
    return rows[:limit]


def load_category_range_detail(
    db_path: str, start_day: str, end_day: str, category_key: str, limit: int = 5,
) -> list[dict]:
    start = date.fromisoformat(start_day)
    end = date.fromisoformat(end_day)
    span = (end - start).days
    if not 0 <= span < 366:
        raise ValueError("日期范围必须为 1 至 366 天，且开始日期不能晚于结束日期")
    dates = [(start + timedelta(days=offset)).isoformat() for offset in range(span + 1)]
    return database.query_category_range_detail(db_path, dates, category_key, limit)


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
        key=lambda item: (
            -int(item.get("effective_seconds", 0) or 0),
            order.index(item["category_key"]) if item["category_key"] in order else len(order),
        ),
    )
