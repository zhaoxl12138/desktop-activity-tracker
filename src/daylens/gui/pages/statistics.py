"""Combined statistics page that reuses the existing software/category pages."""

from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .. import style as ui_style


class StatisticsPage(QWidget):
    def __init__(self, software_page: QWidget, category_page: QWidget,
                 goal_page: QWidget | None = None, parent=None, *, live_page: QWidget | None = None):
        super().__init__(parent)
        self.software_page = software_page
        self.category_page = category_page
        self.goal_page = goal_page
        self.live_page = live_page
        self._pages = (software_page, category_page, goal_page, live_page)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 18)
        layout.setSpacing(10)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {ui_style.COLORS['border']}; "
            f"border-radius: 10px; background: {ui_style.COLORS['card_bg']}; }} "
            f"QTabBar::tab {{ padding: 7px 18px; color: {ui_style.COLORS['text_secondary']}; "
            f"background: {ui_style.COLORS['panel_bg_alt']}; border: 1px solid {ui_style.COLORS['border']}; }} "
            f"QTabBar::tab:selected {{ color: white; background: {ui_style.COLORS['primary']}; }}"
        )
        if live_page is not None:
            self.tabs.addTab(live_page, "实时监控")
        self.tabs.addTab(software_page, "软件")
        self.tabs.addTab(category_page, "分类")
        if goal_page is not None:
            self.tabs.addTab(goal_page, "目标与成果")
        if live_page is not None:
            self.tabs.setCurrentWidget(live_page)
        self.tabs.currentChanged.connect(self._activate_current)
        layout.addWidget(self.tabs)
        self._active = False

    def select_tab(self, tab: str) -> None:
        page = {"software": self.software_page, "category": self.category_page,
                "goals": self.goal_page, "live": self.live_page}.get(tab)
        index = self.tabs.indexOf(page) if page is not None else -1
        self.tabs.setCurrentIndex(max(0, index))

    def activate(self, force: bool = False) -> None:
        self._active = True
        self._activate_current(force=force)

    def deactivate(self) -> None:
        self._active = False
        for page in self._pages:
            if hasattr(page, "deactivate"):
                page.deactivate()

    def shutdown(self, timeout_ms: int = 5_000) -> bool:
        completed = True
        for page in self._pages:
            if hasattr(page, "shutdown"):
                completed = bool(page.shutdown(timeout_ms)) and completed
        return completed

    def resume(self) -> None:
        for page in self._pages:
            if hasattr(page, "resume"):
                page.resume()

    def _activate_current(self, _index: int | None = None, *, force: bool = False) -> None:
        if not self._active:
            return
        current = self.tabs.currentWidget()
        for other in self._pages:
            if other is not current and hasattr(other, "deactivate"):
                other.deactivate()
        if current is not None and hasattr(current, "activate"):
            current.activate(force=force)
