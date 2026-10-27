# 全天活动详情高空闲隐藏：验收记录

## 改动

- 仅在分类时间轴上隐藏明确空闲以及逐条记录 `idle_seconds / duration_seconds > 70%` 的会话；等于 70% 继续显示。
- 可见会话决定横轴范围；被隐藏会话仍保留在有效时长汇总与事件表。悬停和表格选中给出隐藏原因，不生成虚假的彩色高亮。
- 原始数据库、分类、计时、日／周／月报和只读活动服务未修改。

## 验证结果（2026-10-27）

- `python -m pytest -q tests/test_day_activity_category_timeline.py tests/test_day_activity_gui.py`：58 passed。
- `python -m pytest -q`：1324 passed。
- `python -m compileall -q src`：退出码 0。
- `python tests/test_gui_smoke.py`：`GUI smoke test passed`。
- `tools/check_day_activity_layout.py`：100%、125%、150% 均通过 1280×720、1920×1080 的深浅主题布局断言与截图捕获。
- 用真实数据库只读加载 2026-10-27：截图所指会话的有效 1 秒、空闲 25173 秒、总 25174 秒保持原值，时间轴判定隐藏且绘制矩形为空；全天有效总计仍来自原服务。
- `python tools/build_release.py --stage-only`：退出码 0，打包 Qt 与凭据隔离 smoke 通过。
- 当前 `release/DayLens.exe` 的 SHA-256 为 `C92E1E7964298A00668BF61D6F89E12AAFCB5BFB92D1A60376B3DED16C6FD6BB`；上一版保留于 `release_previous/`，更早一版保留于 `release_previous_20261027_before_idle_visibility/`。
- DayLens 经维护命令正常退出并由新发布包重启；唯一进程 PID 39072，窗口可见、未最小化、响应正常。重启后规范数据库会话结束时间持续更新，21:32 左右的读数落后当前时间约 5 秒。

## 说明

150% 的 Qt 离屏截图中，图下说明文字看起来接近最后一条轨道；独立读取控件几何时两者实际相隔 59 个逻辑像素。布局断言通过，但未在真实 150% Windows 桌面缩放下做肉眼复核，因此该截图现象不作为实体界面无重叠的证明。

工作目录在本次改动前已有大量未提交修改，且与本次触及的控件／测试文件重叠；本次未把这些文件整体提交或推送。
