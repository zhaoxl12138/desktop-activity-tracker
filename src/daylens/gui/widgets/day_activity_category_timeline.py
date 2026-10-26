"""One fixed 24-hour category timeline, with no inferred activity positions.

The service supplies chronological, disjoint evidence segments. Their exact
foreground bounds are painted without aggregating or widening short records.
"""
from __future__ import annotations

import html
from bisect import bisect_right

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from ...category_registry import category_definition
from ...utils import fmt_seconds
from .. import style
from .day_activity_event_model import event_details


_GROUPS = (
    ("work", "工作学习", "coding_green"),
    ("entertainment", "娱乐休闲", "video_orange"),
    ("social", "社交通讯", "social_purple"),
    ("finance", "投资理财", "#D8B45B"),
    ("browser_general", "浏览器", "browser_amber"),
    ("tools", "系统工具", "tools_cyan"),
    ("other", "其他", "other_teal"),
)
_STATE_TEXT = {
    "missing": "无记录：不能判断当时是否使用电脑",
    "idle": "记录中的空闲（非有效活动）",
    "future": "尚未到来的时间",
    "unreliable": "异常、冲突或重叠记录：无法可靠展开",
}


class DayActivityCategoryTimeline(QWidget):
    """Paint source events by broad category, always on the same 00–24 axis."""

    event_activated = Signal(str)
    tick_hours = tuple(range(25))
    labelled_hours = tuple(range(0, 25, 2))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = {}
        self.selected_event_id = None
        self.lanes = []
        self._events = {}
        self._event_groups = {}
        self._segments = []
        self._starts = []
        self._lane_indices = {}
        self.setMouseTracking(True)
        self.set_model({})

    def set_model(self, model):
        """Build linear-size indices without changing the detached source model."""
        self.model = model
        self._events = {event["id"]: event for event in model.get("events", [])}
        self._event_groups = {}
        totals = {}
        # Cache category vocabulary lookups: work subtypes deliberately share a lane.
        categories = {}
        for identity, event in self._events.items():
            category = event.get("category_key")
            if category not in categories:
                definition = category_definition(category)
                group = definition.group if definition else "other"
                categories[category] = group if group in {g[0] for g in _GROUPS} | {"idle"} else "other"
            group = categories[category]
            # Legacy rows may identify idle by its display name only.
            if event.get("category_name") == "空闲":
                group = "idle"
            self._event_groups[identity] = group
            if group != "idle":
                totals[group] = totals.get(group, 0) + int(event.get("effective_seconds") or 0)
        present = set(totals) if totals else {g[0] for g in _GROUPS[:4]}
        self.lanes = [dict(key=key, name=name, color=style.COLORS.get(color, color),
                           effective_seconds=totals.get(key, 0))
                      for key, name, color in _GROUPS if key in present]
        self._lane_indices = {lane["key"]: i for i, lane in enumerate(self.lanes)}
        # build_day_activity has already swept, sorted, and split these intervals.
        self._segments = model.get("segments", [])
        self._starts = [segment["start_second"] for segment in self._segments]
        self.selected_event_id = None
        self._update_metrics()
        self.update()

    def _update_metrics(self):
        metrics = self.fontMetrics()
        self._row_pitch = max(38, metrics.height()*2 + 4)
        self._top = max(38, metrics.height() + 20)
        bold = QFont(self.font())
        bold.setBold(True)
        label_metrics = QFontMetricsF(bold)
        self._label_width = max(100, max(label_metrics.horizontalAdvance(lane["name"])
                                         for lane in self.lanes) + 28)
        height = self._top + len(self.lanes)*self._row_pitch + 44
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.updateGeometry()

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.ApplicationFontChange):
            self._update_metrics()

    def _band(self, lane=0):
        return QRectF(self._label_width, self._top + lane*self._row_pitch + 5,
                      max(1, self.width()-self._label_width-18), self._row_pitch-10)

    def _x(self, second):
        band = self._band()
        return band.left() + max(0, min(86400, second))/86400*band.width()

    def _second(self, x):
        band = self._band()
        return max(0, min(86400, (x-band.left())/band.width()*86400))

    def _column(self, start, end):
        first, last = self._band(), self._band(len(self.lanes)-1)
        return QRectF(self._x(start), first.top(), max(0, self._x(end)-self._x(start)),
                      last.bottom()-first.top())

    def event_rect(self, identity):
        """Return exact source foreground geometry; idle spans all neutral lanes."""
        event = self._events.get(identity)
        if event is None:
            return QRectF()
        group = self._event_groups[identity]
        if group == "idle":
            return self._column(event["start_second"], event["end_second"])
        band = self._band(self._lane_indices[group])
        return QRectF(self._x(event["start_second"]), band.top(),
                      max(0, self._x(event["end_second"])-self._x(event["start_second"])), band.height())

    def hour_labels(self):
        """Clock labels and their metric-derived rectangles for the fixed axis."""
        metrics = QFontMetricsF(self.font())
        gap = self._band().width()/12
        full_clock = metrics.horizontalAdvance("00:00") + 4 <= gap
        y = self._top + len(self.lanes)*self._row_pitch + 1
        result = []
        for hour in self.labelled_hours:
            text = f"{hour:02d}:00" if full_clock else f"{hour:02d}"
            width = metrics.horizontalAdvance(text) + 2
            x = min(self.width()-width-5, max(5, self._x(hour*3600)-width/2))
            result.append((hour, QRectF(x, y, width, metrics.height()+2), text))
        return result

    def select_event(self, identity):
        self.selected_event_id = identity if identity in self._events else None
        self.update()

    def _segment_at(self, second):
        index = bisect_right(self._starts, second)-1
        if index >= 0 and second < self._segments[index]["end_second"]:
            return self._segments[index]
        return None

    def _event_at(self, second, group=None):
        segment = self._segment_at(second)
        if segment is None:
            return None
        event = self._events.get(segment.get("event_id"))
        if event and (group is None or self._event_groups[event["id"]] in (group, "idle")):
            return event
        return None

    def tooltip_for_second(self, seconds, group=None):
        """Plain source text; rich tooltip escaping happens only at the UI edge."""
        event = self._event_at(seconds, group)
        if event:
            return event_details(event)
        segment = self._segment_at(seconds)
        if segment and segment.get("kind") == "activity":
            return "该分类此时无前台记录；不推断有效活动位置。"
        return _STATE_TEXT.get(segment.get("kind") if segment else "missing", _STATE_TEXT["missing"])

    def _lane_at(self, point):
        if not self._band().left() <= point.x() <= self._band().right():
            return None
        lane = int((point.y()-self._top)//self._row_pitch)
        if 0 <= lane < len(self.lanes) and self._band(lane).top() <= point.y() <= self._band(lane).bottom():
            return self.lanes[lane]["key"]
        return None

    def mousePressEvent(self, event):  # noqa: N802
        group = self._lane_at(event.position())
        if event.button() == Qt.LeftButton and group is not None:
            source = self._event_at(self._second(event.position().x()), group)
            if source:
                self.select_event(source["id"])
                self.event_activated.emit(source["id"])
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        group = self._lane_at(event.position())
        if group is None:
            QToolTip.hideText()
        else:
            text = self.tooltip_for_second(self._second(event.position().x()), group)
            QToolTip.showText(event.globalPosition().toPoint(),
                             "<qt>" + html.escape(text).replace("\n", "<br>") + "</qt>", self)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        QToolTip.hideText()
        super().leaveEvent(event)

    @staticmethod
    def _event_label(event, rect, metrics):
        text = str(event.get("app") or event.get("process_name") or "")
        available = rect.width()-10
        if not text:
            return ""
        if metrics.horizontalAdvance(text) <= available:
            return text
        if available < metrics.horizontalAdvance(text[0]+"…"):
            return ""
        return metrics.elidedText(text, Qt.ElideRight, available)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(style.COLORS["border"])))
        painter.setBrush(QColor(style.COLORS["card_bg"]))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 10, 10)
        regular = QFont(self.font())
        bold = QFont(regular)
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor(style.COLORS["text"]))
        painter.drawText(QRectF(14, 8, self.width()-28, self._top-10),
                         Qt.AlignVCenter | Qt.AlignLeft, "全天分类分布 · 00:00–24:00")
        for index, lane in enumerate(self.lanes):
            band = self._band(index)
            painter.fillRect(band, QColor(style.COLORS["card_bg_alt"]))
            painter.setPen(QColor(style.COLORS["text"]))
            painter.drawText(QRectF(14, band.top()-3, self._label_width-22, band.height()/2+4),
                             Qt.AlignVCenter | Qt.AlignLeft, lane["name"])
            painter.setFont(regular)
            painter.setPen(QColor(style.COLORS["text_muted"]))
            painter.drawText(QRectF(14, band.center().y()+1, self._label_width-22, band.height()/2+4),
                             Qt.AlignVCenter | Qt.AlignLeft, fmt_seconds(lane["effective_seconds"]))
            painter.setFont(bold)
        painter.setRenderHint(QPainter.Antialiasing, False)
        states = {
            "idle": (style.COLORS["timeline_idle"], Qt.Dense6Pattern),
            "future": (style.COLORS["text_muted"], Qt.Dense7Pattern),
            "unreliable": (style.COLORS["video_orange"], Qt.BDiagPattern),
        }
        for segment in self._segments:
            kind = segment.get("kind")
            if self._event_groups.get(segment.get("event_id")) == "idle":
                kind = "idle"
            if kind not in states:
                continue
            color, pattern = states[kind]
            rect = self._column(segment["start_second"], segment["end_second"])
            tint = QColor(color)
            tint.setAlpha(30 if kind != "idle" else 45)
            painter.fillRect(rect, tint)
            tint.setAlpha(115)
            painter.fillRect(rect, QBrush(tint, pattern))
        painter.setPen(QPen(QColor(style.COLORS["border"]), 1))
        first, last = self._band(), self._band(len(self.lanes)-1)
        for hour in self.tick_hours:
            x = self._x(hour*3600)
            painter.drawLine(x, first.top(), x, last.bottom()+3)
        painter.setFont(regular)
        metrics = QFontMetricsF(regular)
        for identity, source in self._events.items():
            group = self._event_groups[identity]
            if group == "idle":
                continue
            rect = self.event_rect(identity)
            color = QColor(self.lanes[self._lane_indices[group]]["color"])
            painter.fillRect(rect, color)
            if source.get("contains_idle"):
                painter.fillRect(rect, QBrush(QColor(0, 0, 0, 70), Qt.BDiagPattern))
            label = self._event_label(source, rect, metrics)
            if label:
                painter.save()
                painter.setClipRect(rect)
                painter.setPen(QColor("#071522"))
                painter.drawText(rect.adjusted(5, 0, -5, 0), Qt.AlignVCenter | Qt.AlignLeft, label)
                painter.restore()
        if self.selected_event_id in self._events:
            painter.save()
            # A cosmetic outline highlights the original range without changing its width.
            painter.setPen(QPen(QColor(style.COLORS["primary"]), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.event_rect(self.selected_event_id))
            painter.restore()
        painter.setPen(QColor(style.COLORS["text_secondary"]))
        for _hour, rect, label in self.hour_labels():
            painter.drawText(rect, Qt.AlignCenter, label)
        painter.setPen(QColor(style.COLORS["text_muted"]))
        footer = QRectF(14, self.height()-21, self.width()-28, 18)
        painter.drawText(footer, Qt.AlignVCenter | Qt.AlignLeft, "色块为前台范围，不代表全程有效；悬停查看详情。")
