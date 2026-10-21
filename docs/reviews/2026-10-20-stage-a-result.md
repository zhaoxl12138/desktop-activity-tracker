# 阶段 A 交付记录

日期：2026-10-20。代码基线：c69172f。范围仅限可靠性，不改数据库结构、参与阈值、播放器检测和历史会话。

## 实现

- AI 分类当前项、同应用上下文和报告事实经过统一隐私过滤；发送前复核最新设置。无法证明符合当前隐私规则的旧摘要不继续发送。
- 分类 JSON 状态使用进程内锁、操作系统文件锁、递增 revision 和可重放事务日志。命中次数采用增量写入；忽略项留下有界标记，防止迟到任务复活。
- 人工模式停用/删除同步停用显式关联的精确决定；保存状态与采集线程应用状态分开，可重试应用。
- 纠错绑定稳定样本副本，刷新不会将修改目标移到别的标题。
- 普通定时刷新只合并待刷新请求，不使当前慢查询失效；日期和配置变化单独失效。
- 发布先隔离构建和 smoke，再通过 maintenance-exit 安全退出，确认 clean 后替换；没有强制终止运行进程。

## 验证

- 全量 pytest：953 passed（18.16s）。
- 新增 14 项阶段 A 回归，覆盖隐私变化、旧摘要、命中覆盖、迟到队列、停用关联、固定选择、慢查询、上下文失效、中断恢复及线程/进程并发。
- `python tests/test_gui_smoke.py`：通过。
- 源码和打包版隔离弹窗 smoke：插入新记录后保存原选中标题，再修改模式分类并检查持久化；通过。测试使用临时目录，不更改真实纠错数据。
- 发布版 Qt 和 Windows 凭据 smoke：通过。
- compileall、git diff --check：通过（Git 的 LF/CRLF 提示不属于检查失败）。
- 原数据库只读 `PRAGMA quick_check`：ok。

## 发布和恢复

- 唯一运行程序：`D:/OfficeSoftware/DayLens/release/DayLens.exe`。
- 原数据库：`D:/OfficeSoftware/DayLens/data/usage.db`，未迁移或回滚历史数据。
- 旧程序保留在 `D:/OfficeSoftware/DayLens/release_previous`。
- 一致性数据库备份、分类状态、配置、报告清单和校验值：`D:/OfficeSoftware/DayLens/data/backups/20261020-stage-a`。
- 原有无关的 today_overview 和图标测试改动保留，没有混入本次修改范围。

自动测试不等同于全部真实 DPI/交互场景验收；本次未声称完成 B/C/D 或新计量算法验证。
