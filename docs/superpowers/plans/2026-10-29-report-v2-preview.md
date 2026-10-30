# Report V2 and Preview Implementation Plan

**Goal:** 按已确认技术方案实施本地报告 V2、指标语义修正与安全 Qt Markdown 预览。

**Architecture:** 现有混合历史聚合内核生成单一只读上下文，纯渲染器生成三类报告；预览独立有界工作器与缓存，原报告写锁、AI附录、调度和计时不变。

**Tech Stack:** Python、SQLite、PySide6、pytest、PyInstaller。

- [x] A：先写失败的秒数、语义、混合历史、目标、对比及公开导出回归测试。
- [x] B：新增 report_v2_service.py 与 report_v2_renderer.py，委托公开 Markdown 导出，保持 CSV 和路径兼容。
- [x] C：先写失败的缓存、安全、异步及状态测试；新增 report_preview_service.py 和 report_preview.py。
- [x] D：报告中心接入可伸缩布局、只读预览与后台队列，验证分页/多选/同步不回归。
- [x] E：定向、全量、编译、GUI smoke、布局、万条合成数据性能及隔离发布验证。
- [ ] F：记录真实结果、分阶段提交、合并、安全发布重启，保留上一版；不自动 push。
