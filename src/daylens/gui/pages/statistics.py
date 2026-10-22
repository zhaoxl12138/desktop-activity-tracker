"""Combined statistics page that reuses the existing software/category pages."""

from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .. import style as ui_style


class StatisticsPage(QWidget):
    def __init__(self, software_page: QWidget, category_page: QWidget,
                 task_page: QWidget | None = None,
                 goal_page: QWidget | None = None, parent=None):
        super().__init__(parent)
        self.software_page = software_page
        self.category_page = category_page
        self.task_page = task_page
        self.goal_page = goal_page
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
        self.tabs.addTab(software_page, "软件")
        self.tabs.addTab(category_page, "分类")
        if task_page is not None:
            self.tabs.addTab(task_page, "任务链")
        if goal_page is not None:
            self.tabs.addTab(goal_page, "目标与成果")
        self.tabs.currentChanged.connect(self._activate_current)
        layout.addWidget(self.tabs)
        self._active = False

    def select_tab(self, tab: str) -> None:
        self.tabs.setCurrentIndex({"software": 0, "category": 1,
                                   "tasks": 2, "goals": 3}.get(tab, 0))

    def activate(self, force: bool = False) -> None:
        self._active = True
        self._activate_current(force=force)

    def deactivate(self) -> None:
        self._active = False
        for page in (self.software_page, self.category_page, self.task_page, self.goal_page):
            if hasattr(page, "deactivate"):
                page.deactivate()

    def shutdown(self, timeout_ms: int = 5_000) -> bool:
        completed = True
        for page in (self.software_page, self.category_page, self.task_page, self.goal_page):
            if hasattr(page, "shutdown"):
                completed = bool(page.shutdown(timeout_ms)) and completed
        return completed

    def resume(self) -> None:
        for page in (self.software_page, self.category_page, self.task_page, self.goal_page):
            if hasattr(page, "resume"):
                page.resume()

    def _activate_current(self, _index: int | None = None, *, force: bool = False) -> None:
        if not self._active:
            return
        current = self.tabs.currentWidget()
        for other in (self.software_page, self.category_page, self.task_page, self.goal_page):
            if other is not current and hasattr(other, "deactivate"):
                other.deactivate()
        if current is not None and hasattr(current, "activate"):
            current.activate(force=force)
