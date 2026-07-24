# DayLens 历史数据修复与日报补齐设计

## 目标

本批次解决三项问题：

1. 安全修复旧版娱乐挂机逻辑产生的高置信度历史异常数据。
2. 软件统计按“进程 + 标题 + 分类”显示真实分类。
3. 启动时自动补齐数据库中有记录、但日报文件缺失的日期。

## 历史数据自动修复

### 自动修复范围

只自动处理同时满足以下条件的 Session：

- `switch_reason = 'entertainment_idle'`
- `idle_seconds > 0`
- `effective_seconds + idle_seconds > duration_seconds + 1`
- 超出部分为旧版挂机回退造成的重复计时

修复结果必须满足：

- `duration_seconds >= 0`
- `effective_seconds >= 0`
- `idle_seconds >= 0`
- `effective_seconds + idle_seconds <= duration_seconds + 1`

对当前数据库中已确认的旧异常，修复方式是把重复计入的 `idle_seconds` 清零，保留原有 `duration_seconds` 和 `effective_seconds`。不修改 Session 的开始时间、结束时间、进程、标题、分类和切换原因。

### 自动执行条件

- 在数据库初始化和迁移完成后执行。
- 使用 `schema_meta` 中独立版本键记录是否已执行。
- 同一个数据库只自动执行一次。
- 没有匹配记录时仍写入完成标记，避免每次启动重复扫描。

### 备份与事务

修复前创建数据库备份，包含：

- `usage.db`
- 存在时的 `usage.db-wal`
- 存在时的 `usage.db-shm`

备份文件放在数据库同目录的 `backups` 子目录，文件名包含时间戳和用途，例如：

`usage.20260724-123000.before-session-repair.db`

执行顺序：

1. 对当前 WAL 执行安全 checkpoint。
2. 使用 SQLite backup API 生成一致性主库备份。
3. 复制仍存在的 WAL/SHM 作为附加恢复材料。
4. 开启事务。
5. 执行修复并校验影响行。
6. 写入迁移完成标记。
7. 提交事务。

备份失败、SQL 失败或校验失败时回滚事务，不写完成标记。

## 手动“预览并修复”

设置页面的数据质量功能扩展为两阶段操作：

1. 先检查并显示：
   - 检查 Session 数
   - 可自动修复数量
   - 其他异常数量
   - 涉及日期
   - 预计减少的重复空闲秒数
2. 用户点击确认后：
   - 再生成一次带时间戳备份
   - 在事务内修复高置信度记录
   - 重新运行数据质量检查
   - 显示修复前后结果和备份路径

不能明确判断的负数、时间倒序、重复 Session ID 等问题只列出，不自动修改。

## 软件统计分类

当前软件统计先按标题聚合，再从进程的主分类推断标题分类，会导致 Chrome 的所有标题显示为同一个分类。

调整查询结果，使 `by_app_detail` 返回：

- `process_name`
- `window_title`
- `category_key`
- `category_name`
- `effective_seconds`

SQL 按 `process_name, normalized_title, category_key, category_name` 聚合。软件统计服务直接使用该行携带的分类，不再遍历 `by_app` 猜测。

旧 `activity_logs` 回退查询使用相同字段和分组语义。

## 缺失日报自动补齐

### 日期来源

从数据库读取所有存在 Session 或旧 activity log 的日期，按照日期升序处理。

### 补齐规则

- 使用现有 `daily_report_path()` 计算嵌套路径。
- 文件已存在时跳过，不覆盖历史日报。
- 文件缺失时调用现有 Markdown 导出器生成。
- 当天文件交给现有每小时刷新机制，不在补齐任务中重复生成。
- 单个日期失败不阻止其他日期继续补齐。

### 启动时机与界面响应

补齐任务在后台线程执行，避免启动和主页卡顿。应用启动约 15 秒后触发一次；同一次运行不重复扫描。

配置 Obsidian 输出目录时，只同步本次新生成的文件。

任务完成后记录生成数量和失败日期；失败只写日志，不中断记录 Worker。

## 测试

新增回归测试覆盖：

- 只识别并修复高置信度 `entertainment_idle` 异常。
- 备份失败时不修改数据库。
- 自动迁移只执行一次。
- 手动预览统计可修复数量、日期和影响秒数。
- 软件统计为同一浏览器的不同标题保留各自分类。
- 日报补齐只生成缺失日期且跳过当天。
- 单日报生成失败时继续处理其他日期。

完成后运行完整测试、数据质量检查、临时数据库修复演练、Release 打包和 DayLens 重启。

