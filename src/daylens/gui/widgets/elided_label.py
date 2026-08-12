"""Labels that elide text using the active font's measured width."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QWidget


class ElidedLabel(QLabel):
    """A QLabel that keeps full text in its tooltip when width is constrained."""

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        max_lines: int = 1,
    ) -> None:
        self._full_text = str(text or "")
        self._max_lines = max(1, int(max_lines))
        super().__init__("", parent)
        self.setWordWrap(self._max_lines > 1)
        self._apply_elision()

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = str(text or "")
        self._apply_elision()

    def fullText(self) -> str:  # noqa: N802
        return self._full_text

    def setMaxLines(self, max_lines: int) -> None:  # noqa: N802
        self._max_lines = max(1, int(max_lines))
        self.setWordWrap(self._max_lines > 1)
        self._apply_elision()

    def maxLines(self) -> int:  # noqa: N802
        return self._max_lines

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        margins = self.contentsMargins()
        height = (
            self.fontMetrics().height() * self._max_lines
            + margins.top()
            + margins.bottom()
        )
        return QSize(0, height)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        metrics = self.fontMetrics()
        width = max(0, self.contentsRect().width())
        source_lines = self._full_text.splitlines() or [""]
        visible_lines = source_lines[: self._max_lines]
        if len(source_lines) > self._max_lines and visible_lines:
            visible_lines[-1] = f"{visible_lines[-1]} …"
        display_lines = [
            metrics.elidedText(line, Qt.ElideRight, width)
            for line in visible_lines
        ]
        display_text = "\n".join(display_lines)
        QLabel.setText(self, display_text)
        self.setToolTip(
            self._full_text if display_text != self._full_text else ""
        )
