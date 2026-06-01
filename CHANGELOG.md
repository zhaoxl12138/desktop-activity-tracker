# Changelog

## 2026-06-01

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
  - 效率评分卡片（仪表盘）
  - 今日专注时段卡片
  - 时间趋势卡片
  - 软件使用 TOP5 卡片
- 统一主题样式中心 `style.py`，优化颜色体系、卡片圆角、边框、层级、按钮与导航样式。
- 重构 `MainWindow` 壳层视觉（左侧深蓝导航、顶部信息栏、底部状态栏），保留原有功能入口与交互逻辑。

### Fixed
- 修复首页 Dashboard 在 1280x820 下的布局挤压问题：
  - 顶部指标卡不再裁切大数字
  - 时间分布、效率评分、趋势图区域限制高度
  - 软件 TOP5 名称过长时自动收敛显示
- 修复顶部指标卡在长时长文本下仍被右侧裁切的问题，指标值改用紧凑时长格式。
- 修复实时监控页中文文案乱码问题。
- 修复主界面中文文案乱码问题（首页与主窗口显示文本）。
