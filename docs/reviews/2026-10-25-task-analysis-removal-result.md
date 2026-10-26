# 任务分析功能下线验证结果

## 范围与保留项

- 移除统计页“任务链”标签、设置中心的本地任务分析和云端任务建议开关，以及 MainWindow 中任务分析/云端任务请求和结果分发。
- 统计页保留“软件、分类、目标与成果”，目标刷新不再触发任务分析。
- 行为画像不再调用任务归并，移除候选任务插入率、插入明细、同任务连续时长；保留普通工作参与、娱乐活动和连续工作片段。画像输出版本改为 `behavior-v2`。
- 依赖候选插入率的一周实验入口与新报告小节一并移除。旧 `behavior-v1` 实验文件可兼容读取，不接受新实验，也不查询会话生成新对照结论；保留显式停止旧记录的兼容接口。
- 旧任务归属供已有目标和报告读取；原始 SQLite 表、计量算法、分类、凭据、月预算和报告调度不改。没有删除派生数据、实验文件或历史报告，也未对真实数据库运行测试。
- 旧任务 UI/建议源模块保留用于回退，但应用不再导入它们；发布包归档检查确认无 task_chain_detail、task_intelligence_service、task_insights_service、task_insight_widgets、behavior_experiment_service 模块。任务模块中的共享可信会话校验仍供普通目标/画像使用，不执行任务归并。

## 测试过程与结果

| 检查 | 实际结果 |
| --- | --- |
| 原基线 `python -m pytest -q` | 1104 passed in 31.73s |
| 入口/设置先写回归测试 | 4 failed、1 passed，失败均为旧入口和旧任务队列行为 |
| 入口下线定向回归（含目标、报告和旧服务兼容） | 84 passed in 4.46s |
| 扩展行为指标下线先写测试 | 12 failed、8 passed，捕获任务归并、旧指标、实验和界面 |
| 扩展后的定向回归 | 78 passed in 8.01s |
| 最终 `python -m pytest -q` | 1110 passed in 27.73s |
| `python -m compileall -q src/daylens` | 退出码 0 |
| `python tests/test_gui_smoke.py` | 100%、125%、150% 缩放各一次，均输出 GUI smoke test passed |
| 窗口回归 | 测试覆盖 1280×720、1920×1080；GUI smoke 验证新统计标签和目标页导航 |
| `git diff --check` | 退出码 0；仅本机 Git 的 LF/CRLF 转换提示 |
| 独立只读代码审查 | 未发现 Critical、Important 或 Minor 问题 |

新增测试夹具最初混用了新旧包名的 DashboardSnapshot，类型检查忽略了快照。确认两者为不同类后统一为测试窗口的兼容包入口；未修改生产类型检查来迁就测试。

## 发布与真实状态检查

- `python tools/build_release.py --stage-only`：退出码 0，PyInstaller 构建、隔离 Qt 与凭据 smoke 完成。
- 核对显式绝对路径均位于工作区后，将原 `release_previous` 移至 `release_previous_20261025_task_retirement` 保存。使用已有 `_stop_running_gracefully` 安全退出旧 PID 58000，运行状态确认为 `clean`。
- 使用设置服务将两个旧任务开关保存为 False，断言其余 AI 偏好完全保持原值；未变更 API 密钥。
- 使用构建工具已有 `_publish_staging` 原子发布及快捷方式更新，启动规范 `release/DayLens.exe`。
- 发布后唯一进程 PID **21340**，响应正常；运行版与构建版 SHA-256 均为 `384D4014A15F54B7049F3BB0F2121B96380ABCB45BF1A8BD06AB04E5667B2B63`。
- 发布前后真实 `task_decisions.json` SHA-256 均为 `D23F0815308AB571F6EC5BF1C7350145CD383993C9F2DD4BB8F1CC7DCC5BDBEF`；`daily_goals_v1.json` 均为 `9C570E0BED899A71618BA7663011F11C4DE78DE6FE280631A762613F565E0C42`。现场无实验文件；实验保留与不重算由隔离回归测试验证。
- 历史日报补齐函数会跳过已存在文件；本次未触发历史重算。正常自动日报/报告调度继续保留。

## 回退与限制

刚替换的上版程序保存在 `release_previous`。程序回退不需要回滚数据库；旧任务开关已保存为关闭，不会因回退自动启用。

本次未提交或 push；已有其他未提交修改全部保留。先前反馈“时间偏少”的具体原因不在本次下线任务中，不能将功能移除视为已修复计时问题。
