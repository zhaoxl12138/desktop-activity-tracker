# 本地规则简化验收

## 范围与改动

用户确认：主流程只管理应用；标题关键词不要求手动维护，默认折叠保留；测试标题可选。没有删除现有标题识别或改变分类优先级、视频/参与计量。

- `gui/pages/rule_config.py`：主区为应用列表、搜索、添加/移除；默认折叠名称/计时策略/进程文本/关键词高级设置。内部分类ID仅悬停显示，分类增删/重新扫描保留在更多菜单。列表与旧文本编辑器双向同步，增删只改草稿，保存前原数据库不变。应用对话框选择已有规则中的应用，也可自填进程或浏览exe；不自动扫描安装目录。
- `gui/widgets/rule_application_dialog.py`：统一应用选择；仅测试时显示可选标题，明确本地草稿不包含人工纠错或AI、不保存。
- `classifier.py`：新增可选只读内存配置初始化，深拷贝、绕过持久层，原`classify`实现未改。
- `services/rules_service.py`：提取同一规则载荷生成逻辑给保存与内存预览复用。预览使用现有`apply_custom_rules`，不另造优先级引擎。
- 用户实际编辑某个继承列表时，仅该字段改为replace；未编辑的隐藏关键词/正则/继承模式/策略保持。保存后重新读取有效规则，若冲突应用仍归原类会提示，而不是显示虚假的添加成功。
- 保留名“挂机”保存前拒绝，防止保存后被现有过滤器隐藏导致界面报错。

## 测试与审查

- 新增`tests/test_local_rules_simple.py`共10项：折叠/展开不改配置、应用草稿增删/去重/自动选中、空标题测试、输入深拷贝、隐藏字段保存、搜索不标脏、已有归属冲突、继承列表编辑保存一致性与保留名安全。
- 新功能先写失败回归，再实现。独立审查复现2个P2：原始草稿绕过归属归一化；继承列表删除保存后恢复。两者均写失败回归后修复。复核确认两者已解决，并发现保留名隐藏边界；随后同样复现KeyError后加保存前验证。
- 定向97项：`tests/test_local_rules_simple.py tests/test_rule_config_page.py tests/test_classifier_integrity.py tests/test_custom_rule_merge.py tests/test_rules_discovery_persistence.py tests/test_classification_correction.py tests/test_theme_state_preservation.py` → **97 passed in 3.94s**。
- 最终 `QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=1 python -m pytest -q` → **1256 passed in 44.86s**；与构建并行。前两轮1253、1255也通过。
- 三档GUI smoke通过；新`tools/check_local_rules_layout.py`使用两主题、两分辨率和100/125/150%生成48张折叠/展开/添加/测试截图，检查无横向溢出、操作区无交叠、可选标题状态、对话框边界。窄屏高级设置使用既有滚动容器；不宣称超出现有主窗最小尺寸约束。
- 截图工具显式加载中文/emoji字体，使用与页面相同的兼容命名空间主题，避免离屏渲染颜色不实；已人工查看深色宽屏主区、浅色窄屏主区和测试对话框。
- compileall及diff-check通过（仅原仓库LF/CRLF提示）。

## 数据与边界

- 不自动改用户规则；只有用户保存才写入原custom_rules。所有测试使用临时数据库与合成规则，草稿测试不调用API、不修改历史计数。
- 已有多分类冲突仍遵循现有归属/优先级；不是强制改判器。标题为空时，浏览器内容用途仍可能只能回退浏览器，界面明确可选填标题做本地内容测试。
- 不自动commit/push，不清理其他修改、旧发布备份或Obsidian文件。

## 发布与重启

- 最终`python tools/build_release.py --stage-only` exit0；发布包Qt和Windows凭据隔离smoke通过。
- 通过应用维护接口安全退出旧版并确认clean，原子替换并重启。上一版完整程序保留`release_previous/`；更旧回退程序归档`release_previous_20261026_before_local_rules_simple/`，未删除备份。
- 重启进程PID5732；唯一DayLens进程、Responding=true，首次runtime检查running（phase=startup）。发布与dist哈希相同：`0392DAAFE6CCFEE9B651FF0814FC1867880A117CCF165A5F20FC41E45194458B`；上一版哈希`61D3F9187E1C98007C20E29A0E9278B62F1FB8002482F34630B473AA826FC05A`。
