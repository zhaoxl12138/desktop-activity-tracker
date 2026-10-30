"""Pure Markdown rendering of report-v2 facts; no I/O or AI calls."""

from __future__ import annotations

from html import escape
import json
import re

from ..utils import fmt_seconds, normalize_category_display_name, parse_nonnegative_int


def text(value) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", escape(value, quote=False))


def duration(seconds) -> str:
    seconds = parse_nonnegative_int(seconds)
    if seconds is None:
        return "未知"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return (
        (f"{hours}时" if hours else "")
        + (f"{minutes}分" if minutes or hours else "")
        + f"{seconds}秒"
    )


def render_report(model: dict) -> str:
    from ..exporter import _aggregate_report_categories

    kind = model["kind"]
    label = {"daily": "今日复盘", "weekly": "本周复盘", "monthly": "本月复盘"}[kind]
    dates = model["dates"]
    totals = model["stats"]["totals"]
    meta = {
        "format": "report-v2",
        "kind": kind,
        "dates": dates,
        "native_fingerprint": model["native_fingerprint"],
        "goal_revision": model["goals"]["revision"],
    }
    lines = [
        f"# DayLens · {label}",
        "",
        "<!-- daylens-report:"
        + json.dumps(meta, ensure_ascii=True, separators=(",", ":"))
        + " -->",
        f"> 统计范围：{dates[0]} ～ {dates[-1]}"
        + ("（进行中）" if model["ongoing"] else ""),
        f"> 数据更新：{text(model['last_record_at'])}",
        f"> 原生报告生成：{model['generated_at'].replace('T', ' ')}",
        "",
        "## 关键发现",
        "",
    ]
    for fact in model["facts"]:
        if fact["type"] == "category":
            message = f"有效活动最多的分类是{text(normalize_category_display_name('', fact['name']))}，{fmt_seconds(fact['seconds'])}。"
        elif fact["type"] == "goal":
            message = f"目标“{text(fact['name'])}”距计划投入还差{fmt_seconds(fact['seconds'])}。"
        else:
            message = f"可比完整日期的主动参与：{fmt_seconds(fact['before'])} → {fmt_seconds(fact['after'])}。"
        lines.append("- " + message + " <!-- fact:" + text(fact["id"]) + " -->")
    if not model["facts"]:
        lines.append("暂无可提炼的活动记录；数据不足，请保持记录。")
    attention = model.get("attention", {})
    trust_level = attention.get(
        "trust_level",
        {"high": "高", "medium": "中", "low": "低"}[model["trust"]["level"]],
    )
    reason = attention.get("trust_reason", next(iter(model["trust"]["reasons"]), ""))
    lines += [
        "",
        "## 总览",
        "",
        f"- 有效活动：{fmt_seconds(totals['effective_seconds'])}",
        f"- 工作主动参与：{fmt_seconds(totals['work_engaged_seconds'])}",
        f"- 娱乐有效活动：{fmt_seconds(model['entertainment_seconds'])}",
        f"- 参与时间：{fmt_seconds(totals['engaged_seconds'])}",
        f"- 被动媒体：{fmt_seconds(totals['passive_seconds'])}",
        f"- 挂机/空闲时间：{fmt_seconds(totals['idle_seconds'])}",
        f"- 数据可信度：{trust_level}" + (f"（{text(reason)}）" if reason else ""),
        f"- 有记录日期：{len(totals['dates_with_data'])}/{len(model['observed_dates'])} 天（不代表全天覆盖）",
    ]
    apps = model["stats"]["by_app"]
    lines.append("- 最长使用软件：" + text(apps[0]["process_name"] if apps else "-"))
    if (
        totals["legacy_session_count"]
        or totals["legacy_log_sample_count"]
        or totals["anomaly_count"]
    ):
        lines.append(
            "> 主动/被动分项仅含可核实证据；旧记录或异常的未知部分不补零、不反推。"
        )
    comparison = model["comparison"]
    if not comparison["comparable"]:
        lines.append("> 趋势：" + text(comparison["reason"] or "没有已完成的可比日期"))
    else:
        lines.append(
            "> 对比范围："
            + comparison["current_dates"][0]
            + " ～ "
            + comparison["current_dates"][-1]
            + "；上一周期 "
            + comparison["previous_dates"][0]
            + " ～ "
            + comparison["previous_dates"][-1]
        )
    lines += ["", "## 目标与成果", "", "### 计划 / 投入 / 已确认成果", ""]
    goals = model["goals"]
    if goals["status"] == "unavailable":
        lines.append("目标数据暂不可读；原有报告统计不受影响。")
    elif not goals["rows"]:
        lines.append("本周期未设置每日目标。")
    else:
        lines += [
            "| 日期 | 目标 | 计划 | 可信投入 | 偏差 | 成果证据 |",
            "|---|---|---:|---:|---:|---|",
        ]
        for goal in goals["rows"]:
            planned = (
                fmt_seconds(goal["planned_seconds"])
                if goal["planned_seconds"] is not None
                else "成果型"
            )
            actual = (
                fmt_seconds(goal["actual_seconds"])
                if goal["actual_seconds"] is not None
                else "证据不足"
                if goal["type"] == "time_commitment"
                else "—"
            )
            gap = goal["difference_seconds"]
            difference = (
                (
                    "少 " + fmt_seconds(gap)
                    if gap > 0
                    else "多 " + fmt_seconds(-gap)
                    if gap < 0
                    else "持平"
                )
                if gap is not None
                else "—"
            )
            evidence = goal["outcome_evidence"] or (
                "部分证据不可比" if goal["evidence_status"] == "untrusted" else "—"
            )
            lines.append(
                f"| {goal['day']} | {text(goal['title'])} | {planned} | {actual} | {difference} | {evidence} |"
            )
    lines += [
        "",
        "> 时间目标达到计划时长不等于成果完成；成果栏只记录用户手动确认。",
        "",
    ]
    if model["actions"]:
        action = model["actions"][0]
        lines += [
            "## 下一步建议",
            "",
            f"- 下一次安排“{text(action['name'])}”时，可参考本次距计划{fmt_seconds(action['seconds'])}的差额，调整计划或预留时段。",
            "",
        ]
    lines += [
        "## 详细数据",
        "",
        "### 分类统计",
        "",
        "| 分类 | 时长 | 有效活动占比 | Top应用 |",
        "|---|---:|---:|---|",
    ]
    for category in _aggregate_report_categories(model["stats"]["by_category"]):
        candidates = [
            app for app in apps if app["category_key"] in category["source_keys"]
        ]
        top = (
            max(candidates, key=lambda r: r["effective_seconds"])["process_name"]
            if candidates
            else "-"
        )
        seconds = category["effective_seconds"]
        ratio = (
            round(seconds / totals["effective_seconds"] * 100)
            if totals["effective_seconds"]
            else 0
        )
        lines.append(
            f"| {text(category['category_name'])} | {fmt_seconds(seconds)} | {ratio}% | {text(top)} |"
        )
    lines += ["", "### 软件排行", "", "| 应用 | 分类 | 有效活动 |", "|---|---|---:|"]
    for app in apps[:20]:
        lines.append(
            f"| {text(app['process_name'])} | {text(normalize_category_display_name(app['category_key'], app['category_name']))} | {duration(app['effective_seconds'])} |"
        )
    lines += [
        "",
        "### 每日分布",
        "",
        "| 日期 | 有效活动 | 工作主动参与 |",
        "|---|---:|---:|",
    ]
    for day in model["stats"]["daily"]:
        recorded = bool(day["total_samples"])
        lines.append(
            f"| {day['date']} | {duration(day['effective_seconds']) if recorded else '无记录'} | {duration(day['work_engaged_seconds']) if recorded else '未知'} |"
        )
    lines += [
        "",
        "### 会话时间线",
        "",
        "| 日期与时间段 | 应用 | 活动 / 窗口标题 | 分类 | 有效活动 |",
        "|---|---|---|---|---:|",
    ]
    for row in model["sessions"]:
        anomaly = "（计量异常，原记录值）" if row.get("_anomalous") else ""
        lines.append(
            f"| {text(row['start_time'])}—{text(row['end_time'])} | {text(row['process_name'])} | {text(row['normalized_title'])} | {text(normalize_category_display_name(row['category_key'], row['category_name']))} | {duration(row['effective_seconds'])} |"
            + anomaly
        )
    if model["half_hours"]:
        lines += [
            "",
            "### 30分钟时间线概览",
            "",
            "> 根据会话累计值按前台范围分配的估计；不代表精确输入位置，未观测缺口不补为空闲。",
            "",
            "| 时间段 | 有效活动 | 已记录空闲 | 使用最多 |",
            "|---|---:|---:|---|",
        ]
        for block in model["half_hours"]:
            lines.append(
                f"| {block['slot']} | {duration(block['effective_seconds'])} | {duration(block['idle_seconds'])} | {text(block['top_app'])} |"
            )
    lines += ["", "> 本地统计不评价工作质量，也不代表成果、心理状态或因果关系。", ""]
    return "\n".join(lines)
