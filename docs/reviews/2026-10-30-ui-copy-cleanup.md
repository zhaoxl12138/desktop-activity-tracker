# 常驻说明小字清理验收

日期：2026-10-30；基线：`38f6cfe`。用户已确认“去说明、留反馈”，本轮不按字体大小全局隐藏控件。

## 实际范围

- 主窗口：非今日页面隐藏重复副标题；今日日期、AI 事实观察和记录状态保留。
- 报告中心：删除副标题、“当前选中”小标题和空选中解释。自动补报的预算/待补/未完成长说明迁到生成按钮 tooltip，后台补报照常运行。手动生成中的状态持续可见，成功反馈 5 秒后收起，失败持续可见；并行生成时合并显示待处理项目，其他成功不能掩盖已有失败。
- 设置：基础、娱乐边界、自启、数据维护的解释行移到对应控件 tooltip，密钥状态、每日调用数、费用和预算保留。智能开关使用短名称，隐私、调用频率与定时约定留在 tooltip。
- 分类管理与规则：去掉操作引导和规则解释横条；数量放入应用归属标题，具体匹配说明保留 tooltip。字段、保存/确认/失败、未保存提醒不变。
- 目标：去掉重复副标题、上限和示例；就绪时不显示重复口径解释，加载/保存/不可读仍显示。时间进度、还差时长、用户确认成果不变。
- 全天详情：解释图例和绘制脚注迁至 tooltip；隐藏会话数量与覆盖时长保留，空记录及筛选无结果使用短反馈。横轴仍按原范围分配，删除脚注后为大字体刻度保留自适应底边，不改变事件/分类/时长。
- 分类/应用弹窗和首次向导：移除重复引导，保留字段、作用范围和输入错误。

计时、分类、预算、调度、报告内容、原始数据库和历史文件均未修改。仅 GUI、测试、布局工具及文档发生变化；没有测试真实 API，也不写入真实用户配置。

## 自动测试与复核

- 相关基线 73 passed。
- 首批新增回归 8 failed，确认旧界面仍显示解释；后补空反馈占位、大字体横轴边界、宽屏重复标题的先失败后修复测试。
- 独立复核发现先完成的报告可能在其他报告仍生成时启动隐藏定时器。新增两条多任务回归先失败，修复后定向 28 passed；失败不会被后续成功或列表刷新抹除，仅在相应类型被接受重试时清除。
- 最终全量 `python -m pytest -q`：1435 passed in 39.54s。
- `python -m compileall -q src tests tools`：退出码 0。
- `python tests/test_gui_smoke.py`：通过；旧副标题显示断言按新约定改为隐藏。最初旧断言失败后临时目录清理也报错，未涉及生产目录。
- `python -m ruff check src/daylens --select F821,E9 --output-format concise`、`git diff --check`：通过。
- 独立复核首轮相关 49 项通过，补修后独立复核 28 项通过，未剩实质阻塞。

## 布局

以下五组隔离工具均覆盖 1280×720 / 1920×1080、100% / 125% / 150%、明暗主题：

- `tools/check_navigation_layout.py`：今日、实时、设置、规则、报告、目标六个页面；验证必要状态可见及已移除说明不重新出现。
- `tools/check_local_rules_layout.py`：规则简单/高级视图、添加/测试应用弹窗。
- `tools/check_reports_v2_layout.py`：列表、详情与操作按钮。
- `tools/check_day_activity_layout.py`：早间/全天、时间轴/明细/分类筛选。
- `tools/check_settings_rhythm_layout.py`：设置顶部/底部及现有图表。

人工查看了 150% 的报告、活动详情与智能设置截图。真实窗口未做额外点选；视觉结论来自隔离截图与自动边界检查。

## 修改文件

GUI：`main_window.py`、`wizard.py`；pages 下 `reports.py`、`settings.py`、`rule_config.py`、`classification_management.py`、`live_monitor.py`、`daily_goals.py`；widgets 下 `intelligence_settings.py`、`goal_workspace_widgets.py`、`classification_dialog.py`、`rule_application_dialog.py`、`day_activity_dialog.py`、`day_activity_category_timeline.py`。

测试：新增 `tests/test_ui_copy_cleanup.py`，更新原目标/分类/设置/报告/时间轴相关 UI 显示约定；新增用例共 11 项。工具更新 `tools/check_navigation_layout.py`，README 与实施计划同步。
