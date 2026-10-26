# 全天活动详情：全景与双轨放大 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development and test-driven-development. Follow the user-approved 24h overview + 4h detail design; do not reopen task analysis.

**Goal:** 让全天活动可框选、缩放与双向定位，同时保持已有计量真实性。

**Architecture:** 只复用现有只读 day_activity_service 结果。新增独立视口与绘图组件，弹窗统一管理日期、视口、筛选和选择。下轨使用整条会话累计比例，不提供伪造的精确参与位置。

**Tech Stack:** Python, PySide6/QPainter, pytest, isolated offscreen fixtures.

## 边界与基线

- 用户已批准方案，沿用当前 main，不创建分支、不提交/push，不覆盖之前未提交修改。
- 初始定向基线：`python -m pytest -q tests/test_day_activity_gui.py tests/test_day_activity_service.py` → 53 passed。
- 不改数据库、计时、分类、查询、AI、历史记录。小屏幕使用滚动，不能压缩成无法辨认的色带。

## Task 1 — 独立视口和绘图（新文件）

Files: `gui/widgets/day_activity_viewport.py`, `gui/widgets/day_activity_timeline.py`, `tests/test_day_activity_timeline.py`.

- [x] 先写失败测试并执行：视口初始4h，边界0–86400，最小30min，锚点缩放/平移/ensure-visible；像素聚合保留所有事件ID；比例与旧口径不造数。
- [x] 实现 ActivityViewport（QObject + changed(int,int)）和全日overview/局部detail QWidget。overview白框拖动/左右边缘拉伸/外部框选；局部滚轮与±缩放，鼠标锚点；上轨前台，下轨整会话累计比例。
- [x] 图块 event_activated(str)、aggregate_activated(object) 联动；聚合只影响绘制，保留来源ID，缺口/空闲/未来/异常不同样式。
- [x] 定向测试通过并自查，再独立规格和质量审查。

## Task 2 — 弹窗集成（现有文件）

Files: `gui/widgets/day_activity_dialog.py`, `gui/widgets/day_activity_event_model.py`, `tests/test_day_activity_gui.py`.

质量审查补充：密集数据下逐项构建QTableWidget导致拖动卡顿，改为QAbstractTableModel + QTableView按需取值；新增独立模型文件仅负责只读表格呈现，不改变记录或查询。20,000事件/10次平移真实弹窗回归先复现4.57秒，再修复。

- [x] 写失败测试并执行：默认4h，框选只改本地视口不读库，视口事件列表，短事件点击自动显示，日期刷新与后台安全，三项全天指标不随筛选变化。
- [x] 顶部日期/三指标；overview + 局部双轨 + 类别图例；表格显示与视口相交事件，>=300门槛按完整事件有效秒数；时间块和行双向选择。
- [x] 相同日期刷新保留视口，切日重置为首个长事件附近4h；数据状态按缺失/异常覆盖判断，不把无记录说成空闲。
- [x] 外层滚动，小窗口控件可达、表格可用；标签明确“整段累计比例，非实际发生位置”。保留单次后台读、最后请求胜出、关闭不更新。

## Task 3 — 验证与发布

Files: `tools/check_day_activity_layout.py`, `docs/reviews/2026-10-26-day-activity-zoom-result.md`, README.

- [x] 定向测试、全量 `python -m pytest -q`、`python -m compileall -q src/daylens`。
- [x] GUI smoke，1280×720/1920×1080 × 100/125/150% × 深浅主题，实际截图检查顶部和滚动后的明细。
- [x] 性能合成密集事件检查，聚合前后原始事件不变；独立规格、质量审查，修复后复测。
- [x] `python tools/build_release.py --stage-only` 通过后现有工具安全退出/原子替换/隐藏启动，保留上版回退。检查唯一规范进程、响应与运行状态、构建哈希。
- [x] 记录真实测试数、已知边界和回退路径，不宣称样本未覆盖的精确参与分布。
