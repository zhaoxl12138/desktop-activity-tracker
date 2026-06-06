"""Centralized UI theme and QSS styles."""

from __future__ import annotations


DARK_COLORS = {
    "bg": "#020D1D",
    "panel_bg": "#06172B",
    "panel_bg_alt": "#0B203B",
    "card_bg": "#06182C",
    "card_bg_alt": "#09213A",
    "sidebar_bg": "#031020",
    "sidebar_hover": "#102642",
    "sidebar_active": "#1D5DFF",
    "primary": "#2F80FF",
    "primary_hover": "#5AA2FF",
    "accent_cyan": "#19D3FF",
    "coding_green": "#22C55E",
    "video_orange": "#F97316",
    "social_purple": "#3B82F6",
    "idle_gray": "#8FA1BC",
    "ai_blue": "#94A3B8",
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
    "brand": "#4DA8FF",
    "border": "#17304F",
    "border_light": "#254465",
    "success_bg": "#0F2A23",
    "warning_bg": "#332510",
    "danger_bg": "#321827",
    "error_bg": "#3A1620",
}

LIGHT_COLORS = {
    "bg": "#F3F6FB",
    "panel_bg": "#FFFFFF",
    "panel_bg_alt": "#ECF2FB",
    "card_bg": "#FFFFFF",
    "card_bg_alt": "#F7FAFF",
    "sidebar_bg": "#EAF1FB",
    "sidebar_hover": "#DCE8FA",
    "sidebar_active": "#2F80FF",
    "primary": "#2F80FF",
    "primary_hover": "#5AA2FF",
    "accent_cyan": "#19D3FF",
    "coding_green": "#22C55E",
    "video_orange": "#F97316",
    "social_purple": "#3B82F6",
    "idle_gray": "#94A3B8",
    "ai_blue": "#94A3B8",
    "reading_blue": "#0EA5E9",
    "creative_pink": "#EC4899",
    "tools_grey": "#94A3B8",
    "gaming_red": "#EF4444",
    "danger_red": "#DC2626",
    "warning_yellow": "#D97706",
    "success_green": "#16A34A",
    "text": "#0F172A",
    "text_secondary": "#334155",
    "text_muted": "#64748B",
    "text_inverse": "#FFFFFF",
    "brand": "#1E5FBF",
    "border": "#C7D5E8",
    "border_light": "#B6C7E0",
    "success_bg": "#DCFCE7",
    "warning_bg": "#FEF3C7",
    "danger_bg": "#FEE2E2",
    "error_bg": "#FEE2E2",
}

THEMES = {
    "dark": DARK_COLORS,
    "light": LIGHT_COLORS,
}

CURRENT_THEME = "dark"
COLORS = dict(THEMES[CURRENT_THEME])
CATEGORY_COLOR_MAP: dict[str, str] = {}


def refresh_category_colors() -> None:
    CATEGORY_COLOR_MAP.clear()
    CATEGORY_COLOR_MAP.update(
        {
            "work": COLORS["coding_green"],
            "ai_tools": COLORS["ai_blue"],
            "coding": COLORS["coding_green"],
            "reading": COLORS["reading_blue"],
            "creative": COLORS["creative_pink"],
            "entertainment": COLORS["video_orange"],
            "video": COLORS["video_orange"],
            "social": COLORS["social_purple"],
            "tools": COLORS["tools_grey"],
            "system_tools": COLORS["tools_grey"],
            "browser_general": COLORS["tools_grey"],
            "browser_other": COLORS["tools_grey"],
            "idle": COLORS["idle_gray"],
            "other": COLORS["tools_grey"],
        }
    )


def apply_theme(theme_name: str) -> str:
    global CURRENT_THEME
    CURRENT_THEME = "light" if theme_name == "light" else "dark"
    COLORS.clear()
    COLORS.update(THEMES[CURRENT_THEME])
    refresh_category_colors()
    refresh_styles()
    return CURRENT_THEME


def is_dark_theme() -> bool:
    return CURRENT_THEME == "dark"


def get_category_color(category_key: str) -> str:
    return CATEGORY_COLOR_MAP.get(category_key, CATEGORY_COLOR_MAP["other"])


def get_global_style() -> str:
    return f"""
QMainWindow, QWidget {{
    background: {COLORS['bg']};
    color: {COLORS['text']};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
                 "Noto Sans CJK SC", "SimHei", "SimSun", "Segoe UI", sans-serif;
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


def get_sidebar_style() -> str:
    return f"""
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


def get_top_bar_style() -> str:
    return f"""
QFrame#topBar {{
    background: {COLORS['bg']};
    border-bottom: 1px solid rgba(37, 68, 101, 0.38);
}}
"""


def get_bottom_bar_style() -> str:
    return f"""
QFrame#bottomBar {{
    background: {COLORS['panel_bg']};
    border-top: 1px solid {COLORS['border']};
}}
"""


def get_button_primary_style() -> str:
    return f"""
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


def get_button_secondary_style() -> str:
    return f"""
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


def get_button_danger_style() -> str:
    return f"""
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
    background: {COLORS['danger_bg']};
    border-color: {COLORS['danger_red']};
}}
"""


def get_dashboard_card_style() -> str:
    return f"""
QFrame#dashboardCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {COLORS['card_bg_alt']}, stop:1 {COLORS['card_bg']});
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
}}
"""


def get_subtle_tag_style() -> str:
    return f"""
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


def get_section_title() -> str:
    return f"""
font-size: 17px;
font-weight: 800;
color: {COLORS['text']};
"""


def get_input_style() -> str:
    return f"""
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
QTableWidget::item, QTableView::item {{
    padding: 8px;
    border: none;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {COLORS['primary']};
    color: {COLORS['text_inverse']};
}}
QHeaderView::section {{
    background: {COLORS['card_bg_alt']};
    color: {COLORS['text_secondary']};
    border: none;
    padding: 8px;
    font-weight: 700;
}}
QCheckBox {{
    color: {COLORS['text_secondary']};
    spacing: 8px;
}}
"""


def get_table_style() -> str:
    return get_input_style()


def refresh_styles() -> None:
    global GLOBAL_STYLE
    global SIDEBAR_STYLE
    global TOP_BAR_STYLE
    global BOTTOM_BAR_STYLE
    global BUTTON_PRIMARY_STYLE
    global BUTTON_SECONDARY_STYLE
    global BUTTON_DANGER_STYLE
    global DASHBOARD_CARD_STYLE
    global CARD_STYLE
    global SUBTLE_TAG_STYLE
    global SECTION_TITLE
    global INPUT_STYLE
    global TABLE_STYLE

    GLOBAL_STYLE = get_global_style()
    SIDEBAR_STYLE = get_sidebar_style()
    TOP_BAR_STYLE = get_top_bar_style()
    BOTTOM_BAR_STYLE = get_bottom_bar_style()
    BUTTON_PRIMARY_STYLE = get_button_primary_style()
    BUTTON_SECONDARY_STYLE = get_button_secondary_style()
    BUTTON_DANGER_STYLE = get_button_danger_style()
    DASHBOARD_CARD_STYLE = get_dashboard_card_style()
    CARD_STYLE = DASHBOARD_CARD_STYLE
    SUBTLE_TAG_STYLE = get_subtle_tag_style()
    SECTION_TITLE = get_section_title()
    INPUT_STYLE = get_input_style()
    TABLE_STYLE = get_table_style()


refresh_category_colors()
refresh_styles()
