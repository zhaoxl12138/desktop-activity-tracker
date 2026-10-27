"""Work-rhythm columns, labels and activation must share one date geometry."""
import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from daylens.gui import style
from daylens.gui.widgets.dashboard_widgets import _RhythmCanvas, _TrendCanvas, RhythmComparisonCard

DAYS = [f"2026-10-{day}" for day in range(20, 27)]


def app():
    return QApplication.instance() or QApplication([])


def data(values=None):
    return {"kind": "bars", "dates": DAYS, "labels": [f"10/{d}" for d in range(20, 27)],
            "values": values if values is not None else [6000, 60, 1560, 12960, 11700, 720, 300],
            "today_date": DAYS[-1], "day_activation_enabled": True,
            "show_bar_duration_labels": True}


class TextRecorder:
    def __init__(self):
        self._font = QFont()
        self.pen = None
        self.calls = []

    def font(self):
        return QFont(self._font)

    def setFont(self, font):
        self._font = QFont(font)

    def setPen(self, pen):
        self.pen = pen

    def drawText(self, rect, alignment, text):
        self.calls.append((rect, str(text), QFont(self._font), self.pen))

    def setBrush(self, _brush):
        pass

    def drawRoundedRect(self, *_args):
        pass


def test_bar_centers_match_existing_axis_painting_without_geometry_stubs():
    app()
    canvas = _RhythmCanvas()
    canvas.set_data(data())
    chart = QRectF(50, 20, 280, 100)
    bars, labels = TextRecorder(), TextRecorder()
    canvas._draw_bars(bars, chart, 15000)
    canvas._draw_x_labels(labels, chart)
    for index, (rect, _text, _font, _pen) in enumerate(labels.calls):
        assert rect.center().x() == pytest.approx(canvas._bar_hit_rects[index].center().x())


@pytest.mark.parametrize("width", [320, 500, 700])
def test_every_bar_and_date_label_share_the_same_column_center(width):
    application = app()
    canvas = _RhythmCanvas()
    canvas.resize(width, 150)
    canvas.set_data(data())
    canvas.show()
    application.processEvents()
    try:
        chart = canvas._chart_rect()
        recorder = TextRecorder()
        canvas._draw_x_labels(recorder, chart)
        assert len(recorder.calls) == 7
        for index, (rect, label, _font, _pen) in enumerate(recorder.calls):
            assert label == f"10/{20+index}"
            assert canvas._bar_hit_rects[index].center().x() == pytest.approx(rect.center().x())
            assert rect.left() >= 0 and rect.right() <= canvas.width()
        assert canvas.height()-recorder.calls[-1][0].bottom() >= 6
    finally:
        canvas.close()


def test_zero_missing_and_today_keep_original_slots_and_activation_dates():
    application = app()
    source = data([6000, 0, None, 12960, 11700, 720, 300])
    before = copy.deepcopy(source)
    canvas = _RhythmCanvas()
    canvas.resize(500, 150)
    canvas.set_data(source)
    canvas.show()
    application.processEvents()
    seen = []
    canvas.day_activated.connect(seen.append)
    try:
        assert canvas._bar_hit_rects[1].height() >= 2
        assert canvas._bar_hit_rects[2] is None
        chart = canvas._chart_rect()
        for index in (0, 1, 2, 6):
            rect = canvas._bar_slot(index, chart)
            QTest.mouseClick(canvas, Qt.LeftButton, pos=QPoint(round(rect.center().x()), canvas.height()-12))
        assert seen == [DAYS[0], DAYS[1], DAYS[2], DAYS[-1]]
        assert source == before
    finally:
        canvas.close()


def test_axes_are_larger_and_higher_contrast_today_date_is_bold():
    app()
    canvas = _RhythmCanvas()
    canvas.resize(500, 150)
    canvas.set_data(data())
    x, y = TextRecorder(), TextRecorder()
    canvas._draw_x_labels(x, canvas._chart_rect())
    canvas._draw_y_labels(y, canvas._chart_rect(), 14400)
    assert all(call[2].pixelSize() >= 11 for call in x.calls+y.calls)
    assert all(QColor(call[3]).name() != QColor(style.COLORS["text_muted"]).name() for call in y.calls)
    assert x.calls[-1][2].bold()
    assert not x.calls[0][2].bold()
    assert canvas._today_index() == 6


def test_card_passes_snapshot_today_date_without_mutating_the_payload():
    app()
    payload = {"7d": {"date_range": [DAYS[0], DAYS[-1]], "chart": data()}}
    del payload["7d"]["chart"]["today_date"]
    before = copy.deepcopy(payload)
    card = RhythmComparisonCard()
    card.set_data(payload)
    card.set_mode("7d")
    try:
        assert card.canvas._data["today_date"] == DAYS[-1]
        assert payload == before
    finally:
        card.close()


def test_cumulative_curve_x_labels_keep_endpoint_geometry():
    app()
    canvas = _RhythmCanvas()
    canvas.resize(500, 150)
    canvas.set_data({"kind": "cumulative", "current": [i*60 for i in range(48)],
                     "labels": [f"{i//2:02d}:{i%2*30:02d}" for i in range(48)]})
    chart = canvas._chart_rect()
    recorder = TextRecorder()
    canvas._draw_x_labels(recorder, chart)
    assert recorder.calls[0][0].center().x() == pytest.approx(chart.left())
    assert recorder.calls[-1][0].center().x() == pytest.approx(chart.right())
    assert canvas._today_index() is None


def test_thirty_day_sparse_dates_stay_readable_and_centered_on_source_bars():
    application = app()
    canvas = _RhythmCanvas()
    canvas.resize(400, 150)
    canvas.set_data({"kind": "bars", "values": [i*60 for i in range(30)],
                     "labels": [f"9/{i+1}" for i in range(30)]})
    canvas.show()
    application.processEvents()
    try:
        recorder = TextRecorder()
        canvas._draw_x_labels(recorder, canvas._chart_rect())
        indices = canvas._x_label_indices(30)
        assert len(recorder.calls) == 6
        for index, (rect, _text, _font, _pen) in zip(indices, recorder.calls):
            assert rect.width() >= 48
            assert rect.center().x() == pytest.approx(canvas._bar_hit_rects[index].center().x())
            assert 0 <= rect.left() < rect.right() <= canvas.width()
    finally:
        canvas.close()


@pytest.mark.parametrize('kind,count', [('bars',7), ('bars',30), ('cumulative',48)])
def test_y_axis_numbers_only_remain_for_today_curve(kind, count):
    app()
    canvas = _RhythmCanvas()
    canvas.resize(450, 150)
    canvas.set_data({'kind':kind, 'values':[600]*count, 'current':[600]*count})
    recorder = TextRecorder()
    canvas._draw_y_labels(recorder, canvas._chart_rect(), 1500)
    assert len(recorder.calls) == (4 if kind == 'cumulative' else 0)
    assert canvas._chart_rect().left() == (54 if kind == 'cumulative' else 8 if count == 7 else 24)


def test_dense_bars_keep_exact_daily_duration_available_without_y_axis():
    app()
    canvas = _RhythmCanvas()
    canvas.set_data({'kind':'bars', 'values':[600], 'dates':['2026-10-26'], 'labels':['10/26']})
    assert canvas._tooltip_text_for_index(0) == '10/26\n工作参与 10分钟'


def test_today_rhythm_y_labels_leave_twelve_pixels_before_plot():
    app()
    canvas = _RhythmCanvas()
    canvas.resize(500, 160)
    canvas.set_data({'kind': 'cumulative', 'current': [i * 60 for i in range(48)]})
    chart = canvas._chart_rect()
    recorder = TextRecorder()
    canvas._draw_y_labels(recorder, chart, 9000)
    assert len(recorder.calls) == 4
    assert all(chart.left() - rect.right() >= 12 for rect, *_ in recorder.calls)
    assert chart.left() >= 52


def test_trend_painter_and_hover_share_spaced_plot_geometry():
    app()
    canvas = _TrendCanvas()
    canvas.resize(500, 160)
    canvas.set_series([float(i) for i in range(24)], mode='today',
                      work_points=[float(i) for i in range(24)],
                      entertainment_points=[0.0] * 24)
    chart = canvas._chart_rect()
    assert chart.left() - canvas._y_label_rect(chart.top()).right() >= 12
    assert canvas._hover_hour_for_x(chart.left()) == 0
    assert canvas._hover_hour_for_x(chart.right()) == 23
