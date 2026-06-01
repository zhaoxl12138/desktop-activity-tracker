# Desktop Activity Tracker 测试计划

## 文档信息

项目名称：Desktop Activity Tracker

版本：v0.1.0+

测试目标：验证桌面活动记录器核心功能是否正常运行。

---

# 1. 测试环境

操作系统：
- Windows 10
- Windows 11

Python：Python 3.10+

数据库：SQLite

GUI：PySide6

---

# 2. 测试范围

本次测试覆盖：
- 前台窗口检测
- 软件分类
- 活跃状态检测
- Session 记录
- SQLite 存储
- GUI 显示
- Markdown 日报
- CSV 导出
- 系统托盘
- 配置管理

---

# 3. 功能测试

---

## TC-001 启动程序

测试目标：验证程序正常启动。

步骤：
1. 双击启动 Desktop Activity Tracker
2. 等待主界面显示

预期结果：
- 程序正常启动
- 无异常报错
- GUI 显示正常
- 状态栏显示"记录中"

结果：`PASS / FAIL`

---

## TC-002 前台窗口检测

测试目标：验证当前窗口识别是否正常。

步骤：
1. 打开 Chrome
2. 打开 ChatGPT 页面
3. 切换到 Cursor
4. 切换到 Obsidian

预期结果：系统正确识别 chrome.exe / Cursor.exe / Obsidian.exe，窗口标题同步更新。

结果：`PASS / FAIL`

---

## TC-003 软件分类

测试目标：验证分类规则。

| 软件 | 预期分类 |
|---|---|
| ChatGPT | AI 工具 |
| Claude | AI 工具 |
| Cursor | 编程开发 |
| VSCode | 编程开发 |
| Obsidian | 阅读学习 |
| PDF | 阅读学习 |
| Bilibili | 视频娱乐 |
| 腾讯视频 | 视频娱乐 |

预期结果：分类正确。

结果：`PASS / FAIL`

---

## TC-004 活跃检测

测试目标：验证空闲检测。

步骤：
1. 打开 ChatGPT
2. 停止键盘鼠标操作
3. 等待超过 60 秒

预期结果：
- `is_user_active = false`
- `effective_seconds` 停止增长

结果：`PASS / FAIL`

---

## TC-005 视频挂机检测

测试目标：验证 `passive_allowed` 规则。

步骤：
1. 打开 B 站视频
2. 播放视频
3. 超过 60 秒不操作

预期结果：
- `duration_seconds` 增长
- `effective_seconds` 继续增长

结果：`PASS / FAIL`

---

## TC-006 Session 切换

测试目标：验证窗口切换逻辑。

步骤：ChatGPT → Cursor → Obsidian，每个窗口停留 30 秒。

预期结果：数据库产生 3 条 Session。

结果：`PASS / FAIL`

---

## TC-007 SQLite 写入

测试目标：验证数据库记录。

步骤：
1. 使用软件 5 分钟
2. 打开数据库

检查：`SELECT * FROM activity_sessions;`

预期结果：存在记录，字段完整。

结果：`PASS / FAIL`

---

## TC-008 程序异常退出

测试目标：验证数据保护。

步骤：
1. 正常记录
2. 点击关闭

预期结果：当前 Session 自动保存，数据库无损坏。

结果：`PASS / FAIL`

---

## TC-009 GUI 刷新

测试目标：验证首页统计刷新。

步骤：持续使用软件。

预期结果：首页数据实时更新 — 总时长 / 学习时长 / 娱乐时长 / 挂机时间。

结果：`PASS / FAIL`

---

## TC-010 生成日报

测试目标：验证 Markdown 报告生成。

步骤：点击「生成日报」。

预期结果：生成 `reports/daily/YYYY-MM-DD.md`，内容包含总时长 / 分类统计 / 软件排行 / 30 分钟时间线 / 专注时段 / 碎片化情况。

结果：`PASS / FAIL`

---

## TC-011 CSV 导出

测试目标：验证 CSV 导出。

步骤：点击「导出 CSV」。

预期结果：生成 `reports/YYYY-MM-DD.csv`。

结果：`PASS / FAIL`

---

## TC-012 配置加载

测试目标：验证配置文件读取。

步骤：修改 `config.yaml` 中 `sample_interval_seconds: 2`，重新启动。

预期结果：程序按新配置运行。

结果：`PASS / FAIL`

---

# 4. 性能测试

---

## PT-001 长时间运行

目标：连续运行 24 小时。

预期：不崩溃 / 不丢数据 / 内存稳定。

结果：`PASS / FAIL`

---

## PT-002 数据库增长

目标：连续使用 7 天。

检查：`usage.db` 大小。

预期：小于 100MB。

结果：`PASS / FAIL`

---

## PT-003 CPU 占用

目标：后台运行。

预期：CPU < 2%。

结果：`PASS / FAIL`

---

## PT-004 内存占用

目标：后台运行。

预期：RAM < 150MB。

结果：`PASS / FAIL`

---

# 5. 回归测试

每次发布新版本必须执行：

- 启动程序
- 前台窗口检测
- 软件分类
- Session 记录
- 数据库存储
- GUI 显示
- 日报生成

---

# 6. 发布验收标准

版本发布前必须满足：

- [ ] 程序可启动
- [ ] 数据可记录
- [ ] 分类正确
- [ ] GUI 正常
- [ ] 日报可生成
- [ ] 数据库正常
- [ ] 连续运行 8 小时无崩溃
- [ ] Git 提交完成
- [ ] CHANGELOG 已更新
- [ ] TODO 已更新

---

# 7. 测试记录模板

版本：`v0.x.x`

测试日期：`YYYY-MM-DD`

测试人：开发者

测试结果：

| 用例 | 结果 |
|---|---|
| TC-001 | PASS |
| TC-002 | PASS |
| TC-003 | PASS |
| TC-004 | PASS |

问题记录：

```
BUG-001
描述：
复现步骤：
影响：
修复版本：
```

最终结论：`通过发布` / `禁止发布`
