"""Display semantics only; never infer gaps or alter recording counters."""
from dataclasses import dataclass

TIME_DEFINITION = '主动参与 A；被动观看 P；有效活动 E=A+P；已观测 O=A+P+空闲 I。未确认缺口独立统计，旧记录未知。'


@dataclass(frozen=True)
class TimeBreakdown:
    engaged_seconds: int
    passive_seconds: int
    idle_seconds: int
    gap_seconds: int | None = None

    @property
    def effective_seconds(self):
        return self.engaged_seconds + self.passive_seconds

    @property
    def observed_seconds(self):
        return self.effective_seconds + self.idle_seconds

    @property
    def gap_label(self):
        return '未知' if self.gap_seconds is None else str(self.gap_seconds)

    @property
    def description(self):
        return TIME_DEFINITION
