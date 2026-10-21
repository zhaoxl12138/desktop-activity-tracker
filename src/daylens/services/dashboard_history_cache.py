"""Bounded cache for completed-day dashboard evidence."""

from __future__ import annotations

import copy
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CompletedDashboardHistory:
    range_stats: dict
    sessions: tuple[dict, ...]
    yesterday_stats: dict


class DashboardHistoryCache:
    def __init__(self, max_entries: int = 4):
        self._max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[tuple, CompletedDashboardHistory] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def get_or_load(
        self,
        *,
        db_path: str,
        dates: list[str],
        revision: tuple,
        loader: Callable[[], tuple[dict, list[dict], dict]],
    ) -> CompletedDashboardHistory:
        key = (
            os.path.normcase(os.path.abspath(db_path)),
            tuple(dates),
            tuple(revision),
        )
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached

        range_stats, sessions, yesterday_stats = loader()
        value = CompletedDashboardHistory(
            range_stats=copy.deepcopy(range_stats),
            sessions=tuple(copy.deepcopy(sessions)),
            yesterday_stats=copy.deepcopy(yesterday_stats),
        )
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                self._entries.move_to_end(key)
                return existing
            self._entries[key] = value
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
