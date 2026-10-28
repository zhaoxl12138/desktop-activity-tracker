"""Single-flight background refresh for the application dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
        max_age_ms: int | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._loader = loader
        self._foreground = False
        self._closing = False
        self._worker: _DashboardQueryWorker | None = None
        self._pending = False
        self.latest_generation = 0
        self._context_day = date.today()
        self._last_published_payload: dict[str, object] | None = None
        self._max_age_seconds = (
            None if max_age_ms is None else max(0, int(max_age_ms)) / 1000.0
        )
        self._monotonic = monotonic
        self._last_success_at: float | None = None

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
            if not self._snapshot_is_fresh():
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
        if self._context_day != date.today():
            self.invalidate_context()
            return
        if self._worker is not None:
            self._pending = True
            return
        self.latest_generation += 1
        self._start_worker(self.latest_generation)

    def invalidate_context(self) -> None:
        self._context_day = date.today()
        self.latest_generation += 1
        self._last_published_payload = None
        self._last_success_at = None
        if self._closing or not self._foreground:
            return
        if self._worker is not None:
            self._pending = True
        else:
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

    def _snapshot_is_fresh(self) -> bool:
        if self._max_age_seconds is None or self._last_success_at is None:
            return False
        return self._monotonic() - self._last_success_at <= self._max_age_seconds

    def _on_completed(self, generation: int, payload: object) -> None:
        if self._context_day != date.today():
            self.invalidate_context()
            return
        if (
            self._closing
            or not self._foreground
            or generation != self.latest_generation
            or not isinstance(payload, dict)
        ):
            return
        self._last_success_at = self._monotonic()
        if payload == self._last_published_payload:
            return
        self._last_published_payload = payload
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
            self._last_success_at = None
            self._last_published_payload = None
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
        self.latest_generation += 1
        self._start_worker(self.latest_generation)
