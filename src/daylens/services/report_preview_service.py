"""Bounded local Markdown reads. Preview never generates reports or calls AI."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import re
import threading

from .report_sections import summary_section, END


class PreviewCache:
    def __init__(self, root, *, max_entries=8, max_bytes=4 * 1024 * 1024):
        self.root = Path(root).resolve()
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._entries = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    @property
    def entry_count(self):
        return len(self._entries)

    @property
    def byte_count(self):
        return self._bytes

    def load(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.root) or path.suffix.lower() != ".md":
            raise ValueError("仅能预览报告目录内的 Markdown 文件")
        for _attempt in range(2):
            before = path.stat()
            key = (str(path), before.st_mtime_ns, before.st_size)
            with self._lock:
                if key in self._entries:
                    self._entries.move_to_end(key)
                    return dict(self._entries[key][0])
            truncated = before.st_size > 2 * 1024 * 1024
            with path.open("rb") as handle:
                raw = handle.read(128 * 1024 if truncated else 2 * 1024 * 1024 + 1)
            after = path.stat()
            if (before.st_mtime_ns, before.st_size, before.st_ino) != (
                after.st_mtime_ns,
                after.st_size,
                after.st_ino,
            ):
                continue
            # A bounded byte excerpt may end inside a UTF-8 codepoint, but
            # invalid bytes elsewhere are still rejected rather than replaced.
            if truncated:
                import codecs

                content = codecs.getincrementaldecoder("utf-8-sig")().decode(
                    raw, final=False
                )
            else:
                content = raw.decode("utf-8-sig")
            content = content.replace("\r\n", "\n").replace("\r", "\n")
            truncated = truncated or len(content) > 200000 or content.count("\n") > 1200
            payload = {
                "text": content[: 128 * 1024] if truncated else content,
                "path": str(path),
                "identity": key,
                "truncated": truncated,
            }
            size = len(raw)
            with self._lock:
                for old in list(self._entries):
                    if old[0] == str(path):
                        self._bytes -= self._entries.pop(old)[1]
                if size <= self.max_bytes:
                    self._entries[key] = (payload, size)
                    self._bytes += size
                    while self._entries and (
                        len(self._entries) > self.max_entries
                        or self._bytes > self.max_bytes
                    ):
                        self._bytes -= self._entries.popitem(last=False)[1][1]
            return dict(payload)
        raise OSError("报告正在更新，请稍后重试")


def native_status(db_path, content):
    match = re.search(r"<!-- daylens-report:(.*?) -->", content)
    if not match:
        return ""
    try:
        from ..app_paths import AppPaths
        from .daily_goal_service import _read
        from .report_v2_service import goal_plan_fingerprint

        identity = json.loads(match[1])
        days = identity.get("goal_dates")
        if (
            not isinstance(days, list)
            or len(days) > 31
            or not identity.get("goal_fingerprint")
        ):
            return "原生目标依据无法验证"
        directory = AppPaths.from_database(db_path).intelligence_dir
        path = directory / "daily_goals_v1.json"
        if (directory / "daily_goals_v1.pending.json").exists() or (
            path.exists() and path.stat().st_size > 8 * 1024 * 1024
        ):
            return "原生目标状态更新中，暂无法验证"
        state = _read(path) or {"days": {}}
        if goal_plan_fingerprint(state, days) != identity["goal_fingerprint"]:
            return "目标依据已变化，请手动更新原生报告"
        return "原生目标依据一致"
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        return "原生目标依据无法验证"


def _daily_facts_match(db_path, day, identity):
    from .intelligence_report_service import daily_facts, REVIEW_FACTS_VERSION
    from .intelligence_reviews import REVIEW_PROMPT
    from .intelligence_privacy import privacy_revision
    from .intelligence_state import load_settings
    from ..app_paths import AppPaths
    from datetime import date

    settings = load_settings(AppPaths.from_database(db_path).intelligence_dir)
    if (
        identity.get("facts_version") != REVIEW_FACTS_VERSION
        or identity.get("prompt_hash")
        != hashlib.sha256(REVIEW_PROMPT.encode()).hexdigest()
        or identity.get("privacy_revision") != privacy_revision(settings)
        or not identity.get("facts_hash")
    ):
        return None
    facts = [
        {key: value for key, value in fact.items() if key != "session_refs"}
        for fact in daily_facts(db_path, date.fromisoformat(day), settings)
    ]
    digest = hashlib.sha256(
        json.dumps(facts, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return digest == identity["facts_hash"]


def summary_status(db_path, content):
    section = summary_section(content)
    if not section:
        return "未附加 AI 汇总"
    match = re.search(r"<!-- daylens-ai-evidence:(.*?) -->\n", section)
    if not match:
        return "旧汇总无法验证（保留原文）"
    try:
        evidence = json.loads(match[1])
        if (
            evidence.get("kind") not in {"daily", "weekly", "monthly"}
            or not isinstance(evidence.get("dates"), list)
            or not 1 <= len(evidence["dates"]) <= 31
        ):
            return "汇总周期无效，无法验证"
        from datetime import date

        checked_dates = [date.fromisoformat(day) for day in evidence["dates"]]
        if (
            checked_dates != sorted(set(checked_dates))
            or (checked_dates[-1] - checked_dates[0]).days > 30
        ):
            return "汇总范围无效，无法验证"
        body = section[match.end() : -len(END)]
        if hashlib.sha256(body.encode()).hexdigest() != evidence["body_hash"]:
            return "汇总内容已变化，无法验证"
        fingerprint = evidence.get("fingerprint")
        if not fingerprint:
            return "汇总缺少证据，无法验证"
        from .report_evidence_service import evidence_fingerprint

        current = evidence_fingerprint(db_path, evidence["kind"], evidence["dates"])
        if current != fingerprint:
            return "AI 汇总基于旧数据（不会自动重新分析）"
        uncertain = False
        if evidence["kind"] == "daily":
            match_facts = _daily_facts_match(db_path, evidence["dates"][0], evidence)
            if match_facts is False:
                return "AI 汇总基于旧数据（实际事实或标题已变化）"
            uncertain = match_facts is None
        if evidence["kind"] != "daily":
            dependencies = evidence.get("dependencies", [])
            if not dependencies:
                return "汇总直接证据一致；下级摘要状态无法完整验证"
            from ..app_paths import AppPaths
            from .report_evidence_service import report_dates
            from datetime import date
            import calendar

            root = AppPaths.from_database(db_path).intelligence_dir / "reviews"
            pending = list(dependencies)
            seen = set()
            while pending:
                dependency = pending.pop()
                name = dependency["name"]
                if name in seen:
                    continue
                seen.add(name)
                if len(seen) > 80:
                    return "下级摘要过多，无法完整验证"
                matched = re.fullmatch(r"(daily|weekly|monthly)-([0-9W-]+)\.json", name)
                if not matched:
                    return "下级摘要身份无法验证"
                source_path = (root / name).resolve()
                if (
                    not source_path.is_relative_to(root.resolve())
                    or source_path.stat().st_size > 1024 * 1024
                ):
                    return "下级摘要不可安全读取，无法验证"
                source = json.loads(source_path.read_text(encoding="utf-8"))
                digest = hashlib.sha256(
                    json.dumps(source, ensure_ascii=False, sort_keys=True).encode()
                ).hexdigest()
                if digest != dependency["digest"]:
                    return "AI 汇总基于旧数据（下级摘要已变化）"
                source_kind, period = matched.groups()
                if source_kind == "weekly":
                    year, week = period.split("-W")
                    day = date.fromisocalendar(int(year), int(week), 7)
                elif source_kind == "monthly":
                    year, month = map(int, period.split("-"))
                    day = date(year, month, calendar.monthrange(year, month)[1])
                else:
                    day = date.fromisoformat(period)
                stored = source.get("evidence_fingerprint")
                if not stored:
                    return "下级摘要缺少证据，无法完整验证"
                if stored != evidence_fingerprint(
                    db_path, source_kind, report_dates(source_kind, day)
                ):
                    return "AI 汇总基于旧数据（下级摘要证据已变化）"
                if source_kind == "daily":
                    source_identity = dict(
                        source,
                        facts_hash=hashlib.sha256(
                            json.dumps(
                                source.get("facts", []),
                                ensure_ascii=False,
                                sort_keys=True,
                            ).encode()
                        ).hexdigest(),
                    )
                    match_facts = _daily_facts_match(db_path, period, source_identity)
                    if match_facts is False:
                        return "AI 汇总基于旧数据（下级实际事实已变化）"
                    uncertain = uncertain or match_facts is None
                if source_kind != "daily":
                    children = source.get("source_reviews")
                    if not children:
                        return "下级摘要缺少依赖身份，无法完整验证"
                    pending.extend(children)
        if uncertain:
            return "计量证据一致；缺少实际事实身份，无法完整验证"
        if evidence["kind"] != "daily":
            from .intelligence_report_service import REVIEW_FACTS_VERSION
            from .intelligence_reviews import REVIEW_PROMPT
            from .intelligence_privacy import privacy_revision
            from .intelligence_state import load_settings
            from ..app_paths import AppPaths

            settings = load_settings(AppPaths.from_database(db_path).intelligence_dir)
            if (
                evidence.get("facts_version") != REVIEW_FACTS_VERSION
                or evidence.get("prompt_hash")
                != hashlib.sha256(REVIEW_PROMPT.encode()).hexdigest()
                or evidence.get("privacy_revision") != privacy_revision(settings)
            ):
                return "下级证据一致；旧生成策略无法完整验证"
        return "AI 汇总证据一致"
    except (OSError, ValueError, KeyError, TypeError):
        return "当前无法验证 AI 汇总，原文仍可查看"
    except Exception:
        return "当前无法验证 AI 汇总，原文仍可查看"
