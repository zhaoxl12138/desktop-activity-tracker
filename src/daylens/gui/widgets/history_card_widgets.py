"""Presentation shared only by work/entertainment history cards."""
from datetime import date, datetime

from .ui_primitives import MetricCell
from ..style import COLORS


class HistoryMetricCell(MetricCell):
    """Keep peak duration readable without changing unrelated dashboard cells."""

    def __init__(self, label="", parent=None):
        super().__init__(label, parent=parent)
        self.value.setWordWrap(True)
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {COLORS['text_secondary']};"
        )


def compact_app_name(value: object, limit: int = 5) -> str:
    """Keep app names inside compact metric cells without losing the source."""
    text = str(value or "").strip()
    if not text:
        return "--"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def history_range_text(value) -> str:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return ""
    try:
        start, end = (date.fromisoformat(str(part)) for part in value)
        return f"{start.month}/{start.day}–{end.month}/{end.day}"
    except ValueError:
        return ""


def history_captured_text(value) -> str:
    try:
        return f"截至 {datetime.fromisoformat(str(value)).strftime('%H:%M')}"
    except ValueError:
        return ""
