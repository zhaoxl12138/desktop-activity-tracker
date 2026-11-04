"""Local-only report evidence feedback, independent of any preview UI."""
from __future__ import annotations

from .report_preview_service import summary_status
from .report_sections import START, report_file_identity, summary_section


def load_report_freshness(db_path, path, cache):
    for _attempt in range(2):
        payload = cache.load(path)
        if payload["truncated"]:
            state = {"level": "unverifiable", "label": "报告待核验",
                     "message": "报告过大，无法完整核验；原文件未修改"}
        else:
            state = report_freshness(db_path, payload["text"])
        if report_file_identity(payload["path"]) == payload["identity"]:
            return dict(state, file_identity=payload["identity"])
    raise OSError("报告正在更新，请稍后核验")


def report_freshness(db_path: str, content: str) -> dict[str, str]:
    if not summary_section(content):
        return {"level": "none", "label": "", "message": "未附加 AI 汇总"}
    # Validate canonical evidence text without modifying preserved report bytes.
    message = summary_status(db_path, content.replace("\r\n", "\n").replace("\r", "\n"))
    if "旧数据" in message:
        return {"level": "stale", "label": "AI 汇总已过期", "message": message}
    if message == "AI 汇总证据一致":
        return {"level": "current", "label": "", "message": message}
    return {"level": "unverifiable", "label": "AI 汇总待核验", "message": message}


def annotate_summary_freshness(db_path: str, content: str) -> str:
    """Annotate explicitly regenerated native content, preserving the AI bytes."""
    state = report_freshness(db_path, content)
    if state["level"] not in {"stale", "unverifiable"}:
        return content
    notice = ("<!-- daylens-ai-status:start -->\n"
              f"> {state['message']}\n"
              "<!-- daylens-ai-status:end -->\n\n")
    return content.replace(START, notice + START, 1)
