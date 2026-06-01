"""Shared color palette and style constants for Desktop Activity Tracker GUI."""

COLORS = {
    'bg':                '#F5F6FA',
    'card_bg':           '#FFFFFF',
    'sidebar_bg':        '#2C3E50',
    'sidebar_text':      '#BDC3C7',
    'sidebar_active':    '#3498DB',
    'primary':           '#4A90D9',
    'ai_purple':         '#7B68EE',
    'coding_green':      '#2ECC71',
    'reading_blue':      '#3498DB',
    'video_orange':      '#E67E22',
    'idle_gray':         '#95A5A6',
    'danger_red':        '#E74C3C',
    'warning_yellow':    '#F39C12',
    'text':              '#2C3E50',
    'text_light':        '#7F8C8D',
    'text_inverse':      '#FFFFFF',
    'border':            '#E0E0E0',
    'hover':             '#EBF5FB',
}

CATEGORY_COLOR_MAP = {
    'ai_tools':        '#7B68EE',
    'coding':          '#2ECC71',
    'reading':         '#3498DB',
    'video':           '#E67E22',
    'browser_general': '#95A5A6',
    'other':           '#95A5A6',
}


def get_category_color(category_key):
    return CATEGORY_COLOR_MAP.get(category_key, COLORS['idle_gray'])


CARD_STYLE = """
    QFrame#dataCard {
        background: #FFFFFF;
        border: 1px solid #E0E0E0;
        border-radius: 8px;
        padding: 16px;
    }
"""

SIDEBAR_STYLE = """
    QListWidget {
        background: #2C3E50;
        color: #BDC3C7;
        border: none;
        font-size: 14px;
        padding: 8px 0;
    }
    QListWidget::item {
        padding: 12px 20px;
        border-left: 3px solid transparent;
    }
    QListWidget::item:selected {
        background: #34495E;
        color: #FFFFFF;
        border-left: 3px solid #3498DB;
    }
    QListWidget::item:hover {
        background: #34495E;
    }
"""

TOP_BAR_STYLE = """
    QFrame#topBar {
        background: #FFFFFF;
        border-bottom: 1px solid #E0E0E0;
        padding: 8px 16px;
    }
"""

BOTTOM_BAR_STYLE = """
    QFrame#bottomBar {
        background: #FFFFFF;
        border-top: 1px solid #E0E0E0;
        padding: 4px 16px;
        font-size: 12px;
        color: #7F8C8D;
    }
"""

BUTTON_PRIMARY_STYLE = """
    QPushButton {
        background: #3498DB;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 8px 16px;
        font-size: 13px;
    }
    QPushButton:hover { background: #2980B9; }
    QPushButton:pressed { background: #2471A3; }
"""

BUTTON_SECONDARY_STYLE = """
    QPushButton {
        background: #FFFFFF;
        color: #2C3E50;
        border: 1px solid #BDC3C7;
        border-radius: 4px;
        padding: 8px 16px;
        font-size: 13px;
    }
    QPushButton:hover { background: #F5F6FA; }
"""

TABLE_STYLE = """
    QTableWidget {
        border: 1px solid #E0E0E0;
        gridline-color: #F0F0F0;
        font-size: 13px;
    }
    QTableWidget::item { padding: 6px 12px; }
    QHeaderView::section {
        background: #F5F6FA;
        padding: 8px 12px;
        border: none;
        border-bottom: 2px solid #E0E0E0;
        font-weight: bold;
        font-size: 12px;
    }
"""
