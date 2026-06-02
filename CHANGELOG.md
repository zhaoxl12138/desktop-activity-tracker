# Changelog

## 2026-06-02

### Added
- `.docs/skills/maintainer.md`，用于提交前检查 README、CHANGELOG、TODO、TEST_PLAN 与生成 commit message。
- `tests/test_timeline_logic.py`，覆盖今日时间线秒级显示、空闲会话查询、动态标题归一化和 DayLens 自身窗口忽略逻辑。

### Fixed
- 修复 PyInstaller 单文件模式导致点击 DayLens 图标后出现父子两个 `DayLens.exe` 进程的问题；打包改为 onedir 输出。
- 修复今日时间线将 1-59 秒会话强制显示为 `1分钟` 的问题，现在按真实秒级时长显示。
- 修复今日时间线只显示有效会话、遗漏空闲/挂机会话的问题。
- 修复 Windows Terminal 等动态标题前缀导致大量 1 秒碎片会话的问题。
- 修复 DayLens 自身窗口处于前台时实时监控停留在上一个应用的问题；当前会话会被正确结束，DayLens 自身显示为“不计入统计”。
- 修复测试与打包入口仍引用旧包名 `desktop_activity_tracker` 导致全量测试无法收集的问题。

## 2026-06-01

### Added
- 深色 Dashboard 主题，覆盖主窗口、Sidebar、顶部栏、底部状态栏、首页卡片与按钮样式。
- 首页 Dashboard 组件模块：`MetricCard`、`DonutChartWidget`、`ScoreGaugeWidget`、`TimelineWidget`、`TopAppListWidget`、`DistributionLegend`。
- `gui/widgets` 目录用于沉淀可复用展示组件。
- 实时监控页 Dashboard 风格展示：当前前台活动卡片、进程与分类标签、指标块、最近采样记录表格。
- 30 分钟时间线功能，含专注时段识别、碎片化分析、一句话复盘。
- 默认软件显示名映射，TOP5 应用优先展示 `Windows Terminal`、`VS Code`、`Chrome`、`微信` 等可读名称。
- `docs/UI.md`，记录当前深色 Dashboard 的设计边界、组件结构与后续优化方向。
- `docs/TEST_PLAN.md`，含 17 个功能测试用例和 4 个性能测试用例。
- `tests/test_gui_smoke.py`，用临时数据库和临时配置验证默认窗口尺寸、导航切换、暂停/恢复和截图生成。
- 效率评分 Hero 数字（46pt 大号分数字体），评分卡片简化布局突出分数。
- Session 流时间线：时间线从 30 分钟聚合块切换为真实会话流，每行显示时间范围、应用名、分类、时长。
- 最长专注时段展示：专注卡片顶部显示今日最长连续专注时段（时间、分钟、分类、应用）。
- 连续使用天数计数器：专注卡片标题栏显示连续使用天数（≥3 天显示火焰图标）。
- 专注时段应用名使用 `display_name` 映射（VS Code 而非 Code.exe）。
- `database.py` 新增 `query_today_sessions()` 和 `count_consecutive_days()` 查询函数。

### Changed
- 首页视觉升级为深蓝/黑蓝背景、蓝紫主色、深色圆角卡片与统一边框层级。
- Sidebar 调整为 `Activity Tracker` 品牌区与 `Focus · Analyze · Improve` 副标题，导航收敛为当前已有核心页面，规则配置/设置移至底部。
- 重做首页 `TodayOverviewPage` 布局：5 个核心指标卡、时间分布卡片（环图 + 图例）、效率评分卡片（仪表盘 + 评分拆解）、今日专注时段卡片、今日时间线卡片（替换原趋势图）、软件使用 TOP5 卡片（支持显示名映射）。
- 效率评分卡片显示详细评分拆解：学习占比基准分、娱乐惩罚分、最终得分。
- 娱乐时长超过 90 分钟时，Dashboard 顶部显示红色警告横幅，娱乐指标卡数值变红。
- 非首页页面适配深色主题，统一表格、报告页、分类统计、设置页和规则配置页的背景、边框、选中态与输入控件样式。
- 实时监控页采样表格的分类列增加颜色圆点标识。
- 统一主题样式中心 `style.py`，优化颜色体系、卡片圆角、边框、层级、按钮与导航样式。
- 默认窗口改为 1440x860，最小 1280x780。

### Fixed
- 修复空闲检测的幻影重置过滤器 V2：`_phantom_active` 状态机在检测到幻影 HID 事件后按墙钟时间累积 `_effective_idle`，彻底解决 `idle_seconds` 始终为 0 的问题。
- 修复首页 Dashboard 在 1280x820 下的布局挤压问题。
- 修复顶部指标卡在长时长文本下仍被右侧裁切的问题，指标值改用紧凑时长格式。
- 修复实时监控页中文文案乱码问题。
- 修复主界面中文文案乱码问题。
