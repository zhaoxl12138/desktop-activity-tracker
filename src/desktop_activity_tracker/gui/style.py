"""Shared color palette and style constants for Desktop Activity Tracker GUI."""

# ── Modern Color Palette ──────────────────────────────────────────────

COLORS = {
    # Backgrounds
    'bg':                '#F0F2F5',
    'card_bg':           '#FFFFFF',
    'sidebar_bg':        '#1E293B',        # Slate-800
    'sidebar_hover':     '#334155',        # Slate-700
    'sidebar_active':    '#3B82F6',        # Blue-500

    # Accent / category
    'primary':           '#3B82F6',        # Blue-500
    'primary_hover':     '#2563EB',        # Blue-600
    'ai_purple':         '#8B5CF6',        # Violet-500
    'coding_green':      '#10B981',        # Emerald-500
    'reading_blue':      '#06B6D4',        # Cyan-500
    'video_orange':      '#F59E0B',        # Amber-500
    'creative_pink':     '#EC4899',        # Pink-500
    'social_teal':       '#14B8A6',        # Teal-500
    'tools_grey':        '#64748B',        # Slate-500
    'gaming_red':        '#EF4444',        # Red-500
    'idle_gray':         '#94A3B8',        # Slate-400
    'browser_grey':      '#94A3B8',

    # Semantic
    'danger_red':        '#EF4444',
    'warning_yellow':    '#F59E0B',
    'success_green':     '#10B981',

    # Text
    'text':              '#1E293B',        # Slate-800
    'text_secondary':    '#64748B',        # Slate-500
    'text_muted':        '#94A3B8',        # Slate-400
    'text_inverse':      '#F8FAFC',

    # Borders
    'border':            '#E2E8F0',        # Slate-200
    'border_light':      '#F1F5F9',
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
    QScrollBar:vertical {{
        background: {COLORS['bg']};
        width: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {COLORS['text_muted']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {COLORS['text_secondary']};
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
        padding: 8px 0;
        outline: none;
    }}
    QListWidget::item {{
        padding: 8px 16px;
        margin: 1px 8px;
        border-radius: 6px;
        border: none;
    }}
    QListWidget::item:selected {{
        background: {COLORS['sidebar_active']};
        color: white;
        font-weight: bold;
    }}
    QListWidget::item:hover:!selected {{
        background: {COLORS['sidebar_hover']};
    }}
"""

# ── Top bar ──────────────────────────────────────────────────────────

TOP_BAR_STYLE = f"""
    QFrame#topBar {{
        background: {COLORS['card_bg']};
        border-bottom: 1px solid {COLORS['border']};
    }}
"""

# ── Bottom bar ───────────────────────────────────────────────────────

BOTTOM_BAR_STYLE = f"""
    QFrame#bottomBar {{
        background: {COLORS['card_bg']};
        border-top: 1px solid {COLORS['border']};
    }}
"""

# ── Buttons ──────────────────────────────────────────────────────────

BUTTON_PRIMARY_STYLE = f"""
    QPushButton {{
        background: {COLORS['primary']};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 20px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background: {COLORS['primary_hover']}; }}
    QPushButton:pressed {{ background: #1D4ED8; }}
"""

BUTTON_SECONDARY_STYLE = f"""
    QPushButton {{
        background: {COLORS['card_bg']};
        color: {COLORS['text']};
        border: 1px solid {COLORS['border']};
        border-radius: 6px;
        padding: 8px 16px;
        font-size: 13px;
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
        border-radius: 6px;
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
