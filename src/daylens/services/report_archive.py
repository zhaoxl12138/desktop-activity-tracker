"""Calendar routing and Windows publication coordination for vault copies."""
import hashlib
import os
import re
from contextlib import contextmanager
from datetime import date
from pathlib import Path


def report_calendar_date(filename: str) -> date | None:
    name = Path(filename).name
    try:
        weekly = re.fullmatch(r'(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_weekly\.md', name)
        if weekly:
            start, end = (date.fromisoformat(value) for value in weekly.groups())
            return end if 0 <= (end-start).days <= 6 else None
        monthly = re.fullmatch(r'(\d{4})-(\d{2})_monthly\.md', name)
        if monthly:
            return date(int(monthly[1]), int(monthly[2]), 1)
        daily = re.fullmatch(r'(\d{4}-\d{2}-\d{2})\.(?:md|csv)', name)
        return date.fromisoformat(daily[1]) if daily else None
    except ValueError:
        return None


def obsidian_report_destination(filename: str, configured_path: str) -> Path:
    root = Path(configured_path)
    day = report_calendar_date(filename)
    if day is None:
        return root / Path(filename).name
    if re.fullmatch(r'\d{4}', root.name):
        root = root.parent
    elif re.fullmatch(r'\d{4}-\d{2}', root.name) and root.parent.name == root.name[:4]:
        root = root.parent.parent
    return root / f'{day.year:04d}' / day.strftime('%Y-%m') / Path(filename).name


@contextmanager
def obsidian_publication_lock(destination: Path):
    """Serialize only publication of one destination across Windows processes."""
    if os.name != 'nt':
        yield
        return
    import win32event

    canonical = os.path.normcase(str(destination.resolve()))
    key = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    mutex = win32event.CreateMutex(None, False, 'Global\\DayLens_ObsidianSync_' + key)
    try:
        acquired = win32event.WaitForSingleObject(mutex, 5_000)
        if acquired not in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED):
            raise TimeoutError('Obsidian 正在同步此报告，请稍后重试')
        try:
            yield
        finally:
            win32event.ReleaseMutex(mutex)
    finally:
        mutex.Close()
