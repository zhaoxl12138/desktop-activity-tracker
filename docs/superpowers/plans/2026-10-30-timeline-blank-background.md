# Timeline Blank Background Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, with test-driven rendering checks and read-only review.

**Goal:** 按用户确认，非活动区间统一留白，不显示斜纹或点纹；保留活动色块、真实时间间隔和异常悬停信息。

**Architecture:** 仅删除分类时间轴的状态纹理覆盖及含空闲色块的斜纹，调整 tooltip 说明。不改变事件、区间状态、警告、统计与事件明细；未知区间不改称空闲，不压缩时间轴。

**Tech Stack:** PySide6 / QPainter、pytest、离屏像素检查。

- [x] A：运行现有时间轴/服务基线（67 passed）；新增明暗主题下空闲、缺记录、未来、异常区间的底色像素断言，以及含空闲活动纯色断言。初始 6 failed, 4 passed。

```python
image = timeline.grab().toImage()
assert image.pixelColor(x, y).name() == style.COLORS['card_bg_alt']
assert '异常' in timeline.tooltip_for_second(anomaly_second)
```

- [x] B：在 `gui/widgets/day_activity_category_timeline.py` 删除纹理绘制，正常事件仍按原前台矩形绘制；删除未使用的画刷导入。`day_activity_dialog.py` 的静态悬停说明同步，不改变判断和计量代码。
- [x] C：验证原模型深拷贝前后相等、各状态悬停仍不同、事件范围与总量保持。更新 README 显示说明。
- [x] D：定向/全量 pytest、compileall、GUI smoke、Ruff、diff --check；两种分辨率、三档 DPI、明暗主题时间轴隔离截图复查。
- [x] E：只读独立复核，记录实际结果；提交合入本地，安全发布重启并保留上一版程序，不自动 push。
