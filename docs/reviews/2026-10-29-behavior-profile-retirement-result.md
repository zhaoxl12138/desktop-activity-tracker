# 本地行为画像前台下线验收记录

日期：2026-10-29

## 实际修改

- 报告中心删除“行为画像”按钮、打开方法和弹窗模块。
- 智能设置删除“本地行为画像”复选框；旧 `behavior_analysis_enabled` 值继续兼容读取，并在保存其他设置时原样保留。
- 日报、周报、月报的正常与数据不足分支全部停止附加画像诊断。
- 删除无运行时调用方的画像服务、已下线实验服务及其旧内部实现测试。
- README 删除当前功能说明；历史需求、设计和验收文档作为项目历史保留。
- 保留 `trusted_metrics_service.py`、报告证据指纹、统计可信度、跨周期比较和时间守恒逻辑。

没有修改 SQLite 会话、计时算法、分类规则、历史报告文件或 AI 智能汇总，也没有发起 API 请求。

## TDD 证据

新退役回归测试首次运行结果：`5 failed`。失败分别证明旧报告入口、旧设置开关、报告附加内容和残留模块仍然存在。

最小实现完成后，定向测试结果：`111 passed in 2.43s`。

## 完整验证

- 全量测试：`1381 passed in 47.72s`
- 编译检查：`python -m compileall -q src tests tools`，退出码 0
- GUI smoke：`GUI smoke test passed`
- 隔离发布构建：`python tools/build_release.py --stage-only`，退出码 0
- 发布包 Qt 与凭据 smoke 均通过，输出：`Validated staging release prepared`

## 依赖核对

- 运行时代码和 README 中已无 `BehaviorDialog`、`behavior_profile_service`、`behavior_experiment_service` 或画像入口引用。
- `behavior_analysis_enabled` 仅留在兼容设置读写与对应回归测试中，不再触发业务功能。
- `trusted_metrics_service` 仍由 exporter、dashboard 和 insights 服务使用，并保留原测试覆盖。

## 正式发布

- 主分支 fast-forward 至 `9c3c344` 后，使用维护退出和原子目录替换完成发布；没有强制终止记录进程。
- 上一回退版保留在 `release_previous`，更早回退版归档为 `release_previous_20261029_before_behavior_profile_retirement`。
- 正式版与构建产物 SHA-256 均为 `610FDF02F09B2D42CD20C327BF98B0B5423F3401E80C757008E2A075F5712FE4`。
- 新版唯一进程 PID `18604`，主窗口首次启动可见且响应正常。
