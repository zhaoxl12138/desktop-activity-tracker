"""30-minute timeline — aggregates activity_sessions into 48 time blocks,
identifies focus blocks, and computes fragmentation metrics."""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .utils import fmt_seconds


# ── Category groups ──

WORK_CATS = {"ai_tools", "coding", "reading", "creative"}
ENTERTAINMENT_CATS = {"video", "gaming"}


# ── Data classes ──


@dataclass
class TimeBlock:
    slot: str = ""                    # "09:00-09:30"
    dominant_category: str = "离线"
    effective_seconds: int = 0
    entertainment_seconds: int = 0
    idle_seconds: int = 0
    work_seconds: int = 0
    top_app: str = ""
    top_title: str = ""
    switch_count: int = 0
    # Internal accumulator
    _app_seconds: dict = field(default_factory=dict, repr=False)
    _title_seconds: dict = field(default_factory=dict, repr=False)


@dataclass
class FocusBlock:
    start_slot: str = ""
    end_slot: str = ""
    duration_minutes: int = 0
    main_category: str = ""
    effective_seconds: int = 0
    top_apps: list = field(default_factory=list)
    interruption_count: int = 0


# ── Public API ──


def build_timeline(db_path, date_str):
    """Return a list of 48 TimeBlock objects for the given date.

    Reads activity_sessions and distributes each session's duration across
    the 30-minute blocks it spans, splitting by time proportion.
    """
    blocks = _init_blocks()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT session_id, start_time, end_time, process_name,
                  window_title, normalized_title, category_key, category_name,
                  duration_seconds, effective_seconds, idle_seconds
           FROM activity_sessions
           WHERE date = ?
           ORDER BY start_time""",
        (date_str,)
    ).fetchall()
    conn.close()

    if not rows:
        return blocks

    for row in rows:
        start = datetime.strptime(row["start_time"], "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(row["end_time"], "%Y-%m-%d %H:%M:%S")
        dur = row["duration_seconds"] or 0
        if dur <= 0:
            continue

        eff = row["effective_seconds"] or 0
        idle = row["idle_seconds"] or 0
        proc = row["process_name"] or ""
        title = row["normalized_title"] or row["window_title"] or ""
        cat_key = row["category_key"] or ""
        cat_name = row["category_name"] or ""

        _distribute_session(blocks, start, end, dur, eff, idle,
                            proc, title, cat_key, cat_name,
                            row["session_id"])

    # Finalise each block — normalize to exactly 30 min (1800s)
    for b in blocks:
        total = b.effective_seconds + b.idle_seconds
        if total > 1800:
            scale = 1800 / total
            b.effective_seconds = round(b.effective_seconds * scale)
            b.idle_seconds = round(b.idle_seconds * scale)
            b.entertainment_seconds = round(b.entertainment_seconds * scale)
            b.work_seconds = round(b.work_seconds * scale)
        elif 0 < total < 1800:
            b.idle_seconds += 1800 - total
        _finalise_block(b)

    return blocks


def identify_focus_blocks(timeline):
    """Scan timeline for continuous work periods >= 45 min with < 5 min entertainment breaks."""
    focus_blocks = []
    i = 0
    while i < len(timeline):
        b = timeline[i]
        if b.work_seconds < 1200 or b.dominant_category not in ("办公", "AI工具"):
            i += 1
            continue

        # Start of a potential focus block
        j = i
        total_eff = 0
        total_work = 0
        entertainment_break = 0
        interruptions = 0
        app_counter = {}
        main_cat = b.dominant_category

        while j < len(timeline):
            bj = timeline[j]
            if bj.dominant_category in ("办公", "AI工具"):
                if entertainment_break < 300:  # < 5 min entertainment in gap
                    total_eff += bj.effective_seconds
                    total_work += bj.work_seconds
                    if bj.top_app:
                        app_counter[bj.top_app] = app_counter.get(bj.top_app, 0) + bj.effective_seconds
                    j += 1
                    entertainment_break = 0
                    continue
                else:
                    break
            elif bj.dominant_category == "娱乐":
                entertainment_break += bj.entertainment_seconds
                if entertainment_break < 300:
                    interruptions += 1
                    j += 1
                    continue
                else:
                    break
            elif bj.dominant_category == "混合":
                total_eff += bj.effective_seconds
                total_work += bj.work_seconds
                j += 1
                break
            else:
                break

        if total_work >= 2700:  # >= 45 min work
            duration_min = (j - i) * 30
            top_apps = sorted(app_counter.items(), key=lambda x: -x[1])[:3]
            focus_blocks.append(FocusBlock(
                start_slot=timeline[i].slot.split("-")[0],
                end_slot=timeline[j - 1].slot.split("-")[1] if j > i else timeline[i].slot.split("-")[1],
                duration_minutes=duration_min,
                main_category=main_cat,
                effective_seconds=total_work,
                top_apps=[a[0] for a in top_apps],
                interruption_count=interruptions,
            ))

        i = j if j > i else i + 1

    return focus_blocks


def calc_fragmentation(timeline, switch_count):
    """Return fragmentation index 0-100 and a description."""
    total_eff = sum(b.effective_seconds for b in timeline)
    effective_hours = max(total_eff / 3600.0, 1.0)
    index = min(100, round(switch_count / effective_hours * 10))

    mixed_blocks = sum(1 for b in timeline if b.dominant_category == "混合")
    if mixed_blocks > 8:
        index = min(100, index + 15)

    if index < 25:
        desc = "低，今天专注度较好"
    elif index < 50:
        desc = "中等，部分时段存在切换偏多"
    elif index < 75:
        desc = "偏高，切换频繁影响深度工作"
    else:
        desc = "严重碎片化，建议减少频繁切换"

    return index, desc


def generate_one_line_review(timeline, focus_blocks, fragmentation_index):
    """Generate a one-sentence review of today's usage pattern."""
    work_blocks = [b for b in timeline if b.dominant_category in ("办公", "AI工具") and b.work_seconds >= 600]
    entertainment_blocks = [b for b in timeline if b.dominant_category == "娱乐" and b.entertainment_seconds >= 600]

    # Morning: 06:00-12:00, Afternoon: 12:00-18:00, Evening: 18:00-24:00
    morning_work = sum(b.work_seconds for b in work_blocks if b.slot < "12:00")
    afternoon_work = sum(b.work_seconds for b in work_blocks if "12:00" <= b.slot < "18:00")
    evening_work = sum(b.work_seconds for b in work_blocks if b.slot >= "18:00")

    morning_ent = sum(b.entertainment_seconds for b in entertainment_blocks if b.slot < "12:00")
    afternoon_ent = sum(b.entertainment_seconds for b in entertainment_blocks if "12:00" <= b.slot < "18:00")
    evening_ent = sum(b.entertainment_seconds for b in entertainment_blocks if b.slot >= "18:00")

    parts = []

    # Work distribution
    max_work_period = max(
        ("上午", morning_work), ("下午", afternoon_work), ("晚上", evening_work),
        key=lambda x: x[1]
    )
    if max_work_period[1] >= 1800:
        parts.append(f"{max_work_period[0]}办公较集中")
    elif morning_work + afternoon_work + evening_work < 1800:
        parts.append("今日办公时间偏少")

    # Entertainment pattern
    max_ent_period = max(
        ("上午", morning_ent), ("下午", afternoon_ent), ("晚上", evening_ent),
        key=lambda x: x[1]
    )
    if max_ent_period[1] >= 1800:
        parts.append(f"{max_ent_period[0]}娱乐集中发生")
    elif morning_ent + afternoon_ent + evening_ent < 600:
        parts.append("娱乐时间控制得当")

    # Fragmentation
    if fragmentation_index >= 50:
        # Find peak fragmentation period
        afternoon_switches = sum(
            b.switch_count for b in timeline
            if "12:00" <= b.slot < "18:00"
        )
        morning_switches = sum(
            b.switch_count for b in timeline
            if "06:00" <= b.slot < "12:00"
        )
        if afternoon_switches > morning_switches:
            parts.append("下午窗口切换偏多，主线推进不够连续")
        elif morning_switches > 0:
            parts.append("切换偏多，注意保持主线连续推进")

    # Focus blocks
    if focus_blocks:
        longest = max(focus_blocks, key=lambda f: f.duration_minutes)
        parts.append(f"最长专注时段{fmt_seconds(longest.effective_seconds)}")

    if not parts:
        parts.append("今日使用较为均衡")

    return "；".join(parts) + "。"


# ── Internal helpers ──


def _init_blocks():
    """Create 48 empty TimeBlock slots (00:00-00:30 through 23:30-24:00)."""
    blocks = []
    for h in range(24):
        for m in (0, 30):
            start = f"{h:02d}:{m:02d}"
            end_h = h if m == 0 else h
            end_m = 30 if m == 0 else 0
            if m == 30:
                end_h = h + 1 if h < 23 else 0
            end = f"{end_h:02d}:{end_m:02d}"
            slot = f"{start}-{end}"
            blocks.append(TimeBlock(slot=slot))
    return blocks


def _distribute_session(blocks, start, end, dur, eff, idle,
                        proc, title, cat_key, cat_name, session_id):
    """Split a session's duration across the 30-min blocks it overlaps."""
    if dur <= 0:
        return

    current = start
    # Track session_id per block to count switches
    while current < end:
        # Find the block this timestamp belongs to
        block_idx = current.hour * 2 + (1 if current.minute >= 30 else 0)
        if block_idx >= 48:
            break

        # Block boundaries
        block_start_h = block_idx // 2
        block_start_m = 0 if block_idx % 2 == 0 else 30
        block_start = current.replace(hour=block_start_h, minute=block_start_m, second=0, microsecond=0)
        block_end = block_start + timedelta(minutes=30)
        if block_start_m == 30:
            block_start = current.replace(hour=block_start_h, minute=30, second=0, microsecond=0)
            if block_start_h < 23:
                block_end = current.replace(hour=block_start_h + 1, minute=0, second=0, microsecond=0)
            else:
                block_end = current.replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(seconds=1)

        # Recalculate block boundaries more reliably
        slot_h = block_idx // 2
        slot_m = 0 if block_idx % 2 == 0 else 30
        slot_start = current.replace(hour=slot_h, minute=slot_m, second=0, microsecond=0)
        slot_end = slot_start + timedelta(minutes=30)

        overlap_start = max(current, slot_start)
        overlap_end = min(end, slot_end)
        overlap = (overlap_end - overlap_start).total_seconds()

        if overlap > 0:
            ratio = overlap / dur
            b = blocks[block_idx]
            b.effective_seconds += round(eff * ratio)
            b.idle_seconds += round(idle * ratio)
            if cat_key in ENTERTAINMENT_CATS:
                b.entertainment_seconds += round(eff * ratio)
            if cat_key in WORK_CATS:
                b.work_seconds += round(eff * ratio)

            # Track per-app usage
            b._app_seconds[proc] = b._app_seconds.get(proc, 0) + round(eff * ratio)
            b._title_seconds[title] = b._title_seconds.get(title, 0) + round(eff * ratio)

            # Count switch only once per session per block
            if not hasattr(b, '_seen_sessions'):
                b._seen_sessions = set()
            if session_id not in b._seen_sessions:
                b._seen_sessions.add(session_id)
                b.switch_count += 1

        current = slot_end


def _finalise_block(b):
    """Determine dominant category and top app/title for a block."""
    total_eff = b.effective_seconds
    idle = b.idle_seconds

    if total_eff == 0 and idle == 0:
        b.dominant_category = "离线"
        return

    if b.work_seconds >= 1200:
        b.dominant_category = "办公"
    elif b.entertainment_seconds >= 900:
        b.dominant_category = "娱乐"
    elif idle >= 1200 and b.work_seconds < 600:
        b.dominant_category = "挂机"
    elif total_eff > 0 or idle > 0:
        b.dominant_category = "混合"
    else:
        b.dominant_category = "离线"

    if b._app_seconds:
        b.top_app = max(b._app_seconds, key=b._app_seconds.get)
    if b._title_seconds:
        b.top_title = max(b._title_seconds, key=b._title_seconds.get)

    # Clean up accumulators
    if hasattr(b, '_seen_sessions'):
        del b._seen_sessions
    b._app_seconds.clear()
    b._title_seconds.clear()
