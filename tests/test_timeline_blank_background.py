"""Real painter regressions: empty intervals stay blank, evidence stays intact."""
import copy
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from daylens.gui import style
from daylens.gui.widgets.day_activity_category_timeline import DayActivityCategoryTimeline
from tests.test_day_activity_gui import model


@pytest.fixture
def timeline():
    app = QApplication.instance() or QApplication([])
    widget = DayActivityCategoryTimeline()
    source = model()
    event = copy.deepcopy(source['events'][0])
    event.update(start_second=8*3600, end_second=9*3600,
                 duration_seconds=3600, effective_seconds=2700,
                 engaged_seconds=2700, idle_seconds=900, contains_idle=True,
                 app='', process_name='')
    source['events'] = [event]
    source['totals'] = {'effective_seconds':2700, 'engaged_seconds':2700,
                        'passive_seconds':0, 'idle_seconds':900}
    source['segments'] = [
        {'kind':'idle', 'start_second':0, 'end_second':6*3600},
        {'kind':'missing', 'start_second':6*3600, 'end_second':8*3600},
        {'kind':'activity', 'start_second':8*3600, 'end_second':9*3600, 'event_id':event['id']},
        {'kind':'unreliable', 'start_second':9*3600, 'end_second':18*3600},
        {'kind':'future', 'start_second':18*3600, 'end_second':86400},
    ]
    source['warnings'] = ['存在异常区间']
    before = copy.deepcopy(source)
    original_theme = style.CURRENT_THEME
    try:
        widget.set_model(source)
        assert widget._fitted_range == (8*3600, 9*3600)
        widget.set_full_day(True)
        widget.resize(1200, widget.minimumHeight())
        widget.show(); app.processEvents()
        yield widget, app
        assert source == before
        assert widget._fitted_range == (8*3600, 9*3600)
        assert (widget.range_start,widget.range_end) == (0,86400)
        assert widget.lanes[0]['effective_seconds'] == 2700
    finally:
        widget.close()
        style.apply_theme(original_theme)


def patch_colors(widget, second):
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    left = round(widget._x(second)*ratio)
    top = round((widget._band().top()+3)*ratio)
    return {image.pixelColor(x,y).name() for x in range(left,left+7)
            for y in range(top,top+7)}


@pytest.mark.parametrize('theme', ['dark','light'])
@pytest.mark.parametrize('second,label', [(3*3600+113,'空闲'), (7*3600+113,'无记录'),
                                        (13*3600+113,'异常'), (21*3600+113,'尚未')])
def test_non_activity_intervals_are_blank_but_keep_distinct_tooltips(timeline,theme,second,label):
    widget, app = timeline
    style.apply_theme(theme)
    widget.update(); app.processEvents()
    assert label in widget.tooltip_for_second(second)
    assert patch_colors(widget,second) == {QColor(style.COLORS['card_bg_alt']).name()}


@pytest.mark.parametrize('theme', ['dark','light'])
def test_activity_with_idle_is_solid_but_retains_idle_evidence(timeline,theme):
    widget, app = timeline
    style.apply_theme(theme)
    # Reapply to refresh cached lane colors without changing the source data.
    widget.set_model(widget.model)
    widget.set_full_day(True)
    app.processEvents()
    assert '含空闲' in widget.tooltip_for_second(8*3600+1200)
    assert patch_colors(widget,8*3600+1200) == {QColor(widget.lanes[0]['color']).name()}
