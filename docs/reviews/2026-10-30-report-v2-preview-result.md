# 报告 V2 与内置预览验收

实施日期：2026-10-29 ～ 2026-10-30；基线：`03c666f`。

## 实际实现

1. 日报/周报/月报改为统一复盘正文：关键发现、总览、目标与成果、至多一条基于既有目标的下一步建议、详细数据附录。无数据时使用同一结构。
2. 去除新报告中的效率评分和无依据的“最专注”等评价；会话时长精确到秒。损坏计量或时间只标注异常/未知，不阻止报告生成。
3. 同一只读 SQLite 事务批量读取当前与比较日期，复用现有混合历史聚合；目标复用逐日评估，不新增数据库表，不改变原始秒数。
4. 目标报告提取为通用周期包装，周报原入口仍严格验证七天，逐日可信计量与成果确认规则未变。
5. 报告中心新增安全 Qt Markdown 预览、小节目录、Ctrl+F 查找和刷新；宽屏分栏，窄屏列表/正文切换。
6. 独立单飞后台读取、有界 LRU 缓存、旧请求丢弃、页面关闭防更新；正文先展示，AI 核验随后更新，慢核验不阻塞正文。
7. 手动生成复用应用后台队列；分页和多选下载保留。纳秒文件身份可识别同一分钟、相同大小的内容替换。
8. 新附加的 AI 汇总绑定实际附录内容与证据，周/月来源增加纯本地依赖身份；预览核验父子依赖，旧附录无法验证时原样展示。未增加云端事实字段、请求或预算。
9. 禁止预览自动读取外部资源、执行 HTML、打开非白名单链接；大于 2MiB、20 万字符或 1200 行的密集报告使用有限纯文本预览，原文件/导出完整保留。

## TDD 与自动测试

- 初始报告 V2 回归：`16 failed, 1 passed`，确认旧结构及新上下文/渲染器尚不存在。
- 初始预览回归：`6 failed`，确认缓存、只读预览、安全组件尚不存在。
- 额外先失败后修复的案例：精确元信息、后台生成、窄屏切换、AI 附录身份、下级摘要过期、机器元信息隐藏、高密度报告降级、先显示正文、同分钟替换、损坏计量。
- 最终全量：`1423 passed in 41.75s`。
- `python -m compileall -q src tests tools`：退出码 0。
- `python tests/test_gui_smoke.py`：`GUI smoke test passed`。
- `python -m ruff check src/daylens --select F821,E9 --output-format concise`：`All checks passed!`。
- `git diff --check`：通过。
- `python tools/build_release.py --stage-only`：退出码 0，PyInstaller、Qt 与 Windows 凭据隔离 smoke 通过。

测试全部使用临时数据库/报告和假 AI，不测试付费 API，不修改生产历史会话或历史报告。

## 布局与性能

- `tools/check_reports_v2_layout.py` 在 100%/125%/150% 缩放下，分别检查 1280x720、1920x1080、明暗主题，共 12 组通过。
- 预留真实侧栏和顶栏的逻辑尺寸，检查页宽/高、可见按钮边界和正文可用区域；另人工检查窄屏与宽屏截图。
- `tools/check_reports_v2_performance.py`：1 万条合成会话，原始有效总量 50000 秒，统计前后守恒。
- 最后一次性能实测：快照 0.786 秒、纯 Markdown 渲染 0.107 秒、冷预览 0.0153 秒、热缓存 0.0003 秒；文件 992117 字节。
- 注入 0.4 秒慢读取期间，GUI 的 50ms 心跳触发 6 次，正文可正常加载；密集报告走纯文本降级，避免 Qt 大表格富文本阻塞。

## 文件清单

新增业务模块：

- `services/report_v2_service.py`
- `services/report_v2_renderer.py`
- `services/report_preview_service.py`
- `gui/widgets/report_preview.py`

集成修改：`exporter.py`、`gui/pages/reports.py`、`gui/main_window.py`、`services/reports_service.py`、`services/daily_goal_service.py`、`services/report_sections.py`、`services/intelligence_report_service.py`、`services/intelligence_report_schedule.py`。

新测试/工具：`tests/test_report_v2.py`、`tests/test_report_preview.py`、`tools/check_reports_v2_layout.py`、`tools/check_reports_v2_performance.py`。更新现有报告页、元信息、中文编码及可信报告字段断言，保留原 CSV 与调度测试。

## 已知边界

- 旧报告不批量重写；旧 AI 附录没有身份时明确“无法验证”，不假称最新。
- 大/密集报告只作有限纯文本预览，可外部打开或完整下载。
- 本轮不开发搜索、模板、分类复核、新版画像或 AI 问答。
- 数据截止表达与报告文案改变，核心计时、分类、数据库结构及 CSV 导出格式保持。

## 独立复核与补修

独立只读复核发现并补齐四处边界：页面切回恢复读取、慢 AI 核验不占用新正文工作器、实际脱敏事实/构建版本/隐私及提示词身份核验、原生目标小节的只读过期检查。均先补失败测试再修复；复核者再次独立运行相关测试为 `54 passed`，确认原问题已消除。旧记录分项使用“已核实下限／其余未知”，无记录显示未知，不假装为真实零。
