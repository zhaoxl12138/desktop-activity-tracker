"""First-run setup wizard — scan installed apps and let user confirm classifications."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QWidget, QMenu, QProgressBar,
    QLayout, QLayoutItem,
)
from PySide6.QtCore import Qt, QTimer, QRect

from ..app_scanner import (
    classify_scanned_apps, KNOWN_APPS, _scan_registry_uninstall,
)
from ..services.rules_service import save_wizard_classifications
from . import style as ui_style
from .style import COLORS

import os
import yaml

_CATEGORY_CYCLE = [
    "coding", "ai_tools", "reading", "creative",
    "video", "social", "tools", "browser_general",
]

_CAT_INFO = {
    "coding":        ("💼", "工作学习",   COLORS["coding_green"]),
    "ai_tools":      ("🤖", "AI 工具",    COLORS["ai_blue"]),
    "reading":       ("📖", "阅读学习",   COLORS["reading_blue"]),
    "creative":      ("🎨", "创作设计",   COLORS["creative_pink"]),
    "video":         ("📺", "娱乐休闲",   COLORS["video_orange"]),
    "social":        ("💬", "社交通讯",   COLORS["social_purple"]),
    "tools":         ("🔧", "系统工具",   COLORS["tools_cyan"]),
    "browser_general":("🌐", "浏览器",    COLORS["browser_amber"]),
    None:            ("📦", "未分类",     COLORS["text_muted"]),
}


class _ChipButton(QPushButton):
    """A compact toggle chip representing one app."""

    def __init__(self, process_name: str, category_key: str | None, wizard: "SetupWizard"):
        super().__init__()
        self._process = process_name
        self._cat_key = category_key
        self._wizard = wizard
        self._build_label()
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._on_click)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_right_click)

    def _build_label(self):
        info = _CAT_INFO.get(self._cat_key, _CAT_INFO[None])
        color = info[2]
        icon = info[1]
        display = os.path.splitext(self._process)[0]
        text = f"{icon}  {display}"
        self.setText(text)

        cat_name = info[1]
        tooltip = f"{display}\n当前: {cat_name}\n左键切换分类 | 右键选择分类"
        self.setToolTip(tooltip)

        self.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['panel_bg_alt']};
                border: 1px solid {color};
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 12px;
                color: {COLORS['text']};
                text-align: left;
            }}
            QPushButton:hover {{
                background: {COLORS['sidebar_hover']};
                border-color: {COLORS['primary']};
            }}
        """)

    def _on_click(self):
        """Cycle to next category."""
        current = self._cat_key
        try:
            idx = _CATEGORY_CYCLE.index(current)
            next_cat = _CATEGORY_CYCLE[(idx + 1) % len(_CATEGORY_CYCLE)]
        except ValueError:
            next_cat = _CATEGORY_CYCLE[0]
        self._wizard._reclassify(self._process, current, next_cat)
        self._cat_key = next_cat
        self._build_label()

    def _on_right_click(self, pos):
        """Show category picker menu."""
        menu = QMenu(self)
        for cat_key in _CATEGORY_CYCLE:
            info = _CAT_INFO[cat_key]
            action = menu.addAction(f"{info[0]}  {info[1]}")
            action.triggered.connect(lambda checked, ck=cat_key: self._set_cat(ck))
        menu.addSeparator()
        uncat_action = menu.addAction("📦  未分类")
        uncat_action.triggered.connect(lambda: self._set_cat(None))
        menu.exec(self.mapToGlobal(pos))

    def _set_cat(self, cat_key):
        old = self._cat_key
        self._cat_key = cat_key
        self._wizard._reclassify(self._process, old, cat_key)
        self._build_label()


class SetupWizard(QDialog):
    def __init__(self, config_path, db_path, parent=None):
        super().__init__(parent)
        self.config_path = config_path
        self.db_path = db_path
        self._apps: dict[str, str | None] = {}  # {process_name: category_key | None}
        self._section_widgets: dict[str | None, QWidget] = {}
        self._section_layouts: dict[str | None, QHBoxLayout] = {}

        self.setWindowTitle("DayLens · 首次设置")
        self.setMinimumSize(720, 520)
        self.resize(760, 560)
        self.setStyleSheet(f"background: {COLORS['bg']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(12)

        title = QLabel("首次设置向导")
        title.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['text']};")
        root.addWidget(title)

        hint = QLabel("自动扫描已安装软件并分类，点击可切换分类，确认后开始记录。")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        root.addWidget(hint)

        # Progress bar during scan
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background: {COLORS['panel_bg']};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {COLORS['primary']};
                border-radius: 3px;
            }}
        """)
        root.addWidget(self._progress)

        # Scroll area for categorized apps
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border_light']}; border-radius: 3px; min-height: 20px;
            }}
        """)

        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet("background: transparent;")
        self._sections_layout = QVBoxLayout(self._scroll_content)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(8)
        self._sections_layout.addStretch()
        scroll.setWidget(self._scroll_content)
        root.addWidget(scroll, 1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._confirm_btn = QPushButton("确认并开始记录")
        self._confirm_btn.setStyleSheet(ui_style.get_button_primary_style())
        self._confirm_btn.setCursor(Qt.PointingHandCursor)
        self._confirm_btn.clicked.connect(self._on_confirm)
        self._confirm_btn.setEnabled(False)
        btn_row.addWidget(self._confirm_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        # Start registry scan after UI is shown (no COM, fast)
        QTimer.singleShot(150, self._run_scan)

    def _run_scan(self):
        try:
            apps = _scan_registry_uninstall()
        except Exception:
            apps = {}
        classified = classify_scanned_apps(apps)
        self._apps = {}
        for pname in apps:
            cat = None
            for ck, names in classified.items():
                if pname in names:
                    cat = ck
                    break
            self._apps[pname] = cat
        self._build_ui()

    def _build_ui(self):
        # Remove progress
        self._progress.setVisible(False)

        # Group by category
        groups: dict[str | None, list[str]] = {}
        for pname, cat in sorted(self._apps.items()):
            groups.setdefault(cat, []).append(pname)

        # Display order
        order = [k for k in _CATEGORY_CYCLE if k in groups] + \
                ([None] if None in groups else [])

        for cat_key in order:
            apps_list = groups[cat_key]
            info = _CAT_INFO.get(cat_key, _CAT_INFO[None])
            icon, name, color = info

            section = QFrame()
            section.setStyleSheet(f"""
                QFrame {{
                    background: {COLORS['card_bg']};
                    border: 1px solid {color if cat_key else COLORS['border']};
                    border-radius: 10px;
                }}
            """)
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(12, 8, 12, 8)
            section_layout.setSpacing(4)

            header = QLabel(f"{icon}  {name} ({len(apps_list)})")
            header.setObjectName("section_header")
            header.setStyleSheet(
                f"font-size: 14px; font-weight: 700; color: {color if cat_key else COLORS['text_secondary']};"
            )
            section_layout.addWidget(header)

            chips_wrap = QWidget()
            chips_wrap.setStyleSheet("background: transparent;")
            chips_layout = _FlowLayout(chips_wrap)
            chips_layout.setSpacing(6)

            for pname in apps_list:
                chip = _ChipButton(pname, cat_key, self)
                chips_layout.addWidget(chip)

            section_layout.addWidget(chips_wrap)
            self._section_widgets[cat_key] = section
            self._section_layouts[cat_key] = chips_layout

            # Insert before the stretch
            self._sections_layout.insertWidget(
                self._sections_layout.count() - 1, section
            )

        self._confirm_btn.setEnabled(True)

    def _reclassify(self, process_name: str, old_cat: str | None, new_cat: str | None):
        """Move an app chip from one category section to another."""
        self._apps[process_name] = new_cat

        # Find the chip button in the old section and remove it
        chip_to_move = None
        if old_cat in self._section_layouts:
            layout = self._section_layouts[old_cat]
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget():
                    w = item.widget()
                    if isinstance(w, _ChipButton) and w._process == process_name:
                        chip_to_move = w
                        layout.removeWidget(w)
                        break

        if chip_to_move is None:
            return

        # Ensure target section exists
        if new_cat not in self._section_widgets:
            self._create_section(new_cat)

        # Add chip to target section
        self._section_layouts[new_cat].addWidget(chip_to_move)

        # Update section headers (count)
        self._update_section_counts()

    def _create_section(self, cat_key: str | None):
        info = _CAT_INFO.get(cat_key, _CAT_INFO[None])
        icon, name, color = info

        section = QFrame()
        section.setStyleSheet(f"""
            QFrame {{
                background: {COLORS['card_bg']};
                border: 1px solid {color if cat_key else COLORS['border']};
                border-radius: 10px;
            }}
        """)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(12, 8, 12, 8)
        section_layout.setSpacing(4)

        header = QLabel(f"{icon}  {name} (0)")
        header.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {color if cat_key else COLORS['text_secondary']};"
        )
        header.setObjectName("section_header")
        section_layout.addWidget(header)

        chips_wrap = QWidget()
        chips_wrap.setStyleSheet("background: transparent;")
        chips_layout = _FlowLayout(chips_wrap)
        chips_layout.setSpacing(6)
        section_layout.addWidget(chips_wrap)

        self._section_widgets[cat_key] = section
        self._section_layouts[cat_key] = chips_layout
        # Insert before the stretch (always at index count-1)
        self._sections_layout.insertWidget(
            self._sections_layout.count() - 1, section
        )

    def _update_section_counts(self):
        """Refresh count labels on section headers."""
        for cat_key, section in self._section_widgets.items():
            layout = self._section_layouts.get(cat_key)
            count = layout.count() if layout else 0
            info = _CAT_INFO.get(cat_key, _CAT_INFO[None])
            header_text = f"{info[0]}  {info[1]} ({count})"
            # Find the header QLabel (first child label)
            header = section.findChild(QLabel, "section_header")
            if not header:
                # Try first QLabel
                for child in section.children():
                    if isinstance(child, QLabel):
                        header = child
                        break
            if header:
                header.setText(header_text)

    def _on_confirm(self):
        """Merge the confirmed processes while retaining factory rule metadata."""
        with open(self.config_path, "r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        save_wizard_classifications(self.db_path, self._apps, config)
        self.accept()


# ── Flow layout for chip wrapping ────────────────────────────────────

class _FlowLayout(QLayout):
    """A layout that wraps child widgets across rows, like flex-wrap in CSS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h_spacing = 6
        self._v_spacing = 4

    def addItem(self, item: QLayoutItem):
        self._items.append(item)

    def addWidget(self, widget: QWidget):
        super().addWidget(widget)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def removeWidget(self, widget: QWidget):
        for item in self._items:
            if item.widget() is widget:
                self._items.remove(item)
                break

    def setSpacing(self, spacing: int):
        self._h_spacing = spacing
        self._v_spacing = max(2, spacing // 2)

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), dry_run=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, dry_run=False)

    def minimumSize(self):
        size = super().minimumSize()
        return size.expandedTo(self.sizeHint())

    def sizeHint(self):
        return self.minimumSize()

    def _do_layout(self, rect: QRect, dry_run: bool) -> int:
        x = rect.x()
        y = rect.y()
        row_height = 0
        avail_width = rect.width()

        for item in self._items:
            widget = item.widget()
            if widget is None:
                continue
            size_hint = widget.sizeHint()

            if x + size_hint.width() > rect.x() + avail_width and x > rect.x():
                x = rect.x()
                y += row_height + self._v_spacing
                row_height = 0

            if not dry_run:
                widget.setGeometry(QRect(x, y, size_hint.width(), size_hint.height()))

            x += size_hint.width() + self._h_spacing
            row_height = max(row_height, size_hint.height())

        return y + row_height
