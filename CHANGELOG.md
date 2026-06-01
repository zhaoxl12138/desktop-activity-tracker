# Changelog

## 2026-06-01

### Added
- 新增深色 Dashboard 主题，覆盖主窗口、Sidebar、顶部栏、底部状态栏、首页卡片与按钮样式。
- 新增默认软件显示名映射，TOP5 应用优先展示 `Windows Terminal`、`VS Code`、`Chrome`、`微信` 等可读名称。
- 新增 `docs/UI.md`，记录当前深色 Dashboard 的设计边界、组件结构与后续优化方向。
- 新增 `tests/test_gui_smoke.py`，用临时数据库和临时配置验证默认窗口尺寸、导航切换、暂停/恢复和截图生成。

### Changed
- 首页视觉升级为深蓝/黑蓝背景、蓝紫主色、深色圆角卡片与统一边框层级。
- Sidebar 调整为 `Activity Tracker` 品牌区与 `Focus · Analyze · Improve` 副标题，导航收敛为当前已有核心页面。
- 指标卡片、时间分布、效率评分、今日专注时段、今日时间线、TOP5 应用统一切换为深色卡片展示。
- 非首页页面继续适配深色主题，统一表格、报告页、分类统计、设置页和规则配置页的背景、边框、选中态与输入控件样式。

### Added
- 新增实时监控页 Dashboard 风格展示：
  - 当前前台活动卡片
  - 进程与分类标签
  - 前台停留、有效时间、本会话挂机、系统空闲指标块
  - 最近采样记录表格
- 新增首页 Dashboard 组件模块：`MetricCard`、`DonutChartWidget`、`ScoreGaugeWidget`、`TrendChartWidget`、`TopAppListWidget`、`DistributionLegend`。
- 新增 `gui/widgets` 目录用于沉淀可复用展示组件。

### Changed
- 重做首页 `TodayOverviewPage` 布局为正式 Dashboard：
  - 5 个核心指标卡
  - 时间分布卡片（环图 + 图例）
  - 效率评分卡片（仪表盘 + 评分拆解）
  - 今日专注时段卡片
  - 今日时间线卡片（替换原趋势图）
  - 软件使用 TOP5 卡片（支持显示名映射）
- 统一主题样式中心 `style.py`，优化颜色体系、卡片圆角、边框、层级、按钮与导航样式。
- 重构 `MainWindow` 壳层视觉（左侧深蓝导航、顶部信息栏、底部状态栏），保留原有功能入口与交互逻辑。
- 侧边栏导航重新排序：主页面上方，规则配置/设置移至底部，中间添加分隔符。
- 娱乐时长超过 90 分钟时，Dashboard 顶部显示红色警告横幅，娱乐指标卡数值变红。

### Fixed
- 修复空闲检测的幻影重置过滤器 bug：检测到幻影 HID 事件后，后续的采样会错误地将 `_effective_idle` 重置为低值，导致 `idle_seconds` 始终为 0，有效时间占比始终显示 100%。
- 修复首页 Dashboard 在 1280x820 下的布局挤压问题。
- 修复顶部指标卡在长时长文本下仍被右侧裁切的问题。
- 修复应用默认打开宽度不足导致 Dashboard 需要手动拉长的问题，默认窗口改为 1440x860。
- 修复实时监控页中文文案乱码问题。
- 修复主界面中文文案乱码问题。
