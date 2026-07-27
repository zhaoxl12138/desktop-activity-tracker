"""Serial application-level execution for slow GUI-triggered tasks."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal


TaskCallable = Callable[[], object]


@dataclass(frozen=True)
class _QueuedTask:
    key: str
    task: TaskCallable


class _TaskWorker(QThread):
    completed = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, queued_task: _QueuedTask) -> None:
        super().__init__()
        self.queued_task = queued_task

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            result = self.queued_task.task()
        except Exception as exc:
            self.failed.emit(self.queued_task.key, str(exc))
            return
        self.completed.emit(self.queued_task.key, result)


class BackgroundTaskQueue(QObject):
    """Run slow application tasks one at a time and deduplicate by key."""

    task_started = Signal(str)
    task_completed = Signal(str, object)
    task_failed = Signal(str, str)
    task_cancelled = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pending: deque[_QueuedTask] = deque()
        self._active_keys: set[str] = set()
        self._worker: _TaskWorker | None = None
        self._closing = False

    def submit(self, key: str, task: TaskCallable) -> bool:
        normalized_key = str(key).strip()
        if (
            self._closing
            or not normalized_key
            or normalized_key in self._active_keys
        ):
            return False
        queued_task = _QueuedTask(normalized_key, task)
        self._active_keys.add(normalized_key)
        self._pending.append(queued_task)
        self._start_next()
        return True

    def cancel_pending(self, key: str | None = None) -> list[str]:
        target = str(key).strip() if key is not None else None
        retained: deque[_QueuedTask] = deque()
        cancelled: list[str] = []
        while self._pending:
            queued_task = self._pending.popleft()
            if target is None or queued_task.key == target:
                cancelled.append(queued_task.key)
                self._active_keys.discard(queued_task.key)
                self.task_cancelled.emit(queued_task.key)
            else:
                retained.append(queued_task)
        self._pending = retained
        return cancelled

    def shutdown(self, timeout_ms: int = 5_000) -> bool:
        self._closing = True
        self.cancel_pending()

        worker = self._worker
        if worker is None:
            return True
        worker.requestInterruption()
        completed = worker.wait(max(0, int(timeout_ms)))
        if completed:
            self._active_keys.discard(worker.queued_task.key)
            self._worker = None
            worker.deleteLater()
        return bool(completed)

    def resume(self) -> None:
        """Accept work again when an application exit is cancelled."""
        self._closing = False
        self._start_next()

    def _start_next(self) -> None:
        if self._closing or self._worker is not None or not self._pending:
            return
        queued_task = self._pending.popleft()
        worker = _TaskWorker(queued_task)
        self._worker = worker
        worker.completed.connect(self.task_completed)
        worker.failed.connect(self.task_failed)
        worker.finished.connect(self._on_finished)
        self.task_started.emit(queued_task.key)
        worker.start()

    def _on_finished(self) -> None:
        worker = self.sender()
        if not isinstance(worker, _TaskWorker):
            return
        if worker is not self._worker:
            worker.deleteLater()
            return
        self._active_keys.discard(worker.queued_task.key)
        self._worker = None
        worker.deleteLater()
        self._start_next()
