# DayLens v1.5 Issue List

> 给 Codex / Claude Code / DeepSeek 的工程化 Issue 清单。
> 每个 Issue 包含：问题描述、当前表现、目标效果、涉及文件、实现要点。

---

## 总体评价

当前 Dashboard 布局已定型。后续重点从 UI 调整转向：**统计准确性 → Session 质量 → 数据分析能力**。

---

# P0（优先修复）

## Issue-001：今日时间线未正确聚合 Session

**当前表现：**

时间线出现零散采样记录而非聚合会话：

```
13:25:53-13:25:53  Windows Terminal  1分钟
13:25:43-13:25:43  Windows Terminal  1分钟
13:25:11-13:25:43  Windows Terminal  1分钟
```

**目标效果：**

应自动合并相邻/相同窗口的会话为一个逻辑 Session：

```
13:19 - 13:26  Windows Terminal  编程开发  7分钟
```

**涉及文件：**
- `src/daylens/gui/widgets/dashboard_widgets.py` → `TimelineWidget.set_sessions()`
- `src/daylens/database.py` → `query_today_sessions()`

**实现要点：**
1. 在 `TimelineWidget.set_sessions()` 中增加相邻会话合并逻辑：相同 `process_name + category_key` 且结束时间与下一条开始时间间隔 < 60s 的会话合并为一条
2. 合并时累加 `effective_seconds`，取最早 `start_time` 和最晚 `end_time`
3. 或者：在 `query_today_sessions()` 查询层用 SQL 窗口函数合并

---

## Issue-002：趋势图今日模式需要严格按小时聚合

**当前表现：**

趋势图出现尖刺——12 点 22 分钟，13 点 1 分钟，形成剧烈波动。

**目标效果：**

今日模式展示 0~23 点共 24 个固定数据点，每个点 = 该小时内的总活跃分钟数，形成平滑的日活跃曲线。

**涉及文件：**
- `src/daylens/gui/pages/today_overview.py` → `_build_trend_data()`

**实现要点：**
1. `hour_minutes = [0.0] * 24`，float 累加避免截断
2. 每个 session 按其 `effective_seconds` 跨小时比例分配到对应 hour bucket
3. 最终 `[int(round(v)) for v in hour_minutes]`
4. X 轴固定 24 个标签：0h 2h 4h 6h 8h 10h 12h 14h 16h 18h 20h 22h
5. Y 轴单位：分钟

---

## Issue-003：趋势图缺少空数据 / 数据不足状态

**当前表现：**

首次启动或数据极少时显示奇怪折线。

**目标效果：**

- `valid_count == 0` → 显示 **"暂无趋势数据"**
- `0 < valid_count < 3` → 显示 **"数据积累中\n使用一段时间后将显示趋势"**
- X 轴标签始终可见（即使空数据）

**涉及文件：**
- `src/daylens/gui/widgets/dashboard_widgets.py` → `_TrendCanvas.paintEvent()`

**实现要点：**
1. 已部分实现空状态检查，需验证 `valid_count` 阈值是否合理（当前 <3 显示"积累中"）
2. 空状态文字需在深色/浅色主题下都清晰可读
3. 即使空数据，X 轴标签（QLabel 或 paintEvent 绘制）仍应渲染

---

# P1（重要优化）

## Issue-004：时间轴灰色区域过于抢眼

**当前表现：**

"离开/空闲" 的灰色 (`#8FA1BC`) 占据大量视觉空间，视觉权重过高。

**目标效果：**

降低空闲区域透明度，突出学习（绿）、娱乐（橙）、社交（紫）等有效活动。

**涉及文件：**
- `src/daylens/gui/pages/today_overview.py` → `_build_focus_axis()` → `COLORS["idle_gray"]`
- `src/daylens/gui/widgets/dashboard_widgets.py` → `FocusTimelineBarWidget`

**实现要点：**
1. 将 `idle_gray` 的不透明度降低到 40%（例如改为 `#8FA1BC` 且 alpha=100 或调整颜色为更淡的灰）
2. 或在 `FocusTimelineBarWidget.paintEvent()` 中对 idle_gray 颜色单独设置 alpha
3. 深色/浅色主题下均需验证

---

## Issue-005：TOP5 显示名截断问题

**当前表现：**

`Windows Terminal` 显示为 `Windows Term`，被硬截断。

**目标效果：**

显示完整名称，超出宽度时用省略号：`Windows Terminal...`

**涉及文件：**
- `src/daylens/gui/widgets/dashboard_widgets.py` → `TopAppListWidget._build_row()` → `name_label`
- `src/daylens/gui/widgets/dashboard_widgets.py` → `_compact_app_name()`

**实现要点：**
1. 检查 `_compact_app_name()` 是否有硬截断逻辑
2. `name_label.setMinimumWidth(96)` 改为弹性宽度，或用 `setElideMode(Qt.ElideRight)` + 固定宽度
3. 增加 `setToolTip(完整名称)` 悬停显示全名

---

## Issue-006：TOP5 图标覆盖率不足

**当前表现：**

部分软件（Chrome、微信、iQIYI）有图标，部分（system、explorer.exe）没有。

**目标效果：**

所有条目都有图标——成功提取 Windows EXE 图标则用，失败则用默认分类图标。

**涉及文件：**
- `src/daylens/gui/pages/today_overview.py` → `_app_icon()` / `_find_exe_path()`
- `src/daylens/gui/widgets/dashboard_widgets.py` → `TopAppListWidget`

**实现要点：**
1. `_find_exe_path()` 已尝试通过 `psutil.process_iter()` 查找 exe 路径
2. 对于 `system` / `explorer.exe` 等系统进程，使用 `QFileIconProvider` 获取系统图标
3. 对于查找失败的进程，提供一个分类默认图标（按 category_key 映射颜色/emoji）
4. 缓存策略已有 `_icon_cache`，避免重复查找

---

## Issue-007：侧边栏图标风格不统一

**当前表现：**

当前使用文字符号（T/W/E/S/I）代替图标，视觉风格过于简陋。

**目标效果：**

统一使用 Fluent UI Icons 或 Material Icons 的 SVG/Unicode 字符。

**涉及文件：**
- `src/daylens/gui/main_window.py` → `NAV_ITEMS`（当前每个 item 只有 title/key/hint，无 icon 字段）
- `src/daylens/gui/pages/today_overview.py` → `MetricCard`（icon 参数传的是文字 "T"/"W"/"E" 等）

**实现要点：**
1. 方案 A：使用 Unicode 符号（📊 ⚡ 💻 📂 📋 🎯 ⚙️）—— 简单但跨平台渲染不一致
2. 方案 B：使用 PySide6 `QIcon` + SVG 文件 —— 效果好但增加资源文件依赖
3. 方案 C：使用 Material Design Icons 的 Unicode 码点 —— 折中方案
4. 推荐方案 A（成本最低），或 C 如果对渲染效果有要求

---

# P2（后续版本）

## Issue-008：顶部统计信息存在感不足

当前右上角 `总活跃 X | 学习/工作 Y | 娱乐 Z` 仅在 top_bar 右上角小字显示，容易被忽略。

**建议：** 增加今日活跃时长的视觉权重——考虑在 top_bar 中间或左侧增加大字显示核心指标。

**涉及文件：** `src/daylens/gui/main_window.py` → `_build_top_bar()` / `_update_top_bar()`

---

## Issue-009：今日专注模块信息量不足

当前仅显示 "最长专注：XX:XX-XX:XX，N 分钟" 和连续天数，内容偏少。

**建议增加：**
- 最长专注 Session（软件 + 时长）
- 最长连续学习时段
- 今日最佳时段（如 "13:00-14:30，90 分钟"）

**涉及文件：** `src/daylens/gui/pages/today_overview.py` → `_build_focus_card()` / `_update_focus_summary()`

---

## Issue-010：时间统计模块过于简单

当前仅显示：总时长、活跃时长、挂机时长、活跃占比。

**建议增加：** 学习占比、娱乐占比、专注次数、最长 Session。

**涉及文件：** `src/daylens/gui/pages/today_overview.py` → `_build_time_stats_card()` / `refresh()`

---

# P3（未来核心功能）

## Feature-001：周报系统

- 本周学习/娱乐/社交/挂机时长统计
- 最长专注记录
- TOP5 软件
- 趋势分析（与上周对比）
- 输出：Markdown → Obsidian 同步

## Feature-002：月报系统

- 月度学习报告
- 月度趋势图优化
- 分类占比月度变化

## Feature-003：专注分析引擎

分析一天中最容易进入状态的时间段：
- 例如 "09:00-11:00 平均专注时长最高"
- 基于历史数据推荐最佳工作时间窗口

---

# 当前开发优先级

| 阶段 | Issue | 说明 |
|---|---|---|
| **第一阶段（必须修）** | Issue-001, 002, 003 | Session 聚合 + 趋势图小时聚合 + 空状态 |
| **第二阶段（体验优化）** | Issue-004, 005, 006 | 时间轴视觉 + TOP5 名称/图标 |
| **第三阶段（产品能力）** | Feature-001, 002, 003 | 周报 + 月报 + 专注分析 |

---

# 当前版本评价

| 维度 | 完成度 | 说明 |
|---|---|---|
| UI 完成度 | 85% | 布局定型，暗色/亮色双主题 |
| 统计准确性 | 70% | 会话追踪准确，趋势聚合需改进 |
| 数据分析能力 | 55% | 缺少周报/月报/专注分析 |
| 长期使用价值 | 80% | 日常时间追踪可用，分析洞察不足 |

> 现在最需要的不是继续调整界面，而是把 **Session 聚合 + 趋势统计 + 周报分析** 做扎实。这个阶段做对了，DayLens 就从"好看的追踪器"变成"真正每天打开看的数据工具"。
