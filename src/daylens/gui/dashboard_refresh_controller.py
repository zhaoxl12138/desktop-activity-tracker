"""Single-flight background refresh for the application dashboard."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal


@dataclass(frozen=True)
class DashboardSnapshot:
    """A versioned dashboard result safe to share across shell widgets."""

    generation: int
    loaded_at: float
    payload: dict[str, object]


class _DashboardQueryWorker(QThread):
    completed = Signal(int, object)
    failed = Signal(int, str)

    def __init__(
        self,
        generation: int,
        loader: Callable[[], dict[str, object]],
    ) -> None:
        super().__init__()
        self.generation = generation
        self.loader = loader

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            payload = self.loader()
        except Exception as exc:
            self.failed.emit(self.generation, str(exc))
            return
        self.completed.emit(self.generation, payload)


class DashboardRefreshController(QObject):
    """Schedule dashboard reads without overlapping or publishing stale data."""

    snapshot_ready = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        loader: Callable[[], dict[str, object]],
        *,
        interval_ms: int = 5_000,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._loader = loader
        self._foreground = False
        self._closing = False
        self._worker: _DashboardQueryWorker | None = None
        self._pending = False
        self.latest_generation = 0

        self.timer = QTimer(self)
        self.timer.setInterval(max(1, int(interval_ms)))
        self.timer.timeout.connect(self.request_refresh)

    def set_foreground(self, foreground: bool) -> None:
        foreground = bool(foreground)
        if self._closing or foreground == self._foreground:
            return
        self._foreground = foreground
        if foreground:
            self.timer.start()
            self.request_refresh()
            return

        self.timer.stop()
        self._pending = False
        self.latest_generation += 1
        if self._worker is not None:
            self._worker.requestInterruption()

    def request_refresh(self) -> None:
        if self._closing or not self._foreground:
            return
        self.latest_generation += 1
        if self._worker is not None:
            self._pending = True
            return
        self._start_worker(self.latest_generation)

    def shutdown(self, timeout_ms: int = 5_000) -> bool:
        self._closing = True
        self._foreground = False
        self._pending = False
        self.latest_generation += 1
        self.timer.stop()
        worker = self._worker
        if worker is None:
            return True
        worker.requestInterruption()
        completed = worker.wait(max(0, int(timeout_ms)))
        if completed:
            self._worker = None
            worker.deleteLater()
        return bool(completed)

    def resume(self, foreground: bool) -> None:
        """Resume scheduling when a requested application exit is aborted."""
        if not self._closing:
            self.set_foreground(foreground)
            return
        self._closing = False
        self._foreground = False
        self.set_foreground(foreground)

    def _start_worker(self, generation: int) -> None:
        worker = _DashboardQueryWorker(generation, self._loader)
        self._worker = worker
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_finished)
        worker.start()

    def _on_completed(self, generation: int, payload: object) -> None:
        if (
            self._closing
            or not self._foreground
            or generation != self.latest_generation
            or not isinstance(payload, dict)
        ):
            return
        self.snapshot_ready.emit(
            DashboardSnapshot(
                generation=generation,
                loaded_at=time.time(),
                payload=payload,
            )
        )

    def _on_failed(self, generation: int, message: str) -> None:
        if (
            not self._closing
            and self._foreground
            and generation == self.latest_generation
        ):
            self.failed.emit(message)

    def _on_finished(self) -> None:
        worker = self.sender()
        if worker is not self._worker:
            if isinstance(worker, QThread):
                worker.deleteLater()
            return
        self._worker = None
        worker.deleteLater()
        if self._closing or not self._foreground or not self._pending:
            return
        self._pending = False
        self._start_worker(self.latest_generation)
