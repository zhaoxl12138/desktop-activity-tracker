"""Shared theme and QSS snippets for Desktop Activity Tracker GUI."""

COLORS = {
    # Base
    "bg": "#F3F6FB",
    "panel_bg": "#ECF1F8",
    "card_bg": "#FFFFFF",
    "sidebar_bg": "#0F2345",
    "sidebar_hover": "#1A3766",
    "sidebar_active": "#2F6EF8",
    # Brand
    "primary": "#2F6EF8",
    "primary_hover": "#255DE0",
    # Category accents
    "coding_green": "#22B36D",
    "video_orange": "#F59E0B",
    "social_purple": "#8B5CF6",
    "idle_gray": "#8D99AE",
    "ai_blue": "#3B82F6",
    "reading_blue": "#16A3E0",
    "creative_pink": "#F43F82",
    "tools_grey": "#64748B",
    "gaming_red": "#EF4444",
    # Semantic
    "danger_red": "#EF4444",
    "warning_yellow": "#F59E0B",
    "success_green": "#10B981",
    # Text
    "text": "#0F172A",
    "text_secondary": "#475569",
    "text_muted": "#94A3B8",
    "text_inverse": "#F8FAFC",
    # Lines
    "border": "#D6DFEC",
    "border_light": "#E7EDF6",
}


CATEGORY_COLOR_MAP = {
    "ai_tools": COLORS["ai_blue"],
    "coding": COLORS["coding_green"],
    "reading": COLORS["reading_blue"],
    "video": COLORS["video_orange"],
    "creative": COLORS["creative_pink"],
    "social": COLORS["social_purple"],
    "tools": COLORS["tools_grey"],
    "gaming": COLORS["gaming_red"],
    "browser_general": COLORS["tools_grey"],
    "other": COLORS["idle_gray"],
}


def get_category_color(category_key):
    return CATEGORY_COLOR_MAP.get(category_key, COLORS["idle_gray"])


GLOBAL_STYLE = f"""
QMainWindow {{
    background: {COLORS["bg"]};
}}
QWidget {{
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    color: {COLORS["text"]};
}}
QLabel {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: #C0CADB;
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QToolTip {{
    background: {COLORS["sidebar_bg"]};
    color: {COLORS["text_inverse"]};
    border: none;
    border-radius: 8px;
    padding: 6px 10px;
}}
"""


SIDEBAR_STYLE = f"""
QListWidget {{
    background: {COLORS["sidebar_bg"]};
    color: {COLORS["text_inverse"]};
    border: none;
    font-size: 16px;
    padding: 12px 0;
    outline: none;
}}
QListWidget::item {{
    padding: 12px 16px;
    margin: 3px 10px;
    border-radius: 12px;
}}
QListWidget::item:selected {{
    background: {COLORS["sidebar_active"]};
    color: white;
    font-weight: 700;
}}
QListWidget::item:hover:!selected {{
    background: {COLORS["sidebar_hover"]};
}}
"""


TOP_BAR_STYLE = f"""
QFrame#topBar {{
    background: rgba(255, 255, 255, 0.95);
    border-bottom: 1px solid {COLORS["border"]};
}}
"""


BOTTOM_BAR_STYLE = f"""
QFrame#bottomBar {{
    background: rgba(255, 255, 255, 0.95);
    border-top: 1px solid {COLORS["border"]};
}}
"""


BUTTON_PRIMARY_STYLE = f"""
QPushButton {{
    background: {COLORS["primary"]};
    color: white;
    border: none;
    border-radius: 12px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 700;
}}
QPushButton:hover {{
    background: {COLORS["primary_hover"]};
}}
QPushButton:pressed {{
    background: #1D4ED8;
}}
"""


BUTTON_SECONDARY_STYLE = f"""
QPushButton {{
    background: {COLORS["card_bg"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
    padding: 10px 16px;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: #F8FAFF;
    border-color: {COLORS["primary"]};
}}
"""


BUTTON_DANGER_STYLE = f"""
QPushButton {{
    background: transparent;
    color: {COLORS["danger_red"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    padding: 6px 12px;
    font-size: 12px;
}}
QPushButton:hover {{
    background: #FEF2F2;
    border-color: {COLORS["danger_red"]};
}}
"""


DASHBOARD_CARD_STYLE = f"""
QFrame {{
    background: {COLORS["card_bg"]};
    border: 1px solid {COLORS["border_light"]};
    border-radius: 18px;
}}
"""


SUBTLE_TAG_STYLE = f"""
QLabel {{
    font-size: 12px;
    font-weight: 700;
    color: {COLORS["primary"]};
    background: #EEF3FF;
    border: 1px solid #D7E3FF;
    border-radius: 12px;
    padding: 4px 10px;
}}
"""


CARD_STYLE = f"""
QFrame#dataCard {{
    background: {COLORS["card_bg"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
    padding: 16px 18px;
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


TABLE_STYLE = f"""
QTableWidget {{
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
    gridline-color: {COLORS["border_light"]};
    font-size: 13px;
    background: {COLORS["card_bg"]};
    selection-background-color: #EAF1FF;
    selection-color: {COLORS["text"]};
}}
QTableWidget::item {{
    padding: 8px 12px;
}}
QHeaderView::section {{
    background: #F7FAFF;
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid {COLORS["border"]};
    font-weight: 700;
    font-size: 12px;
    color: {COLORS["text_secondary"]};
}}
"""


SECTION_TITLE = f"""
font-size: 20px;
font-weight: 800;
color: {COLORS["text"]};
"""


INPUT_STYLE = f"""
QLineEdit {{
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    background: {COLORS["card_bg"]};
}}
QLineEdit:focus {{
    border-color: {COLORS["primary"]};
}}
QSpinBox {{
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 13px;
    background: {COLORS["card_bg"]};
}}
QSpinBox:focus {{
    border-color: {COLORS["primary"]};
}}
QCheckBox {{
    font-size: 13px;
    spacing: 8px;
}}
"""
