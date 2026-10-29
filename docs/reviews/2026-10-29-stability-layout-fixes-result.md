# DayLens 稳定性与布局修复验收记录

日期：2026-10-29

## 修复范围

- “偏爱应用”展示名称统一去除末尾 `.exe`，不修改原始会话或数据库。
- 修复设置页在无后台任务队列时执行数据修复会引用未定义数据库路径的问题。
- 智能复盘后台结果绑定原请求周期，切换周期后不会把旧结果写到当前周期状态。
- 报告证据指纹优先使用显式分类策略版本和分类来源；指纹读取失败时保留可用报告状态。
- 移除 Python 3.12 专属的同引号嵌套 f-string 写法，保持 Python 3.10+ 兼容。
- 降低主窗口最小尺寸，并按逻辑屏幕尺寸验收 125%/150% DPI 下的 1280x720 布局。
- 更新导航布局检查，覆盖当前单操作按钮顶栏，不再引用已删除控件。

以上修改不改变活动计时、分类时长、历史会话或数据库结构。

## 自动化验证

- 定向回归：`49 passed in 3.55s`
- 全量测试：`1397 passed in 32.70s`
- Python 编译检查：`python -m compileall -q src tests tools` 通过
- GUI smoke：`GUI smoke test passed`
- Ruff 关键错误检查：`All checks passed!`（F821、E9）
- PyInstaller 隔离发布构建：成功，`release_staging` 已完成校验

## 布局验证

下列脚本均在 100%、125%、150% 缩放下通过，并覆盖 1280x720 与 1920x1080 的相关布局：

- `tools/check_navigation_layout.py`
- `tools/check_history_cards_layout.py`
- `tools/check_local_rules_layout.py`
- `tools/check_settings_rhythm_layout.py`
- `tools/check_rhythm_card_layout.py`
- `tools/check_day_activity_layout.py`

人工检查 150% 缩放的 1280x720 首页截图，主窗口、侧栏、顶栏和滚动内容未发生重叠或裁切。

## 保留事项

- 本轮只修复已确认的 P1 稳定性与布局问题，没有重构大型页面文件，也没有调整核心计量逻辑。
- `release_staging/` 是本地发布产物，不纳入 Git 提交。

## 正式发布

- 主分支以 fast-forward 合并到 `97f9adf`，合并后全量复测为 `1397 passed in 42.86s`。
- 已有 `release_previous` 先归档为 `release_previous_20261029_before_stability_layout`，随后使用维护退出和原子目录替换发布；没有强制终止进程。
- 正式发布版与本次构建产物 SHA-256 均为 `CD4D88E89CD520159FBF49002B47A7C9A1069A0511152D67BBE066380D8E5965`。
- 已启动唯一正式进程 PID `48028`，路径为 `D:\OfficeSoftware\DayLens\release\DayLens.exe`；主窗口首次启动即可见且响应正常。
