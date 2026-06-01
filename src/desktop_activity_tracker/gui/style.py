"""Centralized UI theme and QSS styles."""

from __future__ import annotations


COLORS = {
    "bg": "#071326",
    "panel_bg": "#0B1A33",
    "panel_bg_alt": "#0E203D",
    "card_bg": "#10213D",
    "card_bg_alt": "#13284A",
    "sidebar_bg": "#061226",
    "sidebar_hover": "#122A52",
    "sidebar_active": "#1D5DFF",
    "primary": "#2F80FF",
    "primary_hover": "#5AA2FF",
    "accent_cyan": "#19D3FF",
    "coding_green": "#28D17C",
    "video_orange": "#FF9F1A",
    "social_purple": "#8B5CF6",
    "idle_gray": "#8FA1BC",
    "ai_blue": "#3B82F6",
    "reading_blue": "#38BDF8",
    "creative_pink": "#EC4899",
    "tools_grey": "#94A3B8",
    "gaming_red": "#EF4444",
    "danger_red": "#EF4444",
    "warning_yellow": "#FBBF24",
    "success_green": "#22C55E",
    "text": "#F4F8FF",
    "text_secondary": "#B8C4D9",
    "text_muted": "#7F8EA8",
    "text_inverse": "#FFFFFF",
    "border": "#223B63",
    "border_light": "#2C4772",
}


CATEGORY_COLOR_MAP = {
    "ai_tools": COLORS["ai_blue"],
    "coding": COLORS["coding_green"],
    "reading": COLORS["reading_blue"],
    "creative": COLORS["creative_pink"],
    "video": COLORS["video_orange"],
    "gaming": COLORS["gaming_red"],
    "social": COLORS["social_purple"],
    "tools": COLORS["tools_grey"],
    "system_tools": COLORS["tools_grey"],
    "browser_general": COLORS["tools_grey"],
    "browser_other": COLORS["tools_grey"],
    "idle": COLORS["idle_gray"],
    "other": "#64748B",
}


def get_category_color(category_key: str) -> str:
    """Return the theme color for a category key."""
    return CATEGORY_COLOR_MAP.get(category_key, CATEGORY_COLOR_MAP["other"])


GLOBAL_STYLE = f"""
QMainWindow, QWidget {{
    background: {COLORS['bg']};
    color: {COLORS['text']};
    font-family: "Microsoft YaHei", "Segoe UI";
}}
QLabel {{
    background: transparent;
}}
QToolTip {{
    background: {COLORS['panel_bg_alt']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border_light']};
    border-radius: 6px;
    padding: 6px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 2px 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border_light']};
    border-radius: 4px;
    min-height: 32px;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {COLORS['border_light']};
    border-radius: 4px;
}}
"""


SIDEBAR_STYLE = f"""
QListWidget {{
    background: transparent;
    border: none;
    outline: none;
    padding: 14px 12px;
    color: {COLORS['text_secondary']};
}}
QListWidget::item {{
    height: 50px;
    padding-left: 18px;
    margin: 4px 0px;
    border-radius: 12px;
    color: {COLORS['text_secondary']};
    font-weight: 600;
}}
QListWidget::item:hover {{
    background: {COLORS['sidebar_hover']};
    color: {COLORS['text_inverse']};
}}
QListWidget::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS['sidebar_active']}, stop:1 {COLORS['social_purple']});
    color: {COLORS['text_inverse']};
    border: 1px solid #6EA8FF;
}}
"""


TOP_BAR_STYLE = f"""
QFrame#topBar {{
    background: {COLORS['bg']};
    border-bottom: 1px solid {COLORS['border']};
}}
"""


BOTTOM_BAR_STYLE = f"""
QFrame#bottomBar {{
    background: {COLORS['panel_bg']};
    border-top: 1px solid {COLORS['border']};
}}
"""


BUTTON_PRIMARY_STYLE = f"""
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLORS['primary']}, stop:1 {COLORS['social_purple']});
    color: {COLORS['text_inverse']};
    border: none;
    border-radius: 12px;
    padding: 11px 22px;
    font-size: 14px;
    font-weight: 800;
}}
QPushButton:hover {{
    background: {COLORS['primary_hover']};
}}
QPushButton:pressed {{
    background: #1D4ED8;
}}
"""


BUTTON_SECONDARY_STYLE = f"""
QPushButton {{
    background: {COLORS['panel_bg_alt']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border_light']};
    border-radius: 12px;
    padding: 10px 18px;
    font-size: 14px;
    font-weight: 700;
}}
QPushButton:hover {{
    border-color: {COLORS['primary']};
    background: {COLORS['card_bg_alt']};
}}
"""


BUTTON_DANGER_STYLE = f"""
QPushButton {{
    background: transparent;
    color: {COLORS['danger_red']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 700;
}}
QPushButton:hover {{
    background: #321827;
    border-color: {COLORS['danger_red']};
}}
"""


DASHBOARD_CARD_STYLE = f"""
QFrame#dashboardCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {COLORS['card_bg_alt']}, stop:1 {COLORS['card_bg']});
    border: 1px solid {COLORS['border']};
    border-radius: 18px;
}}
"""


CARD_STYLE = DASHBOARD_CARD_STYLE


SUBTLE_TAG_STYLE = f"""
QLabel {{
    font-size: 12px;
    font-weight: 700;
    color: {COLORS['text_secondary']};
    background: {COLORS['panel_bg_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
    padding: 4px 10px;
}}
"""


SECTION_TITLE = f"""
font-size: 17px;
font-weight: 800;
color: {COLORS['text']};
"""


INPUT_STYLE = f"""
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox {{
    background: {COLORS['panel_bg_alt']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: {COLORS['primary']};
}}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {COLORS['primary']};
}}
QTableWidget, QTableView {{
    background: {COLORS['panel_bg']};
    alternate-background-color: {COLORS['panel_bg_alt']};
    color: {COLORS['text']};
    gridline-color: {COLORS['border']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
}}
QHeaderView::section {{
    background: {COLORS['card_bg_alt']};
    color: {COLORS['text_secondary']};
    border: none;
    padding: 8px;
    font-weight: 700;
}}
"""


TABLE_STYLE = INPUT_STYLE
