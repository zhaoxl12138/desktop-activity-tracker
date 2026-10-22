# DayLens V1.7 每日目标与偏差验收记录

## 范围与基线

- 依据 `docs/DayLens_AI_升级开发需求_交付Codex.md` 的 V1.7 四条要求；实现方案见 `docs/superpowers/specs/2026-10-22-daily-goals-v17-design.md`。
- V1.6 本地工作区基线为 1037 passed；本期未提交、推送或替换运行版。
- 每日目标为用户明确输入，不把既有“智能目标”预测当成承诺；只统计可信主动参与，不改原计时/分类、会话库、AI 设置或历史报告。

## 分阶段实现与实测

| 阶段 | 结果 | 验证 |
| --- | --- | --- |
| 目标状态 | `GoalStore` 在规范 intelligence 目录保存版本化 JSON，限制每日最多 3 项，使用文件锁、修订号、原子替换与恢复日志；成果支持确认/撤销 | `tests/test_daily_goal_service.py` 红绿测试 |
| 可信投入 | `attention-v1` 会话校验、稳定 ID 去重；类别目标按主动参与，任务目标只用人工明确归属；相关记录混有旧版或异常时隐藏部分投入与偏差；缺数据与有记录的零投入分开 | 同上，含旧版/损坏/重复会话样本 |
| GUI | 首页“今日计划”卡、统计页“目标”标签、日期切换、增删改、成果确认；保存冲突或损坏文件不覆盖 | `tests/test_daily_goal_gui.py` 与 GUI smoke |
| 周报 | 原周报追加逐项“计划 / 投入 / 已确认成果”；无会话也能呈现计划和用户确认，不跨目标相加 | `tests/test_weekly_goals_report.py` |
| 全量 | `python -m pytest -q` | **1060 passed in 23.71s** |
| 编译 | `python -m compileall -q src/daylens` | 退出码 0 |
| GUI | `python tests/test_gui_smoke.py` | `GUI smoke test passed`，包含 1280×720 和目标页入口 |
| 发布版 | `python tools/build_release.py --stage-only` | 退出码 0，输出 `Validated staging release prepared at: D:\OfficeSoftware\DayLens\release_staging`；不停止或替换运行版 |

额外以 `QT_SCALE_FACTOR=1.25` 和 `1.5` 分别运行 GUI smoke，均输出 `GUI smoke test passed`。`git diff --check` 退出码 0；仅有仓库工作区的 LF/CRLF 提示。

独立审查发现并补测：目标读取失败导致反复刷新、重复/缺 ID 会话误报可信 0、成果改名继承旧确认、周报缺偏差与数据库错误降级、非法娱乐分类目标、跨日旧任务可选及任务纠正后目标未刷新。新增回归使定向测试达到 **23 passed**。高 DPI GUI smoke 必须串行运行；曾并发触发测试之间争用同一配置备份文件，串行重跑 1.25/1.5 均通过。这属于测试执行隔离注意事项，不是业务断言失败。

验证使用 pytest 临时目录和合成会话；没有对真实数据库写入，也未发送云端 AI 请求。目标文件损坏时保留原件、界面显示不可用；旧周报统计仍可生成。回退程序不需数据库迁移或回滚；仅新目标派生 JSON 会保留供之后恢复。

## 明确限制

- V1.7 成果证据只有“用户确认”。Git/Obsidian 自动取证属于正式需求中独立的 P2 后续工作，本期不读取代码或笔记内容。
- 本期周报不会自动重写历史文件；重新生成对应周报后才出现新增小节。
- 任务目标必须先有 V1.6 人工确认的会话归属；无法验证的目标显示“证据不足/未确认任务”，不自动补零或根据同名标题推断。
- 目标允许事后编辑，因此周报中的“计划”是用户当前保存的自述计划，不是不可篡改的事前承诺；本期不据此推断执行纪律。
