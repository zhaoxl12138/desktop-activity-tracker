# UI Copy Cleanup Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline with test-driven changes and independent review before merge.

**Goal:** 全程序按已确认的“去说明、留反馈”边界去掉常驻解释小字，必要解释迁入悬停提示。

**Architecture:** 逐组件显式删除解释标签或移到其对应控件的 tooltip，不根据字体大小全局隐藏。保留所有日期、数值、字段名、分页、空状态和错误/处理中反馈。后台逻辑不变，尤其自动补报、AI 预算、分类、计时和历史文件均不修改。

**Tech Stack:** PySide6、Python、pytest、SQLite 临时测试数据。

## A. 回归与界面边界

- [x] 在现有隔离工作区同步 `38f6cfe`，运行 UI 相关基线测试：73 passed。
- [x] 新增 `tests/test_ui_copy_cleanup.py`，先断言常驻解释已不占布局，而必要状态仍可显示。例如：

```python
assert page.automation_status.isHidden()
assert '待补' in page.btn_daily.toolTip()
page._generation_jobs['failed'] = '日报'
page._generation_failed('failed', '读取失败')
assert not page.automation_status.isHidden()
```

- [x] 覆盖主窗口非今日副标题隐藏、设置/规则/目标说明移入 tooltip、活动详情说明迁移、添加应用缺输入仍显示错误；初始 8 项失败，后补大字体刻度和空反馈占位测试先失败再修复。

## B. 显式清理

- [x] `gui/main_window.py`：非今日页头不显示重复解释；今日日期、AI 事实观察、记录/错误状态保留。
- [x] `gui/pages/reports.py`：删除副标题，补报诊断移至生成按钮 tooltip；仅手动生成进度/成功/失败显示操作状态。后台补报服务不修改。
- [x] `gui/pages/settings.py`、`gui/widgets/intelligence_settings.py`：删除各设置区解释段；控件保留说明 tooltip。精简勾选框名称，将隐私和频率约束放入 tooltip。密钥状态、月费用和日调用数仍可读，未配置/连接失败仍显示。
- [x] `gui/pages/rule_config.py`、`classification_management.py`、`live_monitor.py`：删除常驻操作说明和信息横条；应用数量归入标题，匹配解释保留 tooltip；确认/保存/失败状态保留。
- [x] `gui/pages/daily_goals.py`、`gui/widgets/goal_workspace_widgets.py`：删除副标题、重复上限/示例和正常状态下的口径说明；加载/保存/不可读仍显示，目标进度/成果确认保持。
- [x] `gui/widgets/day_activity_dialog.py`、`day_activity_category_timeline.py`：常驻图例解释与绘制脚注迁为 tooltip；隐藏会话数量、日期范围、异常和筛选空状态保留简短表达；不改时间轴分组或数据。
- [x] `gui/widgets/classification_dialog.py`、`rule_application_dialog.py`、`gui/wizard.py`：删除重复引导，保留表单字段与输入错误；必要规则与作用范围说明移入相关控件 tooltip。

## C. 验证与发布

- [x] 更新仅因显示约定过时的现有断言，回归全部分类、设置、目标、报告和时间轴测试。
- [x] 全量 pytest、compileall、GUI smoke、Ruff F821/E9、diff --check；关键页面在两种分辨率、三档 DPI、明暗主题下隔离截图检查，确认删除标签后不留空白占位。
- [x] 写实际验收结果、独立只读复核、提交说明并合入本地；安全打包替换重启并保留上版程序。未经新指示不 push。
