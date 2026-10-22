"""One explicitly accepted local experiment, with a frozen evidence baseline."""
import json
from datetime import date, timedelta
from pathlib import Path

from .daily_goal_service import GoalStore
from .intelligence_state import atomic_json, load_settings
from .behavior_profile_service import VERSION, dates_before, summarize

SUGGESTION = "未来一周，每天安排一段30分钟免打扰工作，结束后再处理消息。"


class ExperimentStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "behavior_experiment_v1.json"
        # Reuse the existing cross-process state lock, without touching goals.
        self.lock = GoalStore(directory)

    def _load(self):
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            assert value["version"] == VERSION
            assert value["status"] in ("accepted", "stopped")
            date.fromisoformat(value["start"])
            date.fromisoformat(value["end"])
            date.fromisoformat(value["accepted"])
            assert value["baseline"]["ready"] and value["baseline"]["digest"]
            return value
        except (ValueError, KeyError, TypeError, AssertionError) as exc:
            raise ValueError("实验记录损坏，已保留原文件") from exc

    def load(self):
        with self.lock._locked():
            return self._load()

    def accept(self, baseline, today=None):
        today = today or date.today()
        if not load_settings(self.directory).get("behavior_analysis_enabled"):
            raise ValueError("请先开启本地行为画像")
        if (not baseline.get("ready") or baseline.get("insertion_rate") is None
                or baseline.get("dates") != dates_before(today, 7)):
            raise ValueError("需要前7个完整日的同口径工作记录，才能开始实验")
        with self.lock._locked():
            old = self._load()
            if old and old["status"] == "accepted":
                raise ValueError("已有实验；请先查看结果或停止实验")
            # Bounded file: no titles or raw sessions, only baseline totals/hash.
            keep = {key: baseline[key] for key in (
                "ready", "dates", "digest", "versions", "work_seconds", "insertions", "insertion_rate")}
            value = {"version": VERSION, "status": "accepted", "accepted": today.isoformat(),
                     "start": (today + timedelta(days=1)).isoformat(),
                     "end": (today + timedelta(days=7)).isoformat(), "baseline": keep}
            atomic_json(self.path, value)
            return value

    def stop(self):
        with self.lock._locked():
            value = self._load()
            if value:
                value["status"] = "stopped"
                atomic_json(self.path, value)


def feedback(db_path, directory, today=None, *, loader=None):
    today = today or date.today()
    if not load_settings(directory).get("behavior_analysis_enabled"):
        return "行为画像未开启。"
    experiment = ExperimentStore(directory).load()
    if not experiment:
        return "尚未接受实验。"
    if today < date.fromisoformat(experiment["accepted"]):
        return "该日期尚未接受实验。"
    if experiment["status"] == "stopped":
        return "实验已停止。"
    period = f"观察期 {experiment['start']} ～ {experiment['end']}"
    if today <= date.fromisoformat(experiment["end"]):
        return period + "；等待7个完整日结束后反馈。"
    if loader is None:
        from ..database import query_sessions_for_dates
        loader = query_sessions_for_dates
    observed = dates_before(date.fromisoformat(experiment["end"]) + timedelta(days=1), 7)
    baseline = experiment["baseline"]
    rows = loader(str(db_path), baseline["dates"] + observed)
    before = summarize(rows, baseline["dates"])
    after = summarize(rows, observed)
    if (not before["ready"] or not after["ready"] or before["digest"] != baseline["digest"]
            or json.dumps(before["versions"]) != json.dumps(after["versions"])
            or after["insertion_rate"] is None):
        return period + "；基线变化、记录不足或口径不可比，不能评价实验效果。"
    return (period + f"；候选插入/工作小时：{before['insertion_rate']:.2f} → {after['insertion_rate']:.2f}。"
            f"原始次数 {before['insertions']} → {after['insertions']}，"
            f"工作参与 {before['work_seconds']//60} → {after['work_seconds']//60} 分钟。"
            "仅为同口径观察对照；不能证明建议得到执行或导致了变化。")
