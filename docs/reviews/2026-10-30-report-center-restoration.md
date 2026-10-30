# 报告中心界面恢复验收

基线：`5b3a4d5`。需求：用户确认恢复本次正文预览改版前的报告列表＋小详情侧栏，保留报告 V2 与后台生成。

## 修改范围

- `src/daylens/gui/pages/reports.py`：列表恢复主要宽度，小侧栏显示选中文件元信息和纵向下载／打开／同步按钮；移除嵌入正文预览、分栏拖动、窄屏正文切换及正文读取生命周期。
- 窄屏仍同时显示列表与操作，压缩侧栏元信息（文件名可通过提示查看），不再选择报告后隐藏列表。
- 后台生成、列表分页、多选下载、外部打开、Obsidian 同步和纳秒文件身份保持。
- README、页面回归测试及隔离布局工具同步更新。独立预览/证据工具及测试暂保留，报告中心不再构造或调用它们。
- 未修改报告 V2 渲染、统计、数据库、分类、AI 调度及历史报告；没有测试真实 API。

## 自动验证

- 基线相关测试：38 passed。
- 新需求先失败：3 failed, 13 passed（仍构造预览、生成提示仍指向预览）；修复后页面测试：17 passed。
- 全量 `python -m pytest -q`：1424 passed in 38.74s。
- `python -m compileall -q src tests tools`：退出码 0。
- `python tests/test_gui_smoke.py`：GUI smoke test passed。
- `python -m ruff check src/daylens --select F821,E9 --output-format concise`：All checks passed。
- `git diff --check`：通过。
- `tools/check_reports_v2_layout.py`：1280×720／1920×1080、100%／125%／150%、明暗主题，共 12 组通过；检查列表/操作同时可见、控件边界、页面尺寸，人工查看 150% 窄屏与 100% 宽屏截图。

测试使用隔离数据库与合成报告，不修改用户真实报告。
