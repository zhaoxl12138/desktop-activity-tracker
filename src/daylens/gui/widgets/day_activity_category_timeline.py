"""Category timeline fitted to recorded activity, without inferred positions.

The service supplies chronological, disjoint evidence segments. Their exact
foreground bounds are painted without aggregating or widening short records.
"""
from __future__ import annotations

import html
import math
from bisect import bisect_right

from PySide6.QtCore import QEvent, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from ...category_registry import category_definition
from ...utils import fmt_seconds
from .. import style
from .day_activity_event_model import clock, event_details


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
    """Fit all lanes to the same first/last effective-event foreground range."""

    event_activated = Signal(str)
    category_activated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = {}
        self.selected_event_id = None
        self.lanes = []
        self._all_lanes = []
        self.selected_category = None
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
        self._all_lanes = self.lanes
        self.selected_category = None
        self._lane_indices = {lane["key"]: i for i, lane in enumerate(self.lanes)}
        # build_day_activity has already swept, sorted, and split these intervals.
        self._segments = model.get("segments", [])
        self._starts = [segment["start_second"] for segment in self._segments]
        active = [event for identity, event in self._events.items()
                  if not self.is_event_hidden(identity)
                  and int(event.get("effective_seconds") or 0) > 0]
        self.has_activity_range = bool(active)
        self.range_start, self.range_end = 0, 86400
        if active:
            self.range_start = max(0, math.floor(min(e["start_second"] for e in active)/1800)*1800)
            self.range_end = min(86400, math.ceil(max(e["end_second"] for e in active)/1800)*1800)
            # Valid service events have positive spans; retain a safe reference
            # even for an empty synthetic range rather than dividing by zero.
            if self.range_end <= self.range_start:
                self.range_start, self.range_end = 0, 86400
                self.has_activity_range = False
        self.selected_event_id = None
        self._update_metrics()
        self.update()

    def is_event_hidden(self, identity):
        """Keep predominantly idle foreground spans out of the plot only."""
        event = self._events.get(identity)
        if event is None:
            return False
        if self._event_groups.get(identity) == "idle":
            return True
        duration = int(event.get("duration_seconds") or 0)
        idle = int(event.get("idle_seconds") or 0)
        return duration <= 0 or idle * 10 > duration * 7

    @property
    def available_categories(self):
        return tuple(self._all_lanes)

    def group_for_event(self, identity):
        return self._event_groups.get(identity)

    def set_category_filter(self, group):
        """Hide other category lanes without changing the original day axis."""
        self.selected_category = group if any(lane["key"] == group for lane in self._all_lanes) else None
        self.lanes = ([lane for lane in self._all_lanes if lane["key"] == self.selected_category]
                      if self.selected_category else self._all_lanes)
        self._lane_indices = {lane["key"]: index for index, lane in enumerate(self.lanes)}
        if self.selected_event_id and self._event_groups.get(self.selected_event_id) not in self._lane_indices:
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
        clipped = max(self.range_start, min(self.range_end, second))
        return band.left() + (clipped-self.range_start)/(self.range_end-self.range_start)*band.width()

    def _second(self, x):
        band = self._band()
        return max(self.range_start, min(self.range_end,
                   self.range_start+(x-band.left())/band.width()*(self.range_end-self.range_start)))

    def _column(self, start, end):
        if end <= self.range_start or start >= self.range_end:
            return QRectF()
        first, last = self._band(), self._band(len(self.lanes)-1)
        return QRectF(self._x(start), first.top(), max(0, self._x(end)-self._x(start)),
                      last.bottom()-first.top())

    def event_rect(self, identity):
        """Return the original foreground geometry only for plotted events."""
        event = self._events.get(identity)
        if (event is None or self.is_event_hidden(identity)
                or event["end_second"] <= self.range_start or event["start_second"] >= self.range_end):
            return QRectF()
        group = self._event_groups[identity]
        if group not in self._lane_indices:
            return QRectF()
        band = self._band(self._lane_indices[group])
        return QRectF(self._x(event["start_second"]), band.top(),
                      max(0, self._x(event["end_second"])-self._x(event["start_second"])), band.height())

    def _axis_step(self):
        """Use quarter/half/hour ticks, thinning long-day labels when needed."""
        metrics = QFontMetricsF(self.font())
        minimum_gap = metrics.horizontalAdvance("00:00") + 10
        duration = self.range_end-self.range_start
        return next((step for step in (900, 1800, 3600, 7200, 14400, 21600, 43200)
                     if step/duration*self._band().width() >= minimum_gap), 86400)

    def axis_ticks(self):
        step = self._axis_step()
        inside = range((self.range_start//step+1)*step, self.range_end, step)
        return (self.range_start, *inside, self.range_end)

    def range_title(self):
        return (f"活动时段 · {clock(self.range_start)}–{clock(self.range_end)}" if self.has_activity_range
                else "全天分类分布 · 暂无可展示活动")

    def hour_labels(self):
        """Fit complete clock labels and both endpoints without overlaps."""
        metrics = QFontMetricsF(self.font())
        y = self._top + len(self.lanes)*self._row_pitch + 1
        candidates = []
        for second in self.axis_ticks():
            text = clock(second)
            width = metrics.horizontalAdvance(text) + 2
            x = min(self.width()-width-5, max(5, self._x(second)-width/2))
            candidates.append((second, QRectF(x, y, width, metrics.height()+2), text))
        result = [candidates[0]]
        last = candidates[-1]
        for candidate in candidates[1:-1]:
            rect = candidate[1]
            if rect.left() >= result[-1][1].right()+4 and rect.right()+4 <= last[1].left():
                result.append(candidate)
        result.append(last)
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
        if (event and not self.is_event_hidden(event["id"])
                and (group is None or self._event_groups[event["id"]] == group)):
            return event
        return None

    def tooltip_for_second(self, seconds, group=None):
        """Plain source text; rich tooltip escaping happens only at the UI edge."""
        event = self._event_at(seconds, group)
        if event:
            return event_details(event)
        segment = self._segment_at(seconds)
        if segment:
            identity = segment.get("event_id")
            if (identity in self._events and self.is_event_hidden(identity)
                    and self._event_groups[identity] != "idle"
                    and (group is None or self._event_groups[identity] == group)):
                return "此处有记录，但空闲占比超过70%，已从时间轴隐藏；可在事件明细查看。"
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

    def _label_at(self, point):
        if not 0 <= point.x() < self._label_width:
            return None
        lane = int((point.y()-self._top)//self._row_pitch)
        if 0 <= lane < len(self.lanes) and self._band(lane).top() <= point.y() <= self._band(lane).bottom():
            return self.lanes[lane]["key"]
        return None

    def mousePressEvent(self, event):  # noqa: N802
        label_group = self._label_at(event.position())
        if event.button() == Qt.LeftButton and label_group is not None:
            self.category_activated.emit(label_group)
            super().mousePressEvent(event)
            return
        group = self._lane_at(event.position())
        if event.button() == Qt.LeftButton and group is not None:
            second = min(self._second(event.position().x()), self.range_end-1e-6)
            source = self._event_at(second, group)
            if source and self._event_groups.get(source["id"]) in self._lane_indices:
                self.select_event(source["id"])
                self.event_activated.emit(source["id"])
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        group = self._lane_at(event.position())
        if group is None:
            QToolTip.hideText()
        else:
            second = min(self._second(event.position().x()), self.range_end-1e-6)
            text = self.tooltip_for_second(second, group)
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
                         Qt.AlignVCenter | Qt.AlignLeft, self.range_title())
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
            "future": (style.COLORS["text_muted"], Qt.Dense7Pattern),
            "unreliable": (style.COLORS["video_orange"], Qt.BDiagPattern),
        }
        for segment in self._segments:
            kind = segment.get("kind")
            if self.is_event_hidden(segment.get("event_id")):
                continue
            if kind not in states:
                continue
            color, pattern = states[kind]
            rect = self._column(segment["start_second"], segment["end_second"])
            tint = QColor(color)
            tint.setAlpha(30)
            painter.fillRect(rect, tint)
            tint.setAlpha(115)
            painter.fillRect(rect, QBrush(tint, pattern))
        painter.setPen(QPen(QColor(style.COLORS["border"]), 1))
        first, last = self._band(), self._band(len(self.lanes)-1)
        for second in self.axis_ticks():
            x = self._x(second)
            painter.drawLine(x, first.top(), x, last.bottom()+3)
        painter.setFont(regular)
        metrics = QFontMetricsF(regular)
        for identity, source in self._events.items():
            group = self._event_groups[identity]
            if self.is_event_hidden(identity) or group not in self._lane_indices:
                continue
            rect = self.event_rect(identity)
            if rect.isEmpty():
                continue
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
        if self.selected_event_id in self._events and not self.event_rect(self.selected_event_id).isEmpty():
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
        painter.drawText(footer, Qt.AlignVCenter | Qt.AlignLeft,
                         "色块为前台范围，非全程有效；空闲占比超过70%的记录已隐藏。")
