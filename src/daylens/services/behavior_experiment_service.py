"""Legacy experiment storage. Task-derived experiments are no longer offered."""
import json
from datetime import date
from pathlib import Path

from .daily_goal_service import GoalStore
from .intelligence_state import atomic_json, load_settings
LEGACY_VERSION = "behavior-v1"


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
            assert value["version"] == LEGACY_VERSION
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
        raise ValueError("任务级实验已下线，已有记录保留，不再接受新实验")

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
    return "任务级实验已下线；历史记录保留，不再生成效果结论。"
