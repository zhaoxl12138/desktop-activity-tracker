# 2026-10-28 规则管理有效规则与分类分组验收

## 改动结果

- 分类列表改为两级分组：工作学习、娱乐休闲、社交通讯、投资理财、系统与兜底，以及按需出现的自定义分组。
- 分组标题不可选择；分类仍使用原始分类键，`gaming` 与 `video` 的计时策略没有合并。
- 应用列表默认只展示最近30天实际出现或由人工/AI学习的应用。
- 未使用的工厂候选不删除，仍保存在高级设置和内置识别库中，首次出现时仍可本地识别。
- 分类项显示有效应用数；详情显示30天命中次数、有效秒数和隐藏候选数量。
- 应用工具提示显示来源、命中次数、有效秒数和最近出现日期。

## 实现提交

- `0b2ef2b feat: derive active rule usage snapshot`
  - 新增只读规则使用快照，支持大小写去重、30天统计、空库与查询失败降级。
- `75f1603 ui: group rule categories by purpose`
  - 左侧分类列表增加稳定分组标题，并保持原编辑及草稿保护流程。
- `e141893 ui: show active and learned rule applications`
  - 主应用列表过滤未使用候选，保留完整高级规则及所有保存能力。

## 真实数据检查

- 原始规则进程名：417条；按大小写折叠后为395条。
- 默认主要列表：39条有效或学习规则。
- 隐藏但保留：356条未使用候选。
- 快照查询10次：中位数5.667毫秒，最大6.152毫秒。
- `PRAGMA quick_check`：`ok`。
- 未修改 `activity_sessions` 或 `custom_rules` 数据。

## 自动化验证

- TDD 定向测试：规则使用快照、分类分组、应用过滤、完整高级规则保留和Windows连接关闭均覆盖。
- `python -m pytest -q`：`1363 passed in 41.19s`。
- `python -m compileall -q src tests`：退出码0。
- `python tests/test_gui_smoke.py`：`GUI smoke test passed`。
- `git diff --check`：退出码0。
- `python tools/build_release.py --stage-only`：发布构建与阶段验证通过。
- 真实配置GUI检查：分组顺序、不可选标题、分类计数、默认选择和应用摘要均正确。

## 发布与回退

- 当前程序：`release/DayLens.exe`
  - SHA-256：`5F4D959F69ACA33912FD487DEF5DCDBDDAAA7C9981DE76EAB4C8F36109571E08`
- 上一版：`release_previous/DayLens.exe`
  - SHA-256：`055F26F07D3FF214D928715A0ADBC151A671749177124F9F0FAB4FD33AA02AD0`
- 更早版本归档：`release_previous_archive_20261028-232428/`。
- 新进程PID 63684，来自规范发布目录，窗口首次启动可见、响应正常，界面显示“记录中”。

## 安全结论

- 本次是只读派生统计与界面优化，没有删除规则、迁移数据库或重算历史。
- 查询失败会降级显示完整规则，不影响保存、分类和记录线程。
- 关闭或回退程序无需回滚数据库。
