# V1.8 本地行为画像与实验验收

## 本期实现

- `behavior_profile_service.py`：一次读取30天，形成7/14/30完整日画像；复用可信会话校验、分类集合、候选任务插入规则。按会话ID去重；异常、缺日、重叠、版本缺失/不一致时停止趋势输出。
- `behavior_experiment_service.py`：主动接受、次日起7完整日观察、前7日基线、停止及反馈。使用既有跨进程状态锁及原子JSON，不改目标/会话库。文件只保留一个实验的摘要及证据哈希，基线变动不输出效果判断。
- 设置中心增加独立且默认关闭的本地分析开关；报告中心增加“行为画像”弹窗，后台读取，按钮明确接受/停止。
- 原生日/周/月报扩展同一画像和实验小节。关闭时不读取画像数据。无网络调用或新增API费用。

## 真实验证

- `python -m pytest -q tests/test_behavior_v18.py`：初始13 passed；追加窗口尺寸用例后150%缩放下 **15 passed in 0.58s**。
- `python -m pytest -q`：在追加任务连续性指标和布局用例后，最终 **1099 passed in 26.14s**。此前一次全量测试输出有既有自动报告异常路径的 `unable to open database file` 提示，所有断言通过。
- `python -m compileall -q src/daylens`：退出0。
- `python tests/test_gui_smoke.py`：100%及150%均 `GUI smoke test passed`。
- 定向布局：1280×720及1920×1080预留侧栏后，行为画像入口与报告目录按钮不重叠，窗口不被撑宽。
- `git diff --check`：退出0，只有工作区原有LF/CRLF提示。
- `python tools/build_release.py --stage-only`：退出0，发布包与凭据 smoke 通过；在最后修复历史报告时间边界后重新构建并验证打包字节码包含该修复。
- 安全退出旧进程后，保留旧 `release_previous` 为 `release_previous_20261022_v18`，按仓库的 `_publish_staging` 原子替换 `release`，更新桌面快捷方式；启动 `release/DayLens.exe`。最终只有一个 PID 17644，窗口响应正常，运行版与构建版 SHA-256 相同。
- 增加同一候选任务连续片段的前后窗口对照后，按 `python tools/build_release.py` 正式流程再次构建、smoke、安全退出、替换及更新桌面快捷方式。原 `release_previous` 再保留为 `release_previous_20261022_v18_first`。最终唯一进程 PID 59528 运行于 `release/DayLens.exe`，窗口响应正常，运行版与构建版 SHA-256 均为 `09908F6CD9FB0629DD1E2DCC3B987E3C226F0835F49798A29238331EB791E977`。
- 真实库只读核对：7/14天有可信记录日期，但存在旧/异常记录及版本不一致；30天18个可信记录日。当前真实数据不满足严格趋势/实验基线门槛；没有更改历史数据以绕过判断。

## 真实数据诊断与局部展示补充

- 对真实库再次只读核对，近7个完整日虽有7/7天可信会话，但分类版本变化，另有跨日期及时间/计量异常会话；近30个完整日仅18/30天有可信记录。因此仍不生成可比趋势，也不开放一周实验基线。
- 不可比时现在列出缺日、跨日期、异常与版本差异的具体原因，并显示通过校验会话的工作和娱乐时长下限。文案明确说明这些不是全天或区间总量；存在可信会话重叠/会话标识冲突时连局部时长也不展示。
- 冲突会话标识不再随机保留其中一条用于局部汇总，避免误计。原始数据库、会话计时、分类和历史报告均未改写。
- 补充两项回归测试，先观察到2项失败，再修复通过。最后一次 `python -m pytest -q` 为 **1101 passed in 25.33s**，`python -m pytest tests/test_behavior_v18.py -q` 为 **17 passed**；`python -m compileall -q src/daylens` 退出0，`python tests/test_gui_smoke.py` 输出 `GUI smoke test passed`。
- `python tools/build_release.py` 退出0，包含打包运行时与凭据 smoke；安全退出旧进程并确认状态 `clean` 后发布。旧 `release_previous` 移至 `release_previous_20261022_v18_partial` 保存，新 `release_previous` 为刚替换的上版。新版 `release/DayLens.exe` 已启动，唯一进程 PID 13468、窗口响应正常，发布版与构建版 SHA-256 一致（`9CA3989DDFBC0B3168271ADCB445CA558371687A45D338533FFDF0EFAFFC0B8A`）。

## 边界与回退

- 本期提供本地证据画像与确定性实验反馈，没有新增云端画像润色或V2问答。
- 时段按会话起点归组，不能当作每分钟精确活动分布；连续片段只连接相邻无间隙工作会话。任务插入是既有规则的候选关联，非真实认知中断或动机判断。
- 暂不连接人工任务名形成跨日同一任务；候选按日及会话依据展示，避免同名误合并。
- 实验反馈不证明建议被执行或造成变化。不满足7个完整日同口径工作基线时不能接受实验。
- 关闭本地画像开关可停止分析；不自动改写旧报告，无数据库迁移；用户接受后的实验JSON保留。回退需保留此前V1.7兼容的大类目标版本，不能用不认识大类目标的更老版本解释目标文件。
