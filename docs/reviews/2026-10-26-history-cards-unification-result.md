# 历史卡片统一显示验收

## 范围与根因

用户已确认：统一工作/娱乐近7天和近30天的标题、日期、字体亮度、间距与底部摘要；去除工作均值虚线，保留娱乐月热力图；核查日期范围不一致。

根因：工作30天原来截至昨天，且从最早记录日截短；娱乐为固定滚动30天包含今天。现统一为捕获日期前29天至今天，原本31天聚合已含今日，无需增加数据库查询。无记录及最早记录前保留None，原计数/有效日均分母/旧口径与异常保护不变。窗口变化会自然影响工作30天合计，并不代表历史计时被修改。

## 改动文件

- `src/daylens/services/dashboard_service.py`：固定含今30天，补充ISO日期及捕获时间，不新增查询/改写数据库。
- `src/daylens/gui/widgets/history_card_widgets.py`：仅两张历史卡片使用的共用摘要和日期格式；最高日时长13px、高对比，长时长可换行。其他MetricCell不变。
- `src/daylens/gui/widgets/dashboard_widgets.py`：四视图统一标题形式/范围/摘要；工作近7/30天保持使用原数据值，仅统一显示文案；去掉工作均值参照线；娱乐7天日期与柱顶11px，30天周/星期11px，增加留白。重复绘制清理旧悬停几何以保持一日一格，不恢复任务分析或AI调用。
- `tests/test_history_cards_presentation.py`：12项覆盖跨年/闰年日期、含今、缺记录、有效分母、原输入不变、摘要/字体/均值线、重复重绘与今日样式不变。
- `tests/test_dashboard_service.py`：更新旧截至昨天/截短窗口的断言，保留实际数据和口径保护断言。
- `tests/test_dashboard_widgets.py`：更新用户要求的新文案/标题断言。
- `tools/check_history_cards_layout.py`：独立合成截图及文字完整性/边界断言；README与计划同步更新。

## 实际测试

- TDD：旧代码复现9项失败；修正合成行的必要session_count后再次复现3个日期边界失败。重复重绘回归先复现60个命中区域而非30个；统一标题回归先复现旧标题。随后针对性实现并通过。
- 定向 `python -m pytest -q tests/test_history_cards_presentation.py tests/test_dashboard_widgets.py tests/test_dashboard_service.py tests/test_day_activity_gui.py tests/test_rhythm_chart_layout.py` → **162 passed in 2.84s**。
- 最终标准缩放全量 `QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=1 python -m pytest -q` → **1224 passed in 35.08s**。
- `python -m compileall -q src/daylens` 与 `git diff --check` 通过（仅LF/CRLF工作区提示）。
- 深浅主题 × 1280×720/1920×1080 × 100%/125%/150% × 四视图，共48张合成截图与文字完整性、日期/摘要不重叠断言通过，位于 `tmp/history-cards-layout/`。人工检查窄屏深色的工作/娱乐30天与宽屏浅色娱乐7天。
- 三档缩放 `python tests/test_gui_smoke.py` 均通过，全部使用隔离数据。

## 边界

- 保留近7天全天详情入口及已有悬停，30天不增加点击入口。
- 今天为截至捕获时间的累计，不把未结束日补成全天。
- 没有宣称150%下全量测试通过：上一任务已记录无关旧工作片段全文断言在窄宽下的省略问题。本次标准缩放全量及三档GUI smoke单独记录。
- 不访问真实标题/数据库进行截图测试，不发送API，不自动提交/push，不清理无关本地修改。

## 独立审查与发布

- 独立只读代码审查无Critical/Important问题。Minor：共用摘要可能影响今日样式；随后先写失败回归，再把今日模式恢复为原12px弱提示/不换行，明确断言今日图表与数据不变。最终测试、截图和构建在修复后重新执行。
- 最终 `python tools/build_release.py --stage-only` exit 0，发布包Qt/凭据隔离smoke通过；不发布中间构建。
- 应用维护接口安全退出旧版并确认clean；归档此前回退程序至 `release_previous_20261026_before_history_cards`；原子替换release并重启，新进程PID 62348。
- 上一版程序保留在 `release_previous/DayLens.exe`，其SHA256为 `4B3B5DF1FA16F7CF2371CD165FFE4EA321A10A7698AF38A53C5D55BBDC24E66D`。
- 唯一新进程Responding=true，runtime状态running（首次检查phase=startup）；release与最终dist的SHA256相同：`A329A5EE8C9F5213A4C776276F934EFBAFB0C26431865053B27C968607A38152`。
