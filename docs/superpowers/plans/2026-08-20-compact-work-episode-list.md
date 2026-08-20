# Compact Work Episode List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将首页“关键工作片段”改成紧凑、无重复、层级清晰的单列时间流，同时保持现有数据口径、过滤规则和左右栏底部对齐。

**Architecture:** 只调整 `WorkEpisodeListWidget` 的展示职责和 `TodayOverviewPage` 的布局接线。工作片段快照、排序与统计保持不变；列表组件自行控制行高和内容高度，首页卡片继续承担剩余空间以保持双栏对齐。

**Tech Stack:** Python 3.14、PySide6、pytest、PyInstaller

---

## File map

- Modify: `src/daylens/gui/widgets/dashboard_widgets.py` — 紧凑行、左侧参与标记、重复应用隐藏和列表高度。
- Modify: `src/daylens/gui/pages/today_overview.py` — 压缩时间轴并把片段列表固定在卡片顶部。
- Modify: `tests/test_dashboard_widgets.py` — 行高、参与标记、重复隐藏、空状态和多应用回归。
- Modify: `tests/test_ui_responsive_layout.py` — 1280×720 及更大窗口的尺寸、元数据边界和双栏对齐。
- Verify: `tests/test_homepage_redesign.py`、`tests/test_gui_smoke.py` — 既有纯文本和首页接线兼容。

### Task 1: Build compact work-episode rows

**Files:**
- Modify: `tests/test_dashboard_widgets.py`
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py:2314-2415`

- [ ] **Step 1: Write failing compact-row tests**

Add:

```python
def test_work_episode_widget_uses_compact_accented_rows_and_hides_duplicate_app():
    app = _app()
    widget = dashboard_widgets.WorkEpisodeListWidget()
    widget.set_episodes([{
        "start_time": "2026-08-20 08:22:00",
        "end_time": "2026-08-20 08:41:00",
        "topic": "ChatGPT.exe",
        "apps": ["ChatGPT.exe"],
        "engaged_seconds": 615,
    }])
    widget.show()
    app.processEvents()

    row = widget._row_widgets[0]
    accent = row.findChild(QFrame, "workEpisodeAccent")
    apps = row.findChild(QLabel, "workEpisodeApps")
    assert row.height() == 72
    assert accent is not None and accent.width() == 3
    assert dashboard_widgets.COLORS["coding_green"] in accent.styleSheet()
    assert apps is not None and apps.isHidden()
    assert widget.height() == 72

    widget.deleteLater()
    app.processEvents()


def test_work_episode_widget_keeps_distinct_multi_app_chain():
    app = _app()
    widget = dashboard_widgets.WorkEpisodeListWidget()
    widget.set_episodes([{
        "start_time": "2026-08-20 09:00:00",
        "end_time": "2026-08-20 09:20:00",
        "topic": "整理设计方案",
        "apps": ["Obsidian", "ChatGPT.exe"],
        "engaged_seconds": 900,
    }])
    widget.show()
    app.processEvents()

    apps = widget._row_widgets[0].findChild(QLabel, "workEpisodeApps")
    assert apps is not None
    assert apps.text() == "Obsidian / ChatGPT.exe"
    assert apps.isVisible()

    widget.deleteLater()
    app.processEvents()
```

- [ ] **Step 2: Run tests and verify red state**

Run:

```powershell
py -m pytest tests/test_dashboard_widgets.py::test_work_episode_widget_uses_compact_accented_rows_and_hides_duplicate_app tests/test_dashboard_widgets.py::test_work_episode_widget_keeps_distinct_multi_app_chain -q
```

Expected: FAIL because rows are not fixed to 72px, `workEpisodeAccent` does not exist, and duplicate app text remains visible.

- [ ] **Step 3: Implement fixed list sizing**

Add constants, a fixed vertical size policy, and an explicit content-height helper:

```python
class WorkEpisodeListWidget(QFrame):
    MAX_ROWS = 5
    MIN_DISPLAY_SECONDS = 5 * 60
    ROW_HEIGHT = 72
    ROW_SPACING = 6
    EMPTY_HEIGHT = 34

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("workEpisodeList")
        self.setStyleSheet("QFrame#workEpisodeList { background: transparent; border: none; }")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._episodes: list[dict] = []
        self._row_widgets: list[QWidget] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.ROW_SPACING)

    def _set_content_height(self, row_count: int) -> None:
        if row_count <= 0:
            self.setFixedHeight(self.EMPTY_HEIGHT)
            return
        visible_rows = min(row_count, self.MAX_ROWS)
        self.setFixedHeight(
            visible_rows * self.ROW_HEIGHT
            + max(0, visible_rows - 1) * self.ROW_SPACING
        )
```

Update `set_episodes` so every state receives an explicit height:

```python
def set_episodes(self, episodes: list[dict]) -> None:
    for row in self._row_widgets:
        self._layout.removeWidget(row)
        row.deleteLater()
    self._row_widgets.clear()
    filtered: list[dict] = []
    for episode in episodes or []:
        seconds = (
            parse_nonnegative_int(episode.get("seconds"))
            if "seconds" in episode
            else parse_nonnegative_int(episode.get("engaged_seconds"))
        )
        if seconds is not None and seconds > self.MIN_DISPLAY_SECONDS:
            filtered.append(episode)
    self._episodes = filtered
    if not self._episodes:
        empty = QLabel("暂无可回顾的工作片段")
        empty.setTextFormat(Qt.PlainText)
        empty.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_muted']}; padding: 8px 0;"
        )
        self._layout.addWidget(empty)
        self._row_widgets.append(empty)
        self._set_content_height(0)
        return
    for episode in self._episodes[: self.MAX_ROWS]:
        row = self._build_row(episode)
        self._layout.addWidget(row)
        self._row_widgets.append(row)
    self._set_content_height(len(self._row_widgets))
```

- [ ] **Step 4: Implement the accented row and duplicate suppression**

Replace `_build_row` with:

```python
def _build_row(self, episode: dict) -> QFrame:
    row = QFrame()
    row.setObjectName("workEpisodeRow")
    row.setFixedHeight(self.ROW_HEIGHT)
    row.setStyleSheet(
        f"QFrame#workEpisodeRow {{ background: {COLORS['panel_bg_alt']}; "
        f"border: 1px solid {COLORS['border']}; border-radius: 8px; }} "
        f"QFrame#workEpisodeRow:hover {{ background: {COLORS['card_bg_alt']}; }}"
    )
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 7, 12, 7)
    layout.setSpacing(10)

    accent = QFrame()
    accent.setObjectName("workEpisodeAccent")
    accent.setFixedWidth(3)
    accent.setStyleSheet(
        f"QFrame#workEpisodeAccent {{ background: {COLORS['coding_green']}; "
        "border: none; border-radius: 1px; }"
    )
    layout.addWidget(accent)

    text_box = QWidget()
    text_layout = QVBoxLayout(text_box)
    text_layout.setContentsMargins(0, 0, 0, 0)
    text_layout.setSpacing(2)
    topic_text = str(episode.get("topic", "") or "未命名工作片段")
    topic = ElidedLabel(topic_text)
    topic.setObjectName("workEpisodeTopic")
    topic.setTextFormat(Qt.PlainText)
    topic.setStyleSheet(
        f"font-size: 13px; font-weight: 800; color: {COLORS['text']};"
    )
    app_names = [
        str(app).strip()
        for app in episode.get("apps", [])
        if str(app).strip()
    ]
    apps_text = " / ".join(app_names)
    app_label = ElidedLabel(apps_text)
    app_label.setObjectName("workEpisodeApps")
    app_label.setTextFormat(Qt.PlainText)
    app_label.setStyleSheet(
        f"font-size: 11px; color: {COLORS['text_secondary']};"
    )
    duplicate_single_app = (
        len(app_names) == 1
        and app_names[0].casefold() == topic_text.strip().casefold()
    )
    app_label.setVisible(bool(apps_text) and not duplicate_single_app)
    text_layout.addWidget(topic)
    text_layout.addWidget(app_label)
    layout.addWidget(text_box, 1)

    meta_box = QWidget()
    meta_layout = QVBoxLayout(meta_box)
    meta_layout.setContentsMargins(0, 0, 0, 0)
    meta_layout.setSpacing(2)
    start = str(episode.get("start_time", "") or "")
    end = str(episode.get("end_time", "") or "")
    time_label = QLabel(f"{start[11:16]}–{end[11:16]}")
    time_label.setObjectName("workEpisodeTime")
    time_label.setTextFormat(Qt.PlainText)
    time_label.setAlignment(Qt.AlignRight)
    time_label.setStyleSheet(
        f"font-size: 11px; font-weight: 700; color: {COLORS['primary_hover']};"
    )
    seconds = (
        parse_nonnegative_int(episode.get("seconds"))
        if "seconds" in episode
        else parse_nonnegative_int(episode.get("engaged_seconds"))
    ) or 0
    metric_label = str(episode.get("metric_label", "参与") or "参与")
    duration_label = QLabel(f"{metric_label} {fmt_seconds(seconds)}")
    duration_label.setObjectName("workEpisodeDuration")
    duration_label.setTextFormat(Qt.PlainText)
    duration_label.setAlignment(Qt.AlignRight)
    duration_label.setStyleSheet(
        f"font-size: 12px; font-weight: 800; color: {COLORS['primary']};"
    )
    meta_layout.addWidget(time_label)
    meta_layout.addWidget(duration_label)
    layout.addWidget(meta_box)
    return row
```

- [ ] **Step 5: Run widget tests and commit**

Run:

```powershell
py -m pytest tests/test_dashboard_widgets.py -q
```

Expected: all widget tests PASS, including five-minute filtering and pure-text rendering.

Commit:

```powershell
git add -- src/daylens/gui/widgets/dashboard_widgets.py tests/test_dashboard_widgets.py
git commit -m "style: compact work episode rows"
```

### Task 2: Compress the timeline shell without breaking column alignment

**Files:**
- Modify: `tests/test_ui_responsive_layout.py`
- Modify: `src/daylens/gui/pages/today_overview.py:343-412`
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py:155-184`

- [ ] **Step 1: Write failing responsive tests**

Extend `test_dashboard_column_content_bottoms_align_with_compact_rhythm`:

```python
for episode_count in (1, 2):
    page.work_episode_widget.set_episodes([
        {
            "start_time": f"2026-08-20 {8 + index:02d}:00:00",
            "end_time": f"2026-08-20 {8 + index:02d}:20:00",
            "engaged_seconds": 1_200,
            "apps": ["ChatGPT.exe"],
            "topic": f"工作片段 {index + 1}",
        }
        for index in range(episode_count)
    ])
    window.resize(1280, 720)
    app.processEvents()

    rows = page.work_episode_widget._row_widgets
    assert len(rows) == episode_count
    assert all(row.height() == 72 for row in rows)
    expected_height = episode_count * 72 + max(0, episode_count - 1) * 6
    assert page.work_episode_widget.height() == expected_height
    assert page.focus_axis.height() == 28
    assert abs(
        page.focus_timeline_card.geometry().bottom()
        - page.daily_goals_card.geometry().bottom()
    ) <= 2

    for row in rows:
        for object_name in ("workEpisodeTime", "workEpisodeDuration"):
            label = row.findChild(QLabel, object_name)
            assert label is not None
            assert label.geometry().right() <= row.contentsRect().right()
            assert label.textFormat() == Qt.PlainText
```

- [ ] **Step 2: Run responsive test and verify red state**

```powershell
py -m pytest tests/test_ui_responsive_layout.py::test_dashboard_column_content_bottoms_align_with_compact_rhythm -q
```

Expected: FAIL because the axis is still 32px and the list currently expands inside its card.

- [ ] **Step 3: Apply compact shell layout**

In `FocusTimelineBarWidget.__init__`, change:

```python
self.setFixedHeight(28)
```

In `TodayOverviewPage._build_focus_timeline_card`, replace the stretched list insertion with:

```python
self.session_top3_widget = WorkEpisodeListWidget()
self.work_episode_widget = self.session_top3_widget
layout.addWidget(self.session_top3_widget, 0, Qt.AlignTop)
layout.addStretch(1)
```

The outer `left_layout.addWidget(self.focus_timeline_card, 1)` stays unchanged, so left and right card bottoms remain aligned while rows remain compact at the top.

- [ ] **Step 4: Run GUI/layout tests and commit**

Run:

```powershell
py -m pytest tests/test_dashboard_widgets.py tests/test_ui_responsive_layout.py tests/test_homepage_redesign.py tests/test_gui_smoke.py -q
```

Expected: all tests PASS at 1280×720, 1600×900 and 1706×910.

Commit:

```powershell
git add -- src/daylens/gui/pages/today_overview.py src/daylens/gui/widgets/dashboard_widgets.py tests/test_ui_responsive_layout.py
git commit -m "style: tighten focus timeline layout"
```

### Task 3: Full verification and release replacement

**Files:**
- Verify: all tracked source and tests
- Build: `tools/build_release.py`
- Runtime: `release/DayLens.exe`
- Data: `data/usage.db` (read-only verification)

- [ ] **Step 1: Run full verification**

```powershell
py -m pytest -q
py -m compileall -q src
git diff --check
git status --short
```

Expected: all tests pass; compile and diff checks exit 0. Known user-owned untracked documents/screenshots may remain, but no tracked implementation file is dirty.

- [ ] **Step 2: Build and publish**

```powershell
py tools/build_release.py
```

Expected: PyInstaller succeeds, the staging smoke test exits 0, and the release is prepared at `D:\OfficeSoftware\DayLens\release`.

If Windows temporarily locks the old release directory, first verify no `DayLens.exe` process exists and resolve both paths inside `D:\OfficeSoftware\DayLens`; then use native PowerShell `Move-Item -LiteralPath` for the same staging swap. Do not modify the database path.

- [ ] **Step 3: Start and verify the canonical runtime**

Start `D:\OfficeSoftware\DayLens\release\DayLens.exe`, then run:

```powershell
Get-CimInstance Win32_Process -Filter "Name='DayLens.exe'" |
    Select-Object ProcessId, ExecutablePath, CommandLine
```

Expected: exactly one process at `D:\OfficeSoftware\DayLens\release\DayLens.exe`; the desktop shortcut targets the same path and `D:\OfficeSoftware\DayLens\data\usage.db` remains the canonical database.

- [ ] **Step 4: Perform visual acceptance**

At 1280×720 and the current desktop resolution, verify:

- one or two rows stay 72px high instead of stretching;
- duplicate single-app text is absent;
- long titles and app chains elide before touching the right metadata;
- time and participation duration remain fully visible;
- left and right column bottoms remain aligned;
- the existing deep-blue style and green participation accent are consistent.
