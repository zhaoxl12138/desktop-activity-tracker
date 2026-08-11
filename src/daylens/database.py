"""Database facade that re-exports repository helpers."""

from __future__ import annotations

import os
from functools import partial

from . import get_app_root
from .repositories.connection_repository import (
    close_db,
    close_shared_read_conn,
    init_db,
    init_shared_read_conn,
    read_conn,
)
from .repositories.poetry_repository import (
    get_poetry_count as _get_poetry_count,
    get_random_poetry as _get_random_poetry,
    insert_poetry_line,
)
from .repositories.session_repository import (
    insert_activity_log,
    insert_session,
    update_session,
)
from .repositories.settings_repository import (
    apply_custom_rules,
    delete_activity_logs_before,
    load_custom_rules,
    load_settings,
    merge_discovered_rules,
    merge_custom_rules,
    merge_db_settings,
    save_custom_rules,
    save_settings,
)
from .repositories.stats_repository import (
    count_consecutive_days as _count_consecutive_days,
    query_category_detail as _query_category_detail,
    query_date as _query_date,
    query_date_range_stats as _query_date_range_stats,
    query_date_stats as _query_date_stats,
    query_entertainment_trend as _query_entertainment_trend,
    query_session_count as _query_session_count,
    query_sessions_for_dates as _query_sessions_for_dates,
    query_session_entertainment_trend as _query_session_entertainment_trend,
    summarize_daily_trusted_metrics,
    query_timeline_sessions as _query_timeline_sessions,
    query_top_titles_by_category as _query_top_titles_by_category,
    query_today_sessions as _query_today_sessions,
)


def get_db_path(config: dict) -> str:
    db_path = config.get("db_path", "data/usage.db")
    if not os.path.isabs(db_path):
        normalized = str(db_path).replace("\\", "/")
        if normalized == "data" or normalized.startswith("data/"):
            from . import get_data_dir

            relative = normalized.removeprefix("data/").removeprefix("data")
            db_path = os.path.join(get_data_dir(), relative or "usage.db")
        else:
            db_path = os.path.join(get_app_root(), db_path)
    return db_path


query_date = partial(_query_date, read_conn)
query_date_stats = partial(_query_date_stats, read_conn)
query_session_entertainment_trend = partial(_query_session_entertainment_trend, read_conn)
query_entertainment_trend = partial(_query_entertainment_trend, read_conn)
query_session_count = partial(_query_session_count, read_conn)
query_today_sessions = partial(_query_today_sessions, read_conn)
query_sessions_for_dates = partial(_query_sessions_for_dates, read_conn)
query_category_detail = partial(_query_category_detail, read_conn)
count_consecutive_days = partial(_count_consecutive_days, read_conn)
query_date_range_stats = partial(_query_date_range_stats, read_conn)
query_top_titles_by_category = partial(_query_top_titles_by_category, read_conn)
query_timeline_sessions = partial(_query_timeline_sessions, read_conn)
get_random_poetry = partial(_get_random_poetry, read_conn)
get_poetry_count = partial(_get_poetry_count, read_conn)
