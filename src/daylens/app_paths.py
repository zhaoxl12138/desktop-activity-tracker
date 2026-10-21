"""Resolved once per runtime; no directory creation or silent state migration."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    database: Path
    program_dir: Path
    intelligence_dir: Path
    reports_dir: Path
    recovery_file: Path
    logs_dir: Path

    @classmethod
    def from_database(cls, database, *, program_dir=None, reports_dir=None):
        from . import get_app_root
        db = Path(database).resolve()
        data = db.parent
        return cls(db, Path(program_dir or get_app_root()).resolve(), data/'intelligence',
                   Path(reports_dir).resolve() if reports_dir else data/'reports',
                   Path(str(db)+'.session-recovery.json'), data/'logs')

    def check_state_locations(self, candidates):
        scattered = []
        for candidate in candidates:
            candidate = Path(candidate).resolve()
            if candidate != self.intelligence_dir and candidate.is_dir():
                files = sorted(p.name for p in candidate.glob('*.json'))
                if files:
                    scattered.append(f'{candidate} ({", ".join(files)})')
        if scattered:
            raise ValueError('检测到分散的分类状态，请先核对来源，不自动迁移：' + '; '.join(scattered))
