# 导航、首页状态和 Obsidian 归档验收

## 用户确认范围

- 左侧“统计”改为“数据统计”；实时监控移入其标签页；设置中心位于侧栏最后。
- 顶部有效活动和记录状态共用一块紧凑区域，暂停与生成日报44px等高；非首页仍可见记录状态。
- 工作近7/30天隐藏Y轴数字并释放空间，今日曲线Y轴保留；日期/点击/数值不变，30天悬停可查看日时长。
- Obsidian已有年份目录内按`YYYY-MM`归档。用户明确允许删除重复日志；保留最新修改的版本，同时间优先已有标准路径版本。不会根据文件大小判断完整性。删除采用回收站，另保存所有原文件SHA256备份及迁移清单。

## 改动

- `gui/main_window.py`、`gui/pages/statistics.py`：复用原监控实例与纠错信号、兼容`navigate_to('live')`，只向可见监控分发采样；按采样代数防止切换标签重复插入缓存，同内容的新采样仍能插入。
- `gui/widgets/ui_primitives.py`：可选inline状态样式，不影响其他badge；`dashboard_widgets.py`仅本次Y轴/悬停调整，之前历史卡片改动保留。
- `services/report_archive.py`和`exporter.sync_to_obsidian`：统一年月路径、周报按结束日、跨年创建兄弟年目录、已配置年月自动识别；临时文件复制后原子替换，失败保留旧目标。未知文件名仍兼容原路径。
- 设置路径提示说明自动目录规则；不改配置值、数据库或计时/分类。
- `tools/organize_obsidian_reports.ps1`：显式年份目录范围、拒绝链接、只识别根目录及直属月份报告；预览与执行重新比对完整文件清单/分组；先完整备份并校验，再回收旧重复、非覆盖式移动保留版，每步记录恢复清单，最终再验计数和哈希。

## 已执行验证

- TDD先复现旧导航、状态位置、Y轴与平铺导出失败，再实现；缓存重复插入和归档计划被修改也分别先复现再修复。
- 定向`tests/test_obsidian_archive.py tests/test_obsidian_organizer.py tests/test_stage_c_shell.py tests/test_rhythm_chart_layout.py`：最终 **44 passed in 6.23s**。
- 独立只读审查运行44项通过。发现P2缓存重放重复插入；随后加入采样代数保护与失败/通过回归。
- 实际LiveMonitorPage合成诊断：切换回来无新采样时仍1行，相同内容的新采样后2行；未触及真实记录。
- 三档GUI smoke、48张历史卡片截图检查通过；新增36张两主题/两逻辑分辨率/三档缩放/首页监控设置截图与几何检查，位于`tmp/navigation-layout/`。截图仅合成数据，原有屏幕最小尺寸约束不扩大宣称为所有物理屏幕适配。
- 首轮全量1244通过；归档安全测试增加后1246通过。最终版本全量、构建、真实迁移与重启在执行后补记。

## 真实文件预览与边界

- 指定目录：`E:/obsidian_github/Daylog/时间追踪/桌面活动日报/2026`。
- 初次预览：180文件、153独立报告、27重复副本、75移动。预览未移动/删除真实文件。
- 不识别或其他年份文件保留，不改任何笔记正文，不清理其他目录。移动可能影响使用旧相对路径的链接；同名Obsidian wikilink保持文件名不变。
- 另一套代码仍可自行产生副本；本次只修改DayLens，不擅自关闭或修改其他窗口任务。
- 不自动commit/push，不清理无关工作区修改及程序备份。

## 最终验证、迁移和重启

- 最终全量 `QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=1 python -m pytest -q`：**1246 passed in 48.36s**（与打包并行）；compileall及diff-check通过。三档GUI smoke和36张导航截图在缓存代数修复后重跑通过。
- 最终 `python tools/build_release.py --stage-only` exit 0，Qt及Windows凭据隔离smoke通过；仅最终构建发布。
- 安全维护退出旧程序并确认clean后，重新预览仍180/153/27/75。实际整理结果：**75移动、27回收、153保留报告**，SHA256验证通过。年份根目录0文件、同名重复0组；6/7/8/9/10月分别34/36/33/28/22份，共153。
- 删除是可恢复的回收站操作；另有全部180份原文件备份：`D:/OfficeSoftware/DayLens/data/backups/obsidian-organize-20261026/files/`，原路径/哈希/保留决策见同目录上级`plan.json`，完成记录见`result.json`。备份不在Obsidian目录内，避免再次形成重复日志。
- 原子替换后唯一新进程PID **53164**，Responding=true、runtime status=running（首次检查phase=startup）；release与dist SHA256相同：`61D3F9187E1C98007C20E29A0E9278B62F1FB8002482F34630B473AA826FC05A`。
- 重启18:44:36，月份目录中的`2026-10-26.md`于18:44:48自动刷新；复查年份根目录仍0文件，验证真实自动同步使用新年月路径。仅检查文件元数据，未读取笔记正文。
- 上一版程序保留在`release_previous/`；此前回退程序归档至`release_previous_20261026_before_navigation_archive/`。没有删除程序备份、原始数据库或其他用户文件。
