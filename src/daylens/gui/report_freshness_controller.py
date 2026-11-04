"""Single-flight, latest-selection-only local report evidence reads."""
from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from ..services.report_freshness_service import load_report_freshness
from ..services.report_preview_service import PreviewCache
from ..services.report_sections import report_file_identity


class ReportFreshnessController(QObject):
    ready = Signal(object)

    def __init__(self, db_path, reports_dir, parent=None, *, loader=None):
        super().__init__(parent)
        cache = PreviewCache(reports_dir, preview_limits=False)
        self._loader = loader or (lambda path: load_report_freshness(db_path, path, cache))
        self._results = queue.Queue()
        self._generation = 0
        self._inflight = False
        self._pending = None
        self._closed = False
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._poll)

    def request(self, path):
        if self._closed:
            return
        self._generation += 1
        request = (self._generation, str(path))
        if self._inflight:
            self._pending = request
        else:
            self._launch(request)
        self._timer.start()

    def cancel(self):
        self._generation += 1
        self._pending = None

    def close(self):
        self._closed = True
        self.cancel()
        self._timer.stop()

    def _launch(self, request):
        self._inflight = True
        generation, path = request
        loader, results = self._loader, self._results

        def read():
            try:
                result = loader(path)
            except Exception:
                result = {"level": "unverifiable", "label": "AI 汇总待核验",
                          "message": "当前无法核验报告，原文件未修改"}
            results.put((generation, path, result))

        # The daemon owns no QObjects and can safely finish after its page closes.
        threading.Thread(target=read, name="DayLens-ReportFreshness", daemon=True).start()

    def _poll(self):
        if self._closed:
            return
        try:
            generation, path, result = self._results.get_nowait()
        except queue.Empty:
            return
        self._inflight = False
        if generation == self._generation:
            identity = result.get("file_identity")
            if identity is not None:
                try:
                    unchanged = report_file_identity(identity[0]) == identity
                except OSError:
                    unchanged = False
                if not unchanged:
                    result = {"level": "unverifiable", "label": "报告待核验",
                              "message": "报告已更新，重新选择后核验"}
            self.ready.emit(dict(result, path=path))
        if self._pending is not None:
            request, self._pending = self._pending, None
            self._launch(request)
        else:
            self._timer.stop()
