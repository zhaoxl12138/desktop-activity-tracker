# 偏爱应用历史指标 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将工作节奏和娱乐时间7天／30天摘要中的“最高一天”替换为对应分类累计时长最高的“偏爱应用”。

**Architecture:** 服务层从首页已读取的30天会话中，按日期范围、分类集合和既有秒数口径聚合应用，生成完整应用名及累计秒数。GUI 复用统一历史指标单元格，按控件实际像素宽度动态省略并保留完整名称悬停，不增加数据库查询。

**Tech Stack:** Python 3、PySide6、pytest、现有 dashboard snapshot 服务。

---

### Task 1: 服务层偏爱应用聚合

**Files:**
- Modify: `src/daylens/services/dashboard_service.py`
- Test: `tests/test_dashboard_service.py`
- Test: `tests/test_history_cards_presentation.py`

- [ ] **Step 1: Write failing aggregation tests**

新增合成会话测试，断言：工作只累计 `WORK_KEYS` 的 `engaged_seconds`，娱乐只累计 `ENTERTAINMENT_KEYS` 的 `effective_seconds`；7天排除更早会话，30天包含完整范围；并列时按应用名稳定排序。

- [ ] **Step 2: Run tests and verify RED**

Run: `py -m pytest -q tests/test_dashboard_service.py tests/test_history_cards_presentation.py -k favorite_app`

Expected: FAIL，因为快照仍返回“最高一天”，且没有应用聚合字段。

- [ ] **Step 3: Implement a pure aggregation helper**

在 `dashboard_service.py` 增加只处理已加载会话的 `_favorite_app()`：

```python
def _favorite_app(sessions, *, start, end, category_keys, seconds_for):
    totals = {}
    for session in sessions:
        if str(session.get("category_key") or "") not in category_keys:
            continue
        try:
            day = date.fromisoformat(str(session.get("date") or ""))
        except ValueError:
            continue
        if not start <= day <= end:
            continue
        seconds = max(0, int(seconds_for(session) or 0))
        if seconds <= 0:
            continue
        name = _strip_executable_suffix(
            str(session.get("process_name") or "").strip()
        ) or "未知应用"
        totals[name] = totals.get(name, 0) + seconds
    if not totals:
        return {"name": None, "seconds": 0}
    name, seconds = min(totals.items(), key=lambda item: (-item[1], item[0].casefold()))
    return {"name": name, "seconds": seconds}
```

工作使用 `_work_hover_seconds`，娱乐使用 `effective_seconds`。

- [ ] **Step 4: Attach the result to both periods**

让 `_build_seven_day_rhythm`、`_build_thirty_day_rhythm` 和 `build_entertainment_history.build_mode` 接收同一批 `range_sessions`，将第二项指标／摘要改为：

```python
{"label": "偏爱应用", "value": favorite["name"] or "--", "delta": duration}
```

娱乐摘要保存 `favorite_app_name` 与 `favorite_app_seconds`。删除仅用于旧“最高一天”摘要的排名变量，但保留图表每日值。

- [ ] **Step 5: Run focused service tests**

Run: `py -m pytest -q tests/test_dashboard_service.py tests/test_history_cards_presentation.py -k "favorite_app or history"`

Expected: PASS。

### Task 2: 五字符展示与完整悬停

**Files:**
- Modify: `src/daylens/gui/widgets/history_card_widgets.py`
- Modify: `src/daylens/gui/widgets/dashboard_widgets.py`
- Test: `tests/test_dashboard_widgets.py`
- Test: `tests/test_history_cards_presentation.py`

- [ ] **Step 1: Write failing presentation tests**

断言两张卡片第二格标题为“偏爱应用”，宽度足够时显示完整 `ChatGPT`，次值显示累计时长；缩窄后才出现省略号，悬停保留完整 `ChatGPT`。

- [ ] **Step 2: Run tests and verify RED**

Run: `py -m pytest -q tests/test_dashboard_widgets.py tests/test_history_cards_presentation.py -k favorite_app`

Expected: FAIL，因为卡片仍强制写“最高一天”且没有统一截断函数。

- [ ] **Step 3: Add shared presentation helper**

在 `HistoryMetricCell` 中复用现有 `ElidedLabel` 作为值标签：

```python
self.value = ElidedLabel("--", max_lines=1)
```

- [ ] **Step 4: Apply helper in both cards**

工作卡历史模式直接把完整应用名交给 `ElidedLabel`。娱乐卡从 `favorite_app_name`／`favorite_app_seconds` 读取并使用相同标签；标签在 resize 时按字体像素宽度重新计算，其他两个指标不变。

- [ ] **Step 5: Run focused GUI tests**

Run: `py -m pytest -q tests/test_dashboard_widgets.py tests/test_history_cards_presentation.py`

Expected: PASS。

### Task 3: 验证、发布与重启

**Files:**
- Modify: `docs/reviews/2026-10-29-favorite-app-history-result.md`

- [ ] **Step 1: Run full verification**

Run:

```powershell
py -m pytest -q
py -m compileall -q src tests
py tests/test_gui_smoke.py
git diff --check
```

Expected: 所有命令退出码为0。

- [ ] **Step 2: Record real results**

记录定向与全量测试实际通过数、构建结果、未新增查询及口径说明。

- [ ] **Step 3: Commit implementation**

提交服务、卡片、测试和验证记录，不加入现有未跟踪用户文件。

- [ ] **Step 4: Publish and restart**

使用 `tools/build_release.py` 的安全发布流程，归档已有 `release_previous` 后再原子替换；启动 `release/DayLens.exe`，验证单实例、可见主窗口和进程响应。
