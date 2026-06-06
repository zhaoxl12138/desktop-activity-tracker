# DayLens 首页重设计：今日洞察 + 专注 Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把首页从重复统计面板改成“今日洞察 + 专注 Session”面板，并同步增强左下状态卡。

**Architecture:** 首页仍然以 `load_today_snapshot()` 为唯一数据入口，但把首页可见信息拆成三层：时间分布总览、规则化洞察卡、Session 卡片流。服务层先产出首页所需的洞察投影，页面层只负责布局和渲染，避免把规则散落在 GUI 中。Session 区域不再展示逐条采样日志，而是展示按持续时长排序的高价值会话卡片；时间轴只负责展示全天结构，不再承担明细输出。

**Tech Stack:** Python 3.11, PySide6, SQLite, pytest

---

### Task 1: Add today's insight projection

**Files:**
- Modify: `D:\OfficeSoftware\DayLens\src\daylens\services\dashboard_service.py`
- Modify: `D:\OfficeSoftware\DayLens\tests\test_dashboard_service.py`

- [ ] **Step 1: Write the failing test**

```python
from daylens.services.dashboard_service import build_today_insights


def test_today_insight_projection_builds_four_cards():
    sessions = [
        {
            "process_name": "Codex.exe",
            "window_title": "Codex",
            "normalized_title": "Codex",
            "category_name": "工作学习",
            "category_key": "coding",
            "effective_seconds": 4920,
            "start_time": "2026-06-06 14:23:00",
            "end_time": "2026-06-06 15:45:00",
        },
        {
            "process_name": "WeChat.exe",
            "window_title": "微信",
            "normalized_title": "微信",
            "category_name": "社交通讯",
            "category_key": "social",
            "effective_seconds": 260,
            "start_time": "2026-06-06 16:00:00",
            "end_time": "2026-06-06 16:05:00",
        },
    ]
    distribution_sections = [
        {"category_key": "work", "seconds": 6200, "label": "工作学习"},
        {"category_key": "entertainment", "seconds": 3500, "label": "娱乐休闲"},
        {"category_key": "social", "seconds": 260, "label": "社交通讯"},
    ]
    day_comparison = {
        "work": {"seconds_delta": 6000, "direction": "up"},
        "entertainment": {"seconds_delta": 3200, "direction": "up"},
        "social": {"seconds_delta": 260, "direction": "up"},
    }
    totals = {"active_seconds": 12000, "idle_seconds": 2400}

    result = build_today_insights(
        today="2026-06-06",
        sessions=sessions,
        totals=totals,
        distribution_sections=distribution_sections,
        day_comparison=day_comparison,
    )

    assert result["ready"] is True
    assert [card["title"] for card in result["cards"]] == ["最长专注", "最佳状态时段", "最大干扰源", "今日建议"]
    assert result["cards"][0]["primary"] == "Codex"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_service.py::test_today_insight_projection_builds_four_cards -v`
Expected: FAIL because `build_today_insights()` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add a new helper in `dashboard_service.py`:

```python
def build_today_insights(today, sessions, totals, distribution_sections, day_comparison) -> dict:
    ...
```

Return structure:

```python
{
    "ready": True,
    "cards": [
        {
            "title": "最长专注",
            "icon": "🏆",
            "accent": "#2ecc71",
            "primary": "Codex",
            "secondary": "82分钟 · 14:23 - 15:45",
        },
        {
            "title": "最佳状态时段",
            "icon": "🕒",
            "accent": "#3b82f6",
            "primary": "14:00 - 16:00",
            "secondary": "累计专注 52分钟",
        },
        {
            "title": "最大干扰源",
            "icon": "⚠",
            "accent": "#f59e0b",
            "primary": "微信",
            "secondary": "进入 43 次",
        },
        {
            "title": "今日建议",
            "icon": "💡",
            "accent": "#a855f7",
            "primary": "下午专注度明显高于上午",
            "secondary": "建议将高优先级任务安排在 14:00 后",
        },
    ],
}
```

Add a data-insufficient branch:

```python
{
    "ready": False,
    "message": "数据积累中",
    "hint": "使用一段时间后将生成洞察",
    "cards": []
}
```

Wire the helper into `load_today_snapshot()` so callers receive `snapshot["insights"]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_service.py::test_today_insight_projection_builds_four_cards -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daylens/services/dashboard_service.py tests/test_dashboard_service.py
git commit -m "feat: add dashboard insight projection"
```

### Task 2: Rebuild the homepage layout

**Files:**
- Modify: `D:\OfficeSoftware\DayLens\src\daylens\gui\pages\today_overview.py`
- Modify: `D:\OfficeSoftware\DayLens\src\daylens\gui\style.py`
- Modify: `D:\OfficeSoftware\DayLens\tests\test_homepage_redesign.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from daylens import database
from daylens.gui.pages.today_overview import TodayOverviewPage


def test_homepage_has_insight_and_no_time_stats():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "usage.db"
        database.init_db(str(db_path)).close()
        page = TodayOverviewPage(str(db_path))
        page.show()
        app.processEvents()

        assert page.insight_card is not None
        assert page.time_stats_card is None
        assert page.distribution_cmp_labels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_homepage_redesign.py::test_homepage_has_insight_and_no_time_stats -v`
Expected: FAIL because the current layout still builds the old time stats card.

- [ ] **Step 3: Write minimal implementation**

Refactor `TodayOverviewPage` into these named pieces:

- `_build_distribution_card()`
- `_build_insight_card()`
- `_build_focus_axis_card()`
- `_build_session_cards_card()`
- `_build_top_apps_card()`

Replace the old `time_stats_card` with `insight_card`.

Place the `较昨日` labels inside the distribution card footer, with the exact labels:

- `工作学习`
- `娱乐休闲`
- `社交通讯`

Use smaller card spacing so the new middle insight panel fits the 1600×900 layout.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_homepage_redesign.py::test_homepage_has_insight_and_no_time_stats -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daylens/gui/pages/today_overview.py src/daylens/gui/style.py tests/test_homepage_redesign.py
git commit -m "feat: rebuild homepage layout"
```

### Task 3: Replace the sampling timeline with high-value Session cards

**Files:**
- Modify: `D:\OfficeSoftware\DayLens\src\daylens\gui\widgets\dashboard_widgets.py`
- Modify: `D:\OfficeSoftware\DayLens\src\daylens\gui\pages\today_overview.py`
- Modify: `D:\OfficeSoftware\DayLens\tests\test_dashboard_widgets.py`

- [ ] **Step 1: Write the failing test**

```python
from PySide6.QtWidgets import QApplication, QLabel

from daylens.gui.widgets.dashboard_widgets import TimelineWidget


def _app():
    return QApplication.instance() or QApplication([])


def test_session_cards_filter_and_sort():
    app = _app()
    widget = TimelineWidget(max_rows=5, min_effective_seconds=300, sort_by_value=True)

    widget.set_sessions(
        [
            {"start_time": "2026-06-06 14:23:00", "end_time": "2026-06-06 15:45:00", "process_name": "Codex.exe", "window_title": "Codex", "normalized_title": "Codex", "category_name": "工作学习", "category_key": "coding", "effective_seconds": 4920, "duration_seconds": 4920},
            {"start_time": "2026-06-06 16:00:00", "end_time": "2026-06-06 16:04:00", "process_name": "WeChat.exe", "window_title": "微信", "normalized_title": "微信", "category_name": "社交通讯", "category_key": "social", "effective_seconds": 240, "duration_seconds": 240},
        ]
    )

    widget.show()
    app.processEvents()

    assert len(widget._rows) == 1
    labels = [label.text() for label in widget._rows[0].findChildren(QLabel)]
    assert any("Codex" in text for text in labels)
    assert any("82分钟" in text for text in labels)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_widgets.py::test_session_cards_filter_and_sort -v`
Expected: FAIL because the widget still behaves like a timeline list and does not expose session-card state.

- [ ] **Step 3: Write minimal implementation**

Extend `TimelineWidget` so it renders a session-card layout:

- one row per session card
- app / window title line
- time range line
- duration chip
- category tag

Keep the 24-hour structure strip above the cards.

Enforce:

- `effective_seconds >= 300`
- sort descending by duration
- show top 5 only on the homepage
- button text `查看全部 Session (N) ↗`

Make the detail dialog title `今日专注 Session`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_widgets.py::test_session_cards_filter_and_sort -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daylens/gui/widgets/dashboard_widgets.py src/daylens/gui/pages/today_overview.py tests/test_dashboard_widgets.py
git commit -m "feat: replace timeline with session cards"
```

### Task 4: Strengthen the sidebar status card

**Files:**
- Modify: `D:\OfficeSoftware\DayLens\src\daylens\gui\main_window.py`
- Modify: `D:\OfficeSoftware\DayLens\src\daylens\gui\pages\today_overview.py`
- Modify: `D:\OfficeSoftware\DayLens\tests\test_gui_smoke.py`

- [ ] **Step 1: Write the failing test**

```python
import os
import tempfile
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from desktop_activity_tracker import database
from desktop_activity_tracker.gui.main_window import MainWindow


class DummyWorker(QObject):
    sample_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self._paused = False

    def is_paused(self):
        return self._paused

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def update_settings(self, config):
        return None

    def stop(self):
        return None

    def wait(self, timeout=0):
        return True


def _write_config(path: Path):
    config = {
        "db_path": str(path.parent / "usage.db"),
        "reports_dir": str(path.parent / "reports"),
        "obsidian_output_path": "",
        "tracker": {
            "sample_interval_seconds": 1,
            "flush_interval_seconds": 5,
            "idle_threshold_seconds": 60,
            "min_session_seconds": 2,
        },
        "categories": {
            "coding": {
                "display_name": "Coding",
                "active_rule": "interactive_required",
                "match": {"process_names": ["Code.exe"], "title_keywords": []},
            },
            "other": {
                "display_name": "Other",
                "active_rule": "interactive_required",
                "match": {"process_names": [], "title_keywords": []},
            },
        },
    }
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return config


def _build_window():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        config = _write_config(config_path)
        db_path = tmp_path / "usage.db"
        database.init_db(str(db_path)).close()

        app = QApplication.instance() or QApplication([])
        window = MainWindow(
            str(tmp_path),
            config,
            str(db_path),
            str(config_path),
            str(reports_dir),
            DummyWorker(),
        )
        window.show()
        app.processEvents()
        return window


def test_sidebar_status_card_shows_record_summary():
    window = _build_window()
    texts = [
        window.sidebar_record_status.text(),
        window.sidebar_record_value.text(),
        window.sidebar_record_streak.text(),
        window.sidebar_version.text(),
        window.sidebar_sample_time.text(),
    ]

    assert any("正在记录" in text for text in texts)
    assert any("连续记录" in text for text in texts)
    assert any("最后采样" in text for text in texts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gui_smoke.py::test_sidebar_status_card_shows_record_summary -v`
Expected: FAIL because the sidebar still shows only a minimal version label and last-sample label.

- [ ] **Step 3: Write minimal implementation**

Add a small sidebar status block with:

- `🟢 正在记录`
- `已记录：...`
- `连续记录：第...天`
- `版本：v1.5.3`
- `最后采样：HH:MM:SS`

Expose `TodayOverviewPage.last_consecutive_days` and `TodayOverviewPage.last_snapshot_totals` so the main window can update the sidebar without extra queries.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gui_smoke.py::test_sidebar_status_card_shows_record_summary -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/daylens/gui/main_window.py src/daylens/gui/pages/today_overview.py tests/test_gui_smoke.py
git commit -m "feat: strengthen sidebar status card"
```

### Task 5: Update docs and final regression

**Files:**
- Create: `D:\OfficeSoftware\DayLens\CHANGELOG.md`
- Create: `D:\OfficeSoftware\DayLens\TODO.md`
- Modify: `D:\OfficeSoftware\DayLens\tests\test_repo_docs.py`

- [ ] **Step 1: Write the documentation files**

`CHANGELOG.md`

```md
# Changelog

## Unreleased

- Redesign the homepage into an insights-first dashboard.
- Replace the old timeline with high-value session cards.
- Strengthen the sidebar status card with record summary.
```

`TODO.md`

```md
# TODO

- Verify homepage layout at 1600x900 with real data.
- Review whether maximum disruption source needs a stronger proxy later.
- Consider a future lazy-load pass if homepage refresh still feels heavy.
```

- [ ] **Step 2: Update the repo docs test**

```python
from pathlib import Path


def test_docs_files_exist():
    assert Path("CHANGELOG.md").exists()
    assert Path("TODO.md").exists()
```

- [ ] **Step 3: Run the full regression**

Run:

```bash
pytest tests/test_dashboard_service.py tests/test_homepage_redesign.py tests/test_dashboard_widgets.py tests/test_gui_smoke.py tests/test_repo_docs.py -v
```

Expected: all pass.

- [ ] **Step 4: Rebuild the release**

Run:

```bash
python tools/build_release.py
```

Expected: `release/DayLens.exe` is updated.

- [ ] **Step 5: Final git review and commit**

Run:

```bash
git status
git add CHANGELOG.md TODO.md src/daylens/services/dashboard_service.py src/daylens/gui/pages/today_overview.py src/daylens/gui/widgets/dashboard_widgets.py src/daylens/gui/main_window.py src/daylens/gui/style.py tests/test_dashboard_service.py tests/test_homepage_redesign.py tests/test_dashboard_widgets.py tests/test_gui_smoke.py tests/test_repo_docs.py
git commit -m "feat: redesign dashboard insight and session cards"
```
