# Restore Report Center Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this approved UI restoration inline.

**Goal:** 按用户确认，恢复正文预览改版前的报告列表＋小详情侧栏，不回退报告 V2。

**Architecture:** 仅断开 ReportsPage 与预览组件的集成，恢复列表主区域、元信息和三项操作；保留后台生成、分页、多选及纳秒文件更新识别。报告渲染、AI 证据、计时与历史文件不变。窄屏不再切换为正文页面，列表始终可见。

**Tech Stack:** Python、PySide6、pytest、PyInstaller。

## 1. 先验证基线并补回归

- [x] 运行 `python -m pytest tests/test_reports_page.py tests/test_report_v2.py -q`：38 passed。
- [x] 将内置预览的页面测试改为回退需求：

```python
assert not hasattr(page, "preview")
assert page.list_panel.isVisible()
assert page.detail_panel.width() < page.list_panel.width()
```

- [x] 增加切回页面不读取正文、后台生成成功提示不再包含“预览”的断言；保留原分页、下载、打开、同步测试。先运行新测试：3 failed, 13 passed。

## 2. 最小界面回退

- [x] 修改 `src/daylens/gui/pages/reports.py`：撤掉 QSplitter、正文预览/列表切换、自动加载正文和相关生命周期；恢复小详情卡与纵向打开/下载/同步按钮。继续使用现有后台队列生成报告。
- [x] 生成成功提示使用 `已生成，可打开、下载或同步；未增加 AI 请求`。
- [x] 更新 `tools/check_reports_v2_layout.py`，断言报告列表与详情操作始终可见而非检查正文；调整 README，说明不再内置预览。
- [x] 本轮不删除独立预览/证据工具及其测试，不改报告内容、原始数据、AI 调度，也不重写已有历史报告。

## 3. 验证、合并与重启

- [x] 定向与全量 pytest、compileall、GUI smoke、Ruff、diff --check。
- [x] 1280×720、1920×1080，100%/125%/150%，明暗主题，共 12 组隔离布局检查；必要时仅压缩高 DPI 组件尺寸，不恢复正文导航。
- [ ] 记录实际结果，提交改动说明、合入本地主分支；沿用安全发布，归档上版回退程序、替换并重启，核验单实例与运行心跳。不自动 push。
