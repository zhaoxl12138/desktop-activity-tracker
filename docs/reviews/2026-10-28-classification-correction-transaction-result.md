# 2026-10-28 人工分类纠错事务化验收

## 问题与根因

- 现象：在“人工纠错”中把 `Probably Stolen.exe / Probably Stolen` 从“其他”改为“娱乐休闲”后，今日统计仍保留在“其他”。
- 根因：旧流程只保存 `manual_decisions.json` 与标题模式，明确只影响后续采样；已经写入 SQLite 的当天会话不会被修正，本地进程规则也不会自动生成。
- 修复边界：仅修正当天、同进程、同规范化标题的历史会话；不改计时字段，不跨日，不模糊匹配。普通桌面应用写入进程规则，共享浏览器只保存标题规则。

## 实现

- `ff93091 feat: make manual classification correction immediate`
  - 新增事务化纠错服务。
  - 更新分类字段后校验 `duration/effective/engaged/passive/idle` 五项守恒。
  - 保存人工决策、标题模式、进程规则及无标题审计记录。
  - 状态写入失败时补偿恢复数据库与规则。
- `2293595 ui: refresh statistics after manual correction`
  - 实时监控页接入纠错服务并发出历史分类变更信号。
  - 主窗口失效首页、软件、分类统计缓存；本地规则页在无未保存草稿时同步刷新。
- `5c8d481 fix: make process rule correction idempotent`
  - 修复重复执行时目标规则被先删后加、误报 `rule_changed=true` 的问题。
- `30c747b ui: explain immediate correction scope`
  - 更新界面提示，明确当天历史同步修正及普通应用/浏览器的规则差异。

## TDD 与自动化验证

- 新增 `tests/test_classification_correction_service.py`，覆盖：
  - 当天精确匹配、跨日隔离、同进程不同标题隔离。
  - 五项时间守恒。
  - 普通应用进程规则迁移、共享浏览器不写进程规则。
  - 状态保存失败的补偿恢复。
  - 重复执行幂等。
- 相关 GUI 测试覆盖即时刷新信号、成功提示及旧测试壳兼容。
- 最终验证命令与结果在本文件提交前重新执行：
  - `python -m pytest -q`：`1346 passed in 39.53s`。
  - `python -m compileall -q src tests`：退出码 0。
  - `python tests/test_gui_smoke.py`：`GUI smoke test passed`。
  - `git diff --check`：退出码 0。

## 真实数据验收

- 操作前备份：`data/backups/usage-before-manual-correction-20261028-171308.db`
- 备份与当前数据库 `PRAGMA quick_check` 均为 `ok`。
- 修正结果：6 条会话、2319 秒，从 `other` 改为 `gaming / 游戏娱乐`。
- 时间守恒：`duration=2319`、`effective=2319`、`engaged=2319`、`passive=0`、`idle=0`。
- 规则结果：`Probably Stolen.exe` 只存在于 `gaming` 规则，不存在于其他分类。
- 首次执行审计：`data/logs/classification-correction-20261028-171331-374995.json`。
- 幂等验证审计：`data/logs/classification-correction-20261028-171449-033897.json`，结果为 `updated_sessions=0`、`rule_changed=false`。

## 发布与回退

- 发布前阶段构建、Qt smoke 与凭据 smoke 均通过。
- 新程序：`release/DayLens.exe`
  - SHA-256：`6EF39D8B616BC7DFC461BC9FDC31B387F285268D6FAACBAE893E92AAC80028C7`
- 上一版回退：`release_previous/DayLens.exe`
  - SHA-256：`11293DB2402AA056741B1A9A7D3B97F2540E3CBA3F633C6DF2D92DF98B3957C6`
- 更早归档：`release_previous_20261028_before_correction_transaction/DayLens.exe`
  - SHA-256：`8F7F1663E005D19BF893E8230F6E33A5CE27D9D7A3D75F5AD075FDD4E8EB701C`
- 发布后进程：PID 51524，主窗口标题 `DayLens`，窗口可见且响应正常。
- 运行态：`data/logs/runtime-state.json` 持续更新，状态为 `running`；界面显示“记录中”。

## 数据安全结论

- 没有迁移数据库或新增表。
- 没有改写历史计时值，只更新限定范围内的分类字段。
- 备份、审计及上一版程序均可用于核查和回退。
