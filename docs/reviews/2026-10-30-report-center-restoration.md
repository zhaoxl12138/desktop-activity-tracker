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

## 独立复核

只读复核实际差异并独立运行报告页及报告 V2 测试：39 passed。未发现 Critical／Important 问题，同意合入。指出 README 仍提到“预览区分证据”的一处旧说明，已改为保留 AI 汇总和证据身份，不再宣称存在预览入口。

## 本地发布

- `ca43b44` 实现回退，`003785b` 补齐文档，已快进合入本地 `main`；未自动 push。
- 合入后的报告相关测试 39 passed in 2.58s。
- 正式重启后主目录全量回归：1424 passed in 45.68s。
- `python tools/build_release.py` 退出码 0，打包 Qt／凭据 smoke 通过；旧实例 PID 72176 在 18:41:54 确认 `status=clean`、退出码 0，没有强制结束。
- 正式程序 `D:\OfficeSoftware\DayLens\release\DayLens.exe` 的 SHA256 为 `EBD7B9EC91F80E6B81375FCC6F5818D09C51FD7084278672F62B068A7B92796E`，与 `dist` 一致。
- 上版完整保留于 `release_previous`（SHA256 `F40F1CD7A2137E3F0DBAA4398C576291D992E949BFB39C5385110525159EF858`）；更早回退版本移存 `release_previous_20261030_before_report_center_restore`，未删除。
- 2026-10-30 18:42:05 启动正式版；单实例 PID 72564，窗口标题 `DayLens`、非零主窗口句柄、`Responding=true`。真实窗口未做额外点选验证，界面视觉依据为上述隔离截图与布局检查。
- 18:43:05 运行心跳更新为 `phase=running`，18:43:20 再核对进程仍响应。
