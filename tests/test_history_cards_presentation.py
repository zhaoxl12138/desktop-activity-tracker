"""Unified historical work/entertainment cards, using synthetic data only."""
import copy
import os
import re
from datetime import date, datetime, timedelta

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication
from daylens.services.dashboard_service import build_rhythm_snapshot, build_entertainment_history
from daylens.gui.widgets.dashboard_widgets import RhythmComparisonCard, EntertainmentHistoryCard, _RhythmCanvas, _EntertainmentHistoryCanvas
from daylens.gui.widgets.history_card_widgets import HistoryMetricCell
from daylens.gui import style


def application():
    return QApplication.instance() or QApplication([])


def fixture(captured=datetime(2026, 10, 26, 17, 42)):
    rows = []
    for offset in (0, 1, 3, 6, 29, 30):
        rows.append({'date': (captured.date()-timedelta(days=offset)).isoformat(),
                     'total_samples': 1, 'session_count': 1, 'metric_versions': ['attention-v1'],
                     'classification_versions': ['rules-v1'], 'work_engaged_seconds': 600+offset*60,
                     'engaged_seconds': 600+offset*60, 'video_seconds': 300+offset*60})
    original = copy.deepcopy(rows)
    sessions = [
        _favorite_session(captured.date().isoformat(), 'Code.exe', 'coding', engaged=600, effective=600),
        _favorite_session(captured.date().isoformat(), '腾讯视频.exe', 'video', engaged=60, effective=300),
    ]
    work = build_rhythm_snapshot(captured_now=captured, sessions=sessions, daily_rows=rows, query_failed=False)
    entertainment = build_entertainment_history(captured_now=captured, daily_rows=rows,
        current_entertainment_seconds=300, today_has_data=True, weekday_entertainment_limit_minutes=60,
        weekend_entertainment_limit_minutes=120, query_failed=False, sessions=sessions)
    assert rows == original
    return work, {'entertainment_history': entertainment}


def _favorite_session(day, app, category, *, engaged=0, effective=0):
    return {
        'date': day,
        'process_name': app,
        'category_key': category,
        'engaged_seconds': engaged,
        'effective_seconds': effective,
        'metric_version': 'attention-v1',
        'classification_version': 'rules-v1',
    }


def test_history_models_rank_favorite_apps_with_separate_metrics_and_ranges():
    captured = datetime(2026, 10, 29, 18, 0)
    sessions = [
        _favorite_session('2026-10-28', 'ChatGPT.exe', 'coding', engaged=600, effective=700),
        _favorite_session('2026-10-27', 'Code.exe', 'coding', engaged=900, effective=900),
        _favorite_session('2026-10-01', 'ChatGPT.exe', 'coding', engaged=1_000, effective=1_100),
        _favorite_session('2026-10-28', '腾讯视频.exe', 'video', engaged=100, effective=700),
        _favorite_session('2026-10-26', 'Hades2.exe', 'gaming', engaged=900, effective=900),
        _favorite_session('2026-10-01', '腾讯视频.exe', 'video', engaged=100, effective=500),
    ]

    work = build_rhythm_snapshot(
        captured_now=captured, sessions=sessions, daily_rows=[], query_failed=False,
    )
    entertainment = build_entertainment_history(
        captured_now=captured,
        daily_rows=[],
        current_entertainment_seconds=0,
        today_has_data=False,
        weekday_entertainment_limit_minutes=60,
        weekend_entertainment_limit_minutes=120,
        query_failed=False,
        sessions=sessions,
    )

    assert work['7d']['metrics'][1] == {
        'label': '偏爱应用', 'value': 'Code', 'delta': '15分钟',
    }
    assert work['30d']['metrics'][1] == {
        'label': '偏爱应用', 'value': 'ChatGPT', 'delta': '26分钟',
    }
    assert entertainment['week']['summary']['favorite_app_name'] == 'Hades2'
    assert entertainment['week']['summary']['favorite_app_seconds'] == 900
    assert entertainment['month']['summary']['favorite_app_name'] == '腾讯视频'
    assert entertainment['month']['summary']['favorite_app_seconds'] == 1_200


def test_favorite_app_tie_break_is_stable_by_application_name():
    from daylens.services.dashboard_service import _favorite_app

    captured_day = date(2026, 10, 29)
    sessions = [
        {
            **_favorite_session('2026-10-29', 'Zulu.exe', 'coding', engaged=300),
            'display_name': 'Aardvark',
        },
        _favorite_session('2026-10-29', 'Alpha.exe', 'coding', engaged=300),
    ]

    assert _favorite_app(
        sessions,
        start=captured_day,
        end=captured_day,
        category_keys={'coding'},
        seconds_for=lambda row: row['engaged_seconds'],
    ) == {'name': 'Aardvark', 'seconds': 300}


def test_history_metric_cell_elides_only_when_its_width_requires_it():
    app = application()
    cell = HistoryMetricCell('偏爱应用', elide_value=True)
    cell.set_values(label='偏爱应用', value='VeryLongApplicationName', detail='2小时')
    cell.resize(110, 80)
    cell.show()
    app.processEvents()

    assert cell.value.fullText() == 'VeryLongApplicationName'
    assert cell.value.text().endswith('…')
    assert cell.value.toolTip() == 'VeryLongApplicationName'

    cell.resize(520, 80)
    app.processEvents()
    assert cell.value.text() == 'VeryLongApplicationName'
    assert cell.value.toolTip() == ''

    cell.close()


@pytest.mark.parametrize('mode', ['7d', '30d'])
def test_work_card_uses_dynamic_favorite_app_width(mode):
    app = application()
    card = RhythmComparisonCard()
    period = {
        'title': 'history',
        'date_range': ['2026-10-23', '2026-10-29'],
        'status': {'label': '可用', 'kind': 'baseline'},
        'conclusion': '',
        'chart': {'kind': 'bars', 'dates': [], 'values': []},
        'metrics': [
            {'label': '日均参与', 'value': '1小时', 'delta': ''},
            {'label': '偏爱应用', 'value': 'VeryLongApp', 'delta': '2小时'},
            {'label': '总时间', 'value': '7小时', 'delta': ''},
        ],
    }
    card.set_data({'captured_at': '2026-10-29T18:00:00', '7d': period, '30d': period})
    card.set_mode(mode)
    card.resize(600, 300)
    card.show()
    app.processEvents()

    assert card._metric_labels[1][0].text() == '偏爱应用'
    assert card._metric_labels[1][1].fullText() == 'VeryLongApp'
    assert len(card._metric_labels[1][1].text()) > 5
    assert card._metric_labels[1][1].toolTip() == 'VeryLongApp'
    assert card._metric_labels[1][2].text() == '2小时'

    card.close()


@pytest.mark.parametrize('captured', [datetime(2026, 10, 26, 17, 42), datetime(2026, 1, 1), datetime(2028, 3, 1)])
def test_work_and_entertainment_ranges_are_equal_and_include_today(captured):
    work, entertainment = fixture(captured)
    for mode, key, length in [('7d', 'week', 7), ('30d', 'month', 30)]:
        assert work[mode]['date_range'] == entertainment['entertainment_history'][key]['date_range']
        assert work[mode]['chart']['dates'] == [p['date'] for p in entertainment['entertainment_history'][key]['points']]
        assert len(work[mode]['chart']['dates']) == length
        assert work[mode]['chart']['dates'][-1] == captured.date().isoformat()
        assert work[mode]['chart']['values'][-1] == 600
    assert work['captured_at'] == captured.isoformat()


def test_no_history_keeps_thirty_gaps_not_zero_or_truncated_window():
    work = build_rhythm_snapshot(captured_now=datetime(2026, 10, 26), sessions=[], daily_rows=[], query_failed=False)
    assert work['30d']['date_range'] == ['2026-09-27', '2026-10-26']
    assert work['30d']['chart']['values'] == [None]*30


def test_work_summaries_keep_effective_days_denominator_with_today_and_gaps():
    work, _entertainment = fixture()
    for mode in ('7d', '30d'):
        values = work[mode]['chart']['values']
        valid = [v for v in values if v is not None]
        assert len(valid) == (4 if mode == '7d' else 5)
        if mode == '7d':
            assert work[mode]['chart']['average_seconds'] == round(sum(valid)/len(valid))
        assert sum(valid) == (3000 if mode == '7d' else 5340)


@pytest.mark.parametrize('mode', ['7d', '30d'])
def test_cards_share_summary_labels_clear_peak_duration_and_range_caption(mode):
    app = application()
    work, entertainment = fixture()
    a, b = RhythmComparisonCard(), EntertainmentHistoryCard()
    a.set_data(work)
    b.set_data(entertainment)
    for card in (a, b):
        card.set_mode(mode)
        card.resize(470, 285)
        card.show()
    app.processEvents()
    try:
        assert [labels[0].text() for labels in a._metric_labels] == ['日均时长', '偏爱应用', '总时长']
        assert [labels[0].text() for labels in b._summary_labels] == ['日均时长', '偏爱应用', '总时长']
        assert a._title_label.text() == ('工作节奏 · 近7天' if mode == '7d' else '工作节奏 · 近30天')
        assert a._metric_labels[1][1].text() == 'Code'
        assert b._summary_cells[1].value.text() == '腾讯视频'
        assert a._conclusion_label.text() == b._range_label.text()+'  截至 17:42'
        assert a._metric_labels[1][2].text()
        for detail in (a._metric_labels[1][2], b._summary_cells[1].detail):
            assert style.COLORS['text_secondary'] in detail.styleSheet()
            assert '13px' in detail.styleSheet()
        for labels in a._metric_labels:
            assert labels[1].wordWrap()
        assert not a.canvas._data.get('day_activation_enabled') or mode == '7d'
        if mode == '7d':
            assert a.canvas._today_index() == 6
        else:
            assert a.canvas._today_index() == 29
    finally:
        a.close()
        b.close()


class PainterRecorder:
    def __init__(self):
        self._font = QFont()
        self.lines = []
        self.texts = []
    def font(self): return QFont(self._font)
    def setFont(self, font): self._font = QFont(font)
    def setPen(self, pen): self.pen = pen
    def setBrush(self, _brush): pass
    def drawRoundedRect(self, *_args): pass
    def drawRect(self, *_args): pass
    def drawPath(self, *_args): pass
    def drawLine(self, *args): self.lines.append(args)
    def drawText(self, rect, alignment, text): self.texts.append((rect, text, QFont(self._font), self.pen))


def test_month_bars_do_not_paint_average_reference_line():
    application()
    canvas = _RhythmCanvas()
    canvas.set_data({'kind': 'bars', 'values': [600, 1200], 'average_seconds': 900})
    painter = PainterRecorder()
    canvas._draw_bars(painter, QRectF(48, 8, 350, 100), 1500)
    assert painter.lines == []


def test_today_summary_keeps_existing_style_after_switching_history_modes():
    application()
    work, _entertainment = fixture()
    original_today = copy.deepcopy(work['today'])
    card = RhythmComparisonCard()
    card.set_data(work)
    card.set_mode('30d')
    card.set_mode('today')
    try:
        assert not card._metric_labels[0][1].wordWrap()
        assert not card._metric_labels[0][2].wordWrap()
        assert '12px' in card._metric_labels[0][2].styleSheet()
        assert style.COLORS['text_muted'] in card._metric_labels[0][2].styleSheet()
        assert [labels[0].text() for labels in card._metric_labels] == [m['label'] for m in original_today['metrics']]
        assert card.canvas._data['current'] == original_today['chart']['current']
        assert work['today'] == original_today
    finally:
        card.close()


@pytest.mark.parametrize('mode', ['7d', '30d'])
def test_entertainment_axes_have_readable_fonts_and_high_contrast(mode):
    application()
    work, entertainment = fixture()
    canvas = _EntertainmentHistoryCanvas()
    canvas.resize(450, 120)
    period = entertainment['entertainment_history']['week' if mode == '7d' else 'month']
    canvas.set_data(mode, period['points'], period['date_range'])
    painter = PainterRecorder()
    (canvas._draw_bars if mode == '7d' else canvas._draw_calendar)(painter)
    assert painter.texts
    assert all(font.pixelSize() >= 11 for rect, text, font, pen in painter.texts)
    assert all(QColor(pen).name() != QColor(style.COLORS['text_muted']).name() for rect, text, font, pen in painter.texts)


def test_calendar_repaint_keeps_one_hit_region_per_day():
    application()
    _work, entertainment = fixture()
    canvas = _EntertainmentHistoryCanvas()
    canvas.resize(450, 126)
    month = entertainment['entertainment_history']['month']
    canvas.set_data('30d', month['points'], month['date_range'])
    painter = PainterRecorder()
    canvas._draw_calendar(painter)
    canvas._draw_calendar(painter)
    assert len(canvas._calendar_hit_rects) == 30
