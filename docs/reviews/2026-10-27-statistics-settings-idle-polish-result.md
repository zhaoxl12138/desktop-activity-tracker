# 2026-10-27 数据统计、规则、桌面空闲和界面验收记录

## 范围

按已批准的七项改动实施：工作节奏纵轴间距；数据统计默认实时监控及分类时段汇总；娱乐规则名称与保存入口；设置页布局和月度 AI 费用；仅 Explorer 桌面/任务栏即时空闲；全天详情列宽和分类筛选；移除首页“生成日报”按钮并规范记录状态字重。保留历史会话、原计时策略、报告中心和自动报告。未提交或推送 Git。

## 测试与界面检查

- 新测试遵循先失败、再修复的步骤：桌面空闲 12 个预期失败场景、全天详情 3 个初始预期失败场景，以及首页 3 个预期失败场景，修复后均通过。规则保存另覆盖“改后还原不写库”和 `inherit` 原始标题关键词不被覆写。
- 最终 `python -m pytest -q`：**1318 passed in 41.77s**。
- `python -m compileall -q src/daylens`：exit 0；`git diff --check`：exit 0（仅原有 LF/CRLF 提示）。
- `python tests/test_gui_smoke.py`：`GUI smoke test passed`。该文件是手动 smoke 脚本，不能用 pytest 收集；`pytest -q tests/test_gui_smoke.py` 会显示“no tests ran”。
- `tools/check_settings_rhythm_layout.py` 和 `tools/check_day_activity_layout.py` 在隔离数据下完成 1280×720、1920×1080，100%／125%／150%，深浅主题截图检查。实际复看了 150% 的设置页顶部/底部、趋势图和分类筛选全天详情，没有发现文字或边框重叠。截图保存在 `tmp/settings-rhythm-layout/`、`tmp/day-activity-fit-range-layout/`。
- 发布包 `python tools/build_release.py --stage-only`：exit 0，内置 Qt 与 Windows 凭据隔离 smoke 均通过。

## 数据保护与发布

- 规范数据库：`D:\OfficeSoftware\DayLens\data\usage.db`。变更前 SQLite 备份为 `D:\OfficeSoftware\DayLens\data\backups\usage.20261027-135803-172781.before-entertainment-labels-20261027.db`。备份与原库均通过 `PRAGMA integrity_check`，备份时两者各有 28,041 条历史会话。
- 在旧程序安全退出并确认 `runtime-state.json` 为 `clean` 后，单事务且带旧名称/计时策略条件地更新 `custom_rules` 中两行：`gaming`→“游戏娱乐”，`video`→“视频娱乐”。每行恰好命中 1 条；更新时历史会话行数保持不变。其余规则、会话、报告未改。
- 旧 `release_previous/` 已移动保留在 `release_previous_20261027_before_seven_changes/`；刚替换下来的旧程序保留在 `release_previous/`。新程序位于 `release/`，SHA-256 `668A52374F065078C5C8B106AAFE28D2B57096ADE3D0A879042B32F1738402C8`；上一版 SHA-256 `0392DAAFE6CCFEE9B651FF0814FC1867880A117CCF165A5F20FC41E45194458B`。
- 使用正常窗口模式启动新 `release/DayLens.exe`，唯一进程 PID 56824，窗口句柄 6294918，`IsWindowVisible=True`、`IsIconic=False`、`Responding=True`。14:01 的运行状态为 `running`，实时监控的最后采样时间持续更新。实际可访问性树确认顶部没有“生成日报”，只有“暂停记录”和“记录中”。

## 保留的轻微边界

- 分类范围明细展开后，每 30 秒会在后台重读/聚合所选范围；不会阻塞界面，但在长范围上仍有重复计算空间。
- Windows `GetClassName` 或进程名读取失败时，不猜测 Explorer 窗口为桌面，沿用原分类；这是保守降级。
- 真实窗口的截图通道偶发超时；窗口可见性、可访问性树、最新采样和运行心跳均分别核验成功。无自动 Git 提交或推送。
- 全天详情的独立代理复核遇到工具用量限制；主代理直接复查了筛选/时间轴代码、52 项定向测试与 150% 筛选截图，没有发现阻断发布的问题。
