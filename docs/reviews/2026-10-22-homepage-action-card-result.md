# 首页“今日行动”合并卡验证记录（2026-10-22）

## 范围

按 A 方案，将首页单独的“今日计划”和“任务洞察”合为一张紧凑的“今日行动”卡；分别保留“查看目标”和“查看任务”入口。仅调整首页展示和导航，不修改数据表、统计口径、AI 请求或报告。

## 实际验证

- 修改前基线：`python -m pytest -q`，1060 passed。
- 定向测试：`python -m pytest -q tests/test_today_action_card.py tests/test_stage_c_shell.py`，13 passed。
- 全量测试：`python -m pytest -q`，1064 passed in 24.68s。
- `python -m compileall -q src/daylens`，退出码 0。
- `python tests/test_gui_smoke.py`：正常比例、`QT_SCALE_FACTOR=1.25`、`1.5` 顺序运行，均通过。
- Qt 离屏布局测量：宽布局卡片 `sizeHint()` 高度 89px；窄布局 161px，内部两项纵向排列。
- `python tools/build_release.py --stage-only`：退出码 0，暂存版验证完成，路径 `D:\OfficeSoftware\DayLens\release_staging`。
- `git diff --check`：退出码 0；仅有既存 LF/CRLF 提示。
- 启动 `release_staging\DayLens.exe` 后，桌面控件树确认首页只有一张“今日行动”卡，其中有“今日计划”“任务洞察”两行和各自的详情按钮。
- 复核后将悬停提示改为完整摘要；重新验证：定向测试 4 passed、全量测试 1064 passed in 24.56s、`compileall` 与 GUI smoke 均通过，并重新构建暂存版。
- 最终暂存版再次启动成功；系统进程列表仅有一个 DayLens 进程，路径为 `D:\OfficeSoftware\DayLens\release_staging\DayLens.exe`。桌面控件树再次确认“今日行动”、两项摘要及两个入口存在。桌面截图接口超时，且入口位于当前不可点击区域，因此实际鼠标跳转未验证；路由由 GUI smoke 覆盖。

## 发布与回退

当前改动仍在带有 V1.6/V1.7 其他未提交工作的 `main` 工作目录；未替换正式 `release`，未推送。若需撤销本轮布局，只需回退首页卡片及其导航接线，不涉及原始数据库或历史数据回滚。
