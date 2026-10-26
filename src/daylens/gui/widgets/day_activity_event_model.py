"""Lazy read-only chronological event table with complete original evidence."""
from __future__ import annotations

import html

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from ...utils import fmt_seconds


def clock(seconds, *, precise=False):
    value = max(0, min(86400, int(seconds or 0)))
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}" + (f":{seconds:02d}" if precise else "")


def event_details(event):
    lines = [str(event.get("title") or "无标题"), str(event.get("app") or "未知应用"),
             f"前台范围 {clock(event.get('start_second'), precise=True)}–"
             f"{clock(event.get('end_second'), precise=True)}",
             f"有效活动 {fmt_seconds(int(event.get('effective_seconds') or 0))}"]
    if event.get("legacy"):
        lines.append("旧口径：主动／被动分项未知")
    else:
        for key, name in (("engaged_seconds", "主动参与"), ("passive_seconds", "被动活动")):
            value = event.get(key)
            lines.append(f"{name} " + ("未知" if value is None else fmt_seconds(int(value))))
    value = event.get("idle_seconds")
    lines.append("空闲 " + ("未知" if value is None else fmt_seconds(int(value))))
    lines.append("色块表示前台记录范围，不代表全程有效。")
    if event.get("contains_idle"):
        lines.append("含空闲：记录未提供其精确位置，不将整个前台范围视为有效活动")
    return "\n".join(lines)


class DayActivityEventModel(QAbstractTableModel):
    HEADERS = ("时间范围", "应用", "活动 / 窗口标题", "分类", "有效活动", "说明")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events = []
        self._rows = {}

    def set_events(self, events):
        self.beginResetModel()
        self._events = events
        self._rows = {event["id"]: row for row, event in enumerate(events)}
        self.endResetModel()

    def row_for_id(self, identity):
        return self._rows.get(identity)

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self._events)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < len(self.HEADERS):
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._events) or not 0 <= index.column() < len(self.HEADERS):
            return None
        event = self._events[index.row()]
        if role == Qt.ToolTipRole:
            return "<qt>" + html.escape(event_details(event)).replace("\n", "<br>") + "</qt>"
        if role == Qt.UserRole:
            return event["id"]
        if role != Qt.DisplayRole:
            return None
        column = index.column()
        if column == 0:
            return f"{clock(event['start_second'])}–{clock(event['end_second'])}"
        if column == 1:
            return event.get("app") or event.get("process_name") or "未知应用"
        if column == 2:
            return event.get("title") or "无标题"
        if column == 3:
            return event.get("category_name") or event.get("category_key") or "其他"
        if column == 4:
            return fmt_seconds(int(event.get("effective_seconds") or 0))
        return " · ".join(text for text, present in (("含空闲", event.get("contains_idle")),
                                                    ("旧口径", event.get("legacy"))) if present)
