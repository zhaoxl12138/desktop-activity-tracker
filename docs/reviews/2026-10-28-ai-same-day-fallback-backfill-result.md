# 2026-10-28 AI 高置信分类即时回填验收

## 问题与根因

- 现象：`Hades2.exe / Hades II` 的较早会话仍显示为“其他”，后续会话已由 AI 判为“游戏娱乐”；本地规则管理中也没有 `Hades2.exe`。
- 根因：原 AI 分类只影响取得结果后的新采样，不会修正当天同标题的旧兜底会话，也不会把普通桌面应用的高置信结果提升为本地进程规则。
- 修复边界：仅处理当天、同进程、同规范化标题，且当前分类仍为 `other` 或 `browser_general` 的会话；人工分类优先，不跨日、不模糊匹配、不修改任何计时字段。

## 实现

- `f38255e feat: backfill high-confidence AI classifications`
  - 新增 AI 高置信分类回填服务、事务保护、时间守恒校验和无标题审计。
  - 普通桌面应用迁移到唯一的目标进程规则；共享浏览器不写进程规则。
- `4a0f693 feat: emit adopted AI classification events`
  - `SessionTracker` 只在“兜底分类 → AI 高置信非兜底分类”时发出一次可重试事件。
  - 中低置信、冲突、非法或未采用结果不会触发历史回填。
- `701ce0f feat: apply AI backfills during recording`
  - 记录线程接入回填服务并热重载分类器。
  - 统计缓存与分类管理页收到历史分类变更信号后同步刷新；失败仅降级，不中断记录。

## TDD 与自动化验证

- 新增 `tests/test_ai_classification_backfill_service.py`，覆盖精确范围、人工记录保护、跨日隔离、浏览器例外、规则唯一归属、事务回滚、幂等和时间守恒。
- 扩展追踪器、记录线程及主窗口测试，覆盖高置信事件、缓存命中、失败重试、分类器重载及避免重复重载。
- 实现完成后的验证结果：
  - `python -m pytest -q`：`1357 passed in 42.41s`。
  - `python -m compileall -q src tests`：退出码 0。
  - `python tests/test_gui_smoke.py`：`GUI smoke test passed`。
  - `python tools/build_release.py --stage-only`：阶段构建及发布 smoke 全部通过。
  - `git diff --check`：退出码 0。

## 真实数据验收

- 操作前备份：`data/backups/usage-before-ai-backfill-20261028-221300.db`。
- 备份与当前数据库 `PRAGMA quick_check` 均为 `ok`。
- 首次执行：当天 2 条旧兜底会话、93 秒从 `other` 改为 `gaming`；没有改动标题或时间字段。
- 最终结果：`Hades2.exe` 当天 7 条会话全部归入 `gaming`，有效活动合计 1998 秒；`duration=2000`、`engaged=1998`、`passive=0`、`idle=2`，回填前后守恒。
- 规则结果：`Hades2.exe` 只存在于 `gaming` 进程规则。
- 首次执行审计：`data/logs/ai-classification-backfill-20261028-221325-082694.json`。
- 幂等验证审计：`data/logs/ai-classification-backfill-20261028-221325-089735.json`，结果为 `updated_sessions=0`、`rule_changed=false`。

## 发布与回退

- 新程序：`release/DayLens.exe`
  - SHA-256：`055F26F07D3FF214D928715A0ADBC151A671749177124F9F0FAB4FD33AA02AD0`
- 上一版回退：`release_previous/DayLens.exe`
  - SHA-256：`6EF39D8B616BC7DFC461BC9FDC31B387F285268D6FAACBAE893E92AAC80028C7`
- 更早版本归档：`release_previous_archive_20261028-221521/`。
- 发布后进程：PID 35780，主窗口标题 `DayLens`，窗口首次启动即可见且响应正常。
- 运行态：界面显示“记录中”，分类统计中 `Hades2.exe` 已按统一的游戏分类计入。

## 数据安全结论

- 没有新增或迁移数据库表。
- 没有改变计时、有效性、主动、被动或空闲秒数。
- 人工分类不会被 AI 覆盖；浏览器不会被错误提升为整进程规则。
- 数据备份、无标题审计和上一版程序均可用于核查与回退。
