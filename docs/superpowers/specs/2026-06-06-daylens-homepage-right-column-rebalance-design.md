# DayLens 首页重排：删除今日洞察并恢复右侧双卡

## 背景
当前首页中间的“今日洞察”卡片占用了大量横向空间，导致右侧“时间趋势”和“软件使用 TOP5”被挤压，视觉比例失衡。用户要求删除“今日洞察”，恢复更稳定的双列首页结构，并保留“时间分布”“今日专注 Session”“时间趋势”“软件使用 TOP5”四个核心模块。

## 目标
- 删除首页中的“今日洞察”卡片。
- 恢复首页为左侧主信息、右侧辅助信息的双列布局。
- 让“时间趋势”和“软件使用 TOP5”恢复正常宽度与对齐关系。
- 保留已完成的“时间分布 + 较昨日”“今日专注 Session”内容口径。
- 不改业务数据口径，不改统计算法，不改历史日报内容。

## 范围
### 保留
- `时间分布` 卡片
- `今日专注 Session` 卡片
- `时间趋势` 卡片
- `软件使用 TOP5` 卡片
- 左下状态卡增强内容

### 删除
- `今日洞察` 整块卡片
- 与其相关的首页渲染入口和占位逻辑

### 调整
- 首页网格从“左中右三列”调整为更清晰的双列主结构：
  - 左列：`时间分布`、`今日专注 Session`
  - 右列：`时间趋势`、`软件使用 TOP5`
- 重新分配上、下两行的高度比例，让右侧两张卡不再被中间卡挤压。
- 如果需要，适度调整卡片最小高度和内边距，但保持现有暗色主题和组件风格一致。

## 当前相关组件文件
- `D:\OfficeSoftware\DayLens\src\daylens\gui\pages\today_overview.py`
- `D:\OfficeSoftware\DayLens\src\daylens\gui\widgets\dashboard_widgets.py`
- `D:\OfficeSoftware\DayLens\src\daylens\gui\main_window.py`
- 测试：
  - `D:\OfficeSoftware\DayLens\tests\test_homepage_redesign.py`
  - `D:\OfficeSoftware\DayLens\tests\test_dashboard_widgets.py`
  - `D:\OfficeSoftware\DayLens\tests\test_gui_smoke.py`

## 布局方案
### 推荐方案：恢复双列主结构
- 第一行：
  - 左：`时间分布`，占 8/12
  - 右：`时间趋势`，占 4/12
- 第二行：
  - 左：`今日专注 Session`，占 8/12
  - 右：`软件使用 TOP5`，占 4/12

### 关键点
- `今日洞察` 从首页彻底移除，不保留折叠入口。
- `时间分布` 继续承载“较昨日”信息，不再新增重复模块。
- `今日专注 Session` 维持卡片化展示，首页只展示高价值会话。
- `时间趋势` 与 `TOP5` 重新获得独立右侧列宽，避免看起来“被挤瘦”。

## 数据来源说明
- 不新增新的数据结构。
- 首页仍复用现有 `load_today_snapshot()` 返回值：
  - `distribution_sections`
  - `day_comparison`
  - `sessions`
  - `trend.today`
  - `focus_summary`
  - `consecutive_days`
  - `top_app_rows`
- 删除 `今日洞察` 后，不再需要 `insights` 计算与渲染入口。

## 风险点
- 现有首页网格已经做过多轮调整，改动布局时要避免把 `Session` 卡片和右侧卡再次压扁。
- 删除 `今日洞察` 可能会让中间区域留白，需要通过列宽和行高重新平衡，而不是简单删组件。
- `main_window.py` 中可能还残留洞察相关引用，需要一起清理，否则会造成空布局或无用刷新。
- 右侧卡片如果只改字体、不改列宽，问题不会真正消失。

## 测试方案
- 结构测试：
  - 首页不再包含 `今日洞察`
  - `时间趋势` 和 `软件使用 TOP5` 仍存在
  - `time_stats_card` 不存在
  - `distribution_cmp_labels` 仍绑定到 `时间分布`
  - `今日专注 Session` 仍显示
- 布局测试：
  - 右侧两张卡不再被中间卡挤压
  - 首页双列结构在 1600×900 下正常显示
- 回归测试：
  - `tests/test_homepage_redesign.py`
  - `tests/test_dashboard_widgets.py`
  - `tests/test_gui_smoke.py`
- 验证方式：
  - 运行相关测试
  - 重建发布版
  - 更新桌面快捷启动指向最新 `release/DayLens.exe`

## 说明
- 本次只做首页结构重排，不改统计口径、不改 session 判定、不改日报历史内容。
- 这是一次纯 UI 结构修复，目标是恢复首页信息层级和右侧卡片的正常视觉比例。
