# DayLens V1.6 任务链实施与验收记录

## 基线与范围

- 开发起点：本地及 GitHub `main` 均为 `68081a2`；正式需求保存为 `docs/DayLens_AI_升级开发需求_交付Codex.md`。
- 变更前 `python -m pytest -q`：1001 passed；`python -m compileall -q src/daylens`：通过。
- 变更前独立 GUI smoke 的“今日状态提示默认可见”断言与当时的产品行为冲突；已按现行行为改为默认隐藏，随后 GUI smoke 通过。
- 本期仅实现 V1.6 任务识别、任务级切换/插入观察、人工纠错、可选云端建议；未实施 V1.7～V2.0，未变更原计时、分类、报表或 SQLite 结构。

## 分阶段结果

| 阶段 | 实施与保护点 | 验证 |
| --- | --- | --- |
| A | 保存正式需求和设计，修正过期 GUI smoke 断言 | 基线 1001 passed、编译通过；修正后 GUI smoke 通过 |
| B | 一次性只读会话查询；严格版本/异常校验；去重；本地任务候选与独立任务事件 | `tests/test_task_grouping_service.py`、`tests/test_task_insights_service.py`、全量测试 |
| C | 人工确认/改名/拆分/合并/移动/忽略/撤销；锁、原子替换、恢复日志、修订号 | `tests/test_task_decision_service.py`、GUI 纠错模拟测试 |
| D | 双独立开关默认关；每批实际载荷预览确认；脱敏、预算幂等与每日两批；AI 任务命名及候选间关联仅作建议；坏结果与离线降级 | `tests/test_task_intelligence_service.py`、预算/客户端/设置测试 |
| E | 首页任务卡与统计页任务链标签；不替换旧“明显中断” | GUI smoke、`tests/test_task_chain_gui.py` |
| F | 回退/全量验收 | 见下方命令记录 |

## 最终本地验证

- `python -m pytest -q`：**1037 passed in 25.93s**（最后一次，含隐私路径、任务卡状态、AI 候选关联白名单，以及损坏会话不能跨越合并、同窗口续段不算切换测试）。
- `python -m compileall -q src/daylens`：退出码 0。
- `python tests/test_gui_smoke.py`：`GUI smoke test passed`。
- `git diff --check`：退出码 0；仅有工作区 LF/CRLF 提示。
- `python tools/build_release.py --stage-only`：退出码 0，输出 `Validated staging release prepared at: D:\OfficeSoftware\DayLens\release_staging`；只验证暂存包，没有停止或覆盖当前发布版。

测试使用固定合成会话和 pytest 临时目录；没有重置或修改真实用户数据库，没有发送真实 DeepSeek 请求。云端建议测试使用假 provider。正式发布替换未执行。

最终审查中发现并修复：损坏会话原本可能被任务链跳过，导致两侧工作误合并；同一窗口同一标题的续段原本可能被误称为工具切换。两项均先加入失败回归测试，再修正并复测。独立审查代理因账号额度限制未能返回意见，改由主执行者逐项核对关键路径；因此不将独立审查列为通过项。

## 已知边界与回退

- 默认关闭本地任务分析和云端任务建议。只要关闭这两个开关，旧采样、统计、分类与报表仍按原路径运行。
- 人工纠错只保存会话引用和任务名于 `AppPaths.intelligence_dir` 的派生 JSON；原始会话及历史报告不回写。升级失败时无需回滚数据库。
- 任务归属与返回任务是有证据、可纠正的分析建议，不表示成果完成或认知恢复成本。插入的经过时间不等于有效分心时间；原“明显中断”指标保持原口径。
- 云端只在用户检查每批脱敏内容并确认后发送。关闭、无密钥、离线、超时、预算不足、坏 JSON 或文件损坏均不会影响原生记录；不确定请求的预算保守占用以防重复收费。
