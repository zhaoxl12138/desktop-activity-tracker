# 工作节奏卡片坐标与显示优化验收

## 改动

- `dashboard_widgets.py`：柱、日期、柱顶时长、点击使用同一日期格。旧代码日期采用端点坐标、柱采用格中心坐标，已用失败回归复现差异。
- 保留零和缺记录原位置；零显示细实线、缺记录显示空心虚线；今天使用快照日期描边并突出日期，不改变数值。
- 坐标文字、柱顶时长改为11px；提高轴字对比度，减淡网格；为日期与摘要增加留白。共享渲染器同时检查今日曲线和近30天，保持曲线端点坐标、30天稀疏标签与柱中心对应。
- 新增 `tests/test_rhythm_chart_layout.py` 和合成截图工具 `tools/check_rhythm_card_layout.py`；更新原全天弹窗测试的点击坐标。
- 未修改数据库、计时、分类、AI、统计服务及娱乐卡片；未提交或push。

## 实际验证

- 定向：`python -m pytest -q tests/test_rhythm_chart_layout.py tests/test_dashboard_widgets.py tests/test_day_activity_gui.py tests/test_dashboard_service.py` → **150 passed in 2.70s**。
- 标准缩放全量：`QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=1 python -m pytest -q` → **1212 passed in 30.16s**。
- `python -m compileall -q src/daylens` → 通过。
- `git diff --check` → 通过（仅有仓库既有CRLF提示）。
- `python tests/test_gui_smoke.py`：100%、125%、150%分别通过，使用隔离临时目录。
- `python tools/check_rhythm_card_layout.py`：深浅主题×1280×720/1920×1080×100%/125%/150%×今日/近7天/近30天，共36张合成截图及几何断言通过。截图位于 `tmp/rhythm-card-layout/`。offscreen须显式注册微软雅黑才能正确渲染中文；工具已处理。
- 人工检查：150%窄屏深色与100%宽屏浅色截图，10/26无截断，柱与日期居中，日期与摘要不重叠。

## 已知边界

- 将整套旧测试直接放在150%下运行得到1211通过、1失败：`test_work_episode_widget_keeps_distinct_multi_app_chain` 在旧工作片段控件默认宽度下实际发生省略，而测试要求未省略全文。本次未改动该控件，不扩大到这项无关修复。标准缩放全量与三档GUI smoke均通过；不宣称全量测试三档均通过。
- 截图使用合成数据，不是用户实际10/26时长；未读取真实数据库进行视觉测试。

## 独立审查与发布

- 独立只读审查：无Critical/Important问题；独立运行9项新测试通过。微软雅黑实际测宽：最窄支持卡片386px对应每格41.71px，最长每日标签`23h59m`为41px、日期`10/26`为29px。
- `python tools/build_release.py --stage-only` → exit 0；打包内Qt与凭据隔离smoke通过。
- 经应用维护接口安全退出旧进程（确认clean），归档原回退程序至 `release_previous_20261026_before_rhythm_alignment`，原子替换并启动新发布版。
- 新程序 `release/DayLens.exe`：PID 63904；唯一DayLens进程、Responding=true、runtime状态running（初次检查phase=startup）。发布文件哈希与本次dist构建一致：`4B3B5DF1FA16F7CF2371CD165FFE4EA321A10A7698AF38A53C5D55BBDC24E66D`。
- 本次直接回退程序保留在 `release_previous/DayLens.exe`，哈希 `27515C246DDF622D1D1BE10E1617362EC0F381E6C2A33A6FF3B2BDAD6F9E0DFD`。未删除用户数据或任何旧程序备份。
