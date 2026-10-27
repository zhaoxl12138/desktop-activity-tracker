"""Render four history views with synthetic data, without opening a database."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from PySide6.QtCore import QPoint, Qt, QRect
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from daylens.gui import style
from daylens.gui.widgets.dashboard_widgets import RhythmComparisonCard, EntertainmentHistoryCard
from daylens.services.dashboard_service import build_rhythm_snapshot, build_entertainment_history


def sample():
    captured = datetime(2026, 10, 26, 17, 42)
    rows = []
    for offset in range(30):
        if offset in (5, 20, 28):
            continue
        work = (30-offset)*250 if offset % 5 else 0
        entertainment = (offset % 7)*750 if offset else 1080
        rows.append({'date': (captured.date()-timedelta(days=offset)).isoformat(),
                     'total_samples': 1, 'session_count': 1,
                     'metric_versions': ['attention-v1'], 'classification_versions': ['qa'],
                     'work_engaged_seconds': work, 'engaged_seconds': work,
                     'video_seconds': entertainment})
    rhythm = build_rhythm_snapshot(captured_now=captured, sessions=[], daily_rows=rows, query_failed=False)
    history = build_entertainment_history(captured_now=captured, daily_rows=rows,
        current_entertainment_seconds=1080, today_has_data=True,
        weekday_entertainment_limit_minutes=60, weekend_entertainment_limit_minutes=120,
        query_failed=False)
    return rhythm, {'entertainment_history': history}


def assert_text_fits(label):
    text = label.text()
    if not text or label.isHidden():
        return
    bounds = label.fontMetrics().boundingRect(QRect(0, 0, label.contentsRect().width(), 2000),
        Qt.TextWordWrap if label.wordWrap() else Qt.TextSingleLine, text)
    assert bounds.height() <= label.contentsRect().height(), (text, bounds, label.size())
    assert bounds.width() <= label.contentsRect().width(), (text, bounds, label.size())


def main():
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    app.setFont(QFont('Microsoft YaHei', 10))
    scale = float(os.environ.get('QT_SCALE_FACTOR', '1'))
    output = ROOT/'tmp'/'history-cards-layout'/str(scale)
    output.mkdir(parents=True, exist_ok=True)
    for theme in ('dark', 'light'):
        style.apply_theme(theme)
        for width, height in ((1280, 720), (1920, 1080)):
            for mode in ('7d', '30d'):
                for kind, card_type, payload in zip(('work', 'entertainment'),
                        (RhythmComparisonCard, EntertainmentHistoryCard), sample()):
                    card = card_type()
                    card.set_data(payload)
                    card.set_mode(mode)
                    card.resize(min(700, int(width/scale*.55)), 285)
                    card.show()
                    app.processEvents()
                    app.processEvents()
                    assert card.width() <= width/scale and card.height() <= height/scale
                    groups = card._metric_labels if kind == 'work' else [
                        (cell.label, cell.value, cell.detail) for cell in card._summary_cells]
                    assert card.canvas.mapTo(card, QPoint(0, card.canvas.height())).y() < groups[0][0].parentWidget().y()
                    for group in groups:
                        for label in group:
                            assert_text_fits(label)
                    if kind == 'entertainment' and mode == '30d':
                        assert len(card.canvas._calendar_hit_rects) == 30
                        assert len(card.canvas._calendar_week_labels) == 6
                    path = output/f'{theme}-{width}x{height}-{kind}-{mode}.png'
                    assert card.grab().save(str(path))
                    card.close()
    print(f'History card layout captures passed: {output}')


if __name__ == '__main__':
    main()
