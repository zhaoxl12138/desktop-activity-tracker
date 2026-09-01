# 娱乐记录摘要顺序统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让娱乐记录卡按工作节奏卡的阅读顺序展示日均、最高日和总时长。

**Architecture:** 仅调整 `EntertainmentHistoryCard` 创建摘要单元的标签顺序，以及 `_set_summary()` 为这些单元提供的数值顺序。继续使用服务层已提供的 `average_seconds`、`max_date`/`max_seconds` 与 `total_seconds`，不修改数据库、快照模型或图表。

**Tech Stack:** Python 3.14、PySide6、pytest。

---

### Task 1: 统一娱乐摘要标签与数值顺序

**Files:**
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py:2435-2514`
- Modify: `tests/test_dashboard_widgets.py:娱乐记录卡测试`

- [ ] **Step 1: Write the failing test**

```python
def test_entertainment_history_card_matches_work_rhythm_summary_order():
    card = EntertainmentHistoryCard()
    card.set_data({"entertainment_history": _history_with_summary(
        total_seconds=7_200,
        average_seconds=1_200,
        max_date="2026-09-01",
        max_seconds=3_600,
    )})

    assert [label.text() for label, _value in card._summary_labels] == [
        "日均娱乐", "最高一天", "总时间",
    ]
    assert [value.text() for _label, value in card._summary_labels] == [
        "20分钟", "9/1 · 1小时", "2小时",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_widgets.py -k "entertainment_history_card_matches_work_rhythm_summary_order" -q`

Expected: FAIL because the current labels are `总时长`、`日均`、`最高日` and values use the old order.

- [ ] **Step 3: Write minimal implementation**

```python
for title in ("日均娱乐", "最高一天", "总时间"):
    cell = QFrame()
    # Preserve the existing cell construction and label/value wiring.

values = [
    _goal_duration(average) if average is not None else "--",
    f"{self._short_date(str(max_date))} · {_goal_duration(maximum)}"
    if max_date and maximum is not None else "--",
    _goal_duration(total) if total is not None else "--",
]
```

- [ ] **Step 4: Run focused and widget tests**

Run: `python -m pytest tests/test_dashboard_widgets.py -k "entertainment_history" -q`

Expected: PASS, including the empty-data `--` regression cases.

Run: `python -m pytest tests/test_dashboard_widgets.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- src/daylens/gui/widgets/dashboard_widgets.py tests/test_dashboard_widgets.py
git commit -m "fix: align entertainment summary order"
```
