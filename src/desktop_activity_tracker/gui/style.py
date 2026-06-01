"""Shared color palette and style constants for Desktop Activity Tracker GUI."""

# ── Modern Color Palette ──────────────────────────────────────────────

COLORS = {
    # Backgrounds
    'bg':                '#EEF2F7',
    'panel_bg':          '#F7F9FC',
    'card_bg':           '#FFFFFF',
    'sidebar_bg':        '#162033',
    'sidebar_hover':     '#24324A',
    'sidebar_active':    '#4F8CFF',

    # Accent / category
    'primary':           '#387BFF',
    'primary_hover':     '#2B68DB',
    'ai_purple':         '#7C63FF',
    'coding_green':      '#15B67A',
    'reading_blue':      '#0EA5E9',
    'video_orange':      '#F59E0B',
    'creative_pink':     '#EC4899',
    'social_teal':       '#14B8A6',
    'tools_grey':        '#64748B',        # Slate-500
    'gaming_red':        '#EF4444',        # Red-500
    'idle_gray':         '#94A3B8',
    'browser_grey':      '#94A3B8',

    # Semantic
    'danger_red':        '#F04452',
    'warning_yellow':    '#F6B73C',
    'success_green':     '#13B67A',

    # Text
    'text':              '#172033',
    'text_secondary':    '#52627A',
    'text_muted':        '#8A97AB',
    'text_inverse':      '#F8FAFC',

    # Borders
    'border':            '#D9E2EE',
    'border_light':      '#EDF2F8',
}

# ── Category color mapping ───────────────────────────────────────────

CATEGORY_COLOR_MAP = {
    'ai_tools':        COLORS['ai_purple'],
    'coding':          COLORS['coding_green'],
    'reading':         COLORS['reading_blue'],
    'video':           COLORS['video_orange'],
    'creative':        COLORS['creative_pink'],
    'social':          COLORS['social_teal'],
    'tools':           COLORS['tools_grey'],
    'gaming':          COLORS['gaming_red'],
    'browser_general': COLORS['browser_grey'],
    'other':           COLORS['idle_gray'],
}


def get_category_color(category_key):
    return CATEGORY_COLOR_MAP.get(category_key, COLORS['idle_gray'])


# ── Global App Stylesheet ────────────────────────────────────────────

GLOBAL_STYLE = f"""
    QMainWindow {{
        background: {COLORS['bg']};
    }}
    QWidget {{
        font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        color: {COLORS['text']};
    }}
    QLabel {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: #C4D0E0;
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #95A7C0;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QToolTip {{
        background: {COLORS['sidebar_bg']};
        color: {COLORS['text_inverse']};
        border: none;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
    }}
"""

# ── Sidebar ──────────────────────────────────────────────────────────

SIDEBAR_STYLE = f"""
    QListWidget {{
        background: {COLORS['sidebar_bg']};
        color: {COLORS['text_inverse']};
        border: none;
        font-size: 13px;
        padding: 10px 0;
        outline: none;
    }}
    QListWidget::item {{
        padding: 12px 16px;
        margin: 3px 10px;
        border-radius: 10px;
        border: none;
    }}
    QListWidget::item:selected {{
        background: {COLORS['sidebar_active']};
        color: white;
        font-weight: 700;
    }}
    QListWidget::item:hover:!selected {{
        background: {COLORS['sidebar_hover']};
    }}
"""

# ── Top bar ──────────────────────────────────────────────────────────

TOP_BAR_STYLE = f"""
    QFrame#topBar {{
        background: rgba(255, 255, 255, 0.96);
        border-bottom: 1px solid {COLORS['border']};
    }}
"""

# ── Bottom bar ───────────────────────────────────────────────────────

BOTTOM_BAR_STYLE = f"""
    QFrame#bottomBar {{
        background: rgba(255, 255, 255, 0.96);
        border-top: 1px solid {COLORS['border']};
    }}
"""

# ── Buttons ──────────────────────────────────────────────────────────

BUTTON_PRIMARY_STYLE = f"""
    QPushButton {{
        background: {COLORS['primary']};
        color: white;
        border: none;
        border-radius: 10px;
        padding: 10px 20px;
        font-size: 13px;
        font-weight: 700;
    }}
    QPushButton:hover {{ background: {COLORS['primary_hover']}; }}
    QPushButton:pressed {{ background: #1D4ED8; }}
"""

BUTTON_SECONDARY_STYLE = f"""
    QPushButton {{
        background: {COLORS['card_bg']};
        color: {COLORS['text']};
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
        padding: 10px 16px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {COLORS['bg']};
        border-color: {COLORS['primary']};
    }}
"""

BUTTON_DANGER_STYLE = f"""
    QPushButton {{
        background: transparent;
        color: {COLORS['danger_red']};
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
        padding: 6px 14px;
        font-size: 11px;
    }}
    QPushButton:hover {{
        background: #FEF2F2;
        border-color: {COLORS['danger_red']};
    }}
"""

# ── Cards ────────────────────────────────────────────────────────────

CARD_STYLE = f"""
    QFrame#dataCard {{
        background: {COLORS['card_bg']};
        border: 1px solid {COLORS['border']};
        border-radius: 10px;
        padding: 18px 20px;
    }}
"""

CARD_STAT_VALUE = """
    font-size: 24px;
    font-weight: 800;
"""

CARD_STAT_LABEL = """
    font-size: 12px;
    font-weight: 500;
"""

# ── Table ────────────────────────────────────────────────────────────

TABLE_STYLE = f"""
    QTableWidget {{
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        gridline-color: {COLORS['border_light']};
        font-size: 13px;
        background: {COLORS['card_bg']};
        selection-background-color: {COLORS['bg']};
        selection-color: {COLORS['text']};
    }}
    QTableWidget::item {{
        padding: 8px 14px;
    }}
    QHeaderView::section {{
        background: {COLORS['bg']};
        padding: 10px 14px;
        border: none;
        border-bottom: 2px solid {COLORS['border']};
        font-weight: 700;
        font-size: 12px;
        color: {COLORS['text_secondary']};
        text-transform: uppercase;
    }}
"""

# ── Section title ────────────────────────────────────────────────────

SECTION_TITLE = """
    font-size: 20px;
    font-weight: 800;
    color: #1E293B;
    padding-bottom: 4px;
"""

# ── Input fields ─────────────────────────────────────────────────────

INPUT_STYLE = f"""
    QLineEdit {{
        border: 1px solid {COLORS['border']};
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 13px;
        background: {COLORS['card_bg']};
    }}
    QLineEdit:focus {{
        border-color: {COLORS['primary']};
    }}
    QSpinBox {{
        border: 1px solid {COLORS['border']};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 13px;
        background: {COLORS['card_bg']};
    }}
    QSpinBox:focus {{
        border-color: {COLORS['primary']};
    }}
    QCheckBox {{
        font-size: 13px;
        spacing: 8px;
    }}
"""
