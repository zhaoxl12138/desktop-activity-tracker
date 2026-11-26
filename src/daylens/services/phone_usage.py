"""Mirror and read daily iPhone Screen Time Markdown exports."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile


_APP_LINE = re.compile(r"(.+?)\s*[(（]([^()（）]+)[)）]")
_DURATION = re.compile(
    r"\s*(?:([0-9]+)\s*(?:小时|小時)\s*)?"
    r"(?:([0-9]+)\s*(?:分钟|分鐘)\s*)?(?:([0-9]+)\s*秒\s*)?"
)
_PHONE_FOLDER = "手机屏幕使用时间"
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class PhoneUsage:
    apps: list[tuple[str, int]]
    received_days: int
    snapshot_days: int
    unreadable_days: int


def find_phone_archive(obsidian_path: str) -> Path | None:
    if not obsidian_path:
        return None
    output = Path(obsidian_path).expanduser()
    for folder in (output, *output.parents):
        if folder.name == "桌面活动日报":
            return folder.with_name(_PHONE_FOLDER)
        if (folder / ".obsidian").is_dir():
            return folder / "时间追踪" / _PHONE_FOLDER
    return None


def _parse_day(content: str) -> tuple[datetime, dict[str, tuple[str, int]]]:
    header, section, body = content.replace("\r\n", "\n").partition("\n## App 使用时长\n")
    if not section:
        raise ValueError("Missing App usage section")
    received_at = next(
        (line.removeprefix("received_at: ") for line in header.splitlines()
         if line.startswith("received_at: ")), ""
    )
    timestamp = datetime.fromisoformat(received_at)
    apps = {}
    for line in body.splitlines():
        entry = _APP_LINE.fullmatch(line.strip())
        duration = _DURATION.fullmatch(entry[2]) if entry else None
        if not duration or not any(duration.groups()):
            continue
        name = entry[1].strip()
        key = name.casefold()
        hours, minutes, seconds = (int(part or 0) for part in duration.groups())
        total = hours * 3600 + minutes * 60 + seconds
        if name and (key not in apps or total > apps[key][1]):
            apps[key] = (name, total)
    if not apps:
        raise ValueError("No readable App usage")
    return timestamp, apps


def _archive_path(archive: Path, day: date) -> Path:
    return archive / f"{day:%Y}" / f"{day:%Y-%m}" / f"{day.isoformat()}.md"


def _dated_archive_files(archive: Path, through: date):
    for path in archive.glob("????/????-??/????-??-??.md"):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day <= through and path == _archive_path(archive, day):
            yield day, path


def available_phone_days(archive: Path, through: date) -> list[date]:
    days = []
    for day, path in _dated_archive_files(archive, through):
        try:
            _parse_day(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        days.append(day)
    return sorted(days, reverse=True)


def sync_phone_archive(source: Path, archive: Path, through: date) -> int:
    """Copy new and updated exports without removing existing local dates."""
    copied = 0
    for day, path in _dated_archive_files(source, through):
        destination = _archive_path(archive, day)
        try:
            incoming = path.read_bytes()
            try:
                existing = destination.read_bytes()
            except FileNotFoundError:
                existing = b""
            if incoming == existing:
                continue
            received_at, _ = _parse_day(incoming.decode("utf-8-sig"))
            if existing:
                try:
                    local_at, _ = _parse_day(existing.decode("utf-8-sig"))
                except ValueError:
                    pass
                else:
                    if local_at.astimezone() > received_at.astimezone():
                        continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False)
            temp_path = Path(temporary.name)
            try:
                with temporary:
                    temporary.write(incoming)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                temp_path.replace(destination)
            finally:
                temp_path.unlink(missing_ok=True)
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            _LOG.warning("Could not copy the phone export for %s", day, exc_info=True)
            continue
        copied += 1
    return copied


def load_phone_usage(archive: Path, start: date, end: date) -> PhoneUsage:
    totals = {}
    received = snapshots = unreadable = 0
    for delta in range((end - start).days + 1):
        day = start + timedelta(days=delta)
        path = _archive_path(archive, day)
        try:
            timestamp, apps = _parse_day(path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            unreadable += 1
            continue
        received += 1
        snapshots += timestamp.date() == day
        for key, (name, seconds) in apps.items():
            label, total = totals.get(key, (name, 0))
            totals[key] = (label, total + seconds)
    ranked = sorted(totals.values(), key=lambda app: (-app[1], app[0].casefold()))
    return PhoneUsage(ranked, received, snapshots, unreadable)
