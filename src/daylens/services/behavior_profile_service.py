"""Local, read-only longitudinal evidence. Never infer intent or outcomes."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta

from .dashboard_service import WORK_KEYS, ENTERTAINMENT_KEYS
from .task_grouping_service import _trusted
from .intelligence_state import load_settings
from .classification_semantics import resolve_classification_semantics

VERSION = "behavior-v2"


def dates_before(end: date, count: int) -> list[str]:
    return [(end - timedelta(days=n)).isoformat() for n in range(count, 0, -1)]


def summarize(rows: list[dict], days: list[str]) -> dict:
    by_day = {day: {} for day in days}
    reasons = set()
    versions = set()
    rejected = Counter()
    conflicts = set()
    for row in rows:
        day = str(row.get("start_time", ""))[:10]
        if day not in by_day:
            continue
        identity = row.get("session_id")
        if not identity:
            rejected["缺少会话标识"] += 1
            continue
        if row.get("metric_version") != "attention-v1":
            rejected["旧计量版本"] += 1
            continue
        if _trusted(row, day) is None:
            try:
                cross_day = datetime.fromisoformat(str(row["end_time"])).date().isoformat() != day
            except (KeyError, TypeError, ValueError):
                cross_day = False
            rejected["跨日期会话" if cross_day else "时间或计量异常会话"] += 1
            continue
        conflict_key = (day, identity)
        if conflict_key in conflicts:
            continue
        if identity in by_day[day] and by_day[day][identity] != row:
            reasons.add("相同会话标识存在冲突")
            conflicts.add(conflict_key)
            del by_day[day][identity]
            continue
        by_day[day][identity] = row
        version = (
            row.get("metric_version"),
            resolve_classification_semantics(
                row.get("classification_version")
            ).policy_version,
        )
        if not all(isinstance(v, str) and v for v in version):
            reasons.add("缺少计量或分类版本")
        else:
            versions.add(version)
    for label, count in rejected.items():
        reasons.add(f"{label} {count} 条")
    if len(versions) > 1:
        metrics = {metric for metric, _ in versions}
        classes = {classification for _, classification in versions}
        if len(metrics) > 1:
            reasons.add("计量版本不可比")
        if len(classes) > 1:
            reasons.add("分类版本不可比")
    elif not versions:
        reasons.add("没有可核实的版本记录")
    missing = [day for day, items in by_day.items() if not items]
    if missing:
        reasons.add(f"{len(missing)}天缺少可信记录")
    work_hours, leisure_hours = Counter(), Counter()
    daily, evidence = [], []
    for day, items in by_day.items():
        ordered = sorted(items.values(), key=lambda r: r["start_time"])
        work = leisure = longest = run = 0
        previous_end = None
        for row in ordered:
            start, end, engaged = _trusted(row, day)
            if previous_end is not None and start < previous_end:
                reasons.add("会话时间重叠，不能可靠汇总")
            category = row.get("category_key")
            if category in WORK_KEYS:
                work += engaged
                work_hours[start.hour] += engaged
                # A gap/non-work session ends continuity; no invented gap time.
                run = run + engaged if previous_end == start else engaged
                longest = max(longest, run)
            else:
                run = 0
            if category in ENTERTAINMENT_KEYS:
                effective = engaged + int(row.get("passive_seconds") or 0)
                leisure += effective
                leisure_hours[start.hour] += effective
            previous_end = end
            evidence.append({key: row.get(key) for key in (
                "session_id", "start_time", "end_time", "category_key",
                "engaged_seconds", "passive_seconds", "idle_seconds",
                "metric_version", "classification_version", "normalized_title",
                "window_title", "process_name")})
        daily.append({"day": day, "recorded": bool(items), "work": work,
                      "entertainment": leisure, "longest": longest})
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    ready = not reasons
    work = sum(d["work"] for d in daily)
    half = len(daily) // 2
    trend = None
    if ready and half:
        trend = {key: [sum(d[key] for d in daily[:half]) / half,
                       sum(d[key] for d in daily[half:]) / (len(daily) - half)]
                 for key in ("work", "longest")}
    return {"version": VERSION, "dates": days, "ready": ready, "reasons": sorted(reasons),
            "recorded_days": len(days) - len(missing), "versions": sorted(versions),
            "excluded_session_count": sum(rejected.values()),
            "conflicting_session_count": len(conflicts),
            "digest": digest, "daily": daily, "work_seconds": work,
            "work_hours": dict(work_hours), "entertainment_hours": dict(leisure_hours),
            "trend": trend}


def load_profiles(db_path, directory, end: date | None = None, *, loader=None):
    if not load_settings(directory).get("behavior_analysis_enabled", False):
        return {"status": "disabled", "profiles": {}}
    end = min(end or date.today(), date.today())
    if loader is None:
        from ..database import query_sessions_for_dates
        loader = query_sessions_for_dates
    try:
        days = dates_before(end, 30)
        rows = loader(str(db_path), days)
        return {"status": "ready", "profiles": {
            n: summarize(rows, days[-n:]) for n in (7, 14, 30)}}
    except Exception:
        return {"status": "unavailable", "profiles": {}}


def profile_lines(model: dict) -> list[str]:
    if model["status"] == "disabled":
        return []
    lines = ["## 行为画像 · 本地证据", ""]
    if model["status"] != "ready":
        return lines + ["行为数据暂不可读，未生成结论。", ""]
    for n, profile in model["profiles"].items():
        days = profile["dates"]
        lines += [f"### 近{n}个完整日：{days[0]} ～ {days[-1]}",
                  f"可信记录覆盖 {profile['recorded_days']}/{n} 天（不代表全天覆盖）。"]
        if not profile["ready"]:
            lines.append("暂不生成画像和趋势：" + "；".join(profile["reasons"]) + "。")
            unsafe = any("重叠" in reason or "冲突" in reason for reason in profile["reasons"])
            if profile["recorded_days"] and not unsafe:
                leisure = sum(day["entertainment"] for day in profile["daily"])
                lines.append(f"已核实片段：工作参与 {profile['work_seconds']//60} 分钟；"
                             f"娱乐活动 {leisure//60} 分钟。仅为通过校验会话的下限，"
                             "不代表全天或区间总量。")
            lines.append("")
            continue
        for field, name in (("work_hours", "工作投入"), ("entertainment_hours", "娱乐活动")):
            ranked = sorted(profile[field].items(), key=lambda pair: (-pair[1], pair[0]))[:3]
            text = "、".join(f"{hour:02d}时（{seconds//60}分钟）" for hour, seconds in ranked if seconds)
            lines.append(f"{name}较多的会话开始时段：{text or '无'}。")
        lines.append(f"工作参与 {profile['work_seconds']//60} 分钟。")
        for key, label in (("work", "日均工作参与"), ("longest", "日均最长连续工作片段")):
            before, after = profile["trend"][key]
            lines.append(f"窗口前半段 → 后半段，{label}：{before/60:.1f} → {after/60:.1f} 分钟。")
        lines.append("")
    return lines + ["> 时段按会话开始时间近似归组；连续片段仅连接无间隙工作会话。变化不代表因果或心理状态。", ""]


def report_lines(db_path, end):
    from ..app_paths import AppPaths
    directory = AppPaths.from_database(db_path).intelligence_dir
    try:
        anchor = min(date.fromisoformat(end) + timedelta(days=1), date.today())
        model = load_profiles(db_path, directory, anchor)
        return profile_lines(model)
    except Exception:
        return ["## 行为画像", "行为画像暂不可用，原报告统计继续保留。", ""]
