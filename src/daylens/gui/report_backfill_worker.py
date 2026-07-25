"""Background worker for filling gaps in historical daily reports."""

from PySide6.QtCore import QThread, Signal

from ..services.reports_service import backfill_missing_daily_reports


class ReportBackfillWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        db_path: str,
        reports_dir: str,
        obsidian_path: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.db_path = db_path
        self.reports_dir = reports_dir
        self.obsidian_path = obsidian_path

    def run(self) -> None:
        try:
            result = backfill_missing_daily_reports(
                self.db_path,
                self.reports_dir,
                self.obsidian_path,
            )
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
